from __future__ import annotations
"""
Capital Manager V2 — Fase 9C

Regime-aware position sizing, capital layer tracking (70/20/10),
margin semaphore (5 levels), scaled TP management (40/35/25%),
and drawdown recovery protocol.

Complements ProfessionalRiskManager (VaR, correlation, tier limits):
  - ProfessionalRiskManager: broker constraints, cluster caps, daily/weekly limits
  - CapitalManagerV2:        regime-aware sizing, capital layers, margin gate, TP/trailing

Integration point in orchestrator:
  1. update_account(balance, equity, margin_level_pct) — each cycle
  2. set_regime(regime_state)                          — after RegimeRouter
  3. can_open_trade(symbol) -> (bool, reason)          — before execution
  4. get_position_size(symbol, sl_pips)                — lot calculation
  5. get_tp_levels(entry, direction, sl, atr)          — TP structure
  6. manage_open_position(trade, price, atr, regime)   — trailing / BE
  7. get_metrics() -> dict                             — for state.json
"""
import logging
import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ── CapitalLayers ─────────────────────────────────────────────────────────────

@dataclass
class CapitalLayers:
    total: float
    active: float           # 70% — used for trading
    margin_reserve: float   # 20% — never in trades
    emergency: float        # 10% — activated only at DD >= 12%

    @classmethod
    def from_total(cls, total: float) -> CapitalLayers:
        return cls(
            total=round(total, 2),
            active=round(total * 0.70, 2),
            margin_reserve=round(total * 0.20, 2),
            emergency=round(total * 0.10, 2),
        )

    def rebalance(self, new_total: float) -> CapitalLayers:
        return CapitalLayers.from_total(new_total)

    def distribute_profit(self, profit: float) -> tuple[float, float]:
        """Returns (reinvested, withdrawn) — 80/20 split of monthly profit."""
        reinvested = round(profit * 0.80, 2)
        withdrawn  = round(profit * 0.20, 2)
        return reinvested, withdrawn


# ── PositionSizer ─────────────────────────────────────────────────────────────

class PositionSizer:
    BASE_RISK = 0.01       # 1% base risk per trade
    MAX_RISK  = 0.02       # 2% absolute cap — never exceeded

    REGIME_MULT: dict[str, float] = {
        "TRENDING_UP":   1.25,
        "TRENDING_DOWN": 1.25,
        "RANGING":       0.75,
        "VOLATILE":      0.25,
    }

    def get_risk_pct(self, regime: str = "RANGING", drawdown: float = 0.0,
                     winrate_30d: float = 0.50) -> float:
        r = self.BASE_RISK
        r *= self.REGIME_MULT.get(regime, 1.0)
        r *= self._drawdown_mult(drawdown)
        r *= self._performance_mult(winrate_30d)
        return min(r, self.MAX_RISK)

    def get_lots(self, capital_active: float, risk_pct: float,
                 sl_pips: float, pip_value: float = 10.0) -> float:
        """
        lot = floor((capital_active × risk_pct) / (sl_pips × pip_value) × 100) / 100
        pip_value: EUR per pip for 1 standard lot (default 10 EUR — forex standard)
        """
        if sl_pips <= 0 or pip_value <= 0:
            return 0.01
        risk_eur = capital_active * risk_pct
        lots = risk_eur / (sl_pips * pip_value)
        lots = math.floor(lots * 100) / 100
        return max(lots, 0.01)

    @staticmethod
    def _drawdown_mult(dd: float) -> float:
        if dd > 0.12: return 0.25
        if dd > 0.08: return 0.50
        if dd > 0.05: return 0.75
        return 1.00

    @staticmethod
    def _performance_mult(wr: float) -> float:
        if wr > 0.65: return 1.10
        if wr < 0.40: return 0.75
        return 1.00


# ── MarginSemaphore ───────────────────────────────────────────────────────────

