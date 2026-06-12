from __future__ import annotations
"""
OrderBlockDetector — last opposite candle before an impulsive displacement.

Direction convention:
  bullish OB = last bearish candle before a bullish impulse → support zone
  bearish OB = last bullish candle before a bearish impulse → resistance zone

Displacement threshold: candle body >= ATR × displacement_atr_mult (default 0.7).
Mitigation: any subsequent bar whose range overlaps the OB body cancels it.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from .structure import MarketStructure


@dataclass
class OrderBlock:
    top: float
    bottom: float
    direction: str      # "bullish" = support zone | "bearish" = resistance zone
    index: int
    strength: float     # OB body size / ATR
    mitigated: bool     # True once price re-enters the zone after displacement


class OrderBlockDetector:
    def __init__(
        self,
        lookback: int = 50,
        displacement_atr_mult: float = 0.7,
    ):
        self.lookback = lookback
        self.displacement_atr_mult = displacement_atr_mult

    def detect(
        self,
        df: pd.DataFrame,
        structure: MarketStructure,
        atr: float,
    ) -> list[OrderBlock]:
        if atr <= 0 or df is None or len(df) < 3:
            return []

        opens  = df["open"].to_numpy(dtype=float)
        highs  = df["high"].to_numpy(dtype=float)
        lows   = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)

        n = len(closes)
        start = max(0, n - self.lookback)
        thresh = atr * self.displacement_atr_mult
        seen: set[int] = set()
        obs: list[OrderBlock] = []

        for i in range(start + 1, n):
            body = closes[i] - opens[i]
            if abs(body) < thresh:
                continue
            disp_dir = "bullish" if body > 0 else "bearish"

            # Walk backward for the last candle of the opposite color
            for j in range(i - 1, max(start - 1, 0), -1):
                if j in seen:
                    continue
                prev_body = closes[j] - opens[j]
                if prev_body == 0.0:
                    continue
                is_opposite = (
                    (disp_dir == "bullish" and prev_body < 0) or
                    (disp_dir == "bearish" and prev_body > 0)
                )
                if not is_opposite:
                    continue

                top    = round(float(max(opens[j], closes[j])), 5)
                bottom = round(float(min(opens[j], closes[j])), 5)
                strength = round(abs(prev_body) / atr, 3)

                mitigated = any(
                    lows[k] <= top and highs[k] >= bottom
                    for k in range(i + 1, n)
                )

                seen.add(j)
                obs.append(OrderBlock(
                    top=top, bottom=bottom, direction=disp_dir,
                    index=j, strength=strength, mitigated=mitigated,
                ))
                break

        return obs
