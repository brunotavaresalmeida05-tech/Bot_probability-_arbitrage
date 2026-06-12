from __future__ import annotations
"""
TotalScore Engine — V9

Master scoring system combining 7 components per asset per timeframe.
Implements the full mathematical model from the trading methodology:

  TotalScore = wm*MCS_n + wb*BCS_n + wv*VES_n - we*ES_n + wc*CS_n - wr*RS_n

Camada principal (base da decisão técnica):
  MCS: MACD Completion Score    — momentum, divergências e movimento por cumprir
  BCS: Bollinger Completion Score — compressão, expansão e extremos de volatilidade

Camada de expansão / exaustão:
  VES: Volatility Expansion Score — MCS + BCS + ATR expansion + volume surge
  ES:  Exhaustion Score          — fim de movimento (peso negativo)

Camada de contexto e risco:
  CS:  Context Score  — macro + evento + benchmark + correlação
  RS:  Risk Score     — VIX + ATR Stop proximity + evento + drawdown (peso negativo)

Indicadores de suporte (entram como filtros binários ou reforço de CS/MCS/RS):
  VWAP, SMA 50/100, Weis Wave, Fair Price

Weights vary by:
  - Asset class: forex | indices | gold | oil | treasuries | crypto
  - Timeframe: M3 | M5 | M15 | M30 | H1

Final weight: PesoFinal = 0.6 * PesoClasse + 0.4 * PesoTimeframe

Thresholds:
  >= 0.70: strong entry (execute)
  0.50-0.70: moderate entry
  0.35-0.50: wait for confirmation
  < 0.35: no entry
  ES > 0.70: block even if TotalScore good
"""
from dataclasses import dataclass, field
from typing import Optional
import math

import numpy as np

from src.analysis.asset_profiler import AssetClass, get_profile
from src.technical.indicators import IndicatorBundle
from src.technical.macd_analyzer import MACDAnalysis
from src.technical.bollinger_analyzer import BollingerAnalysis
from src.macro.macro_context import MacroContext


# ── Weight Tables ──────────────────────────────────────────────────────────

# Weights by asset class [MCS, BCS, VES, ES, CS, RS]
# HCS removed (Hi-Lo Activator retired); weight redistributed to BCS and VES.
_CLASS_WEIGHTS: dict[str, tuple[float, ...]] = {
    "forex":      (0.26, 0.24, 0.20, 0.12, 0.12, 0.06),
    "indices":    (0.28, 0.24, 0.22, 0.12, 0.08, 0.06),
    "gold":       (0.24, 0.28, 0.20, 0.14, 0.08, 0.06),
    "oil":        (0.22, 0.28, 0.22, 0.14, 0.08, 0.06),
    "treasuries": (0.20, 0.26, 0.20, 0.18, 0.10, 0.06),
    "crypto":     (0.28, 0.24, 0.24, 0.10, 0.07, 0.07),
    "unknown":    (0.24, 0.26, 0.22, 0.12, 0.10, 0.06),
}

# Weights by timeframe [MCS, BCS, VES, ES, CS, RS]
_TF_WEIGHTS: dict[str, tuple[float, ...]] = {
    "M1":  (0.18, 0.32, 0.28, 0.10, 0.07, 0.05),
    "M3":  (0.20, 0.30, 0.26, 0.12, 0.07, 0.05),
    "M5":  (0.24, 0.28, 0.24, 0.12, 0.08, 0.04),
    "M10": (0.26, 0.27, 0.22, 0.12, 0.09, 0.04),
    "M15": (0.28, 0.24, 0.22, 0.12, 0.10, 0.04),
    "M30": (0.30, 0.22, 0.20, 0.14, 0.10, 0.04),
    "H1":  (0.32, 0.20, 0.18, 0.16, 0.10, 0.04),
}

_ALPHA = 0.60   # weight of class in combined weight
_BETA  = 0.40   # weight of timeframe in combined weight

# Exhaustion block threshold
_ES_BLOCK_THRESHOLD = 0.70

# Entry thresholds
THRESHOLD_STRONG   = 0.70
THRESHOLD_MODERATE = 0.50
THRESHOLD_WEAK     = 0.35


