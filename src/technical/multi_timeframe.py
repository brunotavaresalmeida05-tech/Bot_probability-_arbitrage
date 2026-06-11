from __future__ import annotations
"""
Multi-Timeframe Coordinator — V9

Adaptive multi-timeframe analysis following the trading methodology:
  - 3min:  quiet markets (very low volatility)
  - 5min:  default operational (primary)
  - 10min: medium view
  - 15min: medium-structural view
  - 30min: structural view
  - 1H:    macro/context view

Rules:
  1. Primary TF is determined by current market volatility (BB width)
  2. At least 2 of 3 monitored TFs must agree for confluence
  3. Higher TF has veto power: if 1H bearish, no buy on lower TF
  4. "Os indicadores se conversam entre si" — they communicate across TFs

Confluence score: 0-3
  0: no confluence — HOLD
  1: weak confluence — reduce size
  2: moderate confluence — normal size
  3: strong confluence — full size allowed
"""
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from src.technical.indicators import compute_bundle, IndicatorBundle


class TFSignal(str, Enum):
    BULL = "bullish"
    BEAR = "bearish"
    FLAT = "flat"
    NONE = "none"


@dataclass
class TimeframeView:
    timeframe: str
    signal: TFSignal
    macd_dir: str
    bb_state: str           # expanding_up | expanding_down | contracting | neutral
    price_vs_ema50: str      # "above" | "below" | "at"
    price_vs_vwap: str      # "above" | "below" | "at"
    weight: float           # 1H=3, 30m=2, 15m=1.5, 5m=1, 3m=0.5


@dataclass
class MTFResult:
    symbol: str
    primary_tf: str
    confluence_score: float     # 0.0 - 1.0
    confluence_label: str       # "strong" | "moderate" | "weak" | "none"
    direction: str              # "bullish" | "bearish" | "flat"
    higher_tf_veto: bool        # True if 1H contradicts lower TFs
    lot_adjustment: float       # 1.0 = full | 0.7 = moderate | 0.4 = weak
    views: dict[str, TimeframeView] = field(default_factory=dict)
    rationale: list[str] = field(default_factory=list)


# Timeframe weights (higher TF = more weight)
_TF_WEIGHTS = {
    "H1":  3.0,
    "M30": 2.0,
    "M15": 1.5,
    "M10": 1.2,
    "M5":  1.0,
    "M3":  0.5,
}

# Minimum BB width thresholds to determine primary TF
# Very tight BB → use shorter TF; very wide → use longer TF
_BB_WIDTH_PCT_THRESHOLDS = [
    (0.0000, "M3"),     # very quiet < 0.05%
    (0.0005, "M5"),     # normal
    (0.0020, "M10"),    # moderate volatility
    (0.0050, "M15"),    # higher volatility
    (0.0100, "M30"),    # high volatility
]


def select_primary_tf(bb_width_pct: float) -> str:
    """
    Select primary operational timeframe based on current BB width.
    Implements: "Os tempos gráficos têm de ser adaptados à volatilidade do mercado."
    """
    primary = "M5"
    for threshold, tf in _BB_WIDTH_PCT_THRESHOLDS:
        if bb_width_pct >= threshold:
            primary = tf
    return primary


def _build_view(bundle: IndicatorBundle) -> TimeframeView:
    """Extract directional signal from an indicator bundle."""
    if bundle is None:
        return TimeframeView(
            timeframe="?", signal=TFSignal.NONE, macd_dir="flat",
            bb_state="neutral",
            price_vs_ema50="at", price_vs_vwap="at",
            weight=1.0,
        )

    # MACD direction
    macd_dir = bundle.macd.direction if bundle.macd else "flat"

    # BB state
    bb_state = "neutral"
    if bundle.bollinger:
        if bundle.bollinger.width > getattr(bundle.bollinger, "_prev_width", 0) * 1.02:
            if bundle.close > bundle.bollinger.middle:
                bb_state = "expanding_up"
            else:
                bb_state = "expanding_down"
        elif bundle.bollinger.width < getattr(bundle.bollinger, "_prev_width", 1) * 0.98:
            bb_state = "contracting"

    # Price vs MA50
    if bundle.ema50 > 0:
        if bundle.close > bundle.ema50 * 1.001:
            price_vs_ema50 = "above"
        elif bundle.close < bundle.ema50 * 0.999:
            price_vs_ema50 = "below"
        else:
            price_vs_ema50 = "at"
    else:
        price_vs_ema50 = "at"

    # Price vs VWAP
    if bundle.vwap > 0:
        if bundle.close > bundle.vwap * 1.0005:
            price_vs_vwap = "above"
        elif bundle.close < bundle.vwap * 0.9995:
            price_vs_vwap = "below"
        else:
            price_vs_vwap = "at"
    else:
        price_vs_vwap = "at"

    # Composite signal for this TF
    bull_count = sum([
        macd_dir == "bullish",
        bb_state == "expanding_up",
        price_vs_ema50 == "above",
        price_vs_vwap == "above",
    ])
    bear_count = sum([
        macd_dir == "bearish",
        bb_state == "expanding_down",
        price_vs_ema50 == "below",
        price_vs_vwap == "below",
    ])

    if bull_count >= 3:
        signal = TFSignal.BULL
    elif bear_count >= 3:
        signal = TFSignal.BEAR
    else:
        signal = TFSignal.FLAT

    return TimeframeView(
        timeframe=bundle.timeframe,
        signal=signal,
        macd_dir=macd_dir,
        bb_state=bb_state,
        price_vs_ema50=price_vs_ema50,
        price_vs_vwap=price_vs_vwap,
        weight=_TF_WEIGHTS.get(bundle.timeframe, 1.0),
    )


