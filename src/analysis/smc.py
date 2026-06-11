from __future__ import annotations
"""
SMC Layer — Smart Money Concepts (Phase 9B)

Order Blocks   : last opposite candle before an impulsive displacement
Fair Value Gaps: 3-candle imbalances left by fast moves
BOS / ChoCh    : swing-level structure breaks (continuation vs reversal)
Liquidity Sweeps: stop-hunt wicks beyond swing highs/lows with recovery
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class OrderBlock:
    top: float
    bottom: float
    direction: str      # "bullish" = support zone | "bearish" = resistance zone
    index: int
    strength: float     # OB body size / ATR
    mitigated: bool     # True once price re-enters the zone after displacement


@dataclass
class FairValueGap:
    top: float
    bottom: float
    direction: str      # "bullish" | "bearish"
    index: int
    filled: bool        # True once price re-enters the gap


@dataclass
class StructureBreak:
    kind: str           # "BOS" (trend continuation) | "ChoCh" (reversal)
    direction: str      # "bullish" | "bearish"
    level: float        # swing level that was broken
    index: int          # bar that closed beyond the level


@dataclass
class LiquiditySweep:
    direction: str      # "bullish" (lows swept, bear stops taken) | "bearish"
    level: float
    index: int


@dataclass
class SMCResult:
    order_blocks: list[OrderBlock] = field(default_factory=list)
    fvgs: list[FairValueGap] = field(default_factory=list)
    structure_breaks: list[StructureBreak] = field(default_factory=list)
    liquidity_sweeps: list[LiquiditySweep] = field(default_factory=list)
    # Fast-path booleans consumed by signal_generator (checks 9–11)
    bullish_ob_nearby: bool = False     # unmitigated bullish OB at current price
    bearish_ob_nearby: bool = False
    bullish_fvg: bool = False           # unmitigated bullish FVG near current price
    bearish_fvg: bool = False
    last_bos: str | None = None         # "bullish" | "bearish" | None
    last_choch: str | None = None       # "bullish" | "bearish" | None
    sweep_recent: str | None = None     # "bullish" | "bearish" | None


# ── Swing detection ──────────────────────────────────────────────────────────

def _swing_highs(arr: np.ndarray, left: int = 3, right: int = 3) -> list[int]:
    """Return indices of local swing highs (highest value in left+right window)."""
    n = len(arr)
    result: list[int] = []
    for i in range(left, n - right):
        if arr[i] >= arr[i - left:i].max() and arr[i] >= arr[i + 1:i + right + 1].max():
            result.append(i)
    return result


def _swing_lows(arr: np.ndarray, left: int = 3, right: int = 3) -> list[int]:
    """Return indices of local swing lows (lowest value in left+right window)."""
    n = len(arr)
    result: list[int] = []
    for i in range(left, n - right):
        if arr[i] <= arr[i - left:i].min() and arr[i] <= arr[i + 1:i + right + 1].min():
            result.append(i)
    return result


# ── Order Blocks ─────────────────────────────────────────────────────────────

def _find_order_blocks(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    atr: float,
    lookback: int = 50,
) -> list[OrderBlock]:
    """
    An Order Block is the last candle opposite to a displacement.
    Displacement threshold: body >= ATR × 0.7.
    Direction convention:
      bullish OB = last bearish candle before a bullish impulse → support zone
      bearish OB = last bullish candle before a bearish impulse → resistance zone
    """
    if atr <= 0:
        return []

    n = len(closes)
    start = max(0, n - lookback)
    thresh = atr * 0.7
    seen: set[int] = set()
    obs: list[OrderBlock] = []

    for i in range(start + 1, n):
        body = closes[i] - opens[i]
        if abs(body) < thresh:
            continue
        disp_dir = "bullish" if body > 0 else "bearish"

        # Walk backward for the last candle of the opposite color
        for j in range(i - 1, max(start - 1, 0), -1):
            if j in seen:
                continue
            prev_body = closes[j] - opens[j]
            if prev_body == 0.0:
                continue
            is_opposite = (
                (disp_dir == "bullish" and prev_body < 0) or
                (disp_dir == "bearish" and prev_body > 0)
            )
            if not is_opposite:
                continue

            top    = round(float(max(opens[j], closes[j])), 5)
            bottom = round(float(min(opens[j], closes[j])), 5)
            # OB direction matches displacement (bullish displacement → bullish OB = support)
            ob_dir = disp_dir
            strength = round(abs(prev_body) / atr, 3)

            # Mitigation: any bar after the displacement whose range overlaps the OB body
            mitigated = any(
                lows[k] <= top and highs[k] >= bottom
                for k in range(i + 1, n)
            )

            seen.add(j)
            obs.append(OrderBlock(
                top=top, bottom=bottom, direction=ob_dir,
                index=j, strength=strength, mitigated=mitigated,
            ))
            break

    return obs


# ── Fair Value Gaps ──────────────────────────────────────────────────────────

def _find_fvgs(
    highs: np.ndarray,
    lows: np.ndarray,
    lookback: int = 50,
) -> list[FairValueGap]:
    """
    3-candle FVG:
      bullish: candle[i].low > candle[i-2].high  (gap above i-2, below i)
      bearish: candle[i].high < candle[i-2].low  (gap below i-2, above i)
    """
    n = len(lows)
    start = max(2, n - lookback)
    fvgs: list[FairValueGap] = []

    for i in range(start, n):
        # Bullish FVG: gap between previous candle's high and current candle's low
        if lows[i] > highs[i - 2]:
            gap_top    = float(lows[i])
            gap_bottom = float(highs[i - 2])
            filled = any(
                lows[k] <= gap_top and highs[k] >= gap_bottom
                for k in range(i + 1, n)
            )
            fvgs.append(FairValueGap(
                top=round(gap_top, 5), bottom=round(gap_bottom, 5),
                direction="bullish", index=i, filled=filled,
            ))

        # Bearish FVG
        elif highs[i] < lows[i - 2]:
            gap_top    = float(lows[i - 2])
            gap_bottom = float(highs[i])
            filled = any(
                lows[k] <= gap_top and highs[k] >= gap_bottom
                for k in range(i + 1, n)
            )
            fvgs.append(FairValueGap(
                top=round(gap_top, 5), bottom=round(gap_bottom, 5),
                direction="bearish", index=i, filled=filled,
            ))

    return fvgs


# ── Structure Breaks (BOS / ChoCh) ──────────────────────────────────────────

def _find_structure_breaks(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    lookback: int = 80,
) -> list[StructureBreak]:
    """
    BOS  = close breaks a swing level in the same direction as prior trend
           (prior swing structure confirms continuation)
    ChoCh= close breaks a swing level opposite to prior trend
           (structure reversal)
    Each swing level is only broken once (deduplicated).
    """
    n = len(closes)
    start = max(0, n - lookback)

    sub_h = highs[start:]
    sub_l = lows[start:]

    sh_rel = _swing_highs(sub_h)
    sl_rel = _swing_lows(sub_l)

    # Absolute indices
    sh_idx = sorted(i + start for i in sh_rel)
    sl_idx = sorted(i + start for i in sl_rel)

    broken_sh: set[int] = set()
    broken_sl: set[int] = set()
    breaks: list[StructureBreak] = []

    for i in range(start + 1, n):
        # Check breaks above unbroken swing highs
        for sh_i in sh_idx:
            if sh_i >= i or sh_i in broken_sh:
                continue
            if closes[i] > highs[sh_i]:
                # Prior trend: compare this SH to the preceding SH
                prev_sh = [j for j in sh_idx if j < sh_i]
                kind = "BOS" if (prev_sh and highs[sh_i] > highs[prev_sh[-1]]) else "ChoCh"
                breaks.append(StructureBreak(
                    kind=kind, direction="bullish",
                    level=round(float(highs[sh_i]), 5), index=i,
                ))
                broken_sh.add(sh_i)

        # Check breaks below unbroken swing lows
        for sl_i in sl_idx:
            if sl_i >= i or sl_i in broken_sl:
                continue
            if closes[i] < lows[sl_i]:
                prev_sl = [j for j in sl_idx if j < sl_i]
                kind = "BOS" if (prev_sl and lows[sl_i] < lows[prev_sl[-1]]) else "ChoCh"
                breaks.append(StructureBreak(
                    kind=kind, direction="bearish",
                    level=round(float(lows[sl_i]), 5), index=i,
                ))
                broken_sl.add(sl_i)

    return breaks


# ── Liquidity Sweeps ─────────────────────────────────────────────────────────

def _find_liquidity_sweeps(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    atr: float,
    lookback: int = 60,
) -> list[LiquiditySweep]:
    """
    Bullish sweep: wick extends below a recent swing low but close recovers above it.
    Bearish sweep: wick extends above a recent swing high but close drops back below.
    Minimum recovery body: ATR × 0.3 (so the candle actually reversed, not just hovered).
    """
    n = len(closes)
    start = max(0, n - lookback)

    sub_h = highs[start:]
    sub_l = lows[start:]

    sh_rel = _swing_highs(sub_h)
    sl_rel = _swing_lows(sub_l)

    sh_idx = [i + start for i in sh_rel]
    sl_idx = [i + start for i in sl_rel]

    min_recovery = atr * 0.3 if atr > 0 else 0.0
    sweeps: list[LiquiditySweep] = []

    for i in range(start + 1, n):
        # Bullish sweep: wick below swing low, closes back above it
        for sl_i in sl_idx:
            if sl_i >= i:
                continue
            level = lows[sl_i]
            if lows[i] < level and closes[i] > level + min_recovery:
                sweeps.append(LiquiditySweep(
                    direction="bullish",
                    level=round(float(level), 5),
                    index=i,
                ))
                break  # one sweep per candle

        # Bearish sweep: wick above swing high, closes back below it
        for sh_i in sh_idx:
            if sh_i >= i:
                continue
            level = highs[sh_i]
            if highs[i] > level and closes[i] < level - min_recovery:
                sweeps.append(LiquiditySweep(
                    direction="bearish",
                    level=round(float(level), 5),
                    index=i,
                ))
                break


    return sweeps


# ── Public entry point ───────────────────────────────────────────────────────

def analyze(df: pd.DataFrame, atr: float = 0.0) -> SMCResult:
    """
    Compute all SMC elements from an OHLCV DataFrame.
    Returns SMCResult with both raw structures and fast-path boolean summaries.
    """
    if df is None or len(df) < 10:
        return SMCResult()

    opens  = df["open"].to_numpy(dtype=float)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    price  = closes[-1]

    obs     = _find_order_blocks(opens, highs, lows, closes, atr)
    fvgs    = _find_fvgs(highs, lows)
    breaks  = _find_structure_breaks(highs, lows, closes)
    sweeps  = _find_liquidity_sweeps(highs, lows, closes, atr)

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

    last_bos: str | None = None
    last_choch: str | None = None
    for sb in reversed(breaks):
        if sb.kind == "BOS" and last_bos is None:
            last_bos = sb.direction
        elif sb.kind == "ChoCh" and last_choch is None:
            last_choch = sb.direction
        if last_bos is not None and last_choch is not None:
            break

    sweep_recent = sweeps[-1].direction if sweeps else None

    return SMCResult(
        order_blocks=obs,
        fvgs=fvgs,
        structure_breaks=breaks,
        liquidity_sweeps=sweeps,
        bullish_ob_nearby=bullish_ob_nearby,
        bearish_ob_nearby=bearish_ob_nearby,
        bullish_fvg=bullish_fvg,
        bearish_fvg=bearish_fvg,
        last_bos=last_bos,
        last_choch=last_choch,
        sweep_recent=sweep_recent,
    )


# ── Regime-aware SMC scoring ──────────────────────────────────────────────────

def _raw_smc_scores(smc: SMCResult) -> tuple[float, float]:
    """
    Base SMC scores from boolean signals.

    Weights reflect SMC signal hierarchy:
      OB   = 0.40  (institutionally validated zone)
      BOS  = 0.35  (structural confirmation)
      FVG  = 0.25  (imbalance fill — weaker alone, strong with OB)
    """
    bull = 0.0
    bear = 0.0
    if smc.bullish_ob_nearby:  bull += 0.40
    if smc.last_bos == "bullish": bull += 0.35
    if smc.bullish_fvg:        bull += 0.25
    if smc.bearish_ob_nearby:  bear += 0.40
    if smc.last_bos == "bearish": bear += 0.35
    if smc.bearish_fvg:        bear += 0.25
    return min(bull, 1.0), min(bear, 1.0)


def smc_score_with_regime_context(
    smc: SMCResult,
    regime: str,
    adx: float = 20.0,
) -> tuple[float, float]:
    """
    Scale raw SMC scores based on market regime.

    RANGING      — OBs and FVGs are most reliable (full weight).
    TRENDING_*   — BOS/ChoCh dominate; align with trend (+15%), fade against (-40%).
    VOLATILE     — no new SMC signals (positions managed by trailing/TP only).

    Returns (bull_score, bear_score) in [0.0, 1.0].
    """
    bull, bear = _raw_smc_scores(smc)

    if regime == "RANGING":
        return bull, bear

    if regime == "TRENDING_UP":
        bull = min(bull * 1.15, 1.0)
        bear = bear * 0.60
        return bull, bear

    if regime == "TRENDING_DOWN":
        bear = min(bear * 1.15, 1.0)
        bull = bull * 0.60
        return bull, bear

    # VOLATILE or unknown — SMC does not generate new entries
    return 0.0, 0.0