class MarginSemaphore:
    GREEN    = 400   # >400% — full operation
    YELLOW   = 300   # 300-400% — block new trades
    ORANGE   = 200   # 200-300% — close worst position
    RED      = 150   # 150-200% — close 50% of positions
    CRITICAL = 120   # <150% — close all immediately

    def evaluate(self, margin_level_pct: float) -> str:
        if margin_level_pct >= self.GREEN:  return "GREEN"
        if margin_level_pct >= self.YELLOW: return "YELLOW"
        if margin_level_pct >= self.ORANGE: return "ORANGE"
        if margin_level_pct >= self.RED:    return "RED"
        return "CRITICAL"

    def can_open_new_trade(self, margin_level_pct: float) -> bool:
        return margin_level_pct >= self.GREEN

    def required_action(self, status: str) -> str:
        return {
            "CRITICAL": "close_all",
            "RED":      "close_50pct",
            "ORANGE":   "close_worst",
            "YELLOW":   "block_new_trades",
            "GREEN":    "none",
        }.get(status, "none")


# ── TPManager ─────────────────────────────────────────────────────────────────

@dataclass
class TPLevels:
    tp1: float              # 40% of position — fixed level
    tp2: float              # 35% of position — fixed level
    tp3: float | None       # 25% runner — trailing, no fixed target
    lot_split: list         # [0.40, 0.35, 0.25]
    rrr_tp1: float
    rrr_tp2: float


class TPManager:
    LOT_SPLIT    = [0.40, 0.35, 0.25]
    MIN_RRR      = 1.5
    ATR_MULT_TP1 = 1.5
    ATR_MULT_TP2 = 2.5

    def calculate(self, entry: float, sl: float, direction: str,
                  atr: float,
                  nearest_res: float | None = None,
                  second_res: float | None = None) -> TPLevels | None:
        sl_dist = abs(entry - sl)
        if sl_dist <= 0:
            return None

        is_buy = direction.upper() in ("BUY", "LONG")

        if is_buy:
            tp1 = nearest_res if nearest_res else entry + atr * self.ATR_MULT_TP1
            tp2 = second_res  if second_res  else entry + atr * self.ATR_MULT_TP2
        else:
            tp1 = nearest_res if nearest_res else entry - atr * self.ATR_MULT_TP1
            tp2 = second_res  if second_res  else entry - atr * self.ATR_MULT_TP2

        rrr1 = abs(tp1 - entry) / sl_dist
        rrr2 = abs(tp2 - entry) / sl_dist

        # float epsilon guard: 1.5/0.0012 can return 1.49999... in IEEE 754
        if rrr1 < self.MIN_RRR - 1e-9:
            return None

        return TPLevels(
            tp1=round(tp1, 5),
            tp2=round(tp2, 5),
            tp3=None,
            lot_split=self.LOT_SPLIT[:],
            rrr_tp1=round(rrr1, 2),
            rrr_tp2=round(rrr2, 2),
        )


# ── DrawdownRecovery ──────────────────────────────────────────────────────────

@dataclass
class RecoveryPhase:
    phase: int
    label: str
    risk_multiplier: float
    max_trades: int
    max_leverage: int
    drawdown: float


class DrawdownRecovery:
    # (dd_min, dd_max, risk_mult, max_trades, max_leverage, label)
    _PHASES = [
        (0.00, 0.05, 1.00, 6, 10, "NORMAL"),
        (0.05, 0.08, 0.75, 4,  7, "CAUTIOUS"),
        (0.08, 0.12, 0.50, 3,  5, "CONSERVATIVE"),
        (0.12, 0.15, 0.25, 2,  2, "SURVIVAL"),
        (0.15, 1.00, 0.00, 0,  0, "HALTED"),
    ]

    def get_phase(self, drawdown: float) -> RecoveryPhase:
        for i, (lo, hi, rm, mt, ml, label) in enumerate(self._PHASES):
            if lo <= drawdown < hi:
                return RecoveryPhase(
                    phase=i, label=label,
                    risk_multiplier=rm, max_trades=mt,
                    max_leverage=ml, drawdown=drawdown,
                )
        # Edge: drawdown >= 1.0
        return RecoveryPhase(
            phase=4, label="HALTED",
            risk_multiplier=0.0, max_trades=0,
            max_leverage=0, drawdown=drawdown,
        )


