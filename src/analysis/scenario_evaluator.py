from __future__ import annotations
"""
Scenario Evaluator — V9

Consolidates micro + macro signals into a final market scenario per asset:
  TENDENCIA_ALTA | TENDENCIA_BAIXA | INDEFINIDO | LATERAL | BLOQUEADO

Decision tree (fast-fail veto, from blueprint):
  1. Calendar blackout?       -> BLOQUEADO
  2. Spread too wide?         -> BLOQUEADO
  3. Macro alignment?         -> if not: penalty 65%
  4. Volume check?            -> if fail: SKIP
  5. All aligned?             -> CONFIRMAR

Each asset may have a different scenario depending on its sector correlation.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum

from src.macro.macro_context import MacroContext

logger = logging.getLogger(__name__)


class Scenario(str, Enum):
    BULL       = "TENDENCIA_ALTA"
    BEAR       = "TENDENCIA_BAIXA"
    UNDEFINED  = "INDEFINIDO"
    LATERAL    = "LATERAL"
    BLOCKED    = "BLOQUEADO"


# Asset-to-DXY sensitivity (beta): how much DXY moves this asset
# Positive = moves with DXY, Negative = moves against DXY
ASSET_DXY_BETA: dict[str, float] = {
    "EURUSD": -1.00,
    "GBPUSD": -0.85,
    "USDJPY":  0.80,
    "AUDUSD": -0.65,
    "USDCAD":  0.60,
    "USDCHF":  0.55,
    "GOLD":   -0.75,
    "XAUUSD": -0.75,
    "Brent":  -0.55,
    "LCrude": -0.55,
    "WTI":    -0.55,
    "Usa500":  0.40,
    "UsaTec":  0.35,
    "Ger40":  -0.30,
    "GBPUSD": -0.80,
    # Default for unlisted symbols
    "_default": -0.30,
}


@dataclass
class ScenarioResult:
    symbol: str
    scenario: Scenario
    confidence: int             # 0-10
    lot_penalty: float          # 0.35 = 65% cut | 1.0 = full size
    blocked: bool = False
    blocked_reason: str = ""
    signals: list[str] = field(default_factory=list)


def evaluate(
    symbol: str,
    macro: MacroContext,
    calendar_blackout: bool = False,
    spread_ok: bool = True,
    indicator_direction: str = "flat",     # "bullish" | "bearish" | "flat"
    volume_confirms: bool = True,
    open_position_symbols: list[str] | None = None,
    correlation_matrix=None,
) -> ScenarioResult:
    """
    Full scenario evaluation for one symbol.

    Args:
        symbol:               instrument
        macro:                current MacroContext
        calendar_blackout:    True if high-impact event in window
        spread_ok:            True if spread within limits
        indicator_direction:  from MACD/SAR alignment
        volume_confirms:      Weis Wave / volume confirms direction
        open_position_symbols: currently open positions
        correlation_matrix:   CorrelationMatrix instance
    """
    signals = []
    lot_penalty = 1.0

    # --- FAST-FAIL VETO TREE (blueprint order) ---

    # 1. Calendar blackout
    if calendar_blackout:
        return ScenarioResult(
            symbol=symbol, scenario=Scenario.BLOCKED,
            confidence=0, lot_penalty=0.0, blocked=True,
            blocked_reason="Calendario: evento alto impacto em blackout",
        )

    # 2. Spread filter
    if not spread_ok:
        return ScenarioResult(
            symbol=symbol, scenario=Scenario.BLOCKED,
            confidence=0, lot_penalty=0.0, blocked=True,
            blocked_reason="Spread acima do limite operacional",
        )

    # 3. VIX kill
    if not macro.tradeable:
        return ScenarioResult(
            symbol=symbol, scenario=Scenario.BLOCKED,
            confidence=0, lot_penalty=0.0, blocked=True,
            blocked_reason=f"VIX {macro.vix_regime}: mercado nao operavel",
        )

    # --- COLLECT DIRECTIONAL SCORES ---
    scores = []

    # DXY direction vs asset beta
    beta = ASSET_DXY_BETA.get(symbol, ASSET_DXY_BETA["_default"])
    if abs(macro.dxy_change_pct) > 0.001:
        dxy_effect = macro.dxy_change_pct * beta
        if dxy_effect > 0:
            scores.append(1)
            signals.append(f"DXY chg={macro.dxy_change_pct*100:+.2f}% * beta={beta:.2f} -> ALTA")
        else:
            scores.append(-1)
            signals.append(f"DXY chg={macro.dxy_change_pct*100:+.2f}% * beta={beta:.2f} -> BAIXA")

    # Yield curve
    if macro.curve_regime == "inverted":
        scores.append(-1)
        signals.append("Curva invertida: recessao iminente -> BAIXA")
    elif macro.curve_regime == "steep":
        scores.append(1)
        signals.append("Curva steep: expansao -> ALTA")

    # VIX regime
    if macro.vix_regime == "normal":
        scores.append(1)
        signals.append(f"VIX={macro.vix:.1f} normal: condicoes favoraveis")
    elif macro.vix_regime == "alert":
        scores.append(-1)
        signals.append(f"VIX={macro.vix:.1f} alert: cautela maxima -> BAIXA")
        lot_penalty = min(lot_penalty, 0.50)
    elif macro.vix_regime == "caution":
        lot_penalty = min(lot_penalty, 0.75)
        signals.append(f"VIX={macro.vix:.1f} caution: lote reduzido 25%")

    # News
    if macro.news_score == "bullish":
        scores.append(1)
        signals.append("Noticias: bullish")
    elif macro.news_score == "bearish":
        scores.append(-1)
        signals.append("Noticias: bearish")

    # 3. Technical alignment check (from signal_generator)
    if indicator_direction == "bullish":
        scores.append(1)
        signals.append("Indicadores tecnicos: bullish")
    elif indicator_direction == "bearish":
        scores.append(-1)
        signals.append("Indicadores tecnicos: bearish")
    else:
        # Not aligned with macro -> apply 65% penalty (blueprint rule)
        lot_penalty = min(lot_penalty, 0.35)
        signals.append("Sinal tecnico contrario ao macro: lote reduzido 65%")

    # Volume check
    if not volume_confirms:
        signals.append("Volume nao confirma: skip preferido")

    # 4. Correlation penalty (blueprint rule 3)
    if correlation_matrix and open_position_symbols:
        corr_penalty = correlation_matrix.correlation_penalty(symbol, open_position_symbols)
        lot_penalty = min(lot_penalty, corr_penalty)
        if corr_penalty < 1.0:
            signals.append(f"Correlacao elevada com posicao aberta: lote reduzido {corr_penalty*100:.0f}%")

    # --- VERDICT ---
    total = sum(scores)
    confidence = min(10, abs(total) * 2)

    if total >= 3:
        scenario = Scenario.BULL
    elif total <= -3:
        scenario = Scenario.BEAR
    elif total >= 1:
        scenario = Scenario.BULL
        confidence = min(confidence, 5)
    elif total <= -1:
        scenario = Scenario.BEAR
        confidence = min(confidence, 5)
    elif total == 0 and macro.vix < 15:
        scenario = Scenario.LATERAL
    else:
        scenario = Scenario.UNDEFINED

    return ScenarioResult(
        symbol=symbol,
        scenario=scenario,
        confidence=confidence,
        lot_penalty=round(lot_penalty, 2),
        signals=signals,
    )
