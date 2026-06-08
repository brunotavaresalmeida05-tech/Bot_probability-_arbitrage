from __future__ import annotations
"""
Bollinger Analyzer — V9

Advanced Bollinger Band analysis for volatility micro-structure:

Key concepts from trading methodology:
  1. Squeeze: bands narrow → low volatility → breakout imminent
     "Quando o mercado está com baixa volatilidade, as bandas sinalizam imediatamente,
      pois elas estreitam. Quando o mercado está com alta volatilidade, as bandas se
      distanciam umas das outras."

  2. Directional expansion: which band opens more = direction signal
     "Essa retomada de volatilidade tem relação com o contexto macro e pode ser
      verificada no gráfico com a abertura das bandas, fazendo com que a expansão
      de uma das bandas seja maior."

  3. BB points (unfulfilled): like MACD teeth, BB extremes left unvisited
     "Os pontos deixados pelas Bandas de Bollinger também tendem a ser cumpridos."

  4. Walking the band: price stays near upper/lower BB = strong trend
     "Caminhando pela banda" = trend continuation signal

  5. BB10 gives daily max/min projections = channel for the day
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BBUnfulfilledPoint:
    price: float        # BB upper or lower extreme that was left unvisited
    side: str           # "upper" | "lower"
    bar_ago: int        # how many bars ago this point was set
    fulfilled: bool = False


@dataclass
class BollingerAnalysis:
    # Current state
    upper: float
    middle: float
    lower: float
    width: float
    width_pct: float

    # Squeeze
    is_squeeze: bool = False        # True when width < squeeze_threshold
    squeeze_percentile: float = 0.0 # Where current width sits vs history (0-100)
    breakout_imminent: bool = False # squeeze AND starting to expand

    # Expansion
    state: str = "neutral"          # "expanding_up" | "expanding_down" | "contracting" | "neutral"
    expansion_asymmetry: float = 0.0  # positive = upper expanding more, negative = lower

    # Walking the band
    walking_upper: bool = False     # price near upper band for N bars
    walking_lower: bool = False     # price near lower band for N bars
    walk_bars: int = 0             # how many bars walking

    # Unfulfilled points (BB teeth)
    unfulfilled_upper: list[BBUnfulfilledPoint] = field(default_factory=list)
    unfulfilled_lower: list[BBUnfulfilledPoint] = field(default_factory=list)

    # Daily channel (BB10 max/min)
    day_max: float = 0.0            # projected session high (upper × 1.0)
    day_min: float = 0.0            # projected session low (lower × 1.0)

    # Signal
    signal: str = "neutral"         # "buy_setup" | "sell_setup" | "neutral" | "squeeze_watch"


def analyze(
    closes: pd.Series,
    highs: pd.Series,
    lows: pd.Series,
    period: int = 10,
    std_mult: float = 2.0,
    squeeze_pct_threshold: float = 25.0,  # below 25th percentile of width history = squeeze
    walk_min_bars: int = 3,
    history_bars: int = 50,
) -> BollingerAnalysis:
    """
    Full Bollinger Band analysis.

    Args:
        closes:                 price close series
        period:                 BB period (10 per methodology)
        std_mult:               standard deviation multiplier
        squeeze_pct_threshold:  below this percentile = squeeze
        walk_min_bars:          min bars near band to classify as "walking"
    """
    if len(closes) < period + 1:
        mid = float(closes.iloc[-1])
        return BollingerAnalysis(upper=mid, middle=mid, lower=mid, width=0.0, width_pct=0.0)

    rolling_mean = closes.rolling(period).mean()
    rolling_std = closes.rolling(period).std()

    upper_series = rolling_mean + std_mult * rolling_std
    lower_series = rolling_mean - std_mult * rolling_std
    width_series = upper_series - lower_series

    curr_upper = float(upper_series.iloc[-1])
    curr_mid   = float(rolling_mean.iloc[-1])
    curr_lower = float(lower_series.iloc[-1])
    curr_width = float(width_series.iloc[-1])
    prev_width = float(width_series.iloc[-2])
    curr_price = float(closes.iloc[-1])

    width_pct = curr_width / curr_mid if curr_mid > 0 else 0.0

    # Historical width for percentile calculation
    hist_width = width_series.iloc[-history_bars:].dropna()
    squeeze_percentile = float(
        np.searchsorted(np.sort(hist_width.values), curr_width) / len(hist_width) * 100
    ) if len(hist_width) > 0 else 50.0

    is_squeeze = squeeze_percentile <= squeeze_pct_threshold
    breakout_imminent = is_squeeze and curr_width > prev_width * 1.01

    # Expansion direction
    prev_upper = float(upper_series.iloc[-2])
    prev_lower = float(lower_series.iloc[-2])
    upper_expansion = curr_upper - prev_upper
    lower_contraction = prev_lower - curr_lower   # positive if lower band moving down

    if curr_width > prev_width * 1.02:
        if upper_expansion > lower_contraction * 1.2:
            state = "expanding_up"
        elif lower_contraction > upper_expansion * 1.2:
            state = "expanding_down"
        else:
            state = "expanding"
    elif curr_width < prev_width * 0.98:
        state = "contracting"
    else:
        state = "neutral"

    expansion_asymmetry = round(upper_expansion - lower_contraction, 6)

    # Walking the band
    walk_upper_count = 0
    walk_lower_count = 0
    for i in range(1, min(walk_min_bars + 3, len(closes))):
        c = float(closes.iloc[-i])
        u = float(upper_series.iloc[-i])
        l = float(lower_series.iloc[-i])
        mid = float(rolling_mean.iloc[-i])
        if c >= mid + 0.6 * (u - mid):
            walk_upper_count += 1
        if c <= mid - 0.6 * (mid - l):
            walk_lower_count += 1

    walking_upper = walk_upper_count >= walk_min_bars
    walking_lower = walk_lower_count >= walk_min_bars
    walk_bars = walk_upper_count if walking_upper else (walk_lower_count if walking_lower else 0)

    # Unfulfilled BB points (extremes price didn't reach)
    unf_upper, unf_lower = _find_unfulfilled_points(
        closes, upper_series, lower_series, highs, lows, lookback=history_bars
    )

    # Daily channel
    day_max = curr_upper
    day_min = curr_lower

    # Final signal
    signal = _compute_signal(
        is_squeeze, breakout_imminent, state, walking_upper, walking_lower,
        curr_price, curr_upper, curr_lower, curr_mid, expansion_asymmetry,
    )

    return BollingerAnalysis(
        upper=round(curr_upper, 5),
        middle=round(curr_mid, 5),
        lower=round(curr_lower, 5),
        width=round(curr_width, 5),
        width_pct=round(width_pct, 6),
        is_squeeze=is_squeeze,
        squeeze_percentile=round(squeeze_percentile, 1),
        breakout_imminent=breakout_imminent,
        state=state,
        expansion_asymmetry=round(expansion_asymmetry, 6),
        walking_upper=walking_upper,
        walking_lower=walking_lower,
        walk_bars=walk_bars,
        unfulfilled_upper=unf_upper[:5],
        unfulfilled_lower=unf_lower[:5],
        day_max=round(day_max, 5),
        day_min=round(day_min, 5),
        signal=signal,
    )


def _find_unfulfilled_points(
    closes: pd.Series,
    upper: pd.Series,
    lower: pd.Series,
    highs: pd.Series,
    lows: pd.Series,
    lookback: int,
) -> tuple[list[BBUnfulfilledPoint], list[BBUnfulfilledPoint]]:
    """
    Find BB extremes (upper/lower) that price never reached in subsequent bars.
    These are unfulfilled volatility levels the market may return to.
    """
    unf_upper = []
    unf_lower = []
    n = min(lookback, len(closes) - 1)

    for i in range(n, 0, -1):
        idx = -i
        u_val = float(upper.iloc[idx])
        l_val = float(lower.iloc[idx])
        subsequent_highs = highs.iloc[idx + 1:]
        subsequent_lows = lows.iloc[idx + 1:]

        # Upper point unfulfilled if no subsequent high reached it
        if len(subsequent_highs) > 0 and float(subsequent_highs.max()) < u_val:
            unf_upper.append(BBUnfulfilledPoint(price=u_val, side="upper", bar_ago=i))

        # Lower point unfulfilled if no subsequent low reached it
        if len(subsequent_lows) > 0 and float(subsequent_lows.min()) > l_val:
            unf_lower.append(BBUnfulfilledPoint(price=l_val, side="lower", bar_ago=i))

    # Keep only the most recent (closest to current price)
    curr_price = float(closes.iloc[-1])
    unf_upper.sort(key=lambda p: abs(p.price - curr_price))
    unf_lower.sort(key=lambda p: abs(p.price - curr_price))
    return unf_upper, unf_lower


def _compute_signal(
    is_squeeze, breakout_imminent, state, walking_upper, walking_lower,
    price, upper, lower, mid, asymmetry,
) -> str:
    if is_squeeze and not breakout_imminent:
        return "squeeze_watch"
    if breakout_imminent:
        if asymmetry > 0:
            return "buy_setup"   # upper band expanding more = upside breakout
        elif asymmetry < 0:
            return "sell_setup"
        return "squeeze_watch"
    if walking_upper and state in ("expanding_up", "neutral"):
        return "buy_setup"
    if walking_lower and state in ("expanding_down", "neutral"):
        return "sell_setup"
    near_upper = price >= mid + 0.7 * (upper - mid)
    near_lower = price <= mid - 0.7 * (mid - lower)
    if near_lower and state == "expanding_down":
        return "sell_setup"
    if near_upper and state == "expanding_up":
        return "buy_setup"
    return "neutral"
