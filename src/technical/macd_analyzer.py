from __future__ import annotations
"""
MACD Analyzer — V9

Implements the "teeth of volatility" concept:
  - Local peaks/valleys of the MACD line = volatility resistance points
  - Number of teeth at a price level = how many times price may bounce before breaking
  - Unfulfilled teeth = points the market tends to return to
  - MACD direction + macro context = directional bias (never MACD alone)

Key insight from trading methodology:
  "O cruzamento das linhas (rápida e lenta) não significa necessariamente uma inversão
   do mercado. O sistema deve avaliar junto ao contexto macro e micro do momento."
  "Esses dentes significam pontos onde o mercado tende a sofrer uma certa resistência.
   E o número de dentes deixados significa a quantidade de vezes que o preço poderá
   bater até romper."
"""
from dataclasses import dataclass, field
from typing import NamedTuple

import numpy as np
import pandas as pd


@dataclass
class MACDTooth:
    """A single volatility resistance/support point from MACD."""
    macd_value: float       # MACD line value at this tooth
    bar_index: int          # position in history
    tooth_type: str         # "peak" | "trough"
    impact_count: int = 1   # how many times price revisited this level
    fulfilled: bool = False # True if price passed through this level


@dataclass
class MACDAnalysis:
    macd_line: float
    signal_line: float
    direction: str          # "bullish" | "bearish" | "flat"
    momentum: str           # "accelerating" | "decelerating" | "flat"

    # Teeth (unfulfilled volatility points)
    teeth: list[MACDTooth] = field(default_factory=list)
    nearest_resistance: float | None = None   # nearest tooth above current
    nearest_support: float | None = None      # nearest tooth below current
    resistance_impact_count: int = 0          # how many touches before break expected
    support_impact_count: int = 0

    # Cross signals (only informational — must combine with macro)
    cross_event: str = "none"  # "golden_cross" | "death_cross" | "none"
    cross_with_macro: bool = False  # True if cross aligns with macro scenario

    # Divergence
    divergence: str = "none"  # "bullish_div" | "bearish_div" | "none"


def analyze(
    closes: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
    history_bars: int = 100,
    cluster_pct: float = 0.0015,    # cluster teeth within 0.15% of each other
    macro_scenario: str = "indefinido",
) -> MACDAnalysis:
    """
    Full MACD analysis with teeth detection.

    Args:
        closes:         closing price series
        history_bars:   bars to scan for teeth (extended chart view)
        cluster_pct:    group teeth within this % of each other
        macro_scenario: 'alta' | 'baixa' | 'indefinido' — for cross validation
    """
    if len(closes) < slow + signal_period + 2:
        return MACDAnalysis(0.0, 0.0, "flat", "flat")

    # Compute MACD
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

    curr_macd = float(macd_line.iloc[-1])
    curr_signal = float(signal_line.iloc[-1])
    prev_macd = float(macd_line.iloc[-2])
    prev_signal = float(signal_line.iloc[-2])

    # Direction
    if curr_macd > curr_signal:
        direction = "bullish"
    elif curr_macd < curr_signal:
        direction = "bearish"
    else:
        direction = "flat"

    # Momentum (is the MACD line accelerating or decelerating?)
    macd_delta = curr_macd - prev_macd
    prev_delta = prev_macd - float(macd_line.iloc[-3]) if len(macd_line) > 2 else 0.0
    if abs(macd_delta) > abs(prev_delta) * 1.05:
        momentum = "accelerating"
    elif abs(macd_delta) < abs(prev_delta) * 0.95:
        momentum = "decelerating"
    else:
        momentum = "flat"

    # Detect cross event
    cross_event = "none"
    if prev_macd <= prev_signal and curr_macd > curr_signal:
        cross_event = "golden_cross"
    elif prev_macd >= prev_signal and curr_macd < curr_signal:
        cross_event = "death_cross"

    # Cross aligns with macro only if both agree
    cross_with_macro = (
        (cross_event == "golden_cross" and macro_scenario == "alta") or
        (cross_event == "death_cross" and macro_scenario == "baixa")
    )

    # Find teeth on extended history
    scan_series = macd_line.iloc[-history_bars:]
    raw_teeth = _find_all_teeth(scan_series)

    # Cluster nearby teeth (group within cluster_pct)
    clustered = _cluster_teeth(raw_teeth, cluster_pct)

    # Mark which are fulfilled (current price already past them)
    current_price = float(closes.iloc[-1])
    for tooth in clustered:
        # Approximate price level from MACD value relative to current
        tooth.fulfilled = _is_fulfilled(tooth, macd_line, closes)

    unfulfilled = [t for t in clustered if not t.fulfilled]

    # Find nearest resistance (above) and support (below) teeth
    above = [t for t in unfulfilled if t.macd_value > curr_macd]
    below = [t for t in unfulfilled if t.macd_value < curr_macd]

    nearest_resistance = min(above, key=lambda t: t.macd_value, default=None)
    nearest_support = max(below, key=lambda t: t.macd_value, default=None)

    # Divergence: price making new high/low but MACD not confirming
    divergence = _detect_divergence(closes, macd_line, lookback=20)

    return MACDAnalysis(
        macd_line=round(curr_macd, 6),
        signal_line=round(curr_signal, 6),
        direction=direction,
        momentum=momentum,
        teeth=unfulfilled[:10],   # keep last 10 unfulfilled teeth
        nearest_resistance=nearest_resistance.macd_value if nearest_resistance else None,
        nearest_support=nearest_support.macd_value if nearest_support else None,
        resistance_impact_count=nearest_resistance.impact_count if nearest_resistance else 0,
        support_impact_count=nearest_support.impact_count if nearest_support else 0,
        cross_event=cross_event,
        cross_with_macro=cross_with_macro,
        divergence=divergence,
    )


