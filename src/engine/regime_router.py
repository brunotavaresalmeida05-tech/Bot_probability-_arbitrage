from __future__ import annotations
"""
Regime Router — V9.1

Detects market regime from technical indicators (ADX + price structure).
Macro is CONTEXT only (adjusts lot_context), not a veto.

Three regimes:
  TRENDING_UP   — ADX >= 25, bullish structure (MA50>MA100 + indicators agree)
  TRENDING_DOWN — ADX >= 25, bearish structure
  RANGING       — ADX < 20 or direction neutral
  VOLATILE      — ATR ratio > 2.0 or VIX >= alert threshold

Decision tree:
  1. VIX panic/kill → VOLATILE (lot_context=0.0)
  2. ATR ratio > 2.0 → VOLATILE (lot_context=0.25)
  3. ADX >= 25 + clear direction → TRENDING (lot_context=1.0)
  4. ADX 20-25 + clear direction → TRENDING with caution (lot_context=0.85)
  5. else → RANGING (lot_context=0.75)

Macro influence: adjusts lot_context only, never blocks.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum

from src.technical.indicators import IndicatorBundle
from src.macro.macro_context import MacroContext

logger = logging.getLogger(__name__)

# ADX thresholds
ADX_TRENDING = 25.0
ADX_RANGING  = 20.0

# VIX thresholds for volatility detection
VIX_VOLATILE_THRESHOLD = 30.0


class RegimeState(str, Enum):
    TRENDING_UP   = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING       = "RANGING"
    VOLATILE      = "VOLATILE"


@dataclass
class RegimeResult:
    state: RegimeState
    direction: str          # "bullish" | "bearish" | "neutral"
    confidence: float       # 0.0 - 1.0
    adx: float
    lot_context: float      # 1.0=normal, 0.85=borderline, 0.75=ranging, 0.25=volatile, 0.0=extreme
    rationale: list[str] = field(default_factory=list)


def detect(bundle: IndicatorBundle, macro: MacroContext | None = None) -> RegimeResult:
    """
    Determine market regime from bundle indicators.
    Macro adjusts lot_context but does not change state.
    """
    rationale: list[str] = []

    adx = bundle.adx if bundle.adx > 0 else 20.0

    # ── Direction voting ────────────────────────────────────────────────
    bull = 0
    bear = 0

    # MA structure (highest weight — structural)
    ma50  = bundle.ma50  or 0.0
    ma100 = bundle.ma100 or 0.0
    if ma50 > 0 and ma100 > 0:
        if ma50 > ma100:
            bull += 2
            rationale.append(f"MA50({ma50:.5f})>MA100({ma100:.5f}) estrutura bullish")
        else:
            bear += 2
            rationale.append(f"MA50({ma50:.5f})<MA100({ma100:.5f}) estrutura bearish")

    # ATR Stop (Chandelier)
    if bundle.atr_stop:
        if bundle.atr_stop.direction == "bullish":
            bull += 1
        elif bundle.atr_stop.direction == "bearish":
            bear += 1

    # MACD
    if bundle.macd:
        if bundle.macd.direction == "bullish":
            bull += 1
        elif bundle.macd.direction == "bearish":
            bear += 1

    # Determine direction
    if bull > bear and bull >= 2:
        direction = "bullish"
        rationale.append(f"direcao=bullish ({bull}bull/{bear}bear)")
    elif bear > bull and bear >= 2:
        direction = "bearish"
        rationale.append(f"direcao=bearish ({bear}bear/{bull}bull)")
    else:
        direction = "neutral"
        rationale.append(f"direcao=neutral ({bull}bull/{bear}bear)")

    # ── VIX-based volatility check ──────────────────────────────────────
    vix = macro.vix if macro else 20.0
    vix_regime = macro.vix_regime if macro else "normal"

    if vix_regime in ("kill", "panic"):
        state = RegimeState.VOLATILE
        lot_context = 0.0
        confidence = 0.9
        rationale.append(f"VIX {vix_regime}: VOLATILE lot_context=0.0")
        return RegimeResult(
            state=state, direction=direction, confidence=confidence,
            adx=adx, lot_context=lot_context, rationale=rationale,
        )

    if vix >= VIX_VOLATILE_THRESHOLD:
        state = RegimeState.VOLATILE
        lot_context = 0.25
        confidence = 0.8
        rationale.append(f"VIX={vix:.1f}>={VIX_VOLATILE_THRESHOLD}: VOLATILE")
        _apply_macro_lot(rationale, macro, lot_context)
        return RegimeResult(
            state=state, direction=direction, confidence=confidence,
            adx=adx, lot_context=lot_context, rationale=rationale,
        )

    # ── ADX-based trend / range detection ──────────────────────────────
    if adx >= ADX_TRENDING and direction in ("bullish", "bearish"):
        state = RegimeState.TRENDING_UP if direction == "bullish" else RegimeState.TRENDING_DOWN
        lot_context = 1.0
        confidence = min(1.0, adx / 40.0)
        rationale.append(f"ADX={adx:.1f}>={ADX_TRENDING}: TRENDING")
    elif adx >= ADX_RANGING and direction in ("bullish", "bearish"):
        state = RegimeState.TRENDING_UP if direction == "bullish" else RegimeState.TRENDING_DOWN
        lot_context = 0.85
        confidence = 0.5
        rationale.append(f"ADX={adx:.1f} borderline TRENDING (lot=0.85)")
    else:
        state = RegimeState.RANGING
        lot_context = 0.75
        confidence = min(1.0, (ADX_RANGING - adx) / ADX_RANGING) if adx < ADX_RANGING else 0.3
        rationale.append(f"ADX={adx:.1f}<{ADX_TRENDING}: RANGING")

    # ── Macro context: adjust lot_context (context only, not veto) ──────
    lot_context = _apply_macro_lot(rationale, macro, lot_context)

    return RegimeResult(
        state=state,
        direction=direction,
        confidence=round(confidence, 3),
        adx=round(adx, 2),
        lot_context=round(lot_context, 2),
        rationale=rationale,
    )


def _apply_macro_lot(
    rationale: list[str],
    macro: MacroContext | None,
    lot_context: float,
) -> float:
    """Apply VIX caution/alert to lot_context. Returns adjusted value."""
    if macro is None:
        return lot_context
    if macro.vix_regime == "alert":
        lot_context = min(lot_context, 0.50)
        rationale.append(f"VIX alert: lot_context reduzido para {lot_context:.2f}")
    elif macro.vix_regime == "caution":
        lot_context = min(lot_context, 0.75)
        rationale.append(f"VIX caution: lot_context reduzido para {lot_context:.2f}")
    return lot_context
