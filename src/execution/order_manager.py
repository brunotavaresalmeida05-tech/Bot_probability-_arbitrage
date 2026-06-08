from __future__ import annotations
"""
Order Manager — V9

Professional order management via MT5Bridge.
Handles open, close, and position monitoring with full logging.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from src.risk.professional_risk import ProfessionalRiskManager, SizeResult

logger = logging.getLogger(__name__)

MAGIC = 20260902    # unique magic number for V9 orders


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


class OrderManager:
    """
    Wraps MT5Bridge for professional order execution.
    All orders are gated through ProfessionalRiskManager.
    """

    def __init__(self, mt5, risk: ProfessionalRiskManager, dry_run: bool = True):
        self._mt5 = mt5
        self._risk = risk
        self._dry_run = dry_run
        self._orders_today: list[dict] = []

    def open_position(
        self,
        symbol: str,
        direction: str,     # "buy" | "sell"
        sl_distance: float,
        tp_distance: float | None = None,
        point_value: float = 1.0,
        comment: str = "V9",
    ) -> OrderResult:
        ts = datetime.now(timezone.utc).isoformat()

        # Gate: can we open?
        allowed, reason = self._risk.can_open(symbol, direction)
        if not allowed:
            logger.warning(f"ORDER BLOCKED {symbol} {direction}: {reason}")
            return OrderResult(False, symbol, direction, 0, 0, 0, 0, reason=reason, timestamp=ts)

        # Size
        sizing: SizeResult = self._risk.size_position(symbol, sl_distance, point_value)
        if sizing.blocked:
            return OrderResult(False, symbol, direction, 0, 0, 0, 0, reason=sizing.reason, timestamp=ts)

        # Get current price from MT5
        try:
            import MetaTrader5 as mt5lib
            tick = mt5lib.symbol_info_tick(symbol)
            if not tick:
                return OrderResult(False, symbol, direction, 0, 0, 0, 0, reason="No tick", timestamp=ts)
            price = tick.ask if direction == "buy" else tick.bid
        except Exception as e:
            return OrderResult(False, symbol, direction, 0, 0, 0, 0, reason=str(e), timestamp=ts)

        sl = price - sl_distance if direction == "buy" else price + sl_distance
        tp_dist = tp_distance if tp_distance else sl_distance * 2.0
        tp = price + tp_dist if direction == "buy" else price - tp_dist

        if self._dry_run:
            logger.info(
                f"[DRY RUN] {direction.upper()} {symbol} "
                f"lots={sizing.lots} entry={price:.5f} sl={sl:.5f} tp={tp:.5f} "
                f"risk={sizing.risk_pct*100:.2f}% tier={sizing.tier}"
            )
            self._risk.register_open(symbol, direction, sizing.lots, price, sl)
            return OrderResult(True, symbol, direction, sizing.lots, price, sl, tp, ticket=0, timestamp=ts)

        # Live execution
        try:
            import MetaTrader5 as mt5lib
            order_type = mt5lib.ORDER_TYPE_BUY if direction == "buy" else mt5lib.ORDER_TYPE_SELL
            request = {
                "action": mt5lib.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": sizing.lots,
                "type": order_type,
                "price": price,
                "sl": round(sl, 5),
                "tp": round(tp, 5),
                "deviation": 20,
                "magic": MAGIC,
                "comment": comment,
                "type_time": mt5lib.ORDER_TIME_GTC,
                "type_filling": mt5lib.ORDER_FILLING_IOC,
            }
            result = mt5lib.order_send(request)
            if result and result.retcode == mt5lib.TRADE_RETCODE_DONE:
                self._risk.register_open(symbol, direction, sizing.lots, price, sl)
                logger.info(
                    f"ORDER OK {direction.upper()} {symbol} ticket={result.order} "
                    f"lots={sizing.lots} entry={price:.5f}"
                )
                return OrderResult(
                    True, symbol, direction, sizing.lots, price, sl, tp,
                    ticket=result.order, timestamp=ts,
                )
            else:
                reason = f"MT5 retcode={result.retcode if result else 'None'}"
                logger.error(f"ORDER FAIL {symbol}: {reason}")
                return OrderResult(False, symbol, direction, 0, 0, 0, 0, reason=reason, timestamp=ts)
        except Exception as e:
            logger.exception(f"Order send error {symbol}: {e}")
            return OrderResult(False, symbol, direction, 0, 0, 0, 0, reason=str(e), timestamp=ts)

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
                price = tick.bid if direction == "sell" else tick.ask
                request = {
                    "action": mt5lib.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": pos.volume,
                    "type": order_type,
                    "position": pos.ticket,
                    "price": price,
                    "deviation": 20,
                    "magic": MAGIC,
                    "comment": f"close:{reason}",
                    "type_time": mt5lib.ORDER_TIME_GTC,
                    "type_filling": mt5lib.ORDER_FILLING_IOC,
                }
                result = mt5lib.order_send(request)
                if result and result.retcode == mt5lib.TRADE_RETCODE_DONE:
                    pnl = pos.profit
                    self._risk.register_close(symbol, pnl)
                    closed = True
            return closed
        except Exception as e:
            logger.exception(f"Close error {symbol}: {e}")
            return False
