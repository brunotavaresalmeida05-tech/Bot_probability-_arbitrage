from __future__ import annotations
"""
Execution Validator — V9

Gates final order submission with:
  1. R:R validation (minimum ratio required)
  2. Slippage / execution cost estimate
  3. MFE/MAE tracking (post-trade quality)
  4. Spread check vs volatility

The system should never enter a trade where:
  - R:R < minimum after deducting execution costs
  - Spread represents > X% of the expected move
  - Entry price is too far from fair value (chasing)

Formula:
  ExecutionCost = Spread + Slippage + Fees
  Net_TP = TP - ExecutionCost
  Net_SL = SL + ExecutionCost
  Net_RR = Net_TP / Net_SL
"""
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExecutionCost:
    spread_pct: float       # spread as % of price
    slippage_pct: float     # expected slippage as % of price
    fee_pct: float          # commission/fee as % (often 0 for CFDs)
    total_pct: float        # total cost as % of price
    total_points: float     # total cost in price points


@dataclass
class RRResult:
    raw_rr: float           # (tp - entry) / (entry - sl)
    net_rr: float           # after deducting execution cost
    sl_distance: float
    tp_distance: float
    execution_cost: ExecutionCost
    acceptable: bool        # True if net R:R >= minimum
    reason: str = ""


@dataclass
class MFEMAERecord:
    symbol: str
    direction: str
    entry: float
    sl: float
    tp: float
    mfe: float = 0.0    # Maximum Favorable Excursion
    mae: float = 0.0    # Maximum Adverse Excursion
    exit_price: float = 0.0
    pnl: float = 0.0
    quality_score: float = 0.0  # MFE / (MFE + MAE)


# Default minimum R:R by asset class
_MIN_RR: dict[str, float] = {
    "forex":      1.5,
    "indices":    1.5,
    "gold":       1.5,
    "oil":        1.8,    # more volatile, need better R:R
    "treasuries": 1.3,
    "crypto":     2.0,    # higher risk needs better ratio
    "unknown":    1.5,
}

# Maximum spread as % of expected daily range (if spread > X% of ATR, skip)
_MAX_SPREAD_OF_ATR = 0.20   # 20% of ATR max


def estimate_execution_cost(
    symbol: str,
    price: float,
    spread_points: float,
    atr: float = 0.0,
    broker_fee_pct: float = 0.0,
    vix: float = 20.0,
) -> ExecutionCost:
    """
    Estimate total execution cost.
    Slippage increases with VIX (higher volatility = more slippage).
    """
    if price <= 0:
        return ExecutionCost(0, 0, 0, 0, 0)

    spread_pct = spread_points / price
    # Slippage: base 0.01% + VIX adjustment
    slippage_pct = 0.0001 + max(0, (vix - 20) / 10000)
    fee_pct = broker_fee_pct
    total_pct = spread_pct + slippage_pct + fee_pct
    total_points = total_pct * price

    return ExecutionCost(
        spread_pct=round(spread_pct, 8),
        slippage_pct=round(slippage_pct, 8),
        fee_pct=round(fee_pct, 8),
        total_pct=round(total_pct, 8),
        total_points=round(total_points, 8),
    )


