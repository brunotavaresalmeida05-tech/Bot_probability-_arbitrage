from __future__ import annotations
from dataclasses import dataclass
import pandas as pd


@dataclass
class VWAPResult:
    vwap: pd.Series
    above_vwap: pd.Series   # close > vwap
    below_vwap: pd.Series   # close < vwap
    current_vwap: float


class VWAP:
    """
    VWAP ancorado à sessão (reseta em cada novo dia UTC).
    typical_price = (high + low + close) / 3
    """

    def compute(self, df: pd.DataFrame) -> VWAPResult:
        times = pd.to_datetime(df["time"], utc=True)
        session_date = times.dt.date   # âncora = dia calendário UTC

        tp  = (df["high"] + df["low"] + df["close"]) / 3.0
        vol = df["volume"]

        tp_vol  = tp * vol
        vwap_vals = []

        cum_tp_vol = 0.0
        cum_vol    = 0.0
        prev_date  = None

        for i in range(len(df)):
            d = session_date.iloc[i]
            if d != prev_date:
                cum_tp_vol = 0.0
                cum_vol    = 0.0
                prev_date  = d
            cum_tp_vol += float(tp_vol.iloc[i])
            cum_vol    += float(vol.iloc[i])
            vwap_vals.append(cum_tp_vol / cum_vol if cum_vol > 0 else float("nan"))

        vwap_series = pd.Series(vwap_vals, index=df.index, dtype=float)

        close       = df["close"]
        above_vwap  = (close > vwap_series).astype(bool)
        below_vwap  = (close < vwap_series).astype(bool)

        return VWAPResult(
            vwap=vwap_series,
            above_vwap=above_vwap,
            below_vwap=below_vwap,
            current_vwap=float(vwap_series.iloc[-1]),
        )
