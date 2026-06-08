from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class StochRSIResult:
    k: pd.Series
    d: pd.Series
    long_trigger: pd.Series    # K cruzou de <20 para >=20
    short_trigger: pd.Series   # K cruzou de >80 para <=80
    is_oversold: pd.Series     # K < 20
    is_overbought: pd.Series   # K > 80
    current_k: float
    current_d: float


class StochRSI:
    """
    Stochastic RSI com parâmetros institucionais fixos.
    RSI period=14, Stoch period=14, K smooth=3, D smooth=3, applied to close.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        stoch_period: int = 14,
        k_smooth: int = 3,
        d_smooth: int = 3,
        oversold: float = 20.0,
        overbought: float = 80.0,
    ):
        self.rsi_period = rsi_period
        self.stoch_period = stoch_period
        self.k_smooth = k_smooth
        self.d_smooth = d_smooth
        self.oversold = oversold
        self.overbought = overbought

    def compute(self, df: pd.DataFrame) -> StochRSIResult:
        close = df["close"].copy().reset_index(drop=True)
        min_len = self.rsi_period + self.stoch_period + self.k_smooth + self.d_smooth
        n = len(close)

        nan_series = pd.Series([float("nan")] * n)

        if n < min_len:
            false_series = pd.Series([False] * n)
            return StochRSIResult(
                k=nan_series, d=nan_series,
                long_trigger=false_series, short_trigger=false_series,
                is_oversold=false_series, is_overbought=false_series,
                current_k=float("nan"), current_d=float("nan"),
            )

        # 1. RSI
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(com=self.rsi_period - 1, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(com=self.rsi_period - 1, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        # 2. Stochastic of RSI
        rsi_min = rsi.rolling(self.stoch_period).min()
        rsi_max = rsi.rolling(self.stoch_period).max()
        rsi_range = (rsi_max - rsi_min).replace(0, np.nan)
        stoch = (rsi - rsi_min) / rsi_range * 100.0

        # 3. Smooth K and D
        k = stoch.rolling(self.k_smooth).mean()
        d = k.rolling(self.d_smooth).mean()

        # Clip to [0, 100]
        k = k.clip(0, 100)
        d = d.clip(0, 100)

        # 4. Signals
        prev_k = k.shift(1)
        long_trigger  = (prev_k < self.oversold)  & (k >= self.oversold)
        short_trigger = (prev_k > self.overbought) & (k <= self.overbought)
        is_oversold   = k < self.oversold
        is_overbought = k > self.overbought

        # Fill NaN booleans with False
        long_trigger  = long_trigger.fillna(False)
        short_trigger = short_trigger.fillna(False)
        is_oversold   = is_oversold.fillna(False)
        is_overbought = is_overbought.fillna(False)

        # Restore original index
        k.index = df.index
        d.index = df.index
        long_trigger.index  = df.index
        short_trigger.index = df.index
        is_oversold.index   = df.index
        is_overbought.index = df.index

        return StochRSIResult(
            k=k, d=d,
            long_trigger=long_trigger,
            short_trigger=short_trigger,
            is_oversold=is_oversold,
            is_overbought=is_overbought,
            current_k=float(k.iloc[-1]) if not k.isna().iloc[-1] else float("nan"),
            current_d=float(d.iloc[-1]) if not d.isna().iloc[-1] else float("nan"),
        )
