from __future__ import annotations
"""
SMCEngine — aggregates StructureAnalyzer, OrderBlockDetector, FairValueGapDetector,
and LiquiditySweepDetector into a single SMCResult.

SMCResult exposes:
  - market_structure: MarketStructure (new — BOS/ChoCh, HH/HL, swing points)
  - order_blocks / fvgs / liquidity_sweeps: raw structures
  - Boolean fast-path flags (backward compatible with signal_generator + orchestrator)
"""

import pandas as pd
from dataclasses import dataclass, field

from .structure import StructureAnalyzer, MarketStructure
from .order_blocks import OrderBlockDetector, OrderBlock
from .fvg import FairValueGapDetector, FairValueGap
from .liquidity import LiquiditySweepDetector, LiquiditySweep


@dataclass
class SMCResult:
    # New modular structures
    market_structure: MarketStructure = field(
        default_factory=lambda: MarketStructure(
            trend="uncertain", last_event=None, last_event_level=None,
            last_event_bars_ago=None, hh_hl=False, lh_ll=False,
        )
    )
    order_blocks: list[OrderBlock] = field(default_factory=list)
    fvgs: list[FairValueGap] = field(default_factory=list)
    liquidity_sweeps: list[LiquiditySweep] = field(default_factory=list)

    # Fast-path booleans — backward compatible with signal_generator and orchestrator
    bullish_ob_nearby: bool = False
    bearish_ob_nearby: bool = False
    bullish_fvg: bool = False
    bearish_fvg: bool = False
    last_bos: str | None = None         # "bullish" | "bearish" | None
    last_choch: str | None = None       # "bullish" | "bearish" | None
    sweep_recent: str | None = None     # "bullish" | "bearish" | None


class SMCEngine:
    def __init__(
        self,
        structure_analyzer: StructureAnalyzer | None = None,
        ob_detector: OrderBlockDetector | None = None,
        fvg_detector: FairValueGapDetector | None = None,
        sweep_detector: LiquiditySweepDetector | None = None,
    ):
        self._structure  = structure_analyzer or StructureAnalyzer()
        self._ob         = ob_detector or OrderBlockDetector()
        self._fvg        = fvg_detector or FairValueGapDetector()
        self._sweep      = sweep_detector or LiquiditySweepDetector()

    def analyze(self, df: pd.DataFrame, atr: float = 0.0) -> SMCResult:
        if df is None or len(df) < 10:
            return SMCResult()

        price = float(df["close"].iloc[-1])

        structure = self._structure.analyze(df, atr)
        obs       = self._ob.detect(df, structure, atr)
        fvgs      = self._fvg.detect(df)
        sweeps    = self._sweep.detect(df, structure, atr, analyzer=self._structure)

        # Proximity thresholds for "nearby" checks
        ob_prox  = max(atr * 0.5, price * 0.001) if atr > 0 else price * 0.001
        fvg_prox = max(atr * 0.3, price * 0.0005) if atr > 0 else price * 0.0005

        bullish_ob_nearby = any(
            ob.direction == "bullish" and not ob.mitigated
            and ob.bottom - ob_prox <= price <= ob.top + ob_prox
            for ob in obs
        )
        bearish_ob_nearby = any(
            ob.direction == "bearish" and not ob.mitigated
            and ob.bottom - ob_prox <= price <= ob.top + ob_prox
            for ob in obs
        )
        bullish_fvg = any(
            fvg.direction == "bullish" and not fvg.filled
            and fvg.bottom - fvg_prox <= price <= fvg.top + fvg_prox
            for fvg in fvgs
        )
        bearish_fvg = any(
            fvg.direction == "bearish" and not fvg.filled
            and fvg.bottom - fvg_prox <= price <= fvg.top + fvg_prox
            for fvg in fvgs
        )

        # Derive boolean BOS/ChoCh flags from MarketStructure.last_event
        last_bos: str | None = None
        last_choch: str | None = None
        evt = structure.last_event
        if evt == "BOS_bull":
            last_bos = "bullish"
        elif evt == "BOS_bear":
            last_bos = "bearish"
        elif evt == "ChoCh_bull":
            last_choch = "bullish"
        elif evt == "ChoCh_bear":
            last_choch = "bearish"

        sweep_recent = sweeps[-1].direction if sweeps else None

        return SMCResult(
            market_structure=structure,
            order_blocks=obs,
            fvgs=fvgs,
            liquidity_sweeps=sweeps,
            bullish_ob_nearby=bullish_ob_nearby,
            bearish_ob_nearby=bearish_ob_nearby,
            bullish_fvg=bullish_fvg,
            bearish_fvg=bearish_fvg,
            last_bos=last_bos,
            last_choch=last_choch,
            sweep_recent=sweep_recent,
        )