def _sigmoid(x: float) -> float:
    """Normalize any value to (0, 1) via sigmoid."""
    return 1.0 / (1.0 + math.exp(-x))


def _normalize(value: float, center: float = 0.0, scale: float = 1.0) -> float:
    """Normalize raw score to [0, 1] via z-score then sigmoid."""
    return _sigmoid((value - center) / scale if scale != 0 else 0.0)


def _combined_weights(asset_class: str, timeframe: str) -> tuple[float, ...]:
    """Compute final weights: 60% class + 40% timeframe. Returns (wm, wb, wv, we, wc, wr)."""
    cls_w = _CLASS_WEIGHTS.get(asset_class, _CLASS_WEIGHTS["unknown"])
    tf_w  = _TF_WEIGHTS.get(timeframe, _TF_WEIGHTS["M15"])
    return tuple(_ALPHA * c + _BETA * t for c, t in zip(cls_w, tf_w))


# ── Individual Score Functions ─────────────────────────────────────────────

def _macd_completion_score(
    macd: MACDAnalysis | None,
    bundle: IndicatorBundle,
) -> float:
    """
    MCS = a1 * |MACD-Signal|/ATR + a2 * slope + a3 * hist + a4 * zero_distance
    Measures remaining momentum / volatility still to be completed.
    """
    if not macd:
        return 0.5
    atr = bundle.atr if bundle.atr > 0 else 1e-6

    dist = abs(macd.macd_line - macd.signal_line) / atr if atr > 0 else 0
    slope = 1.0 if macd.momentum == "accelerating" else (-0.5 if macd.momentum == "decelerating" else 0.0)
    hist = abs(macd.macd_line - macd.signal_line)   # raw histogram magnitude
    zero_dist = abs(macd.macd_line) / (abs(macd.signal_line) + 1e-10)

    raw = 0.35 * dist + 0.30 * slope + 0.20 * min(hist, 1.0) + 0.15 * min(zero_dist, 2.0)
    # If MACD is decelerating and near cross, momentum is exhausting
    if macd.momentum == "decelerating":
        raw *= 0.7
    return float(np.clip(raw, 0.0, 3.0))


def _bollinger_completion_score(
    bb: BollingerAnalysis | None,
    bundle: IndicatorBundle,
) -> float:
    """
    BCS = b1 * band_position + b2 * band_expansion + b3 * extreme_distance
    Measures remaining band expansion / unfulfilled zones.
    """
    if not bb:
        return 0.5
    if bb.width == 0:
        return 0.3

    # Band position: 0 = at lower, 0.5 = middle, 1 = at upper
    band_pos = (bundle.close - bb.lower) / bb.width if bb.width > 0 else 0.5
    band_pos = float(np.clip(band_pos, 0.0, 1.0))

    # Band expansion (positive = expanding)
    prev_w = getattr(bb, "prev_width", 0.0)
    bwe = (bb.width - prev_w) / prev_w if prev_w > 0 else 0.0

    # Distance to extremes: how far from ±2σ band edges
    dist_to_upper = (bb.upper - bundle.close) / bb.width if bb.width > 0 else 0.5
    dist_to_lower = (bundle.close - bb.lower) / bb.width if bb.width > 0 else 0.5
    extreme_dist = min(dist_to_upper, dist_to_lower)   # how far from nearest extreme

    # Unfulfilled points add potential
    unf_bonus = (len(bb.unfulfilled_upper) + len(bb.unfulfilled_lower)) * 0.05

    raw = 0.35 * band_pos + 0.35 * max(0.0, bwe) + 0.20 * (1 - extreme_dist) + 0.10 + unf_bonus
    return float(np.clip(raw, 0.0, 2.0))


