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
  - min 4/9 technical confirmations (8 tech + max 2 SMC with RSI guard)
"""
from dataclasses import dataclass, field

from src.technical.indicators import IndicatorBundle
from src.technical.macd_analyzer import MACDAnalysis
from src.technical.bollinger_analyzer import BollingerAnalysis
from src.technical.multi_timeframe import MTFResult
from src.analysis.scenario_evaluator import ScenarioResult, Scenario
from src.analysis.total_score import compute as compute_total_score, TotalScoreResult, describe_score
from src.macro.macro_context import MacroContext
from src.engine import regime_router as _regime
from src.engine.regime_router import RegimeState
from src.analysis.smc import smc_score_with_regime_context

import logging
logger = logging.getLogger(__name__)

SIGNAL_BUY   = "BUY"
SIGNAL_SELL  = "SELL"
SIGNAL_HOLD  = "HOLD"
SIGNAL_BLOCK = "BLOCKED"

# ── Idiosyncratic move config (lazy-loaded once from strategies.yaml) ─────────
_IDIO_CFG: dict | None = None


def _get_idio_config() -> dict:
    global _IDIO_CFG
    if _IDIO_CFG is None:
        try:
            import yaml
            from pathlib import Path
            data = yaml.safe_load(Path("config/strategies.yaml").read_text(encoding="utf-8")) or {}
            _IDIO_CFG = data.get("strategies", {}).get("idiosyncratic_move", {})
        except Exception:
            _IDIO_CFG = {}
    return _IDIO_CFG


def _detect_pure_technical_bias(
    bundle: "IndicatorBundle",
    macd_analysis: "MACDAnalysis | None",
    bb_analysis: "BollingerAnalysis | None",
    ts_result: "TotalScoreResult",
    cfg: dict,
) -> str | None:
    """
    Returns SIGNAL_BUY, SIGNAL_SELL, or None.

    Fires when macro scenario is neutral but technicals show a clean
    directional move (idiosyncratic / pure-technical mode).

    Requirements:
      1. TotalScore >= min_total_score
      2. BB not in squeeze (move needs energy)
      3. At least min_directional_agrees of MACD/ATRStop agree on one direction
      4. RSI not in exhaustion zone for that direction
    """
    min_score   = cfg.get("min_total_score", 0.72)
    min_agrees  = cfg.get("min_directional_agrees", 2)
    rsi_max_long  = cfg.get("rsi_max_long",  75.0)
    rsi_min_short = cfg.get("rsi_min_short", 25.0)

    if ts_result.total_score < min_score:
        return None

    # BB not in squeeze
    if bb_analysis:
        if bb_analysis.is_squeeze:
            return None
    elif bundle.bollinger and bundle.bollinger.state == "squeeze":
        return None

    # Count directional agreement for each side
    buy_agrees  = 0
    sell_agrees = 0

    # MACD
    macd_dir = None
    if macd_analysis:
        macd_dir = macd_analysis.direction
    elif bundle.macd:
        macd_dir = bundle.macd.direction
    if macd_dir == "bullish":
        buy_agrees  += 1
    elif macd_dir == "bearish":
        sell_agrees += 1

    # ATR Stop
    if bundle.atr_stop:
        if bundle.atr_stop.direction == "bullish":
            buy_agrees  += 1
        elif bundle.atr_stop.direction == "bearish":
            sell_agrees += 1

    # Determine unambiguous bias
    if buy_agrees >= min_agrees and buy_agrees > sell_agrees:
        bias = SIGNAL_BUY
    elif sell_agrees >= min_agrees and sell_agrees > buy_agrees:
        bias = SIGNAL_SELL
    else:
        return None  # split or insufficient agreement

    # RSI exhaustion check
    rsi = getattr(bundle, "rsi", 50.0)
    if bias == SIGNAL_BUY  and rsi >= rsi_max_long:
        return None
    if bias == SIGNAL_SELL and rsi <= rsi_min_short:
        return None

    return bias


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

    # ── VETO 5: Scenario not directional → V9.1: check regime before blocking ─
    pure_technical  = False
    trending_regime = False
    pure_technical_bias: str | None = None
    regime_result = _regime.detect(bundle, macro)

    macro_directional = (
        scenario_result is not None
        and scenario_result.scenario in (Scenario.BULL, Scenario.BEAR)
    )

    if macro_directional:
        pass  # macro provides clear direction — proceed to confirmations
    elif regime_result.state in (RegimeState.TRENDING_UP, RegimeState.TRENDING_DOWN):
        # V9.1: trending regime — macro=neutral is NOT a veto
        pure_technical  = True
        trending_regime = True
        pure_technical_bias = (
            SIGNAL_BUY if regime_result.direction == "bullish" else SIGNAL_SELL
        )
        base_signal.scenario = regime_result.state.value
        rationale.append(
            f"[TRENDING] ADX={regime_result.adx:.1f} dir={regime_result.direction} "
            f"conf={regime_result.confidence:.2f} lot_ctx={regime_result.lot_context:.2f}"
        )
        logger.debug(
            f"[{bundle.symbol}] TRENDING regime: {regime_result.state} "
            f"adx={regime_result.adx:.1f} lot_ctx={regime_result.lot_context:.2f}"
        )
    else:
        # RANGING or VOLATILE — try TECNICO_PURO, else HOLD
        idio_cfg = _get_idio_config()
        if idio_cfg.get("enabled", False):
            pure_technical_bias = _detect_pure_technical_bias(
                bundle, macd_analysis, bb_analysis, ts_result, idio_cfg
            )
        if pure_technical_bias:
            pure_technical = True
            base_signal.scenario = Scenario.TECNICO_PURO.value
            rationale.append(f"[TECNICO_PURO] Movimento idiossincrático: {pure_technical_bias}")
            logger.debug(f"[{bundle.symbol}] TECNICO_PURO: ts={ts_result.total_score:.3f}")
        else:
            rationale.append(
                f"Cenario nao direcional: regime={regime_result.state} adx={regime_result.adx:.1f} "
                f"scenario={scenario_result.scenario if scenario_result else 'None'}"
            )
            base_signal.rationale = rationale
            return base_signal

    # ── VETO 6: MTF no confluence (skipped in pure-technical mode) ───
    if not pure_technical:
        if mtf_result and mtf_result.confluence_label == "none":
            rationale.append("MTF: sem confluencia — HOLD")
            base_signal.rationale = rationale
            return base_signal

    # ── VETO 7: Higher TF veto (applies even in pure-technical mode) ─
    if mtf_result and mtf_result.higher_tf_veto:
        rationale.append("Higher TF veto: timeframe superior contradiz sinal")
        base_signal.rationale = rationale
        return base_signal

    # ── DETERMINE BIAS ───────────────────────────────────────────────
    if pure_technical:
        bias = pure_technical_bias  # type: ignore[assignment]
    else:
        scenario_str = scenario_result.scenario.value
        bias = SIGNAL_BUY if scenario_str == Scenario.BULL.value else SIGNAL_SELL

    # ── COLLECT CONFIRMATIONS (9 conditions max: 8 technical + max 2 SMC with RSI guard) ──
    confirms = 0

    # 1. MACD divergence bonus
    if macd_analysis:
        if (macd_analysis.divergence == "bullish_div" and bias == SIGNAL_BUY) or \
           (macd_analysis.divergence == "bearish_div" and bias == SIGNAL_SELL):
            confirms += 1
            rationale.append(f"[+] MACD divergence: {macd_analysis.divergence}")
        else:
            rationale.append(f"[-] MACD: sem divergencia ({macd_analysis.direction})")

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

    # 3. ATR Stop
    if bundle.atr_stop:
        atr_stop_ok = (bias == SIGNAL_BUY and bundle.atr_stop.direction == "bullish") or \
                      (bias == SIGNAL_SELL and bundle.atr_stop.direction == "bearish")
        if atr_stop_ok:
            confirms += 1
            rationale.append(f"[+] ATR Stop {bundle.atr_stop.direction} @ {bundle.atr_stop.value}")
        else:
            rationale.append(f"[-] ATR Stop {bundle.atr_stop.direction} vs bias {bias}")

    # 4. Price vs VWAP
    if bundle.vwap > 0:
        vwap_ok = (bias == SIGNAL_BUY and price > bundle.vwap) or \
                  (bias == SIGNAL_SELL and price < bundle.vwap)
        if vwap_ok:
            confirms += 1
            rationale.append(f"[+] VWAP: preco {'acima' if bias==SIGNAL_BUY else 'abaixo'}")
        else:
            rationale.append(f"[-] VWAP: lado errado")

    # 5. EMA alignment (20/50/100) — exige alinhamento perfeito das 3 EMAs
    ema20, ema50, ema100 = bundle.ema20, bundle.ema50, bundle.ema100
    if ema20 > 0 and ema50 > 0 and ema100 > 0:
        ema_bull = ema20 > ema50 > ema100
        ema_bear = ema20 < ema50 < ema100
        if bias == SIGNAL_BUY and ema_bull:
            confirms += 1
            rationale.append("[+] EMA:aligned_bull(20>50>100)")
        elif bias == SIGNAL_SELL and ema_bear:
            confirms += 1
            rationale.append("[+] EMA:aligned_bear(20<50<100)")
        elif bias == SIGNAL_BUY and ema50 > ema100:
            rationale.append("[~] EMA:partial_bull(50>100,20 lagging)")
        elif bias == SIGNAL_SELL and ema50 < ema100:
            rationale.append("[~] EMA:partial_bear(50<100,20 lagging)")
        else:
            rationale.append("[-] EMA:misaligned")

    # 6. Fair price proximity (good entry zone)
    if fair_price > 0:
        dist_pct = abs(price - fair_price) / fair_price
        if dist_pct <= 0.004:
            confirms += 1
            rationale.append(f"[+] Preco justo proximity: {dist_pct*100:.3f}%")
        elif dist_pct > 0.015:
            rationale.append(f"[-] Longe do preco justo: {dist_pct*100:.3f}%")

    # ── SMC CONFIRMATIONS (7–8) — regime-weighted score ────────────────────
    # Score computed once from regime context:
    #   RANGING:      full OB/FVG/BOS weight (best environment for zone trading)
    #   TRENDING_*:   aligned side +15%, opposing side -40%
    #   VOLATILE:     0.0 — no new SMC entries
    # score >= 0.75 → 2 confirms (strong confluence); >= 0.30 → 1; else 0
    smc = bundle.smc
    if smc is not None:
        regime_str = regime_result.state.value if regime_result else "RANGING"
        bull_smc, bear_smc = smc_score_with_regime_context(smc, regime_str, bundle.adx)
        smc_score = bull_smc if bias == SIGNAL_BUY else bear_smc

        # RSI extreme guard: PermissionScore already blocks, SMC shouldn't add confidence
        if (bias == SIGNAL_BUY and bundle.rsi >= 75.0) or \
           (bias == SIGNAL_SELL and bundle.rsi <= 25.0):
            smc_score = 0.0
            rationale.append(f"[~] SMC: zeroed — RSI extremo {bundle.rsi:.1f}")

        if smc_score >= 0.75:
            confirms += 2
            rationale.append(f"[+] SMC: forte confluencia regime={regime_str} score={smc_score:.2f}")
        elif smc_score >= 0.30:
            confirms += 1
            rationale.append(f"[+] SMC: confluencia regime={regime_str} score={smc_score:.2f}")
        else:
            rationale.append(f"[-] SMC: score={smc_score:.2f} regime={regime_str} (insuficiente)")

        # ChoCh logged for context (informs reversal conviction, not a gate)
        if smc.last_choch:
            choch_aligned = (bias == SIGNAL_BUY and smc.last_choch == "bullish") or \
                            (bias == SIGNAL_SELL and smc.last_choch == "bearish")
            tag = "[+]" if choch_aligned else "[~]"
            rationale.append(f"{tag} SMC: ChoCh {smc.last_choch}")

    # ── FINAL DECISION ─────────────────────────────────────────────────────
    # Gate selection by mode (pool = 9 = 8 tech + max 2 SMC with RSI guard):
    #   TRENDING  (V9.1) — 3/9 confirms, TotalScore=context, only H1 veto applies
    #   TECNICO_PURO     — 5/9 confirms, TotalScore >= 0.72, MTF not required
    #   Normal macro     — 4/9 confirms, TotalScore execute/moderate, MTF >= 0.50
    if pure_technical and trending_regime:
        min_confirms = 3
        ts_ok = True
        mtf_ok = not (mtf_result and mtf_result.higher_tf_veto)
    elif pure_technical:
        idio_cfg = _get_idio_config()
        min_confirms = idio_cfg.get("min_confirmations", 5)
        ts_ok = ts_result.total_score >= idio_cfg.get("min_total_score", 0.72)
        mtf_ok = True
    else:
        min_confirms = 4
        ts_ok = ts_result.decision in ("execute", "moderate")
        mtf_ok = mtf_result and mtf_result.confluence_score >= 0.50

    if confirms >= min_confirms and mtf_ok and ts_ok:
        final_signal = bias
        raw_conf = (confirms
                    + int((mtf_result.confluence_score if mtf_result else 0) * 3)
                    + int(ts_result.total_score * 3))
        if pure_technical and trending_regime:
            confidence = min(8, raw_conf)
        elif pure_technical:
            idio_cfg = _get_idio_config()
            confidence = min(idio_cfg.get("max_confidence", 7), raw_conf)
        else:
            confidence = min(10, raw_conf)
    else:
        final_signal = SIGNAL_HOLD
        confidence = confirms
        rationale.append(
            f"HOLD: conf={confirms}/{min_confirms} "
            f"mtf={mtf_result.confluence_score if mtf_result else 0:.2f} "
            f"ts={ts_result.total_score:.3f}({ts_result.decision})"
        )

    # ── LOT MULTIPLIER ─────────────────────────────────────────────────────
    # TRENDING:    regime.lot_context (VIX-adjusted) × TotalScore
    # TECNICO_PURO: TotalScore × idio lot_penalty (half size, no macro)
    # Normal:       scenario.lot_penalty × MTF.lot_adjustment × TotalScore
    lot_mult = 1.0
    if pure_technical and trending_regime:
        lot_mult *= regime_result.lot_context
        lot_mult *= ts_result.lot_multiplier
    elif pure_technical:
        lot_mult *= ts_result.lot_multiplier
        idio_cfg = _get_idio_config()
        lot_mult *= idio_cfg.get("lot_penalty", 0.50)
    else:
        if scenario_result:
            lot_mult *= scenario_result.lot_penalty
        if mtf_result:
            lot_mult *= mtf_result.lot_adjustment
        lot_mult *= ts_result.lot_multiplier
    lot_mult = round(max(0.0, min(1.0, lot_mult)), 4)

    # ── CHART LEVELS ─────────────────────────────────────────────────
    macd_resistance = macd_analysis.nearest_resistance if macd_analysis else None
    macd_support = macd_analysis.nearest_support if macd_analysis else None
    bb_day_max = bb_analysis.day_max if bb_analysis else 0.0
    bb_day_min = bb_analysis.day_min if bb_analysis else 0.0

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
    return base_signal
