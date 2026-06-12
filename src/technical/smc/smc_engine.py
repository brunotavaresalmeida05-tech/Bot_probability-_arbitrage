from __future__ import annotations
"""
SMCEngine — agrega StructureAnalyzer, OrderBlockDetector, FairValueGapDetector
e LiquiditySweepDetector num único SMCResult.

SMCResult expõe:
  - market_structure: MarketStructure (BOS/ChoCh, HH/HL, swing points)
  - order_blocks: list[OrderBlock] — nearest bullish + bearish (0–2 items)
  - fvgs / liquidity_sweeps: estruturas cruas
  - Flags booleanas fast-path (compatíveis com signal_generator + orchestrator)
"""

import pandas as pd
from dataclasses import dataclass, field

from .structure import StructureAnalyzer, MarketStructure
from .order_blocks import OrderBlockDetector, OrderBlock
from .fvg import FairValueGapDetector, FairValueGap
from .liquidity import LiquiditySweepDetector, LiquiditySweep


@dataclass
class SMCResult:
    # Estruturas modulares
    market_structure: MarketStructure = field(
        default_factory=lambda: MarketStructure(
            trend="uncertain", last_event=None, last_event_level=None,
            last_event_bars_ago=None, hh_hl=False, lh_ll=False,
        )
    )
    # nearest bullish + nearest bearish (0–2 items); None entries excluídas
    order_blocks: list[OrderBlock] = field(default_factory=list)
    fvgs: list[FairValueGap] = field(default_factory=list)
    liquidity_sweeps: list[LiquiditySweep] = field(default_factory=list)

    # Fast-path booleans — backward compatible com signal_generator e orchestrator
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

        # OrderBlockDetector nova API: retorna (nearest_bull, nearest_bear)
        bull_ob, bear_ob = self._ob.detect(df, atr, price)
        obs = [ob for ob in (bull_ob, bear_ob) if ob is not None]

        fvgs   = self._fvg.detect(df)
        sweeps = self._sweep.detect(df, structure, atr, analyzer=self._structure)

        # OB nearby via price_in_ob() (inclui margem ATR × proximity_atr_mult)
        bullish_ob_nearby = self._ob.price_in_ob(bull_ob, price, atr)
        bearish_ob_nearby = self._ob.price_in_ob(bear_ob, price, atr)

        # FVG proximity
        fvg_prox = max(atr * 0.3, price * 0.0005) if atr > 0 else price * 0.0005
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

        # BOS/ChoCh flags derivadas de MarketStructure.last_event
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