def validate_rr(
    entry: float,
    sl: float,
    tp: float,
    asset_class: str = "unknown",
    execution_cost: Optional[ExecutionCost] = None,
    macro_score: float = 0.0,
) -> RRResult:
    """
    Validate Risk:Reward ratio after deducting execution costs.

    Strong macro context can lower the minimum R:R requirement slightly.
    """
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)

    if sl_dist <= 0:
        return RRResult(0.0, 0.0, 0.0, 0.0,
                        ExecutionCost(0,0,0,0,0), False, "Zero stop distance")

    raw_rr = tp_dist / sl_dist

    # Net R:R after execution cost
    if execution_cost:
        cost = execution_cost.total_points
        net_tp = tp_dist - cost   # cost reduces our profit
        net_sl = sl_dist + cost   # cost increases our loss
        net_rr = net_tp / net_sl if net_sl > 0 else 0.0
    else:
        net_rr = raw_rr
        execution_cost = ExecutionCost(0, 0, 0, 0, 0)

    # Minimum R:R (slightly relaxed with strong macro confirmation)
    min_rr = _MIN_RR.get(asset_class, 1.5)
    if macro_score > 0.7:
        min_rr *= 0.90    # 10% relaxation for very strong macro

    acceptable = net_rr >= min_rr

    reason = (
        f"R:R={net_rr:.2f} vs min={min_rr:.2f} "
        f"(raw={raw_rr:.2f}, exec_cost={execution_cost.total_points:.5f})"
    )
    if not acceptable:
        reason = f"R:R too low: " + reason

    return RRResult(
        raw_rr=round(raw_rr, 4),
        net_rr=round(net_rr, 4),
        sl_distance=round(sl_dist, 5),
        tp_distance=round(tp_dist, 5),
        execution_cost=execution_cost,
        acceptable=acceptable,
        reason=reason,
    )


def validate_spread_vs_atr(spread_points: float, atr: float) -> tuple[bool, str]:
    """
    Spread should not exceed MAX_SPREAD_OF_ATR % of ATR.
    If spread is too wide relative to ATR, the trade is not viable.
    """
    if atr <= 0:
        return True, "ATR not available"
    ratio = spread_points / atr
    ok = ratio <= _MAX_SPREAD_OF_ATR
    msg = f"Spread/ATR={ratio*100:.1f}% (max {_MAX_SPREAD_OF_ATR*100:.0f}%)"
    return ok, msg


def validate_entry_vs_fair(
    entry: float,
    fair_price: float,
    atr: float,
    max_atr_distance: float = 0.5,
) -> tuple[bool, str]:
    """
    Entry should not be more than N * ATR away from fair price.
    Prevents chasing moves already far from fair value.
    """
    if fair_price <= 0 or atr <= 0:
        return True, "Fair price/ATR not available"
    distance = abs(entry - fair_price)
    ok = distance <= max_atr_distance * atr
    msg = f"Entry vs FairPrice: {distance:.5f} vs max {max_atr_distance*atr:.5f}"
    return ok, msg


class MFEMAETracker:
    """
    Tracks Maximum Favorable/Adverse Excursion for open positions.
    Used for calibrating stops and take profits.
    """

    def __init__(self):
        self._records: dict[str, MFEMAERecord] = {}
        self._history: list[MFEMAERecord] = []

    def open(self, symbol: str, direction: str, entry: float, sl: float, tp: float):
        self._records[symbol] = MFEMAERecord(symbol, direction, entry, sl, tp)

    def update(self, symbol: str, current_price: float):
        rec = self._records.get(symbol)
        if not rec:
            return
        if rec.direction == "buy":
            fav = current_price - rec.entry
            adv = rec.entry - current_price
        else:
            fav = rec.entry - current_price
            adv = current_price - rec.entry
        rec.mfe = max(rec.mfe, fav)
        rec.mae = max(rec.mae, adv)

    def close(self, symbol: str, exit_price: float) -> Optional[MFEMAERecord]:
        rec = self._records.pop(symbol, None)
        if not rec:
            return None
        rec.exit_price = exit_price
        if rec.direction == "buy":
            rec.pnl = exit_price - rec.entry
        else:
            rec.pnl = rec.entry - exit_price
        total = rec.mfe + rec.mae
        rec.quality_score = round(rec.mfe / total, 4) if total > 0 else 0.5
        self._history.append(rec)
        return rec

    def avg_quality(self) -> float:
        """Average quality score of closed trades (0=all at MAE, 1=all at MFE)."""
        if not self._history:
            return 0.5
        return round(sum(r.quality_score for r in self._history[-50:]) / len(self._history[-50:]), 4)
