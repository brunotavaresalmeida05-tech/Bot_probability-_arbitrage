from __future__ import annotations
"""
StructureAnalyzer — Swing detection, BOS/ChoCh classification.

Design principles:
  - Swing confirmed with swing_lookback=3 bars each side.
  - Too-close swings deduplicated: keep the more extreme of the two.
  - BOS = close breaks prior swing level in the SAME direction as trend (continuation).
  - ChoCh = close breaks prior swing level AGAINST the current trend (reversal).
  - ChoCh overrides HH/HL structure because it is a stronger structural signal.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class SwingPoint:
    index: int
    price: float
    kind: str           # "high" | "low"
    bar_time: object = None


@dataclass
class MarketStructure:
    trend: str                  # "bullish" | "bearish" | "ranging" | "uncertain"
    last_event: str | None      # "BOS_bull" | "BOS_bear" | "ChoCh_bull" | "ChoCh_bear" | None
    last_event_level: float | None
    last_event_bars_ago: int | None
    hh_hl: bool                 # True → HH + HL pattern (bullish structure)
    lh_ll: bool                 # True → LH + LL pattern (bearish structure)
    swing_highs: list[SwingPoint] = field(default_factory=list)
    swing_lows: list[SwingPoint] = field(default_factory=list)
    sufficient_data: bool = False
    swing_count: int = 0


class StructureAnalyzer:
    def __init__(
        self,
        swing_lookback: int = 3,
        max_swings_tracked: int = 10,
        bos_confirmation_atr: float = 0.10,
        min_swing_distance_bars: int = 3,
    ):
        self.swing_lookback = swing_lookback
        self.max_swings_tracked = max_swings_tracked
        self.bos_confirmation_atr = bos_confirmation_atr
        self.min_swing_distance_bars = min_swing_distance_bars

    # ── Public entry point ────────────────────────────────────────────────────

    def analyze(self, df: pd.DataFrame, atr: float = 0.0) -> MarketStructure:
        min_bars = self.swing_lookback * 2 + 2
        if df is None or len(df) < min_bars:
            return MarketStructure(
                trend="uncertain", last_event=None, last_event_level=None,
                last_event_bars_ago=None, hh_hl=False, lh_ll=False,
                sufficient_data=False, swing_count=0,
            )

        highs  = df["high"].to_numpy(dtype=float)
        lows   = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        times  = df.index.tolist() if hasattr(df.index, "tolist") else list(range(len(df)))

        swing_highs = self._detect_swings(highs, kind="high", times=times)
        swing_lows  = self._detect_swings(lows,  kind="low",  times=times)

        # Keep only the most recent N swings
        swing_highs = swing_highs[-self.max_swings_tracked:]
        swing_lows  = swing_lows[-self.max_swings_tracked:]

        swing_count = len(swing_highs) + len(swing_lows)
        sufficient  = swing_count >= 4

        hh_hl = self._is_hh_hl(swing_highs, swing_lows)
        lh_ll = self._is_lh_ll(swing_highs, swing_lows)

        last_event, last_level, last_bars_ago = self._detect_last_event(
            highs, lows, closes, swing_highs, swing_lows, atr, n_bars=len(df)
        )

        trend = self._classify_trend(hh_hl, lh_ll, last_event)

        return MarketStructure(
            trend=trend,
            last_event=last_event,
            last_event_level=last_level,
            last_event_bars_ago=last_bars_ago,
            hh_hl=hh_hl,
            lh_ll=lh_ll,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
            sufficient_data=sufficient,
            swing_count=swing_count,
        )

    # ── Public utilities (used by OrderBlocks and Liquidity detectors) ────────

    def get_last_swing_high(self, structure: MarketStructure) -> SwingPoint | None:
        return structure.swing_highs[-1] if structure.swing_highs else None

    def get_last_swing_low(self, structure: MarketStructure) -> SwingPoint | None:
        return structure.swing_lows[-1] if structure.swing_lows else None

    def get_recent_swing_highs(self, structure: MarketStructure, n: int = 5) -> list[SwingPoint]:
        return structure.swing_highs[-n:]

    def get_recent_swing_lows(self, structure: MarketStructure, n: int = 5) -> list[SwingPoint]:
        return structure.swing_lows[-n:]

    # ── Private ───────────────────────────────────────────────────────────────

    def _detect_swings(
        self, arr: np.ndarray, kind: str, times: list
    ) -> list[SwingPoint]:
        n = arr.shape[0]
        lb = self.swing_lookback
        raw: list[SwingPoint] = []

        for i in range(lb, n - lb):
            window_left  = arr[i - lb:i]
            window_right = arr[i + 1:i + lb + 1]
            if kind == "high":
                confirmed = arr[i] >= window_left.max() and arr[i] >= window_right.max()
            else:
                confirmed = arr[i] <= window_left.min() and arr[i] <= window_right.min()
            if confirmed:
                raw.append(SwingPoint(index=i, price=float(arr[i]), kind=kind, bar_time=times[i]))

        return self._deduplicate_swings(raw, kind)

    def _deduplicate_swings(self, swings: list[SwingPoint], kind: str) -> list[SwingPoint]:
        if not swings:
            return swings
        result: list[SwingPoint] = [swings[0]]
        for sp in swings[1:]:
            last = result[-1]
            if sp.index - last.index < self.min_swing_distance_bars:
                # Keep the more extreme of the two
                if kind == "high" and sp.price > last.price:
                    result[-1] = sp
                elif kind == "low" and sp.price < last.price:
                    result[-1] = sp
            else:
                result.append(sp)
        return result

    def _is_hh_hl(self, highs: list[SwingPoint], lows: list[SwingPoint]) -> bool:
        if len(highs) < 2 or len(lows) < 2:
            return False
        hh = highs[-1].price > highs[-2].price
        hl = lows[-1].price > lows[-2].price
        return hh and hl

    def _is_lh_ll(self, highs: list[SwingPoint], lows: list[SwingPoint]) -> bool:
        if len(highs) < 2 or len(lows) < 2:
            return False
        lh = highs[-1].price < highs[-2].price
        ll = lows[-1].price < lows[-2].price
        return lh and ll

    def _detect_last_event(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        atr: float,
        n_bars: int,
    ) -> tuple[str | None, float | None, int | None]:
        """
        Scan all closes for the LAST structural break.
        BOS vs ChoCh is determined by context at the time of the break:
          - Breaking a swing high that was an HH (prev SH < this SH) → BOS_bull (trend continuation)
          - Breaking a swing high that was an LH (prev SH > this SH) → ChoCh_bull (structure reversal)
          - Breaking a swing low  that was an LL (prev SL > this SL) → BOS_bear
          - Breaking a swing low  that was an HL (prev SL < this SL) → ChoCh_bear
        """
        events: list[tuple[int, str, float]] = []  # (bar_index, event_type, level)
        broken_sh: set[int] = set()
        broken_sl: set[int] = set()

        for i in range(1, n_bars):
            # --- Check breaks above swing highs ---
            for idx, sh in enumerate(swing_highs):
                if sh.index >= i or sh.index in broken_sh:
                    continue
                if closes[i] > sh.price:
                    prev_shs = [s for s in swing_highs if s.index < sh.index]
                    if prev_shs and sh.price > prev_shs[-1].price:
                        kind = "BOS_bull"
                    else:
                        kind = "ChoCh_bull"
                    events.append((i, kind, sh.price))
                    broken_sh.add(sh.index)

            # --- Check breaks below swing lows ---
            for sl in swing_lows:
                if sl.index >= i or sl.index in broken_sl:
                    continue
                if closes[i] < sl.price:
                    prev_sls = [s for s in swing_lows if s.index < sl.index]
                    if prev_sls and sl.price < prev_sls[-1].price:
                        kind = "BOS_bear"
                    else:
                        kind = "ChoCh_bear"
                    events.append((i, kind, sl.price))
                    broken_sl.add(sl.index)

        if not events:
            return None, None, None

        last_bar, last_kind, last_level = events[-1]
        bars_ago = n_bars - 1 - last_bar
        return last_kind, round(last_level, 5), bars_ago

    def _classify_trend(self, hh_hl: bool, lh_ll: bool, last_event: str | None) -> str:
        # ChoCh overrides HH/HL because it signals a stronger change
        if last_event == "ChoCh_bull":
            return "bullish"
        if last_event == "ChoCh_bear":
            return "bearish"
        if hh_hl:
            return "bullish"
        if lh_ll:
            return "bearish"
        if last_event == "BOS_bull":
            return "bullish"
        if last_event == "BOS_bear":
            return "bearish"
        return "ranging"
