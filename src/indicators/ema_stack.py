from __future__ import annotations
from dataclasses import dataclass
import pandas as pd


@dataclass
class EMAResult:
    ema20: pd.Series
    ema50: pd.Series
    ema100: pd.Series
    aligned_up: pd.Series      # EMA20 > EMA50 > EMA100
    aligned_down: pd.Series    # EMA20 < EMA50 < EMA100
    near_ema20: pd.Series      # close within tolerance of EMA20
    near_ema50: pd.Series      # close within tolerance of EMA50
    bias: pd.Series            # "up" | "down" | "neutral"
    current_ema20: float
    current_ema50: float
    current_ema100: float


class EMAStack:
    """
    EMA 20/50/100 — mapa de estrutura e contexto direccional.
    Detecta alinhamento, viés e qualidade de pullback.
    """

    def __init__(
        self,
        periods: list[int] | None = None,
        near_pct: float = 0.002,  # 0.2% da EMA para considerar "near"
    ):
        self.periods = periods or [20, 50, 100]
        self.near_pct = near_pct

    def compute(self, df: pd.DataFrame) -> EMAResult:
        close = df["close"]

        ema20  = close.ewm(span=self.periods[0], adjust=False).mean()
        ema50  = close.ewm(span=self.periods[1], adjust=False).mean()
        ema100 = close.ewm(span=self.periods[2], adjust=False).mean()

        aligned_up   = (ema20 > ema50) & (ema50 > ema100)
        aligned_down = (ema20 < ema50) & (ema50 < ema100)

        near_ema20 = (close - ema20).abs() / ema20 <= self.near_pct
        near_ema50 = (close - ema50).abs() / ema50 <= self.near_pct

        bias = pd.Series("neutral", index=df.index)
        bias[aligned_up]   = "up"
        bias[aligned_down] = "down"

        return EMAResult(
            ema20=ema20, ema50=ema50, ema100=ema100,
            aligned_up=aligned_up,
            aligned_down=aligned_down,
            near_ema20=near_ema20,
            near_ema50=near_ema50,
            bias=bias,
            current_ema20=float(ema20.iloc[-1]),
            current_ema50=float(ema50.iloc[-1]),
            current_ema100=float(ema100.iloc[-1]),
        )
