"""
src/macro/regime_engine.py — Macro Regime Engine.

Classifies the global macro environment using cross-asset signals:
  DXY, Yields (10Y-2Y), VIX, GOLD, Oil, S&P500, Nasdaq, BTC

Output:
  - regime: "risk_on" | "risk_off" | "inflation" | "deflation" | "crisis" | "neutral"
  - risk_on_score  (0–1)
  - risk_off_score (0–1)
  - inflation_score (0–1)
  - liquidity_score (0–1)
  - symbol_mults: dict[symbol → float 0.0–1.0]

Per-symbol multipliers are computed from a cross-asset sensitivity matrix.
Positive sensitivity = factor moving up helps the symbol.
Negative sensitivity = factor moving up hurts the symbol.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.macro.cross_asset_monitor import CrossAssetState

logger = logging.getLogger(__name__)

# ── Cross-Asset Sensitivity Matrix ─────────────────────────────────────────────
# Columns: dxy  yields  gold  oil  sp500  btc
# Range:   -1.0  to  +1.0
# Negative = adverse when factor goes up.
# The matrix captures standard inter-market correlations.
_SENSITIVITY: dict[str, dict[str, float]] = {
    #             dxy    yields  gold   oil    sp500  btc
    "EURUSD":  {"dxy":-0.90,"yields":-0.30,"gold": 0.10,"oil":-0.10,"sp500": 0.20,"btc": 0.00},
    "GBPUSD":  {"dxy":-0.75,"yields":-0.25,"gold": 0.10,"oil":-0.05,"sp500": 0.25,"btc": 0.00},
    "USDJPY":  {"dxy": 0.60,"yields": 0.60,"gold":-0.20,"oil": 0.10,"sp500": 0.30,"btc": 0.05},
    "AUDUSD":  {"dxy":-0.65,"yields":-0.10,"gold": 0.30,"oil": 0.20,"sp500": 0.40,"btc": 0.10},
    "NZDUSD":  {"dxy":-0.60,"yields":-0.10,"gold": 0.25,"oil": 0.15,"sp500": 0.40,"btc": 0.05},
    "USDCHF":  {"dxy": 0.50,"yields": 0.20,"gold":-0.40,"oil": 0.00,"sp500":-0.30,"btc": 0.00},
    "USDCAD":  {"dxy": 0.40,"yields": 0.10,"gold":-0.10,"oil":-0.60,"sp500":-0.20,"btc": 0.00},
    "USDNOK":  {"dxy": 0.35,"yields": 0.05,"gold":-0.05,"oil":-0.70,"sp500":-0.15,"btc": 0.00},
    "USDMXN":  {"dxy": 0.70,"yields": 0.30,"gold":-0.10,"oil":-0.20,"sp500":-0.40,"btc":-0.10},
    "EURJPY":  {"dxy":-0.20,"yields": 0.40,"gold":-0.10,"oil": 0.05,"sp500": 0.50,"btc": 0.05},
    # Indices
    "Usa500":  {"dxy":-0.20,"yields":-0.50,"gold":-0.10,"oil":-0.30,"sp500": 0.00,"btc": 0.20},
    "UsaTec":  {"dxy":-0.25,"yields":-0.70,"gold":-0.05,"oil":-0.20,"sp500": 0.80,"btc": 0.30},
    "USAtec":  {"dxy":-0.25,"yields":-0.70,"gold":-0.05,"oil":-0.20,"sp500": 0.80,"btc": 0.30},
    "USA500Jun26": {"dxy":-0.20,"yields":-0.50,"gold":-0.10,"oil":-0.30,"sp500": 0.00,"btc": 0.20},
    "US100Jun26":  {"dxy":-0.25,"yields":-0.70,"gold":-0.05,"oil":-0.20,"sp500": 0.80,"btc": 0.30},
    "Ger40":   {"dxy":-0.15,"yields":-0.40,"gold":-0.05,"oil":-0.30,"sp500": 0.60,"btc": 0.10},
    "Ger40Jun26":  {"dxy":-0.15,"yields":-0.40,"gold":-0.05,"oil":-0.30,"sp500": 0.60,"btc": 0.10},
    "UK100":   {"dxy":-0.10,"yields":-0.30,"gold": 0.10,"oil": 0.20,"sp500": 0.50,"btc": 0.05},
    "UK100Jun26":  {"dxy":-0.10,"yields":-0.30,"gold": 0.10,"oil": 0.20,"sp500": 0.50,"btc": 0.05},
    "Jp225":   {"dxy": 0.30,"yields": 0.20,"gold":-0.10,"oil":-0.20,"sp500": 0.50,"btc": 0.05},
    "Jp225Jun26":  {"dxy": 0.30,"yields": 0.20,"gold":-0.10,"oil":-0.20,"sp500": 0.50,"btc": 0.05},
    # Commodities
    "GOLD":    {"dxy":-0.80,"yields":-0.70,"gold": 0.00,"oil": 0.10,"sp500":-0.20,"btc": 0.10},
    "SILVER":  {"dxy":-0.70,"yields":-0.60,"gold": 0.80,"oil": 0.15,"sp500":-0.10,"btc": 0.05},
    "LCrude":  {"dxy":-0.40,"yields": 0.10,"gold": 0.20,"oil": 0.00,"sp500":-0.10,"btc": 0.00},
    "Brent":   {"dxy":-0.40,"yields": 0.10,"gold": 0.20,"oil": 0.95,"sp500":-0.10,"btc": 0.00},
    "NGas":    {"dxy":-0.30,"yields": 0.05,"gold": 0.10,"oil": 0.50,"sp500":-0.05,"btc": 0.00},
    "Coffee":  {"dxy":-0.25,"yields": 0.00,"gold": 0.05,"oil": 0.10,"sp500": 0.05,"btc": 0.00},
    # Crypto
    "BTCUSD":  {"dxy":-0.50,"yields":-0.60,"gold": 0.20,"oil": 0.05,"sp500": 0.70,"btc": 0.00},
    "ETHUSD":  {"dxy":-0.45,"yields":-0.55,"gold": 0.15,"oil": 0.00,"sp500": 0.65,"btc": 0.90},
}

# Default sensitivity for unknown symbols
_DEFAULT_SENSITIVITY = {"dxy":-0.20,"yields":-0.20,"gold": 0.05,"oil":-0.10,"sp500": 0.30,"btc": 0.05}

# Regime thresholds
_RISK_OFF_THRESHOLD  =  0.55   # risk_off_score above this → block/reduce
_RISK_ON_THRESHOLD   =  0.55   # risk_on_score  above this → allow full size
_INFLATION_THRESHOLD =  0.60   # inflation_score above this → reduce growth/crypto
_CRISIS_THRESHOLD    =  0.85   # risk_off + vix above this → crisis mode


@dataclass
class RegimeState:
    # Raw z-scores of macro factors
    dxy_z:    float = 0.0
    yield_z:  float = 0.0   # 10Y-2Y spread normalised
    vix:      float = 15.0
    gold_z:   float = 0.0
    oil_z:    float = 0.0
    sp500_z:  float = 0.0
    btc_z:    float = 0.0

    # Composite scores (0–1)
    risk_on_score:     float = 0.5
    risk_off_score:    float = 0.2
    inflation_score:   float = 0.3
    liquidity_score:   float = 0.7

    # Global regime
    regime: str = "neutral"   # risk_on | risk_off | inflation | deflation | crisis | neutral

    # Per-symbol multipliers (populated by compute_symbol_mults)
    symbol_mults: dict[str, float] = field(default_factory=dict)

    # Central bank pressure by pair
    cb_flags: dict[str, str] = field(default_factory=dict)

    def global_mult(self) -> float:
        """Global lot multiplier based on regime."""
        return {
            "crisis":    0.0,
            "risk_off":  0.50,
            "inflation": 0.65,
            "deflation": 0.75,
            "risk_on":   1.00,
            "neutral":   0.85,
        }.get(self.regime, 0.85)

    def summary(self) -> str:
        return (
            f"regime={self.regime}  "
            f"risk_on={self.risk_on_score:.2f}  "
            f"risk_off={self.risk_off_score:.2f}  "
            f"inflation={self.inflation_score:.2f}  "
            f"liquidity={self.liquidity_score:.2f}  "
            f"vix={self.vix:.1f}"
        )


class MacroRegimeEngine:
    """
    Stateless calculator: call update() once per cycle to recompute the regime.
    Zero I/O — all inputs provided by caller.

    Usage in AlphaEngine:
        self._regime_engine.update(
            dxy_zscore   = dxy.state.zscore,
            yield_spread = yield_.state.spread_10y_2y,
            vix          = vix_monitor.vix,
            cross_asset  = cross_asset_monitor.state,
        )
        mult = self._regime_engine.symbol_mult("EURUSD")
    """

    def __init__(self):
        self._state = RegimeState()

    @property
    def state(self) -> RegimeState:
        return self._state

    def symbol_mult(self, symbol: str) -> float:
        """Returns per-symbol lot multiplier. 1.0 = no restriction."""
        return self._state.symbol_mults.get(symbol, self._state.global_mult())

    def update(
        self,
        dxy_zscore:    float,
        yield_spread:  float,   # 10Y-2Y in pp
        vix:           float,
        cross_asset:   CrossAssetState,
    ) -> RegimeState:

        gold_z   = cross_asset.gold.zscore
        oil_z    = cross_asset.oil.zscore
        sp500_z  = cross_asset.sp500.zscore
        btc_z    = cross_asset.btc.zscore

        # ── Yield z-score (normalise spread to -2…+2 range) ────────────────
        # spread_10y_2y: normal range -1% to +2.5%; normalise to z-score-like
        yield_z = (yield_spread - 0.5) / 1.0   # 0 = flat, +1 = steep, -1.5 = inverted

        # ── Risk-Off Score ──────────────────────────────────────────────────
        # High DXY, high yields, high VIX, gold surging, SP500 falling
        vix_z   = (vix - 18.0) / 8.0   # normalised: 0=normal, 1=elevated, 2=high
        risk_off_signals = [
            max(0, dxy_zscore)  * 0.25,   # DXY strong
            max(0, yield_z)     * 0.15,   # yields rising (hurts risk)
            max(0, vix_z)       * 0.35,   # VIX elevated (strongest signal)
            max(0, gold_z)      * 0.15,   # gold surging (refuge)
            max(0, -sp500_z)    * 0.10,   # SP500 falling
        ]
        risk_off_score = min(sum(risk_off_signals), 1.0)

        # ── Risk-On Score ───────────────────────────────────────────────────
        risk_on_signals = [
            max(0, -dxy_zscore) * 0.20,   # DXY weak
            max(0, sp500_z)     * 0.35,   # SP500 rising
            max(0, btc_z)       * 0.20,   # BTC leading risk appetite
            max(0, -vix_z)      * 0.15,   # VIX low
            max(0, yield_z)     * 0.10,   # steepening curve (growth expectation)
        ]
        risk_on_score = min(sum(risk_on_signals), 1.0)

        # ── Inflation Score ─────────────────────────────────────────────────
        inflation_signals = [
            max(0, oil_z)       * 0.40,   # oil surging
            max(0, gold_z)      * 0.20,   # gold (inflation hedge)
            max(0, yield_z)     * 0.25,   # yields rising (inflation expectation)
            max(0, dxy_zscore)  * 0.15,   # USD strong (imported deflation elsewhere)
        ]
        inflation_score = min(sum(inflation_signals), 1.0)

        # ── Liquidity Score ─────────────────────────────────────────────────
        # High liquidity = risk assets favoured
        liquidity_signals = [
            max(0, -dxy_zscore) * 0.30,   # DXY weak = liquidity expanding
            max(0, sp500_z)     * 0.25,   # equities up = ample liquidity
            max(0, -vix_z)      * 0.25,   # VIX low = calm = liquid
            max(0, btc_z)       * 0.20,   # crypto as liquidity proxy
        ]
        liquidity_score = min(sum(liquidity_signals), 1.0)

        # ── Regime Classification ───────────────────────────────────────────
        crisis_score = risk_off_score + (vix_z * 0.3 if vix_z > 0 else 0)
        if crisis_score >= _CRISIS_THRESHOLD:
            regime = "crisis"
        elif risk_off_score >= _RISK_OFF_THRESHOLD and inflation_score < 0.40:
            regime = "risk_off"
        elif inflation_score >= _INFLATION_THRESHOLD:
            regime = "inflation"
        elif risk_on_score >= _RISK_ON_THRESHOLD and risk_off_score < 0.25:
            regime = "risk_on"
        elif yield_z < -1.0 and risk_off_score > 0.35:
            regime = "deflation"
        else:
            regime = "neutral"

        # ── Per-Symbol Multipliers ──────────────────────────────────────────
        factors = {
            "dxy":    dxy_zscore,
            "yields": yield_z,
            "gold":   gold_z,
            "oil":    oil_z,
            "sp500":  sp500_z,
            "btc":    btc_z,
        }
        symbol_mults = {}
        for sym, sens in _SENSITIVITY.items():
            symbol_mults[sym] = self._compute_symbol_mult(sens, factors, regime)

        self._state = RegimeState(
            dxy_z   = round(dxy_zscore, 3),
            yield_z = round(yield_z,    3),
            vix     = round(vix,        2),
            gold_z  = round(gold_z,     3),
            oil_z   = round(oil_z,      3),
            sp500_z = round(sp500_z,    3),
            btc_z   = round(btc_z,      3),
            risk_on_score   = round(risk_on_score,   3),
            risk_off_score  = round(risk_off_score,  3),
            inflation_score = round(inflation_score, 3),
            liquidity_score = round(liquidity_score, 3),
            regime      = regime,
            symbol_mults = symbol_mults,
        )
        return self._state

    @staticmethod
    def _compute_symbol_mult(
        sensitivity: dict[str, float],
        factors: dict[str, float],
        regime: str,
    ) -> float:
        """
        Per-symbol multiplier.
        Logic: each factor's z-score × sensitivity → adverse pressure score.
        Adverse pressure reduces the multiplier.
        """
        adverse = 0.0
        for factor, z in factors.items():
            s = sensitivity.get(factor, 0.0)
            if s != 0:
                # If s negative and factor rising (z>0) → adverse
                # If s positive and factor falling (z<0) → adverse
                contribution = -s * z   # positive = headwind
                adverse += max(0.0, contribution) * abs(s)

        # Normalise adverse score to 0-1
        max_adverse = sum(abs(s) * 1.5 for s in sensitivity.values())
        adverse_norm = min(adverse / max_adverse, 1.0) if max_adverse > 0 else 0.0

        # Map to multiplier: 0 adverse → 1.0, full adverse → 0.25
        mult = 1.0 - (adverse_norm * 0.75)

        # Apply regime hard caps
        if regime == "crisis":
            mult = min(mult, 0.25)
        elif regime == "risk_off":
            mult = min(mult, 0.60)

        return round(max(0.10, mult), 3)