# ── Metrics dataclass ─────────────────────────────────────────────────────────

@dataclass
class _CMMetrics:
    total_capital: float    = 0.0
    drawdown_current: float = 0.0
    drawdown_peak: float    = 0.0
    recovery_phase: int     = 0
    risk_multiplier: float  = 1.0
    margin_level_status: str = "GREEN"
    open_trades_count: int  = 0
    monthly_pnl: float      = 0.0
    winrate_30d: float      = 0.50
    profit_factor_30d: float = 1.0
    trade_count_30d: int    = 0
    wins_30d: int           = 0
    last_rebalance_date: str = ""


# ── CapitalManagerV2 ──────────────────────────────────────────────────────────

class CapitalManagerV2:
    """
    Capital Manager V2 — Fase 9C.

    Regime-aware sizing, capital layer accounting (70/20/10),
    margin semaphore (5 levels), scaled TP (40/35/25%),
    and drawdown recovery protocol (5 phases).

    Thread-safe via internal lock.
    """

    def __init__(self, initial_capital: float = 10_000.0):
        self._lock    = threading.RLock()  # RLock: get_metrics() calls get_capital_layers() re-entrantly
        self._layers  = CapitalLayers.from_total(initial_capital)
        self._sizer   = PositionSizer()
        self._margin  = MarginSemaphore()
        self._tp_mgr  = TPManager()
        self._recovery = DrawdownRecovery()

        self._metrics = _CMMetrics(
            total_capital=initial_capital,
            drawdown_peak=initial_capital,
        )
        self._current_regime: str     = "RANGING"
        self._margin_level_pct: float = 9999.0   # unknown on start → assume safe
        self._margin_free: float      = 0.0
        self._month_start_equity: float = initial_capital
        self._month: str = datetime.now(timezone.utc).strftime("%Y-%m")
        self._peak_seeded: bool = False   # True after first real balance from MT5

    # ── V1-compatible interface ───────────────────────────────────────────────

    def update(self, pnl: float) -> None:
        """Register a closed trade. Updates drawdown tracking and 30d metrics."""
        with self._lock:
            self._metrics.monthly_pnl += pnl
            new_total = self._layers.total + pnl

            if new_total > self._metrics.drawdown_peak:
                self._metrics.drawdown_peak = new_total

            if self._metrics.drawdown_peak > 0:
                self._metrics.drawdown_current = max(
                    0.0,
                    (self._metrics.drawdown_peak - new_total) / self._metrics.drawdown_peak,
                )

            self._metrics.trade_count_30d += 1
            if pnl > 0:
                self._metrics.wins_30d += 1
            if self._metrics.trade_count_30d > 0:
                self._metrics.winrate_30d = (
                    self._metrics.wins_30d / self._metrics.trade_count_30d
                )

            self._layers = self._layers.rebalance(new_total)
            self._metrics.total_capital = new_total
            phase = self._recovery.get_phase(self._metrics.drawdown_current)
            self._metrics.recovery_phase  = phase.phase
            self._metrics.risk_multiplier = phase.risk_multiplier

    def get_position_size(self, symbol: str, sl_pips: float,
                          pip_value: float = 10.0) -> float:
        """
        Returns lot size adjusted for regime, drawdown, and winrate.
        sl_pips: stop-loss distance in pips
        pip_value: EUR per pip for 1 standard lot (default 10 EUR)
        """
        with self._lock:
            risk_pct = self._sizer.get_risk_pct(
                regime=self._current_regime,
                drawdown=self._metrics.drawdown_current,
                winrate_30d=self._metrics.winrate_30d,
            )
            risk_pct *= self._metrics.risk_multiplier
            return self._sizer.get_lots(
                capital_active=self._layers.active,
                risk_pct=risk_pct,
                sl_pips=sl_pips,
                pip_value=pip_value,
            )

    def can_open_trade(self, symbol: str) -> tuple[bool, str]:
        """
        Gate check: margin semaphore + drawdown recovery.
        Returns (allowed, reason).
        """
        with self._lock:
            if not self._margin.can_open_new_trade(self._margin_level_pct):
                status = self._margin.evaluate(self._margin_level_pct)
                return False, f"Margin {status}: {self._margin_level_pct:.0f}%"

            phase = self._recovery.get_phase(self._metrics.drawdown_current)
            if phase.max_trades == 0:
                return False, (
                    f"Recovery phase HALTED "
                    f"(DD={self._metrics.drawdown_current:.1%})"
                )
            if self._metrics.open_trades_count >= phase.max_trades:
                return False, (
                    f"Recovery phase {phase.label}: "
                    f"max_trades={phase.max_trades} reached"
                )
            return True, ""

    # ── New V2 methods ────────────────────────────────────────────────────────

    def update_account(self, balance: float, equity: float,
                       margin_level_pct: float = 9999.0,
                       margin_free: float = 0.0) -> None:
        """Call each cycle with fresh MT5 account data.

        Capital base = min(equity, balance) — mais conservador:
        equity inclui PnL flutuante; se equity < balance há perda não realizada.
        """
        with self._lock:
            self._margin_level_pct = margin_level_pct
            self._margin_free = margin_free
            self._metrics.margin_level_status = self._margin.evaluate(margin_level_pct)

            if balance > 0 and equity > 0:
                # Capital base conservador: o menor dos dois valores
                capital_base = min(equity, balance)

                # Primeira leitura real: calibra o peak ao capital real da conta
                if not self._peak_seeded:
                    self._metrics.drawdown_peak = capital_base
                    self._peak_seeded = True

                if capital_base > self._metrics.drawdown_peak:
                    self._metrics.drawdown_peak = capital_base
                if self._metrics.drawdown_peak > 0:
                    self._metrics.drawdown_current = max(
                        0.0,
                        (self._metrics.drawdown_peak - capital_base) / self._metrics.drawdown_peak,
                    )
                self._layers = self._layers.rebalance(capital_base)
                self._metrics.total_capital = capital_base

            phase = self._recovery.get_phase(self._metrics.drawdown_current)
            self._metrics.recovery_phase  = phase.phase
            self._metrics.risk_multiplier = phase.risk_multiplier
            self._maybe_monthly_reset(equity)

    def set_regime(self, regime: str) -> None:
        """Called by orchestrator after RegimeRouter detection."""
        with self._lock:
            self._current_regime = regime

    def set_open_trades_count(self, count: int) -> None:
        """Sync number of open positions from orchestrator."""
        with self._lock:
            self._metrics.open_trades_count = count

    def check_margin_level(self, margin_level_pct: float) -> str:
        """Evaluate margin, update internal state, return status string."""
        with self._lock:
            self._margin_level_pct = margin_level_pct
            status = self._margin.evaluate(margin_level_pct)
            self._metrics.margin_level_status = status
            return status

    def get_capital_layers(self) -> dict:
        with self._lock:
            return {
                "total":          round(self._layers.total, 2),
                "active":         round(self._layers.active, 2),
                "margin_reserve": round(self._layers.margin_reserve, 2),
                "emergency":      round(self._layers.emergency, 2),
            }

    def get_tp_levels(self, entry: float, direction: str, sl: float,
                      atr: float,
                      nearest_res: float | None = None,
                      second_res: float | None = None) -> dict | None:
        """
        Calculate 3-level TP structure (40/35/25%).
        Returns dict or None if RRR < 1.5.
        """
        result = self._tp_mgr.calculate(
            entry=entry, sl=sl, direction=direction,
            atr=atr, nearest_res=nearest_res, second_res=second_res,
        )
        if result is None:
            return None
        return {
            "tp1":       result.tp1,
            "tp2":       result.tp2,
            "tp3":       result.tp3,
            "lot_split": result.lot_split,
            "rrr_tp1":   result.rrr_tp1,
            "rrr_tp2":   result.rrr_tp2,
        }

    def manage_open_position(self, trade: dict, current_price: float,
                             atr: float, current_regime: str = "RANGING") -> dict:
        """
        Active position management: trailing stop, break-even, partial TP.
        trade keys: entry, direction, sl, tp1_hit (bool), be_set (bool)
        Returns action dict: {action, reason, new_sl?}
        """
        entry     = trade.get("entry", 0.0)
        direction = trade.get("direction", "BUY")
        sl        = trade.get("sl", 0.0)
        tp1_hit   = trade.get("tp1_hit", False)

        if not entry or not sl:
            return {"action": "hold", "reason": "incomplete_trade_data"}

        is_buy = direction.upper() in ("BUY", "LONG")

        # After TP1: move SL to break-even (once)
        if tp1_hit and not trade.get("be_set", False):
            return {
                "action": "update_sl",
                "new_sl": entry,
                "reason": "tp1_hit_move_to_be",
            }

        # After TP1 + BE set: trail stop at ATR×1.5
        if tp1_hit:
            if is_buy:
                trailing_sl = current_price - atr * 1.5
                if trailing_sl > sl:
                    return {
                        "action": "update_sl",
                        "new_sl": round(trailing_sl, 5),
                        "reason": "trailing_after_tp1",
                    }
            else:
                trailing_sl = current_price + atr * 1.5
                if trailing_sl < sl:
                    return {
                        "action": "update_sl",
                        "new_sl": round(trailing_sl, 5),
                        "reason": "trailing_after_tp1",
                    }

        return {"action": "hold", "reason": "no_action_needed"}

    def get_recovery_phase(self) -> dict:
        with self._lock:
            phase = self._recovery.get_phase(self._metrics.drawdown_current)
            return {
                "phase":           phase.phase,
                "label":           phase.label,
                "risk_multiplier": phase.risk_multiplier,
                "max_trades":      phase.max_trades,
                "max_leverage":    phase.max_leverage,
                "drawdown":        round(self._metrics.drawdown_current, 4),
            }

    def monthly_rebalance(self) -> dict:
        """Distribute monthly profits (80% reinvested / 20% withdrawn)."""
        with self._lock:
            profit = self._metrics.monthly_pnl
            reinvested, withdrawn = (
                self._layers.distribute_profit(profit) if profit > 0
                else (0.0, 0.0)
            )
            self._metrics.last_rebalance_date = (
                datetime.now(timezone.utc).date().isoformat()
            )
            return {
                "monthly_pnl": round(profit, 2),
                "reinvested":  reinvested,
                "withdrawn":   withdrawn,
                "layers_after": self.get_capital_layers(),
            }

    def get_metrics(self) -> dict:
        """Snapshot for state.json and dashboard."""
        with self._lock:
            total = self._metrics.total_capital
            return {
                "total_capital":       round(total, 2),
                "layers":              self.get_capital_layers(),
                "drawdown_current":    round(self._metrics.drawdown_current, 4),
                "drawdown_peak":       round(self._metrics.drawdown_peak, 2),
                "recovery_phase":      self._metrics.recovery_phase,
                "risk_multiplier":     self._metrics.risk_multiplier,
                "margin_level_status": self._metrics.margin_level_status,
                "margin_level_pct":    round(self._margin_level_pct, 1),
                "margin_free":         round(self._margin_free, 2),
                "open_trades_count":   self._metrics.open_trades_count,
                "monthly_pnl_pct":     round(
                    self._metrics.monthly_pnl / total if total > 0 else 0.0, 4
                ),
                "winrate_30d":         round(self._metrics.winrate_30d, 4),
                "profit_factor_30d":   round(self._metrics.profit_factor_30d, 4),
            }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _maybe_monthly_reset(self, equity: float) -> None:
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        if current_month != self._month:
            self._month              = current_month
            self._month_start_equity = equity
            self._metrics.monthly_pnl    = 0.0
            self._metrics.trade_count_30d = 0
            self._metrics.wins_30d        = 0
            self._metrics.winrate_30d     = 0.50
            logger.info(f"[CM] Monthly reset. new_month={current_month}")
