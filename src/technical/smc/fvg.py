from __future__ import annotations
"""
FairValueGapDetector — 3-candle imbalances left by fast moves.

bullish FVG: candle[i].low > candle[i-2].high  (gap above i-2, below i)
bearish FVG: candle[i].high < candle[i-2].low  (gap below i-2, above i)

Filled when a subsequent bar's range overlaps the gap entirely.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class FairValueGap:
    top: float
    bottom: float
    direction: str      # "bullish" | "bearish"
    index: int
    filled: bool        # True once price re-enters the gap


class FairValueGapDetector:
    def __init__(self, lookback: int = 50):
        self.lookback = lookback

    def detect(self, df: pd.DataFrame) -> list[FairValueGap]:
        if df is None or len(df) < 3:
            return []

        highs = df["high"].to_numpy(dtype=float)
        lows  = df["low"].to_numpy(dtype=float)
        n = len(lows)
        start = max(2, n - self.lookback)
        fvgs: list[FairValueGap] = []

        for i in range(start, n):
            if lows[i] > highs[i - 2]:
                gap_top    = float(lows[i])
                gap_bottom = float(highs[i - 2])
                filled = any(
                    lows[k] <= gap_top and highs[k] >= gap_bottom
                    for k in range(i + 1, n)
                )
                fvgs.append(FairValueGap(
                    top=round(gap_top, 5), bottom=round(gap_bottom, 5),
                    direction="bullish", index=i, filled=filled,
                ))

            elif highs[i] < lows[i - 2]:
                gap_top    = float(lows[i - 2])
                gap_bottom = float(highs[i])
                filled = any(
                    lows[k] <= gap_top and highs[k] >= gap_bottom
                    for k in range(i + 1, n)
                )
                fvgs.append(FairValueGap(
                    top=round(gap_top, 5), bottom=round(gap_bottom, 5),
                    direction="bearish", index=i, filled=filled,
                ))

        return fvgs