def _volatility_expansion_score(
    mcs_n: float,
    bcs_n: float,
    bundle: IndicatorBundle,
    atr_avg: float = 0.0,
    vol_avg: float = 0.0,
) -> float:
    """
    VES = c1*MCS_n + c2*BCS_n + c3*ATR_expansion + c4*volume_surge
    Combines momentum + band + ATR + volume into expansion signal.
    """
    atr_expansion = 0.0
    if atr_avg > 0 and bundle.atr > 0:
        atr_expansion = (bundle.atr - atr_avg) / atr_avg
        atr_expansion = float(np.clip(atr_expansion, -1.0, 1.0))

    volume_surge = 0.0
    if vol_avg > 0 and bundle.volume > 0:
        volume_surge = (bundle.volume - vol_avg) / vol_avg
        volume_surge = float(np.clip(volume_surge, -1.0, 1.0))

    raw = (0.30 * mcs_n + 0.30 * bcs_n
           + 0.25 * max(0.0, atr_expansion)
           + 0.15 * max(0.0, volume_surge))
    return float(np.clip(raw, 0.0, 1.0))


def _exhaustion_score(
    bb: BollingerAnalysis | None,
    macd: MACDAnalysis | None,
    bundle: IndicatorBundle,
    fair_price: float = 0.0,
    expected_range: float = 0.0,
) -> float:
    """
    ES = d1*overextension + d2*divergence + d3*wick_ratio + d4*volume_fade + d5*band_stretch

    High ES = movement near end → reduce size or block.
    """
    price = bundle.close

    # 1. Overextension: how far from fair value vs expected range
    overextension = 0.0
    if fair_price > 0 and expected_range > 0:
        overextension = abs(price - fair_price) / expected_range
        overextension = float(np.clip(overextension, 0.0, 1.0))

    # 2. MACD divergence
    divergence = 0.0
    if macd and macd.divergence != "none":
        divergence = 0.8

    # 3. Band stretch: BB very open + price at extreme
    band_stretch = 0.0
    if bb:
        if bb.squeeze_percentile > 75 and (bb.walking_upper or bb.walking_lower):
            band_stretch = 0.7
        elif bb.width_pct > 0.02:   # very wide bands
            band_stretch = 0.5

    # 4. Momentum decelerating
    momentum_fade = 0.0
    if macd and macd.momentum == "decelerating":
        momentum_fade = 0.5

    # 5. MACD near zero after big move (exhaustion)
    macd_near_zero = 0.0
    if macd and abs(macd.macd_line) < abs(macd.signal_line) * 0.3:
        macd_near_zero = 0.4

    raw = (0.30 * overextension
           + 0.25 * divergence
           + 0.20 * band_stretch
           + 0.15 * momentum_fade
           + 0.10 * macd_near_zero)
    return float(np.clip(raw, 0.0, 1.0))


def _context_score(
    macro: MacroContext,
    regime_score: float,
    benchmark_risk_on: float = 0.0,
    correlation_ok: bool = True,
    event_positive: bool = True,
    bias: str = "buy",
) -> float:
    """
    CS = e1*regime + e2*event + e3*benchmark + e4*correlation

    Positive = context favors bias direction.
    """
    # Regime alignment
    if bias == "buy":
        regime_align = max(0.0, regime_score)         # risk-on favors buy
    else:
        regime_align = max(0.0, -regime_score)        # risk-off favors sell

    # Event (no blackout + no adverse news)
    event_score = 0.8 if event_positive else 0.2

    # Benchmark (risk-on score from BenchmarkMonitor)
    bench_score = (benchmark_risk_on + 1.0) / 2.0   # normalize -1,+1 -> 0,1
    if bias == "sell":
        bench_score = 1.0 - bench_score

    # Correlation (0 = correlated conflict, 1 = clean)
    corr_score = 1.0 if correlation_ok else 0.3

    raw = (0.40 * regime_align
           + 0.25 * event_score
           + 0.25 * bench_score
           + 0.10 * corr_score)
    return float(np.clip(raw, 0.0, 1.0))


