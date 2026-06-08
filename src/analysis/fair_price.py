from __future__ import annotations
"""
Fair Price Engine — calculates fair price and volatility channels per asset.

Fair Price = previous_close * (1 + reference_var_pct)
  reference = DXY variation % (default) or VIX variation %

Delta (volatility) = abs(fair_price * reference_var_pct)
Channels = Fair Price +/- Delta (N levels via Fibonacci ratios)

The result is stored in MacroContext.fair_prices[symbol].
"""
from dataclasses import dataclass

import numpy as np


# Fibonacci ratios used to project volatility channels
_FIB_RATIOS = [0.236, 0.382, 0.500, 0.618, 0.786, 1.000, 1.272, 1.618]


@dataclass
class FairPriceResult:
    symbol: str
    prev_close: float
    reference_var_pct: float    # DXY or VIX variation %
    fair_price: float
    delta: float                # absolute volatility projection
    channels_up: list[float]    # levels above fair price (Fibonacci)
    channels_down: list[float]  # levels below fair price (Fibonacci)
    # Bollinger-based max/min for the day (set externally after BB calc)
    bb_max: float = 0.0
    bb_min: float = 0.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "prev_close": round(self.prev_close, 5),
            "fair_price": round(self.fair_price, 5),
            "delta": round(self.delta, 5),
            "reference_var_pct": round(self.reference_var_pct * 100, 4),
            "channels_up": [round(c, 5) for c in self.channels_up],
            "channels_down": [round(c, 5) for c in self.channels_down],
            "bb_max": round(self.bb_max, 5),
            "bb_min": round(self.bb_min, 5),
        }


def calculate(
    symbol: str,
    prev_close: float,
    dxy_change_pct: float,
    vix_change_pct: float = 0.0,
    use_vix: bool = False,
) -> FairPriceResult:
    """
    Calculate fair price and Fibonacci volatility channels for one asset.

    Args:
        symbol:          instrument ticker
        prev_close:      previous session closing price
        dxy_change_pct:  DXY percentage variation (e.g. 0.005 = +0.5%)
        vix_change_pct:  VIX percentage variation
        use_vix:         if True, use VIX instead of DXY as reference
    """
    ref_pct = vix_change_pct if use_vix else dxy_change_pct
    fair_price = prev_close * (1.0 + ref_pct)
    delta = abs(fair_price * ref_pct)

    channels_up = [fair_price + delta * r for r in _FIB_RATIOS]
    channels_down = [fair_price - delta * r for r in _FIB_RATIOS]

    return FairPriceResult(
        symbol=symbol,
        prev_close=prev_close,
        reference_var_pct=ref_pct,
        fair_price=fair_price,
        delta=delta,
        channels_up=channels_up,
        channels_down=channels_down,
    )


def update_bb_channels(result: FairPriceResult, bb_upper: float, bb_lower: float) -> FairPriceResult:
    """Inject Bollinger Band max/min into the FairPriceResult."""
    result.bb_max = bb_upper
    result.bb_min = bb_lower
    return result


def nearest_channel(result: FairPriceResult, current_price: float) -> dict:
    """
    Find nearest channel levels above and below current price.
    Useful for identifying where the market may 'go to'.
    """
    all_up = [c for c in result.channels_up if c > current_price]
    all_down = [c for c in result.channels_down if c < current_price]
    return {
        "next_resistance": min(all_up) if all_up else result.channels_up[-1],
        "next_support": max(all_down) if all_down else result.channels_down[-1],
        "within_channel": result.bb_min <= current_price <= result.bb_max,
        "distance_to_resistance_pct": (
            round((min(all_up) - current_price) / current_price * 100, 4)
            if all_up else 0.0
        ),
        "distance_to_support_pct": (
            round((current_price - max(all_down)) / current_price * 100, 4)
            if all_down else 0.0
        ),
    }
