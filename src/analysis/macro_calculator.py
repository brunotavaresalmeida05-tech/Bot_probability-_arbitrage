from __future__ import annotations
"""
Macro Calculator — V9

Implements the macro calculation layer:
  1. Economic surprise: (actual - consensus) / σ
  2. Macro regime score: weighted composite of macro indicators
  3. Yield curve slopes (10y-2y, 5y-2y, 10y-3m)
  4. Relative strength: asset vs benchmark, asset vs class

These feed the Context Score (CS) and the ScenarioEvaluator.

Macro calculation must precede all other calculations.
Priority: macro > correlation > volatility > technical > execution
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from src.macro.macro_context import MacroContext
from src.benchmark.portfolio_monitor import BenchmarkSnapshot


# ── Economic Surprise ──────────────────────────────────────────────────────

@dataclass
class EconomicSurprise:
    event: str
    actual: float
    consensus: float
    surprise_raw: float         # actual - consensus
    surprise_norm: float        # (actual - consensus) / historical_std
    direction: str              # "beat" | "miss" | "inline"
    impact: str                 # "high" | "medium" | "low"
    bullish_for_usd: bool       # True if surprise is good for USD strength


def calc_economic_surprise(
    event: str,
    actual: float,
    consensus: float,
    historical_std: float = 1.0,
    impact: str = "medium",
) -> EconomicSurprise:
    """
    Calculate economic surprise score.
    Formula: surprise_norm = (actual - consensus) / σ_historical
    """
    raw = actual - consensus
    norm = raw / historical_std if historical_std > 0 else 0.0

    if abs(norm) <= 0.5:
        direction = "inline"
    elif norm > 0:
        direction = "beat"
    else:
        direction = "miss"

    # Keywords that make a beat bullish for USD
    _usd_positive_events = [
        "payroll", "gdp", "retail", "pmi", "confidence", "adp",
        "employment", "income", "pce", "ism"
    ]
    _usd_negative_events = ["cpi", "pce_inflation", "inflation", "unemployment", "jobless"]

    event_lower = event.lower()
    if any(kw in event_lower for kw in _usd_positive_events):
        bullish_for_usd = direction == "beat"
    elif any(kw in event_lower for kw in _usd_negative_events):
        bullish_for_usd = direction == "miss"   # lower inflation = potentially bullish USD via rates
    else:
        bullish_for_usd = direction == "beat"

    return EconomicSurprise(
        event=event,
        actual=actual,
        consensus=consensus,
        surprise_raw=round(raw, 4),
        surprise_norm=round(norm, 4),
        direction=direction,
        impact=impact,
        bullish_for_usd=bullish_for_usd,
    )


# ── Macro Regime Score ─────────────────────────────────────────────────────

# Weights for macro regime composite score
# These are directional weights: positive = risk-on signal, negative = risk-off
_REGIME_WEIGHTS = {
    "dxy":       -0.25,    # DXY up = risk-off (negative for risk assets)
    "vix":       -0.20,    # VIX up = risk-off
    "yields_10y": 0.10,    # yields up = growth expectations (mildly risk-on)
    "sp500":      0.20,    # SP500 up = risk-on
    "gold":       0.10,    # gold up = mixed (safe haven + inflation hedge)
    "oil":        0.15,    # oil up = growth/demand (mildly risk-on)
}


@dataclass
class MacroRegimeScore:
    raw_score: float            # [-1, +1]
    regime: str                 # risk_on | risk_off | neutral | inflation | stress
    confidence: float           # 0-1
    components: dict = field(default_factory=dict)
    probability: dict = field(default_factory=dict)


def calc_regime_score(macro: MacroContext, benchmark: Optional[BenchmarkSnapshot] = None) -> MacroRegimeScore:
    """
    Compute weighted macro regime score.
    RegimeScore = Σ wi * normalized_change(indicator_i)

    Each indicator is normalized to its typical range, then weighted.
    """
    components = {}
    scores = []

    # DXY: change_pct normalized (typically -1% to +1% = extreme)
    dxy_norm = np.clip(macro.dxy_change_pct / 0.01, -1.0, 1.0)  # 1% = extreme
    dxy_score = dxy_norm * _REGIME_WEIGHTS["dxy"]
    components["dxy"] = round(float(dxy_score), 4)
    scores.append(dxy_score)

    # VIX: change from neutral (20 = neutral)
    vix_dev = (macro.vix - 20.0) / 10.0   # 10 point swing = extreme
    vix_norm = np.clip(vix_dev, -1.0, 1.0)
    vix_score = -vix_norm * abs(_REGIME_WEIGHTS["vix"])  # VIX up = risk-off (negative)
    components["vix"] = round(float(vix_score), 4)
    scores.append(vix_score)

    # Yields 10Y: direction of change matters
    yield_dev = (macro.us10y - 4.0) / 1.0   # 1pp swing normalized
    yield_norm = np.clip(yield_dev, -1.0, 1.0)
    yield_score = yield_norm * _REGIME_WEIGHTS["yields_10y"]
    components["yields_10y"] = round(float(yield_score), 4)
    scores.append(yield_score)

    # Yield curve shape
    if macro.curve_regime == "inverted":
        scores.append(-0.10)
        components["yield_curve"] = -0.10
    elif macro.curve_regime == "steep":
        scores.append(0.05)
        components["yield_curve"] = 0.05
    else:
        components["yield_curve"] = 0.0

    # Gold: up = mixed (safe haven risk-off, but also inflation)
    gold_dev = macro.gold_change_pct / 0.01  # 1% change normalized
    gold_norm = np.clip(gold_dev, -1.0, 1.0)
    gold_score = gold_norm * _REGIME_WEIGHTS["gold"]
    components["gold"] = round(float(gold_score), 4)
    scores.append(gold_score)

    # Oil: up = growth/demand signal
    oil_dev = macro.wti_change_pct / 0.02   # 2% change normalized
    oil_norm = np.clip(oil_dev, -1.0, 1.0)
    oil_score = oil_norm * _REGIME_WEIGHTS["oil"]
    components["oil"] = round(float(oil_score), 4)
    scores.append(oil_score)

    # Benchmark SP500 (from portfolio monitor if available)
    if benchmark:
        sp = benchmark.quotes.get("SP500") or benchmark.quotes.get("SPY")
        if sp and sp.change_pct != 0:
            sp_norm = np.clip(sp.change_pct / 0.02, -1.0, 1.0)
            sp_score = float(sp_norm) * _REGIME_WEIGHTS["sp500"]
            components["sp500"] = round(sp_score, 4)
            scores.append(sp_score)

    raw_score = float(np.clip(sum(scores), -1.0, 1.0))

    # Classify regime
    if raw_score >= 0.30:
        regime = "risk_on"
        confidence = min(1.0, raw_score / 0.8)
    elif raw_score <= -0.30:
        regime = "risk_off"
        confidence = min(1.0, abs(raw_score) / 0.8)
    elif macro.vix > 28 and macro.dxy_change_pct > 0:
        regime = "stress"
        confidence = 0.7
    elif macro.us10y > 5.0 and macro.gold_change_pct > 0:
        regime = "inflation"
        confidence = 0.5
    else:
        regime = "neutral"
        confidence = 0.3

    # Simple probability estimates
    prob = {
        "risk_on":  round(max(0, (raw_score + 1) / 2), 4),
        "risk_off": round(max(0, (1 - raw_score) / 2), 4),
        "neutral":  round(1.0 - abs(raw_score), 4),
    }

    return MacroRegimeScore(
        raw_score=round(raw_score, 4),
        regime=regime,
        confidence=round(confidence, 4),
        components=components,
        probability=prob,
    )


# ── Yield Curve Calculations ───────────────────────────────────────────────

@dataclass
class YieldCurveMetrics:
    slope_10y_2y: float     # primary: recession indicator
    slope_5y_2y: float      # short-end momentum
    slope_10y_3m: float     # Fed-watched spread
    shape: str              # steep | flat | inverted | kinked
    carry_premium: float    # reward for holding longer duration
    inversion_depth: float  # how inverted (negative = more inverted)


def calc_yield_curve(us10y: float, us2y: float, us5y: float = 0.0, us3m: float = 0.0) -> YieldCurveMetrics:
    """
    Calculate full yield curve metrics.

    slope_10y_2y > 0.25: steep (normal, expansion)
    slope_10y_2y 0 to 0.25: flat (transition/tightening)
    slope_10y_2y < 0: inverted (recession signal)
    """
    s_10_2 = us10y - us2y
    s_5_2  = (us5y - us2y) if us5y > 0 else 0.0
    s_10_3 = (us10y - us3m) if us3m > 0 else 0.0

    if s_10_2 < -0.10:
        shape = "inverted"
    elif s_10_2 < 0.25:
        if s_5_2 < 0 and s_10_2 >= 0:
            shape = "kinked"
        else:
            shape = "flat"
    else:
        shape = "steep"

    carry_premium = s_10_2   # reward for extending duration
    inversion_depth = min(0.0, s_10_2)

    return YieldCurveMetrics(
        slope_10y_2y=round(s_10_2, 4),
        slope_5y_2y=round(s_5_2, 4),
        slope_10y_3m=round(s_10_3, 4),
        shape=shape,
        carry_premium=round(carry_premium, 4),
        inversion_depth=round(inversion_depth, 4),
    )


# ── Relative Strength ──────────────────────────────────────────────────────

def calc_relative_strength(
    asset_return: float,
    benchmark_return: float,
    window_returns_asset: list[float] | None = None,
    window_returns_benchmark: list[float] | None = None,
) -> dict:
    """
    Calculate relative strength of asset vs benchmark.
    RS = asset_return - benchmark_return (alpha)
    Beta = Cov(asset, benchmark) / Var(benchmark)

    Returns: rs (alpha), beta, outperforming flag
    """
    rs = asset_return - benchmark_return

    beta = 1.0
    if window_returns_asset and window_returns_benchmark:
        n = min(len(window_returns_asset), len(window_returns_benchmark))
        if n >= 5:
            arr_a = np.array(window_returns_asset[-n:])
            arr_b = np.array(window_returns_benchmark[-n:])
            var_b = np.var(arr_b)
            if var_b > 0:
                beta = float(np.cov(arr_a, arr_b)[0][1] / var_b)

    return {
        "rs": round(rs, 6),
        "beta": round(beta, 4),
        "outperforming": rs > 0,
        "alpha_annualized": round(rs * 252, 4),
    }


# ── Z-Score ────────────────────────────────────────────────────────────────

def price_zscore(
    price: float,
    mean: float,
    std: float,
    vwap: float = 0.0,
) -> dict:
    """
    Calculate z-score of price relative to recent distribution.
    z > +2: significantly above average (overextended up)
    z < -2: significantly below average (overextended down)
    """
    z_price = (price - mean) / std if std > 0 else 0.0
    z_vwap  = (price - vwap) / std if std > 0 and vwap > 0 else 0.0

    if abs(z_price) >= 3.0:
        zone = "extreme"
    elif abs(z_price) >= 2.0:
        zone = "overextended"
    elif abs(z_price) >= 1.0:
        zone = "elevated"
    else:
        zone = "normal"

    return {
        "z_price": round(z_price, 4),
        "z_vwap":  round(z_vwap, 4),
        "zone": zone,
        "mean_reversion_probability": round(min(1.0, abs(z_price) / 3.0), 4),
    }
