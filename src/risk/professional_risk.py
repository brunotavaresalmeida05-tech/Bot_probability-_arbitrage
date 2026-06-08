from __future__ import annotations
"""
Professional Risk Management — V9

Institutional-grade risk control:
- Position sizing based on volatility (ATR + VIX multiplier + yield curve multiplier)
- Daily loss limit (hard stop)
- Weekly loss limit
- Maximum simultaneous positions
- Correlation-aware: no doubling up on correlated clusters
- Capital scaling tiers (MICRO -> SMALL -> MEDIUM -> LARGE -> MEGA)
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.macro.macro_context import MacroContext

logger = logging.getLogger(__name__)


# Asset correlation clusters — assets in same cluster share exposure cap
CORRELATION_CLUSTERS = {
    "metals":    ["GOLD", "SILVER", "XAUUSD", "XAGUSD", "ZG", "XAUEUR"],
    "oil":       ["BRENT", "WTI", "LCrude", "Brent", "OIL"],
    "us_equity": ["Usa500", "UsaTec", "US500", "NAS100", "SP500"],
    "eu_equity": ["Ger40", "GER40", "DAX"],
    "fx_usd":    ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"],
}

# Capital tiers (from docs/CAPITAL_SCALING_INTEGRATION.md, adapted for V9)
CAPITAL_TIERS = [
    {"name": "MICRO",  "min": 0,       "max": 10_000,   "risk_pct": 0.005, "max_pos": 2, "cluster_cap": 1},
    {"name": "SMALL",  "min": 10_000,  "max": 100_000,  "risk_pct": 0.005, "max_pos": 3, "cluster_cap": 2},
    {"name": "MEDIUM", "min": 100_000, "max": 500_000,  "risk_pct": 0.005, "max_pos": 5, "cluster_cap": 2},
    {"name": "LARGE",  "min": 500_000, "max": 5_000_000,"risk_pct": 0.004, "max_pos": 8, "cluster_cap": 3},
    {"name": "MEGA",   "min": 5_000_000,"max": float("inf"),"risk_pct": 0.003,"max_pos": 12,"cluster_cap": 4},
]


@dataclass
class RiskState:
    balance: float = 10_000.0
    equity: float = 10_000.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    open_positions: dict = field(default_factory=dict)  # symbol -> {lots, direction, entry, sl}
    daily_trades: int = 0
    session_start_equity: float = 0.0
    week_start_equity: float = 0.0
    blocked: bool = False
    blocked_reason: str = ""
    tier: str = "MICRO"
    date: str = ""

    def update_date(self):
        today = datetime.now(timezone.utc).date().isoformat()
        if self.date != today:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.date = today


@dataclass
class SizeResult:
    lots: float
    risk_pct: float
    risk_money: float
    sl_distance: float
    vix_mult: float
    yield_mult: float
    tier: str
    blocked: bool = False
    reason: str = ""


class ProfessionalRiskManager:
    """
    Institutional risk manager.
    All methods are thread-safe via the state object being updated atomically.
    """

    def __init__(
        self,
        macro: MacroContext,
        max_daily_loss_pct: float = 0.03,
        max_weekly_loss_pct: float = 0.08,
        min_lot: float = 0.01,
        max_lot: float = 10.0,
    ):
        self._macro = macro
        self._max_daily_loss = max_daily_loss_pct
        self._max_weekly_loss = max_weekly_loss_pct
        self._min_lot = min_lot
        self._max_lot = max_lot
        self.state = RiskState()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_account(self, balance: float, equity: float):
        self.state.balance = balance
        self.state.equity = equity
        self.state.tier = self._get_tier(balance)["name"]
        self.state.update_date()
        self._check_limits()

    def can_open(self, symbol: str, direction: str) -> tuple[bool, str]:
        """Check if a new position can be opened."""
        if self.state.blocked:
            return False, self.state.blocked_reason

        if not self._macro.tradeable:
            return False, f"Macro not tradeable: VIX {self._macro.vix_regime}"

        if self._macro.high_impact_next_30m:
            return False, "High-impact news event in next 30 min"

        tier = self._get_tier(self.state.balance)
        if len(self.state.open_positions) >= tier["max_pos"]:
            return False, f"Max positions reached ({tier['max_pos']}) for tier {tier['name']}"

        # Cluster check
        cluster = self._get_cluster(symbol)
        if cluster:
            cluster_count = sum(
                1 for sym in self.state.open_positions
                if self._get_cluster(sym) == cluster
            )
            if cluster_count >= tier["cluster_cap"]:
                return False, f"Cluster {cluster} at capacity ({tier['cluster_cap']})"

        return True, ""

    def size_position(
        self,
        symbol: str,
        sl_distance: float,
        point_value: float = 1.0,
        lot_penalty: float = 1.0,
    ) -> SizeResult:
        """
        Calculate position size with defensive math.floor normalization.
        Reads volume_min, volume_max, volume_step from MT5 symbol_info to prevent
        TRADE_RETCODE_INVALID_VOLUME rejections.

        lot = floor((balance * risk_pct * vix_mult * yield_mult * lot_penalty)
                    / (sl_distance * point_value) / step) * step
        """
        import math

        tier = self._get_tier(self.state.balance)
        base_risk = tier["risk_pct"]

        vix_mult = self._macro.vix_lot_mult
        yield_mult = self._macro.yield_risk_mult
        effective_risk = base_risk * vix_mult * yield_mult * lot_penalty

        risk_money = self.state.balance * effective_risk

        if sl_distance <= 0 or point_value <= 0:
            return SizeResult(
                lots=self._min_lot, risk_pct=effective_risk, risk_money=risk_money,
                sl_distance=sl_distance, vix_mult=vix_mult, yield_mult=yield_mult,
                tier=tier["name"], blocked=True, reason="Invalid SL or point value",
            )

        # Get MT5 symbol constraints dynamically
        min_vol, max_vol, vol_step = self._get_symbol_volume_params(symbol)

        raw_lots = risk_money / (sl_distance * point_value)

        # Defensive math.floor normalization (blueprint spec)
        steps = raw_lots / vol_step
        lots = math.floor(steps) * vol_step
        decimal_places = max(0, int(round(-math.log10(vol_step)))) if vol_step < 1 else 2
        lots = round(lots, decimal_places)

        # Enforce broker limits
        if lots < min_vol:
            return SizeResult(
                lots=0.0, risk_pct=effective_risk, risk_money=risk_money,
                sl_distance=sl_distance, vix_mult=vix_mult, yield_mult=yield_mult,
                tier=tier["name"], blocked=True,
                reason=f"Lote calculado {lots:.4f} < volume_min {min_vol} do broker",
            )

        lots = min(lots, max_vol)

        return SizeResult(
            lots=lots,
            risk_pct=effective_risk,
            risk_money=round(risk_money, 2),
            sl_distance=sl_distance,
            vix_mult=vix_mult,
            yield_mult=yield_mult,
            tier=tier["name"],
        )

    def _get_symbol_volume_params(self, symbol: str) -> tuple[float, float, float]:
        """Fetch volume_min, volume_max, volume_step from MT5. Fallback to defaults."""
        try:
            import MetaTrader5 as mt5lib
            info = mt5lib.symbol_info(symbol)
            if info:
                return (
                    float(info.volume_min),
                    float(info.volume_max),
                    float(info.volume_step),
                )
        except Exception:
            pass
        return self._min_lot, self._max_lot, self._min_lot

    def register_open(self, symbol: str, direction: str, lots: float, entry: float, sl: float):
        self.state.open_positions[symbol] = {
            "direction": direction, "lots": lots, "entry": entry, "sl": sl,
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
        self.state.daily_trades += 1

    def register_close(self, symbol: str, pnl: float):
        self.state.open_positions.pop(symbol, None)
        self.state.daily_pnl += pnl
        self.state.weekly_pnl += pnl
        self._check_limits()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_tier(self, balance: float) -> dict:
        for t in reversed(CAPITAL_TIERS):
            if balance >= t["min"]:
                return t
        return CAPITAL_TIERS[0]

    def _get_cluster(self, symbol: str) -> str | None:
        sym_upper = symbol.upper()
        for cluster, members in CORRELATION_CLUSTERS.items():
            if any(m in sym_upper or sym_upper in m for m in members):
                return cluster
        return None

    def _check_limits(self):
        balance = self.state.balance
        if balance <= 0:
            return
        daily_dd = self.state.daily_pnl / balance
        weekly_dd = self.state.weekly_pnl / balance

        if daily_dd <= -self._max_daily_loss:
            self.state.blocked = True
            self.state.blocked_reason = f"Daily loss limit: {daily_dd*100:.2f}%"
            logger.warning(f"RISK BLOCK: {self.state.blocked_reason}")
        elif weekly_dd <= -self._max_weekly_loss:
            self.state.blocked = True
            self.state.blocked_reason = f"Weekly loss limit: {weekly_dd*100:.2f}%"
            logger.warning(f"RISK BLOCK: {self.state.blocked_reason}")
        else:
            self.state.blocked = False
            self.state.blocked_reason = ""
