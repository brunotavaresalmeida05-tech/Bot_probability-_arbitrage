from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class ADXResult:
    adx: pd.Series
    plus_di: pd.Series
    minus_di: pd.Series
    regime: pd.Series       # "strong_up" | "strong_down" | "weak" | "transition"
    is_trending: pd.Series  # ADX >= strong_threshold
    current_adx: float
    current_plus_di: float
    current_minus_di: float


class ADXRegime:
    """
    ADX + DI+/DI- com classificador de regime.
    Mede FORÇA de tendência, não direcção.
    """

    def __init__(
        self,
        period: int = 14,
        strong_threshold: float = 25.0,
        weak_threshold: float = 20.0,
    ):
        self.period = period
        self.strong_threshold = strong_threshold
        self.weak_threshold = weak_threshold

    def compute(self, df: pd.DataFrame) -> ADXResult:
        high  = df["high"]
        low   = df["low"]
        close = df["close"]
        n     = len(df)

        # True Range
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)

        # Directional Movement
        up_move   = high - high.shift(1)
        down_move = low.shift(1) - low

        plus_dm  = np.where((up_move > down_move)   & (up_move > 0),   up_move,   0.0)
        minus_dm = np.where((down_move > up_move)   & (down_move > 0), down_move, 0.0)

        plus_dm  = pd.Series(plus_dm,  index=df.index, dtype=float)
        minus_dm = pd.Series(minus_dm, index=df.index, dtype=float)

        # Wilder smoothing (EMA with alpha = 1/period)
        def _wilder(s: pd.Series) -> pd.Series:
            return s.ewm(alpha=1.0 / self.period, adjust=False).mean()

        atr_s      = _wilder(tr)
        plus_dm_s  = _wilder(plus_dm)
        minus_dm_s = _wilder(minus_dm)

        plus_di  = 100.0 * plus_dm_s  / atr_s.replace(0, np.nan)
        minus_di = 100.0 * minus_dm_s / atr_s.replace(0, np.nan)

        dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx = _wilder(dx)

        # Clip negatives from floating point noise
        plus_di  = plus_di.clip(lower=0)
        minus_di = minus_di.clip(lower=0)
        adx      = adx.clip(lower=0)

        # Regime classification
        regime = pd.Series("transition", index=df.index, dtype=object)
        regime[adx < self.weak_threshold] = "weak"
        regime[(adx >= self.strong_threshold) & (plus_di >= minus_di)] = "strong_up"
        regime[(adx >= self.strong_threshold) & (minus_di >  plus_di)] = "strong_down"
        # NaN rows stay as transition
        regime[adx.isna()] = pd.NA

        is_trending = adx >= self.strong_threshold

        return ADXResult(
            adx=adx, plus_di=plus_di, minus_di=minus_di,
            regime=regime, is_trending=is_trending,
            current_adx=float(adx.iloc[-1])      if not adx.isna().iloc[-1]      else 0.0,
            current_plus_di=float(plus_di.iloc[-1])  if not plus_di.isna().iloc[-1]  else 0.0,
            current_minus_di=float(minus_di.iloc[-1]) if not minus_di.isna().iloc[-1] else 0.0,
        )