def _find_all_teeth(series: pd.Series) -> list[MACDTooth]:
    """Find all local peaks and troughs in the MACD series."""
    values = series.values
    teeth = []
    for i in range(1, len(values) - 1):
        p, c, n = values[i - 1], values[i], values[i + 1]
        if c > p and c > n:
            teeth.append(MACDTooth(float(c), i, "peak"))
        elif c < p and c < n:
            teeth.append(MACDTooth(float(c), i, "trough"))
    return teeth


def _cluster_teeth(teeth: list[MACDTooth], cluster_pct: float) -> list[MACDTooth]:
    """
    Group teeth that are within cluster_pct of each other.
    The impact_count of a clustered tooth = number of teeth in the cluster.
    """
    if not teeth:
        return []
    clustered = []
    used = [False] * len(teeth)
    for i, t in enumerate(teeth):
        if used[i]:
            continue
        group = [t]
        used[i] = True
        for j, other in enumerate(teeth):
            if used[j] or i == j:
                continue
            if t.tooth_type == other.tooth_type:
                ref = abs(t.macd_value) if t.macd_value != 0 else 1e-10
                if abs(t.macd_value - other.macd_value) / ref <= cluster_pct:
                    group.append(other)
                    used[j] = True
        representative = max(group, key=lambda x: abs(x.macd_value))
        representative.impact_count = len(group)
        clustered.append(representative)
    return sorted(clustered, key=lambda t: t.macd_value)


def _is_fulfilled(tooth: MACDTooth, macd_line: pd.Series, closes: pd.Series) -> bool:
    """
    A tooth is considered fulfilled if the MACD line has crossed through it
    in subsequent bars (the market visited and passed that volatility level).
    """
    if tooth.bar_index >= len(macd_line) - 1:
        return False
    subsequent = macd_line.values[tooth.bar_index + 1:]
    if tooth.tooth_type == "peak":
        return bool(np.any(subsequent > tooth.macd_value))
    else:
        return bool(np.any(subsequent < tooth.macd_value))


def _detect_divergence(closes: pd.Series, macd_line: pd.Series, lookback: int = 20) -> str:
    """
    Detect bullish or bearish divergence between price and MACD.
    Bullish: price makes lower low, MACD makes higher low -> potential reversal up
    Bearish: price makes higher high, MACD makes lower high -> potential reversal down
    """
    if len(closes) < lookback:
        return "none"
    price_slice = closes.iloc[-lookback:]
    macd_slice = macd_line.iloc[-lookback:]

    price_min_idx = price_slice.idxmin()
    price_max_idx = price_slice.idxmax()
    macd_at_price_min = float(macd_line.loc[price_min_idx])
    macd_at_price_max = float(macd_line.loc[price_max_idx])

    curr_price = float(closes.iloc[-1])
    curr_macd = float(macd_line.iloc[-1])

    # Bullish divergence: price lower but MACD higher (at lows)
    if curr_price < float(price_slice.min()) * 1.001:
        if curr_macd > macd_at_price_min:
            return "bullish_div"

    # Bearish divergence: price higher but MACD lower (at highs)
    if curr_price > float(price_slice.max()) * 0.999:
        if curr_macd < macd_at_price_max:
            return "bearish_div"

    return "none"


def teeth_to_price_levels(
    teeth: list[MACDTooth],
    current_price: float,
    current_macd: float,
    price_macd_ratio: float = 1.0,
) -> list[dict]:
    """
    Convert MACD tooth values to approximate price levels.
    Used for chart projection in the prep workflow.

    price_macd_ratio: rough ratio of price_range / macd_range over N bars
    """
    levels = []
    for tooth in teeth:
        delta_macd = tooth.macd_value - current_macd
        approx_price = current_price + delta_macd * price_macd_ratio
        levels.append({
            "macd_value": round(tooth.macd_value, 6),
            "approx_price": round(approx_price, 5),
            "type": tooth.tooth_type,
            "impact_count": tooth.impact_count,
            "resistance_strength": "high" if tooth.impact_count >= 3 else
                                   "medium" if tooth.impact_count == 2 else "low",
        })
    return sorted(levels, key=lambda x: x["approx_price"])
