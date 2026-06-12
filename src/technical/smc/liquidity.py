from __future__ import annotations
"""
LiquiditySweepDetector — stop-hunt wicks beyond swing levels with recovery.

Bullish sweep: wick extends below a recent swing low but candle closes above it.
Bearish sweep: wick extends above a recent swing high but candle closes back below.

Uses StructureAnalyzer's public utilities (get_recent_swing_highs / lows)
instead of re-computing swings internally.

Minimum recovery: ATR × recovery_atr_mult so the candle actually reversed.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from .structure import MarketStructure, StructureAnalyzer


@dataclass
class LiquiditySweep:
    direction: str      # "bullish" (lows swept) | "bearish" (highs swept)
    level: float
    index: int


class LiquiditySweepDetector:
    def __init__(
        self,
        lookback: int = 60,
        recovery_atr_mult: float = 0.3,
        swing_window: int = 5,
    ):
        self.lookback = lookback
        self.recovery_atr_mult = recovery_atr_mult
        self.swing_window = swing_window

    def detect(
        self,
        df: pd.DataFrame,
        structure: MarketStructure,
        atr: float,
        analyzer: StructureAnalyzer | None = None,
    ) -> list[LiquiditySweep]:
        if df is None or len(df) < 3:
            return []

        highs  = df["high"].to_numpy(dtype=float)
        lows   = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        n = len(closes)
        start = max(0, n - self.lookback)
        min_recovery = atr * self.recovery_atr_mult if atr > 0 else 0.0

        # Get swing levels from structure (populated by StructureAnalyzer.analyze())
        _analyzer = analyzer or StructureAnalyzer()
        recent_sh = _analyzer.get_recent_swing_highs(structure, self.swing_window)
        recent_sl = _analyzer.get_recent_swing_lows(structure, self.swing_window)

        sh_levels = [(sp.index, sp.price) for sp in recent_sh]
        sl_levels = [(sp.index, sp.price) for sp in recent_sl]

        sweeps: list[LiquiditySweep] = []

        for i in range(start + 1, n):
            # Bullish sweep: wick below swing low, closes back above
            for sl_idx, level in sl_levels:
                if sl_idx >= i:
                    continue
                if lows[i] < level and closes[i] > level + min_recovery:
                    sweeps.append(LiquiditySweep(
                        direction="bullish",
                        level=round(float(level), 5),
                        index=i,
                    ))
                    break

            # Bearish sweep: wick above swing high, closes back below
            for sh_idx, level in sh_levels:
                if sh_idx >= i:
                    continue
                if highs[i] > level and closes[i] < level - min_recovery:
                    sweeps.append(LiquiditySweep(
                        direction="bearish",
                        level=round(float(level), 5),
                        index=i,
                    ))
                    break

        return sweeps
