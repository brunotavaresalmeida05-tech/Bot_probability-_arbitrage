from __future__ import annotations
"""
Order Manager — V9.1

Sends orders to MT5 with structured 3-level TP (40 / 35 / 25 % of lots).

Open flow:
  1. ProfessionalRiskManager.can_open()  — risk gate
  2. ProfessionalRiskManager.size_position() — lot calculation
  3. Get live price from MT5 (ask for buy, bid for sell)
  4. Build SL = price +/- sl_distance
  5. CapitalManagerV2.get_tp_levels() — TP1 / TP2 / runner
  6. Split lots into [40%, 35%, 25%] — floor-normalised per MT5 volume_step
  7. Send 3 orders (or fewer if account is netting / lots too small)

Fallback chain:
  - 3 orders impossible → 2 orders (TP1 + runner, split 60/40)
  - 2 orders impossible → 1 order with TP1 level (still better than ATR×3)
  - CM not available  → 1 order with original tp_distance

Runner (3rd order) has no fixed TP (tp=0.0) — to be trailed by Phase-9D
active management loop.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.risk.professional_risk import ProfessionalRiskManager, SizeResult

if TYPE_CHECKING:
    from src.engine.capital_manager import CapitalManagerV2

logger = logging.getLogger(__name__)

MAGIC = 20260902

# Lot split percentages [TP1, TP2, runner]
_SPLIT = [0.40, 0.35, 0.25]
# Minimum pct of total lots each slice must represent before we collapse to fewer orders
_MIN_SLICE_PCT = 0.20


@dataclass
class OrderResult:
    success: bool
    symbol: str
    direction: str
    lots: float
    entry: float
    sl: float
    tp: float
    ticket: int = 0
    reason: str = ""
    timestamp: str = ""
    # structured TP metadata (populated when 3-level executed)
    tp2: float = 0.0
    runner_ticket: int = 0
    orders_sent: int = 1


class OrderManager:
    """
    Professional order execution with structured 3-level TP support.
    """

    def __init__(
        self,
        mt5,
        risk: ProfessionalRiskManager,
        dry_run: bool = True,
        cm: "CapitalManagerV2 | None" = None,
    ):
        self._mt5      = mt5
        self._risk     = risk
        self._dry_run  = dry_run
        self._cm       = cm

    # ── Public API ─────────────────────────────────────────────────────────

    def open_position(
        self,
        symbol: str,
        direction: str,          # "buy" | "sell"
        sl_distance: float,
        tp_distance: float | None = None,
        point_value: float = 1.0,
        comment: str = "V9",
        atr: float = 0.0,
        nearest_res: float | None = None,
        second_res: float | None = None,
        lot_multiplier: float = 1.0,
    ) -> OrderResult:
        """
        Open a position with structured 3-level TP when possible.

        atr          — ATR of the primary timeframe; drives TP1/TP2 if no resistance levels
        nearest_res  — MACD nearest resistance (buy) or support (sell); used as TP1 target
        second_res   — second resistance/support; used as TP2 target
        lot_multiplier — signal quality multiplier [0,1]; 0 = skip execution
        """
        ts = datetime.now(timezone.utc).isoformat()

        if lot_multiplier <= 0.0:
            return OrderResult(False, symbol, direction, 0, 0, 0, 0,
                               reason=f"lot_multiplier={lot_multiplier:.3f} — signal blocked",
                               timestamp=ts)

        allowed, reason = self._risk.can_open(symbol, direction)
        if not allowed:
            logger.warning(f"ORDER BLOCKED {symbol} {direction}: {reason}")
            return OrderResult(False, symbol, direction, 0, 0, 0, 0, reason=reason, timestamp=ts)

        sizing: SizeResult = self._risk.size_position(symbol, sl_distance, point_value)
        if sizing.blocked:
            return OrderResult(False, symbol, direction, 0, 0, 0, 0,
                               reason=sizing.reason, timestamp=ts)

        # Apply signal quality multiplier to lot size
        if lot_multiplier < 1.0:
            adjusted = sizing.lots * lot_multiplier
            sym_min = self._symbol_min_vol(symbol)
            sizing.lots = round(max(sym_min, adjusted), 4)

        # Live price
        price = self._get_price(symbol, direction)
        if price is None:
            return OrderResult(False, symbol, direction, 0, 0, 0, 0,
                               reason="No tick from MT5", timestamp=ts)

        # Enforce MT5 minimum stop distance (prevents retcode=10016)
        sl_distance = self._enforce_min_stop(symbol, sl_distance)

        sl = round(
            price - sl_distance if direction == "buy" else price + sl_distance,
            5,
        )
        # TP must also respect minimum stop distance; enforce RRR >= 1.5 on fallback
        effective_tp_dist = max(tp_distance or 0.0, sl_distance * 1.5)
        effective_tp_dist = self._enforce_min_stop(symbol, effective_tp_dist)
        fallback_tp = round(
            price + effective_tp_dist if direction == "buy"
            else price - effective_tp_dist,
            5,
        )

        # ── Try structured 3-level TP ──────────────────────────────────────
        if self._cm is not None and atr > 0:
            tp_lvls = self._cm.get_tp_levels(
                entry=price,
                direction=direction,
                sl=sl,
                atr=atr,
                nearest_res=nearest_res,
                second_res=second_res,
            )
            if tp_lvls and tp_lvls.get("rrr_tp1", 0) >= 1.5:
                result = self._open_structured(
                    symbol=symbol,
                    direction=direction,
                    total_lots=sizing.lots,
                    price=price,
                    sl=sl,
                    tp_lvls=tp_lvls,
                    sizing=sizing,
                    comment=comment,
                    ts=ts,
                )
                if result is not None:
                    return result

        # ── Fallback: single order, TP1 level if available ─────────────────
        if self._cm is not None and atr > 0:
            tp_lvls = self._cm.get_tp_levels(
                entry=price, direction=direction, sl=sl, atr=atr,
                nearest_res=nearest_res, second_res=second_res,
            )
            single_tp = tp_lvls["tp1"] if (tp_lvls and tp_lvls.get("rrr_tp1", 0) >= 1.5) else fallback_tp
        else:
            single_tp = fallback_tp

        return self._send_order(
            symbol=symbol, direction=direction, lots=sizing.lots,
            price=price, sl=sl, tp=single_tp,
            sizing=sizing, comment=comment, ts=ts,
        )

    def close_position(self, symbol: str, ticket: int = 0, reason: str = "") -> bool:
        logger.info(f"CLOSE {symbol} ticket={ticket} reason={reason}")
        if self._dry_run:
            self._risk.register_close(symbol, pnl=0.0)
            return True
        try:
            import MetaTrader5 as mt5lib
            positions = mt5lib.positions_get(symbol=symbol) or []
            closed = False
            for pos in positions:
                if ticket and pos.ticket != ticket:
                    continue
                direction = "sell" if pos.type == mt5lib.POSITION_TYPE_BUY else "buy"
                order_type = mt5lib.ORDER_TYPE_SELL if direction == "sell" else mt5lib.ORDER_TYPE_BUY
                tick = mt5lib.symbol_info_tick(symbol)
                close_price = tick.bid if direction == "sell" else tick.ask
                request = {
                    "action":       mt5lib.TRADE_ACTION_DEAL,
                    "symbol":       symbol,
                    "volume":       pos.volume,
                    "type":         order_type,
                    "position":     pos.ticket,
                    "price":        close_price,
                    "deviation":    20,
                    "magic":        MAGIC,
                    "comment":      f"close:{reason}",
                    "type_time":    mt5lib.ORDER_TIME_GTC,
                    "type_filling": mt5lib.ORDER_FILLING_IOC,
                }
                res = mt5lib.order_send(request)
                if res and res.retcode == mt5lib.TRADE_RETCODE_DONE:
                    self._risk.register_close(symbol, pos.profit)
                    closed = True
            return closed
        except Exception as e:
            logger.exception(f"Close error {symbol}: {e}")
            return False

    # ── Internal ───────────────────────────────────────────────────────────

    def _open_structured(
        self,
        symbol: str,
        direction: str,
        total_lots: float,
        price: float,
        sl: float,
        tp_lvls: dict,
        sizing: SizeResult,
        comment: str,
        ts: str,
    ) -> OrderResult | None:
        """
        Send up to 3 orders (TP1 / TP2 / runner).
        Returns None if splitting is not feasible (caller falls back to single).
        """
        try:
            import MetaTrader5 as mt5lib
            info = mt5lib.symbol_info(symbol)
            if info is None:
                return None
            min_vol  = float(info.volume_min)
            vol_step = float(info.volume_step)
        except Exception:
            min_vol  = 0.01
            vol_step = 0.01

        tp1 = round(float(tp_lvls["tp1"]), 5)
        tp2 = round(float(tp_lvls["tp2"]), 5)

        lots1, lots2, lots3 = self._split_lots(total_lots, _SPLIT, vol_step, min_vol)

        # Need at least the first slice to be viable
        if lots1 < min_vol:
            return None

        orders_sent = 0
        primary: OrderResult | None = None

        # ── Order 1 — TP1 (40%) ───────────────────────────────────────────
        r1 = self._send_order(
            symbol=symbol, direction=direction, lots=lots1,
            price=price, sl=sl, tp=tp1,
            sizing=sizing, comment=f"{comment}:tp1", ts=ts,
            register=True,
        )
        if not r1.success:
            return r1   # if primary fails, abort (return failure)
        primary = r1
        orders_sent += 1

        # ── Order 2 — TP2 (35%) ───────────────────────────────────────────
        if lots2 >= min_vol:
            r2 = self._send_order(
                symbol=symbol, direction=direction, lots=lots2,
                price=price, sl=sl, tp=tp2,
                sizing=sizing, comment=f"{comment}:tp2", ts=ts,
                register=False,   # don't double-register in risk state
            )
            if r2.success:
                primary.tp2 = tp2
                orders_sent += 1
            else:
                logger.warning(f"[ORDER] TP2 order failed for {symbol}: {r2.reason}")

        # ── Order 3 — Runner (25%), no fixed TP ───────────────────────────
        if lots3 >= min_vol:
            r3 = self._send_order(
                symbol=symbol, direction=direction, lots=lots3,
                price=price, sl=sl, tp=0.0,   # no TP: managed by trailing
                sizing=sizing, comment=f"{comment}:run", ts=ts,
                register=False,
            )
            if r3.success:
                primary.runner_ticket = r3.ticket
                orders_sent += 1
            else:
                logger.warning(f"[ORDER] Runner order failed for {symbol}: {r3.reason}")

        primary.orders_sent = orders_sent
        logger.info(
            f"[STRUCTURED] {direction.upper()} {symbol} "
            f"orders={orders_sent} lots=[{lots1}/{lots2}/{lots3}] "
            f"sl={sl} tp1={tp1} tp2={tp2} rrr1={tp_lvls.get('rrr_tp1'):.2f}"
        )
        return primary

    def _send_order(
        self,
        symbol: str,
        direction: str,
        lots: float,
        price: float,
        sl: float,
        tp: float,
        sizing: SizeResult,
        comment: str,
        ts: str,
        register: bool = True,
    ) -> OrderResult:
        if self._dry_run:
            logger.info(
                f"[DRY RUN] {direction.upper()} {symbol} "
                f"lots={lots} entry={price:.5f} sl={sl:.5f} tp={tp:.5f} "
                f"risk={sizing.risk_pct*100:.2f}% tier={sizing.tier}"
            )
            if register:
                self._risk.register_open(symbol, direction, lots, price, sl)
            return OrderResult(True, symbol, direction, lots, price, sl, tp,
                               ticket=0, timestamp=ts)

        try:
            import MetaTrader5 as mt5lib
            order_type = mt5lib.ORDER_TYPE_BUY if direction == "buy" else mt5lib.ORDER_TYPE_SELL

            # Final guard: ensure SL and TP meet broker minimum stop distance
            min_dist = self._enforce_min_stop(symbol, 0.0)  # get minimum
            if min_dist > 0:
                sl_dist = abs(price - sl)
                if sl_dist < min_dist:
                    sl = round(price - min_dist if direction == "buy" else price + min_dist, 5)
                if tp:
                    tp_dist = abs(price - tp)
                    if tp_dist < min_dist:
                        tp = round(price + min_dist * 1.5 if direction == "buy" else price - min_dist * 1.5, 5)

            request = {
                "action":       mt5lib.TRADE_ACTION_DEAL,
                "symbol":       symbol,
                "volume":       lots,
                "type":         order_type,
                "price":        price,
                "sl":           round(sl, 5),
                "tp":           round(tp, 5) if tp else 0.0,
                "deviation":    20,
                "magic":        MAGIC,
                "comment":      comment,
                "type_time":    mt5lib.ORDER_TIME_GTC,
                "type_filling": mt5lib.ORDER_FILLING_IOC,
            }
            result = mt5lib.order_send(request)
            if result and result.retcode == mt5lib.TRADE_RETCODE_DONE:
                if register:
                    self._risk.register_open(symbol, direction, lots, price, sl)
                logger.info(
                    f"ORDER OK {direction.upper()} {symbol} ticket={result.order} "
                    f"lots={lots} entry={price:.5f} sl={sl:.5f} tp={tp:.5f}"
                )
                return OrderResult(True, symbol, direction, lots, price, sl, tp,
                                   ticket=result.order, timestamp=ts)
            else:
                reason = f"MT5 retcode={result.retcode if result else 'None'}"
                logger.error(f"ORDER FAIL {symbol} {direction}: {reason}")
                return OrderResult(False, symbol, direction, 0, 0, 0, 0,
                                   reason=reason, timestamp=ts)
        except Exception as e:
            logger.exception(f"Order send error {symbol}: {e}")
            return OrderResult(False, symbol, direction, 0, 0, 0, 0,
                               reason=str(e), timestamp=ts)

    def _symbol_min_vol(self, symbol: str) -> float:
        """Return the symbol's MT5 minimum volume (volume_min), fallback to 0.01."""
        try:
            import MetaTrader5 as mt5lib
            info = mt5lib.symbol_info(symbol)
            if info and info.volume_min > 0:
                return float(info.volume_min)
        except Exception:
            pass
        return getattr(self._risk, "_min_lot", 0.01)

    def _enforce_min_stop(self, symbol: str, sl_distance: float) -> float:
        """Expand sl_distance to meet MT5's minimum stop distance (prevents retcode=10016).

        When trade_stops_level=0 (dynamic broker minimum) uses spread×2 as floor.
        """
        if self._dry_run:
            return sl_distance
        try:
            import MetaTrader5 as mt5lib
            info = mt5lib.symbol_info(symbol)
            if info and info.point > 0:
                stops_pts = max(int(getattr(info, "trade_stops_level", 0)), 0)
                spread_pts = max(int(getattr(info, "spread", 1)), 1)
                # Minimum = max(broker freeze level, 2×spread) + 5pt buffer
                min_pts = max(stops_pts, spread_pts * 2) + 5
                min_dist = min_pts * info.point
                if sl_distance < min_dist:
                    logger.debug(
                        f"[MINSTOP] {symbol}: {sl_distance:.6f} → {min_dist:.6f} "
                        f"(stops={stops_pts} spread={spread_pts}pts)"
                    )
                    return min_dist
        except Exception:
            pass
        return sl_distance

    def _get_price(self, symbol: str, direction: str) -> float | None:
        try:
            import MetaTrader5 as mt5lib
            tick = mt5lib.symbol_info_tick(symbol)
            if not tick:
                return None
            return tick.ask if direction == "buy" else tick.bid
        except Exception as e:
            logger.debug(f"Tick error {symbol}: {e}")
            return None

    @staticmethod
    def _split_lots(
        total: float,
        splits: list[float],
        step: float,
        min_vol: float,
    ) -> tuple[float, float, float]:
        """
        Divide total lots into 3 floor-normalised slices.
        Remainder (from floor rounding) goes to the first slice.

        Returns (lots1, lots2, lots3).
        Any slice below min_vol is returned as 0.0.
        """
        dp = max(0, round(-math.log10(step))) if step < 1 else 2

        def _floor(x: float) -> float:
            return round(math.floor(x / step) * step, dp)

        l2 = _floor(total * splits[1])
        l3 = _floor(total * splits[2])
        l1 = round(total - l2 - l3, dp)   # first slice absorbs rounding remainder
        l1 = _floor(l1)                    # still floor it

        # Zero out slices below minimum
        if l2 < min_vol: l2 = 0.0
        if l3 < min_vol: l3 = 0.0
        if l1 < min_vol: l1 = 0.0

        return l1, l2, l3
