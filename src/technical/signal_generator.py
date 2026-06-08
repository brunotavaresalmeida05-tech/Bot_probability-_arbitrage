from __future__ import annotations
"""
Signal Generator — V9 (Fully Integrated)

Final signal aggregation combining:
  - Macro scenario (from ScenarioEvaluator)
  - Multi-timeframe confluence (from MTFResult)
  - MACD teeth (volatility resistance)
  - Bollinger micro-structure (squeeze, expansion, walking)
  - Fair price proximity
  - Calendar blackout gate

Blueprint fast-fail veto tree (executed in order):
  1. Calendar blackout?            -> BLOCK
  2. Spread too wide?              -> SKIP
  3. Macro not aligned with tech?  -> lot_penalty 35%
  4. Volume step violation?        -> SKIP (handled by risk manager)
  5. All aligned?                  -> CONFIRM + submit

Signal requires ALL of:
  - macro_scenario in (alta, baixa)
  - MTF confluence >= moderate (score >= 0.50)
  - No higher TF veto
  - Bollinger not in full contraction
  - MACD direction aligns
  - min 4/8 technical confirmations
"""
from dataclasses import dataclass, field

from src.technical.indicators import IndicatorBundle
from src.technical.macd_analyzer import MACDAnalysis
from src.technical.bollinger_analyzer import BollingerAnalysis
from src.technical.multi_timeframe import MTFResult
from src.analysis.scenario_evaluator import ScenarioResult, Scenario
from src.analysis.total_score import compute as compute_total_score, TotalScoreResult, describe_score
from src.macro.macro_context import MacroContext

import logging
logger = logging.getLogger(__name__)

SIGNAL_BUY  = "BUY"
SIGNAL_SELL = "SELL"
SIGNAL_HOLD = "HOLD"
SIGNAL_BLOCK = "BLOCKED"


@dataclass
class FinalSignal:
    symbol: str
    timeframe: str
    signal: str                     # BUY | SELL | HOLD | BLOCKED
    confidence: int                 # 0-10
    lot_multiplier: float           # combined lot adjustment (MTF × scenario × VIX × yield)
    entry: float
    sl_distance: float
    tp_distance: float
    scenario: str
    mtf_confluence: str
    rationale: list[str] = field(default_factory=list)
    blocked_reason: str = ""
    # TotalScore engine output
    total_score: float = 0.0
    total_score_decision: str = ""
    # Score components — usados pelo Opportunity-Permission Engine
    mcs_n: float = 0.0
    bcs_n: float = 0.0
    hcs_n: float = 0.0
    ves:   float = 0.0
    es:    float = 0.0
    cs:    float = 0.0
    rs:    float = 0.0
    rsi: float = 50.0          # RSI(14) no momento do sinal; 50.0 = neutro/sem dados
    # Chart projection levels for dashboard
    macd_resistance: float | None = None
    macd_support: float | None = None
    bb_day_max: float = 0.0
    bb_day_min: float = 0.0
    pivot_r1: float = 0.0
    pivot_s1: float = 0.0