def _risk_score(
    macro: MacroContext,
    daily_dd_pct: float = 0.0,
    event_minutes_away: float = 999.0,
    correlation_risk: float = 0.0,
    atr_stop_dist_pct: float = 1.0,
) -> float:
    """
    RS = f1*vix + f2*atr_stop_proximity + f3*event + f4*correlation + f5*drawdown

    ATR Stop proximity: price close to stop = higher risk penalty.
    High RS = risky conditions → reduce size or block.
    """
    vix_risk = (macro.vix - 15.0) / 30.0
    vix_risk = float(np.clip(vix_risk, 0.0, 1.0))

    # ATR Stop proximity: dist_pct near 0 = price at stop = max risk
    atr_stop_risk = max(0.0, 1.0 - atr_stop_dist_pct * 20.0)  # 5% dist = 0 risk

    event_risk = max(0.0, 1.0 - event_minutes_away / 30.0)

    corr_risk = float(np.clip(correlation_risk, 0.0, 1.0))

    dd_risk = float(np.clip(abs(daily_dd_pct) / 0.03, 0.0, 1.0))

    raw = (0.28 * vix_risk
           + 0.25 * atr_stop_risk
           + 0.24 * event_risk
           + 0.14 * corr_risk
           + 0.09 * dd_risk)
    return float(np.clip(raw, 0.0, 1.0))


# ── Main Score Function ────────────────────────────────────────────────────

@dataclass
class TotalScoreResult:
    symbol: str
    timeframe: str
    asset_class: str
    total_score: float          # [0, 1]
    decision: str               # execute | moderate | wait | block
    lot_multiplier: float       # how much to scale position
    # Components
    mcs_raw: float
    bcs_raw: float
    mcs_n: float
    bcs_n: float
    ves: float
    es: float
    cs: float
    rs: float
    # Weights used
    weights: dict = field(default_factory=dict)
    # Debug
    blocked_by_es: bool = False
    notes: list[str] = field(default_factory=list)


def compute(
    symbol: str,
    timeframe: str,
    bundle: IndicatorBundle,
    macro: MacroContext,
    macd_analysis: MACDAnalysis | None = None,
    bb_analysis: BollingerAnalysis | None = None,
    fair_price: float = 0.0,
    expected_range: float = 0.0,
    regime_score: float = 0.0,
    benchmark_risk_on: float = 0.0,
    correlation_ok: bool = True,
    event_positive: bool = True,
    event_minutes_away: float = 999.0,
    daily_dd_pct: float = 0.0,
    correlation_risk: float = 0.0,
    atr_avg: float = 0.0,
    vol_avg: float = 0.0,
    bias: str = "buy",
) -> TotalScoreResult:
    """
    Compute TotalScore for one symbol/timeframe combination.
    This is the master decision function.
    """
    profile = get_profile(symbol)
    asset_class_str = profile.asset_class.value
    notes = []

    # ── 1. Compute raw scores ──────────────────────────────────────────────
    mcs_raw = _macd_completion_score(macd_analysis, bundle)
    bcs_raw = _bollinger_completion_score(bb_analysis, bundle)

    # ── 2. Normalize to [0, 1] via sigmoid ────────────────────────────────
    mcs_n = _normalize(mcs_raw, center=0.5, scale=0.5)
    bcs_n = _normalize(bcs_raw, center=0.5, scale=0.5)

    # ── 3. Compute VES, ES, CS, RS ────────────────────────────────────────
    ves = _volatility_expansion_score(mcs_n, bcs_n, bundle, atr_avg, vol_avg)
    ves_n = _normalize(ves, center=0.5, scale=0.3)

    es = _exhaustion_score(bb_analysis, macd_analysis, bundle, fair_price, expected_range)
    es_n = _normalize(es, center=0.4, scale=0.3)

    cs = _context_score(macro, regime_score, benchmark_risk_on, correlation_ok, event_positive, bias)
    cs_n = cs

    # ATR Stop proximity for RS
    atr_stop_dist_pct = 1.0
    if bundle.atr_stop and bundle.close > 0:
        atr_stop_dist_pct = abs(bundle.close - bundle.atr_stop.value) / bundle.close

    rs = _risk_score(macro, daily_dd_pct, event_minutes_away, correlation_risk, atr_stop_dist_pct)
    rs_n = rs

    # ── 4. Get combined weights ────────────────────────────────────────────
    wm, wb, wv, we, wc, wr = _combined_weights(asset_class_str, timeframe)

    # ── 5. TotalScore ─────────────────────────────────────────────────────
    total = (wm * mcs_n + wb * bcs_n + wv * ves_n
             - we * es_n          # ES subtracts
             + wc * cs_n
             - wr * rs_n)         # RS subtracts (risk penalty)

    total = float(np.clip(total, 0.0, 1.0))

    # ── 6. Exhaustion block ────────────────────────────────────────────────
    blocked_by_es = es > _ES_BLOCK_THRESHOLD
    if blocked_by_es:
        notes.append(f"BLOCKED: ES={es:.3f} > threshold {_ES_BLOCK_THRESHOLD}")
        total = min(total, 0.35)  # force below entry threshold

    # ── 7. Decision ───────────────────────────────────────────────────────
    if blocked_by_es:
        decision = "block"
        lot_mult = 0.0
    elif total >= THRESHOLD_STRONG:
        decision = "execute"
        lot_mult = 1.0
        notes.append(f"Strong signal: {total:.3f}")
    elif total >= THRESHOLD_MODERATE:
        decision = "moderate"
        lot_mult = 0.7
        notes.append(f"Moderate signal: {total:.3f}")
    elif total >= THRESHOLD_WEAK:
        decision = "wait"
        lot_mult = 0.0
        notes.append(f"Weak signal, wait: {total:.3f}")
    else:
        decision = "block"
        lot_mult = 0.0
        notes.append(f"Below threshold: {total:.3f}")

    # ── 8. Risk-score lot reduction ───────────────────────────────────────
    if rs > 0.6 and lot_mult > 0:
        lot_mult *= (1.0 - rs * 0.5)
        notes.append(f"RS={rs:.3f} → lot reduced to {lot_mult:.2f}")

    lot_mult = round(float(np.clip(lot_mult, 0.0, 1.0)), 4)

    return TotalScoreResult(
        symbol=symbol,
        timeframe=timeframe,
        asset_class=asset_class_str,
        total_score=round(total, 4),
        decision=decision,
        lot_multiplier=lot_mult,
        mcs_raw=round(mcs_raw, 4),
        bcs_raw=round(bcs_raw, 4),
        mcs_n=round(mcs_n, 4),
        bcs_n=round(bcs_n, 4),
        ves=round(ves, 4),
        es=round(es, 4),
        cs=round(cs, 4),
        rs=round(rs, 4),
        weights={"wm": wm, "wb": wb, "wv": wv, "we": we, "wc": wc, "wr": wr},
        blocked_by_es=blocked_by_es,
        notes=notes,
    )