def analyze(
    symbol: str,
    bundles: dict[str, IndicatorBundle],
    macro_scenario: str = "indefinido",
) -> MTFResult:
    """
    Multi-timeframe analysis and confluence detection.

    Args:
        symbol:          instrument
        bundles:         dict of TF -> IndicatorBundle
        macro_scenario:  from PrepWorkflow: 'alta' | 'baixa' | 'indefinido'
    """
    rationale = []
    views: dict[str, TimeframeView] = {}

    for tf, bundle in bundles.items():
        views[tf] = _build_view(bundle)

    if not views:
        return MTFResult(symbol, "M5", 0.0, "none", "flat", False, 0.4)

    # Determine primary TF from BB width of M5 or best available
    primary_tf = "M5"
    for tf in ["M5", "M3", "M10", "M15"]:
        if tf in bundles and bundles[tf].bollinger:
            bb_width_pct = bundles[tf].bollinger.width_pct
            primary_tf = select_primary_tf(bb_width_pct)
            rationale.append(f"Primary TF={primary_tf} (BB width={bb_width_pct*100:.3f}%)")
            break

    # Weighted confluence scoring
    bull_weight = 0.0
    bear_weight = 0.0
    total_weight = 0.0

    for tf, view in views.items():
        w = view.weight
        total_weight += w
        if view.signal == TFSignal.BULL:
            bull_weight += w
        elif view.signal == TFSignal.BEAR:
            bear_weight += w

    bull_ratio = bull_weight / total_weight if total_weight > 0 else 0.0
    bear_ratio = bear_weight / total_weight if total_weight > 0 else 0.0

    if bull_ratio > bear_ratio:
        direction = "bullish"
        raw_confluence = bull_ratio
    elif bear_ratio > bull_ratio:
        direction = "bearish"
        raw_confluence = bear_ratio
    else:
        direction = "flat"
        raw_confluence = 0.0

    # Higher TF veto: 1H or 30min contradicts lower TF direction
    higher_tf_veto = False
    for tf in ["H1", "M30"]:
        if tf in views:
            htf_sig = views[tf].signal
            if (direction == "bullish" and htf_sig == TFSignal.BEAR) or \
               (direction == "bearish" and htf_sig == TFSignal.BULL):
                higher_tf_veto = True
                rationale.append(f"VETO: {tf} signal={htf_sig} contradicts {direction}")
                raw_confluence *= 0.5   # heavy penalty
                break

    # Macro scenario alignment
    if macro_scenario == "alta" and direction == "bullish":
        raw_confluence = min(1.0, raw_confluence * 1.2)
        rationale.append("Macro 'alta' alinha com bullish tecnico (+20% conf)")
    elif macro_scenario == "baixa" and direction == "bearish":
        raw_confluence = min(1.0, raw_confluence * 1.2)
        rationale.append("Macro 'baixa' alinha com bearish tecnico (+20% conf)")
    elif macro_scenario in ("alta", "baixa") and direction != "flat":
        raw_confluence *= 0.7
        rationale.append(f"Macro '{macro_scenario}' nao alinha com {direction} (-30% conf)")

    confluence_score = round(raw_confluence, 4)

    if confluence_score >= 0.70:
        label = "strong"
        lot_adj = 1.0
    elif confluence_score >= 0.50:
        label = "moderate"
        lot_adj = 0.7
    elif confluence_score >= 0.30:
        label = "weak"
        lot_adj = 0.4
    else:
        label = "none"
        lot_adj = 0.0

    # Log TF summary
    for tf, view in sorted(views.items()):
        rationale.append(f"{tf}: {view.signal.value} MACD={view.macd_dir} BB={view.bb_state}")

    return MTFResult(
        symbol=symbol,
        primary_tf=primary_tf,
        confluence_score=confluence_score,
        confluence_label=label,
        direction=direction,
        higher_tf_veto=higher_tf_veto,
        lot_adjustment=lot_adj,
        views=views,
        rationale=rationale,
    )