def generate(
    bundle: IndicatorBundle,
    macro: MacroContext,
    scenario_result: ScenarioResult,
    mtf_result: MTFResult,
    macd_analysis: MACDAnalysis | None = None,
    bb_analysis: BollingerAnalysis | None = None,
    calendar_blackout: bool = False,
    spread_ok: bool = True,
    fair_price: float = 0.0,
    regime_score: float = 0.0,
    benchmark_risk_on: float = 0.0,
    daily_dd_pct: float = 0.0,
    atr_avg: float = 0.0,
    vol_avg: float = 0.0,
) -> FinalSignal:
    """
    Generate final trading signal with full fast-fail veto tree.

    All parameters except bundle and macro can be None (graceful degradation).
    """
    rationale = []
    price = bundle.close
    atr_sl = bundle.atr * 1.5 if bundle.atr > 0 else price * 0.003
    tp_dist = atr_sl * 2.0

    # ── Compute TotalScore (runs regardless of veto outcome — for logging) ─
    bias_for_score = "buy"
    if scenario_result and scenario_result.scenario == Scenario.BEAR:
        bias_for_score = "sell"
    ts_result: TotalScoreResult = compute_total_score(
        symbol=bundle.symbol,
        timeframe=bundle.timeframe,
        bundle=bundle,
        macro=macro,
        macd_analysis=macd_analysis,
        bb_analysis=bb_analysis,
        fair_price=fair_price,
        expected_range=bundle.atr * 3 if bundle.atr > 0 else 0.0,
        regime_score=regime_score,
        benchmark_risk_on=benchmark_risk_on,
        correlation_ok=not (scenario_result and scenario_result.lot_penalty < 0.5) if scenario_result else True,
        event_positive=not calendar_blackout,
        event_minutes_away=0.0 if calendar_blackout else 999.0,
        daily_dd_pct=daily_dd_pct,
        atr_avg=atr_avg,
        vol_avg=vol_avg,
        bias=bias_for_score,
    )
    logger.debug(describe_score(ts_result))

    base_signal = FinalSignal(
        symbol=bundle.symbol,
        timeframe=bundle.timeframe,
        signal=SIGNAL_HOLD,
        confidence=0,
        lot_multiplier=1.0,
        entry=price,
        sl_distance=round(atr_sl, 5),
        tp_distance=round(tp_dist, 5),
        scenario=scenario_result.scenario.value if scenario_result else "indefinido",
        mtf_confluence=mtf_result.confluence_label if mtf_result else "none",
        total_score=ts_result.total_score,
        total_score_decision=ts_result.decision,
        mcs_n=ts_result.mcs_n,
        bcs_n=ts_result.bcs_n,
        hcs_n=ts_result.hcs_n,
        ves=ts_result.ves,
        es=ts_result.es,
        cs=ts_result.cs,
        rs=ts_result.rs,
        rsi=getattr(bundle, "rsi", 50.0),
    )

    # ── VETO 1: Calendar blackout ─────────────────────────────────────
    if calendar_blackout:
        base_signal.signal = SIGNAL_BLOCK
        base_signal.blocked_reason = "Blackout: evento macro de alto impacto"
        logger.debug(f"[{bundle.symbol}] VETO 1: blackout")
        return base_signal

    # ── VETO 2: Spread ───────────────────────────────────────────────
    if not spread_ok:
        base_signal.signal = SIGNAL_BLOCK
        base_signal.blocked_reason = "Spread acima do limite operacional"
        return base_signal

    # ── VETO 3: Macro not tradeable ──────────────────────────────────
    if not macro.tradeable:
        base_signal.signal = SIGNAL_BLOCK
        base_signal.blocked_reason = f"VIX {macro.vix_regime}: mercado nao operavel"
        return base_signal

    # ── VETO 4: Scenario blocked ─────────────────────────────────────
    if scenario_result and scenario_result.blocked:
        base_signal.signal = SIGNAL_BLOCK
        base_signal.blocked_reason = scenario_result.blocked_reason
        return base_signal

    # ── VETO 5: Scenario not directional ─────────────────────────────
    if not scenario_result or scenario_result.scenario in (Scenario.UNDEFINED, Scenario.LATERAL, Scenario.BLOCKED):
        rationale.append(f"Cenario nao direcional: {scenario_result.scenario if scenario_result else 'None'}")
        base_signal.rationale = rationale
        return base_signal

    # ── VETO 6: MTF no confluence ────────────────────────────────────
    if mtf_result and mtf_result.confluence_label == "none":
        rationale.append("MTF: sem confluencia — HOLD")
        base_signal.rationale = rationale
        return base_signal

    # ── VETO 7: Higher TF veto ───────────────────────────────────────
    if mtf_result and mtf_result.higher_tf_veto:
        rationale.append("Higher TF veto: timeframe superior contradiz sinal")
        base_signal.rationale = rationale
        return base_signal

    # ── DETERMINE BIAS ───────────────────────────────────────────────
    scenario_str = scenario_result.scenario.value
    bias = SIGNAL_BUY if scenario_str == Scenario.BULL.value else SIGNAL_SELL

    # ── COLLECT CONFIRMATIONS (8 conditions) ─────────────────────────
    confirms = 0

    # 1. MACD direction
    if macd_analysis:
        macd_ok = (bias == SIGNAL_BUY and macd_analysis.direction == "bullish") or \
                  (bias == SIGNAL_SELL and macd_analysis.direction == "bearish")
        if macd_ok:
            confirms += 1
            rationale.append(f"[+] MACD {macd_analysis.direction}")
        else:
            rationale.append(f"[-] MACD {macd_analysis.direction} vs bias {bias}")
        # Divergence bonus
        if (macd_analysis.divergence == "bullish_div" and bias == SIGNAL_BUY) or \
           (macd_analysis.divergence == "bearish_div" and bias == SIGNAL_SELL):
            confirms += 1
            rationale.append(f"[+] MACD divergence: {macd_analysis.divergence}")
    elif bundle.macd:
        macd_ok = (bias == SIGNAL_BUY and bundle.macd.direction == "bullish") or \
                  (bias == SIGNAL_SELL and bundle.macd.direction == "bearish")
        if macd_ok:
            confirms += 1
            rationale.append(f"[+] MACD {bundle.macd.direction}")

    # 2. Bollinger signal
    if bb_analysis:
        bb_ok = (bias == SIGNAL_BUY and bb_analysis.signal in ("buy_setup",)) or \
                (bias == SIGNAL_SELL and bb_analysis.signal in ("sell_setup",))
        if bb_ok:
            confirms += 1
            rationale.append(f"[+] BB signal={bb_analysis.signal} state={bb_analysis.state}")
        elif bb_analysis.is_squeeze:
            rationale.append(f"[~] BB squeeze — aguardar expansao ({bb_analysis.signal})")
        else:
            rationale.append(f"[-] BB signal={bb_analysis.signal}")
        # Walking the band = strong trend confirmation
        if (bias == SIGNAL_BUY and bb_analysis.walking_upper) or \
           (bias == SIGNAL_SELL and bb_analysis.walking_lower):
            confirms += 1
            rationale.append(f"[+] Caminhando pela banda ({bb_analysis.walk_bars} bars)")
    elif bundle.bollinger:
        if bundle.bollinger.state == "expanding":
            confirms += 1
            rationale.append("[+] BB expanding")

    # 3. Hi-Lo Activator
    if bundle.hi_lo:
        hilo_ok = (bias == SIGNAL_BUY and bundle.hi_lo.direction == "bullish") or \
                  (bias == SIGNAL_SELL and bundle.hi_lo.direction == "bearish")
        if hilo_ok:
            confirms += 1
            rationale.append(f"[+] Hi-Lo {bundle.hi_lo.direction} @ {bundle.hi_lo.value}")
        else:
            rationale.append(f"[-] Hi-Lo {bundle.hi_lo.direction} vs bias {bias}")

    # 4. ATR Stop
    if bundle.atr_stop:
        atr_stop_ok = (bias == SIGNAL_BUY and bundle.atr_stop.direction == "bullish") or \
                      (bias == SIGNAL_SELL and bundle.atr_stop.direction == "bearish")
        if atr_stop_ok:
            confirms += 1
            rationale.append(f"[+] ATR Stop {bundle.atr_stop.direction} @ {bundle.atr_stop.value}")
        else:
            rationale.append(f"[-] ATR Stop {bundle.atr_stop.direction} vs bias {bias}")

    # 5. SAR direction
    if bundle.sar:
        sar_ok = (bias == SIGNAL_BUY and bundle.sar.direction == "bullish") or \
                 (bias == SIGNAL_SELL and bundle.sar.direction == "bearish")
        if sar_ok:
            confirms += 1
            rationale.append(f"[+] SAR {bundle.sar.direction}")
        else:
            rationale.append(f"[-] SAR {bundle.sar.direction}")

    # 6. Price vs VWAP
    if bundle.vwap > 0:
        vwap_ok = (bias == SIGNAL_BUY and price > bundle.vwap) or \
                  (bias == SIGNAL_SELL and price < bundle.vwap)
        if vwap_ok:
            confirms += 1
            rationale.append(f"[+] VWAP: preco {'acima' if bias==SIGNAL_BUY else 'abaixo'}")
        else:
            rationale.append(f"[-] VWAP: lado errado")

    # 7. MA50/MA100 trend alignment
    if bundle.ma50 > 0 and bundle.ma100 > 0:
        ma_ok = (bias == SIGNAL_BUY and price > bundle.ma50 > bundle.ma100) or \
                (bias == SIGNAL_SELL and price < bundle.ma50 < bundle.ma100)
        if ma_ok:
            confirms += 1
            rationale.append("[+] MA50>MA100: tendencia alinhada")
        else:
            rationale.append("[-] MA: tendencia nao alinhada")

    # 8. Fair price proximity (good entry zone)
    if fair_price > 0:
        dist_pct = abs(price - fair_price) / fair_price
        if dist_pct <= 0.004:
            confirms += 1
            rationale.append(f"[+] Preco justo proximity: {dist_pct*100:.3f}%")
        elif dist_pct > 0.015:
            rationale.append(f"[-] Longe do preco justo: {dist_pct*100:.3f}%")

    # ── FINAL DECISION ─────────────────────────────────────────────────────
    # Gate 1: technical confirmations (min 4/8)
    # Gate 2: MTF confluence >= moderate
    # Gate 3: TotalScore >= MODERATE threshold (0.55)
    min_confirms = 4
    ts_ok = ts_result.decision in ("execute", "moderate")
    mtf_ok = mtf_result and mtf_result.confluence_score >= 0.50

    if confirms >= min_confirms and mtf_ok and ts_ok:
        final_signal = bias
        # Confidence: technical + MTF + TotalScore
        confidence = min(10, confirms
                         + int((mtf_result.confluence_score if mtf_result else 0) * 3)
                         + int(ts_result.total_score * 3))
    else:
        final_signal = SIGNAL_HOLD
        confidence = confirms
        rationale.append(
            f"HOLD: conf={confirms}/{min_confirms} "
            f"mtf={mtf_result.confluence_score if mtf_result else 0:.2f} "
            f"ts={ts_result.total_score:.3f}({ts_result.decision})"
        )

    # ── LOT MULTIPLIER (3 layers) ─────────────────────────────────────────
    # Layer 1: scenario lot penalty (correlation, VIX caution)
    # Layer 2: MTF confluence adjustment
    # Layer 3: TotalScore lot multiplier (from VES/ES analysis)
    lot_mult = 1.0
    if scenario_result:
        lot_mult *= scenario_result.lot_penalty
    if mtf_result:
        lot_mult *= mtf_result.lot_adjustment
    lot_mult *= ts_result.lot_multiplier    # TotalScore-based adjustment
    lot_mult = round(max(0.0, min(1.0, lot_mult)), 4)

    # ── CHART LEVELS ─────────────────────────────────────────────────
    macd_resistance = macd_analysis.nearest_resistance if macd_analysis else None
    macd_support = macd_analysis.nearest_support if macd_analysis else None
    bb_day_max = bb_analysis.day_max if bb_analysis else 0.0
    bb_day_min = bb_analysis.day_min if bb_analysis else 0.0
    pivot_r1 = bundle.pivot.r1 if bundle.pivot else 0.0
    pivot_s1 = bundle.pivot.s1 if bundle.pivot else 0.0

    if final_signal != SIGNAL_HOLD:
        logger.info(
            f"SIGNAL {final_signal} {bundle.symbol} {bundle.timeframe} "
            f"conf={confidence}/10 lot_mult={lot_mult:.2f} "
            f"confirms={confirms}/{min_confirms} mtf={mtf_result.confluence_label if mtf_result else '?'}"
        )

    base_signal.signal = final_signal
    base_signal.confidence = confidence
    base_signal.lot_multiplier = lot_mult
    base_signal.rationale = rationale
    base_signal.macd_resistance = macd_resistance
    base_signal.macd_support = macd_support
    base_signal.bb_day_max = bb_day_max
    base_signal.bb_day_min = bb_day_min
    base_signal.pivot_r1 = pivot_r1
    base_signal.pivot_s1 = pivot_s1
    return base_signal
