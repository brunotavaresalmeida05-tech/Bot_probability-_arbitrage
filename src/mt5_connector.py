"""
src/mt5_connector.py  —  com validação de distância mínima de SL (fix retcode 10016)
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import MT5_PATH, MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1,
}


def connect() -> bool:
    kwargs = {"path": MT5_PATH} if MT5_PATH else {}
    if not mt5.initialize(**kwargs):
        return False
    if MT5_LOGIN:
        ok = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
        if not ok:
            mt5.shutdown()
            return False
    return True


def disconnect():
    mt5.shutdown()


def get_account_info() -> dict:
    info = mt5.account_info()
    if info is None:
        return {}
    return {"balance": info.balance, "equity": info.equity, "margin": info.margin,
            "currency": info.currency, "server": info.server, "login": info.login}


def get_bars(symbol: str, timeframe_str: str, count: int) -> Optional[pd.DataFrame]:
    tf = TIMEFRAME_MAP.get(timeframe_str)
    if tf is None:
        return None
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, count + 1)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df.iloc[:-1]  # remove barra actual (aberta)


def get_spread_points(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    return float(info.spread) if info else 9999.0


def get_tick(symbol: str):
    return mt5.symbol_info_tick(symbol)


def get_symbol_info(symbol: str):
    return mt5.symbol_info(symbol)


def get_open_positions(symbol: str = None, magic: int = None) -> list:
    positions = mt5.positions_get()
    if positions is None:
        return []
    result = list(positions)
    if symbol:
        result = [p for p in result if p.symbol == symbol]
    if magic:
        result = [p for p in result if p.magic == magic]
    return result


def get_today_deals(symbol: str, magic: int) -> list:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(today, datetime.now())
    if deals is None:
        return []
    return [d for d in deals if d.symbol == symbol and d.magic == magic]


def get_min_sl_distance(symbol: str) -> float:
    """
    Devolve a distância mínima obrigatória entre preço e SL/TP em preço.
    Evita retcode 10016 (Invalid stops).
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        return 0.0
    # stops_level em pontos × point
    min_dist = info.trade_stops_level * info.point
    # Adicionar margem de segurança de 2 pontos
    return min_dist + 2 * info.point


def calculate_lot_size(symbol: str, risk_money: float, sl_distance_price: float) -> float:
    if sl_distance_price <= 0:
        return 0.0
    info = mt5.symbol_info(symbol)
    if info is None:
        return 0.0
    tick_size, tick_value = info.trade_tick_size, info.trade_tick_value
    if tick_size <= 0 or tick_value <= 0:
        return 0.0
    risk_per_lot = (sl_distance_price / tick_size) * tick_value
    if risk_per_lot <= 0:
        return 0.0
    lots = risk_money / risk_per_lot
    step = info.volume_step
    lots = np.floor(lots / step) * step
    lots = max(lots, info.volume_min)
    lots = min(lots, info.volume_max)
    return round(lots, 2)


def validate_sl(symbol: str, direction: str, entry_price: float, sl_price: float) -> float:
    """
    Valida e corrige o SL se estiver demasiado próximo da entrada.
    Retorna o SL corrigido (ou 0 se impossível calcular).
    """
    min_dist = get_min_sl_distance(symbol)
    if min_dist <= 0:
        return sl_price

    actual_dist = abs(entry_price - sl_price)
    if actual_dist >= min_dist:
        return sl_price  # SL válido

    # Corrigir: afastar o SL à distância mínima
    info = mt5.symbol_info(symbol)
    if info is None:
        return 0.0

    digits = info.digits
    if direction == "BUY":
        corrected = round(entry_price - min_dist * 1.1, digits)
    else:
        corrected = round(entry_price + min_dist * 1.1, digits)

    return corrected


def send_order(symbol, order_type, lots, sl, tp, magic, comment="MR", deviation=20):
    tick = get_tick(symbol)
    if tick is None:
        return {"success": False, "error": "no tick"}

    price    = tick.ask if order_type == "BUY" else tick.bid
    mt5_type = mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL

    # Validar SL antes de enviar
    sl_validated = validate_sl(symbol, order_type, price, sl)
    if sl_validated == 0.0:
        return {"success": False, "error": "SL inválido após correcção"}

    if sl_validated != sl:
        import src.logger as log
        log.warning(f"SL corrigido: {sl:.5f} → {sl_validated:.5f} (min dist enforced)", symbol)

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lots,
        "type":         mt5_type,
        "price":        price,
        "sl":           sl_validated,
        "tp":           tp,
        "deviation":    deviation,
        "magic":        magic,
        "comment":      comment,
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"success": False, "error": "order_send returned None"}
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True, "ticket": result.order, "price": result.price, "volume": result.volume}
    return {"success": False, "retcode": result.retcode, "error": result.comment}


def close_position(position, magic, deviation=20):
    tick = get_tick(position.symbol)
    if tick is None:
        return {"success": False, "error": "no tick"}

    close_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price      = tick.bid if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_ASK

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       position.symbol,
        "volume":       position.volume,
        "type":         close_type,
        "position":     position.ticket,
        "price":        price,
        "deviation":    deviation,
        "magic":        magic,
        "comment":      "MR_close",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        return {"success": False, "error": "None"}
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True, "ticket": result.order}
    return {"success": False, "retcode": result.retcode, "error": result.comment}
