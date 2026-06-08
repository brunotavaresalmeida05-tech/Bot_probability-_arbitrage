"""
src/macro/interest_rate_transmission.py — Interest Rate Transmission Engine.

Classifies rate direction from yield/CB data and computes per-symbol
transmission multipliers.

Transmission chain:
  Rate direction (hike/cut/hold) × tone (hawkish/dovish)
    → Consumer spending effect
    → Durable goods effect
    → Corporate capex/hiring
    → FX effect (DXY and cross-rates)
    → Equity discount rate effect
    → Bond duration effect
    → Commodity (USD-priced) effect
    → Crypto (liquidity-beta) effect

Output:
  RateEnvironment  — classifies the current rate environment
  symbol_mult()    — per-symbol lot multiplier from rate transmission

Data sources (already in the system):
  YieldMonitor  → us10y, us2y, spread_10y_2y
  DXYBasket     → dxy_zscore
  MacroRegime   → regime (risk_on/off/inflation/deflation)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_MAP_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "macro_asset_map.yaml"

# ── Rate direction constants ─────────────────────────────────────────────────
HIKE   = "hike"
CUT    = "cut"
HOLD   = "hold"
EASING = "easing"    # prolonged cuts / QE
TIGHT  = "tight"     # prolonged hikes / QT

# ── Transmission weights by asset class ─────────────────────────────────────
# How much of the rate effect transmits to each class
# (negative = adverse when US rates rise)
_CLASS_SENSITIVITY: dict[str, float] = {
    "fx":          -0.40,   # most FX pairs adversely affected by US hikes
    "indices":     -0.55,   # equity discount rate effect
    "commodities": -0.30,   # USD pricing effect
    "crypto":      -0.70,   # most sensitive to liquidity
    "unknown":     -0.30,
}

# ── Prolonged regime multipliers ────────────────────────────────────────────
# Applied when rate environment is persistent, not just one event
_PROLONGED_MULT: dict[str, dict[str, float]] = {
    TIGHT: {
        "fx":          0.75,
        "indices":     0.60,
        "commodities": 0.70,
        "crypto":      0.40,
        "unknown":     0.65,
    },
    EASING: {
        "fx":          0.90,
        "indices":     1.00,
        "commodities": 0.85,
        "crypto":      1.00,
        "unknown":     0.90,
    },
    HOLD: {
        "fx":          0.90,
        "indices":     0.90,
        "commodities": 0.85,
        "crypto":      0.85,
        "unknown":     0.90,
    },
}


@dataclass
class RateEnvironment:
    direction:      str    # hike | cut | hold
    prolonged_mode: str    # tight | easing | hold
    us10y:          float
    us2y:           float
    spread:         float  # 10Y-2Y
    dxy_zscore:     float
    real_yield_est: float  # us10y - estimated inflation (proxy)

    # Derived
    is_hawkish:     bool
    is_dovish:      bool
    real_yield_up:  bool   # rising real yields = adverse for gold/growth/crypto

    def summary(self) -> str:
        tone = "hawkish" if self.is_hawkish else ("dovish" if self.is_dovish else "neutral")
        return (
            f"rate_dir={self.direction} mode={self.prolonged_mode} tone={tone} "
            f"10Y={self.us10y:.2f}% 2Y={self.us2y:.2f}% "
            f"spread={self.spread:+.2f}pp real_yield_up={self.real_yield_up}"
        )


class InterestRateTransmissionEngine:
    """
    Reads yield state + DXY to classify rate environment.
    Provides per-symbol lot multiplier based on transmission theory.

    Usage:
        engine = InterestRateTransmissionEngine(asset_map)
        env = engine.classify(yield_state, dxy_zscore, inflation_score)
        mult = engine.symbol_mult("BTCUSD", env)
    """

    def __init__(self, asset_map: dict | None = None):
        self._map = asset_map or _load_map()

    def classify(
        self,
        us10y:           float,
        us2y:            float,
        dxy_zscore:      float,
        inflation_score: float = 0.3,   # from MacroRegimeEngine
        prev_us10y:      float = 0.0,   # previous reading for momentum
    ) -> RateEnvironment:

        spread     = us10y - us2y
        real_yield = us10y - (inflation_score * 4.0)  # rough proxy: score → annualised %
        real_yield_est = round(real_yield, 3)

        # Rate direction from curve and momentum
        yield_rising  = us10y > prev_us10y + 0.05 if prev_us10y else False
        yield_falling = us10y < prev_us10y - 0.05 if prev_us10y else False

        if yield_rising and us10y > 4.0:
            direction = HIKE
        elif yield_falling and us10y < 4.5:
            direction = CUT
        else:
            direction = HOLD

        # Prolonged mode from level and curve shape
        if us10y > 4.5 and spread < 0.5:
            prolonged_mode = TIGHT
        elif us10y < 3.5 or spread < 0:
            prolonged_mode = EASING
        else:
            prolonged_mode = HOLD

        # Hawkish: rates high + DXY strong + inflation elevated
        is_hawkish = us10y > 4.2 and dxy_zscore > 0.5 and inflation_score > 0.4
        is_dovish  = us10y < 4.0 and dxy_zscore < -0.5 and inflation_score < 0.3

        real_yield_up = real_yield > 1.5 or (yield_rising and real_yield > 0)

        return RateEnvironment(
            direction      = direction,
            prolonged_mode = prolonged_mode,
            us10y          = us10y,
            us2y           = us2y,
            spread         = spread,
            dxy_zscore     = dxy_zscore,
            real_yield_est = real_yield_est,
            is_hawkish     = is_hawkish,
            is_dovish      = is_dovish,
            real_yield_up  = real_yield_up,
        )

    def symbol_mult(self, symbol: str, env: RateEnvironment) -> float:
        """
        Per-symbol lot multiplier from interest rate transmission.
        Combines:
          1. Per-symbol rate sensitivity from macro_asset_map.yaml
          2. Asset-class transmission weight
          3. Prolonged regime discount
        """
        profile   = self._map.get(symbol, {})
        sens      = profile.get("rate_sensitivity", {})
        asset_cls = _asset_class(symbol)

        # Map direction to YAML key
        if env.direction == HIKE:
            rate_key = "us_hike"
        elif env.direction == CUT:
            rate_key = "us_cut"
        else:
            rate_key = None

        # Per-symbol sensitivity (0 if unknown)
        sym_sens = float(sens.get(rate_key, 0.0)) if rate_key else 0.0

        # Only apply if sensitivity is adverse (negative)
        if sym_sens >= 0:
            # Neutral or beneficial rate environment — no penalty
            rate_mult = 1.0
        else:
            # Convert adverse sensitivity to multiplier: -0.8 → 0.4 penalty
            adverse = abs(sym_sens)
            rate_mult = max(0.20, 1.0 - (adverse * 0.6))

        # Prolonged regime discount (from class table)
        prolonged = _PROLONGED_MULT.get(env.prolonged_mode, {})
        class_mult = prolonged.get(asset_cls, prolonged.get("unknown", 0.90))

        # Real yield effect: if real yields rising, penalise gold and crypto extra
        real_yield_penalty = 1.0
        if env.real_yield_up:
            if asset_cls == "crypto":
                real_yield_penalty = 0.70
            elif symbol in ("GOLD", "SILVER"):
                real_yield_penalty = 0.75

        final = rate_mult * class_mult * real_yield_penalty
        return round(max(0.15, min(final, 1.0)), 3)

    def consumer_effect(self, env: RateEnvironment) -> str:
        """Qualitative consumer spending effect for logging."""
        if env.is_hawkish:
            return "credit_expensive → consumer_spending↓ durable_goods↓ capex↓"
        if env.is_dovish:
            return "credit_cheap → consumer_spending↑ durable_goods↑ capex↑"
        return "neutral"

    def equity_effect(self, env: RateEnvironment) -> str:
        if env.prolonged_mode == TIGHT:
            return "discount_rate↑ → valuations_compressed esp. growth/tech"
        if env.prolonged_mode == EASING:
            return "discount_rate↓ → multiples_expand → risk_on"
        return "neutral"


def _load_map() -> dict:
    try:
        with open(_MAP_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("symbols", {})
    except Exception as e:
        logger.warning(f"[MacroAssetMap] Failed to load: {e}")
        return {}


def _asset_class(symbol: str) -> str:
    fx = {"EURUSD","GBPUSD","USDJPY","AUDUSD","NZDUSD","USDCHF","USDCAD","EURJPY","USDNOK","USDMXN"}
    indices = {"Usa500","UsaTec","USAtec","Ger40","UK100","Jp225","USA500Jun26","US100Jun26","Ger40Jun26","UK100Jun26","Jp225Jun26"}
    crypto  = {"BTCUSD","ETHUSD","SOLUSD"}
    if symbol in fx:      return "fx"
    if symbol in indices: return "indices"
    if symbol in crypto:  return "crypto"
    return "commodities"