def opportunity_score_from_result(result: TotalScoreResult) -> tuple[float, str]:
    """
    Extrai OpportunityScore e label a partir de um TotalScoreResult existente.
    Conveniência para integração com o scanner sem recalcular tudo.
    """
    from src.engine.scanner import compute_opportunity_score
    return compute_opportunity_score(
        mcs=result.mcs_n,
        bcs=result.bcs_n,
        ves=result.ves,
        es=result.es,
    )


def permission_score_from_result(
    result: TotalScoreResult,
    blackout: bool = False,
) -> "PermissionResult":  # noqa: F821
    """
    Extrai PermissionScore e decisão a partir de um TotalScoreResult existente.
    """
    from src.engine.scanner import compute_permission_score, PermissionResult
    perm = compute_permission_score(
        cs=result.cs,
        rs=result.rs,
        es=result.es,
        atr_fit=0.5,  # default quando ATRFit não calculado externamente
        blackout=blackout,
    )
    perm.symbol    = result.symbol
    perm.timeframe = result.timeframe
    return perm


def describe_score(result: TotalScoreResult) -> str:
    """Human-readable summary of a TotalScore result."""
    return (
        f"{result.symbol} {result.timeframe} [{result.asset_class}] "
        f"score={result.total_score:.3f} -> {result.decision.upper()} "
        f"lot={result.lot_multiplier:.2f} | "
        f"MCS={result.mcs_n:.2f} BCS={result.bcs_n:.2f} "
        f"VES={result.ves:.2f} ES={result.es:.2f} "
        f"CS={result.cs:.2f} RS={result.rs:.2f}"
    )
