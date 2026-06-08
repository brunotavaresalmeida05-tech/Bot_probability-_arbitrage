from __future__ import annotations
"""
Volatility Channels — V9

Generates the 'price sandwich' — the range where the asset
is expected to work during the session.

Method:
  1. Take the largest Bollinger Band (10 periods) width of the previous session
  2. Apply Fibonacci projections from the Fair Price reference point
  3. These channels are memory points — the market tends to 'visit' them

The channels are computed once at session open and refreshed intraday.
"""
from dataclasses import dataclass, field

import numpy as np

# Extended Fibonacci levels (expansion ratios)
_FIB_EXPANSION = [0.236, 0.382, 0.500, 0.618, 0.786, 1.000, 1.272, 1.618, 2.000, 2.618]


@dataclass
class VolatilityChannel:
    fair_price: float
    bb_width: float                 # BB10 amplitude used as base unit
    channels_up: list[float] = field(default_factory=list)
    channels_down: list[float] = field(default_factory=list)
    max_extrema: float = 0.0        # 1.618× projection (daily potential max)
    min_extrema: float = 0.0        # 1.618× projection (daily potential min)
    daily_range_pct: float = 0.0    # expected daily range as % of fair price

    def nearest_above(self, price: float) -> float:
        above = [c for c in self.channels_up if c > price]
        return min(above) if above else self.max_extrema

    def nearest_below(self, price: float) -> float:
        below = [c for c in self.channels_down if c < price]
        return max(below) if below else self.min_extrema

    def price_position(self, price: float) -> str:
        """Describe where the price is within the channel structure."""
        mid = (self.max_extrema + self.min_extrema) / 2
        q = (self.max_extrema - self.min_extrema) / 4
        if price >= self.max_extrema * 0.99:
            return "at_max_extrema"
        elif price >= mid + q:
            return "upper_zone"
        elif price >= mid - q:
            return "mid_zone"
        elif price >= self.min_extrema * 1.01:
            return "lower_zone"
        else:
            return "at_min_extrema"

    def to_dict(self) -> dict:
        return {
            "fair_price": round(self.fair_price, 5),
            "bb_width": round(self.bb_width, 5),
            "max_extrema": round(self.max_extrema, 5),
            "min_extrema": round(self.min_extrema, 5),
            "channels_up": [round(c, 5) for c in self.channels_up],
            "channels_down": [round(c, 5) for c in self.channels_down],
            "daily_range_pct": round(self.daily_range_pct * 100, 4),
        }


def compute(
    fair_price: float,
    bb_width: float,
    additional_fib: list[float] | None = None,
) -> VolatilityChannel:
    """
    Compute volatility channels from fair price and Bollinger Band width.

    Args:
        fair_price: reference price (from fair_price.py)
        bb_width:   largest BB10 band width of the previous or current session
        additional_fib: override Fibonacci levels if needed
    """
    levels = additional_fib or _FIB_EXPANSION
    channels_up = [fair_price + bb_width * lev for lev in levels]
    channels_down = [fair_price - bb_width * lev for lev in levels]

    # 1.618 level = max daily potential extrema
    idx_max = levels.index(1.618) if 1.618 in levels else -1
    max_e = channels_up[idx_max] if idx_max >= 0 else channels_up[-1]
    min_e = channels_down[idx_max] if idx_max >= 0 else channels_down[-1]

    daily_range_pct = (max_e - min_e) / fair_price if fair_price > 0 else 0.0

    return VolatilityChannel(
        fair_price=fair_price,
        bb_width=bb_width,
        channels_up=channels_up,
        channels_down=channels_down,
        max_extrema=max_e,
        min_extrema=min_e,
        daily_range_pct=daily_range_pct,
    )


def from_bb_series(
    closes: "pd.Series",
    fair_price: float,
    period: int = 10,
    std_mult: float = 2.0,
) -> VolatilityChannel:
    """
    Build channels directly from a price series (computes BB10 internally).
    """
    import pandas as pd
    mid = closes.rolling(period).mean().iloc[-1]
    std = closes.rolling(period).std().iloc[-1]
    bb_width = float(2 * std_mult * std)
    return compute(fair_price, bb_width)
