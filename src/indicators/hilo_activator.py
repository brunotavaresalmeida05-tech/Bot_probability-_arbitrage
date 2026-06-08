from __future__ import annotations
from dataclasses import dataclass
import pandas as pd


@dataclass
class HiLoResult:
    level: pd.Series        # trailing stop price
    triggered: pd.Series    # True se posição invalidada nesta barra
    current_level: float


class HiLoActivator:
    """
    HiLo Activator — trailing stop virtual baseado em máximas/mínimas rolantes.
    LONG:  level = rolling min(low, period). Triggered se close < level.
    SHORT: level = rolling max(high, period). Triggered se close > level.
    """

    def __init__(self, period: int = 3):
        self.period = period

    def compute(self, df: pd.DataFrame, direction: str) -> HiLoResult:
        if direction not in ("long", "short"):
            raise ValueError(f"direction deve ser 'long' ou 'short', recebeu '{direction}'")

        if direction == "long":
            level     = df["low"].rolling(self.period).min()
            triggered = df["close"] < level
        else:
            level     = df["high"].rolling(self.period).max()
            triggered = df["close"] > level

        triggered = triggered.fillna(False).astype(bool)

        return HiLoResult(
            level=level,
            triggered=triggered,
            current_level=float(level.iloc[-1]) if not level.isna().iloc[-1] else float("nan"),
        )
