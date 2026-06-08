import os
import time

import MetaTrader5 as mt5
import pandas as pd


TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M2": mt5.TIMEFRAME_M2,
    "M3": mt5.TIMEFRAME_M3,
    "M4": mt5.TIMEFRAME_M4,
    "M5": mt5.TIMEFRAME_M5,
    "M6": mt5.TIMEFRAME_M6,
    "M10": mt5.TIMEFRAME_M10,
    "M12": mt5.TIMEFRAME_M12,
    "M15": mt5.TIMEFRAME_M15,
    "M20": mt5.TIMEFRAME_M20,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H2": mt5.TIMEFRAME_H2,
    "H3": mt5.TIMEFRAME_H3,
    "H4": mt5.TIMEFRAME_H4,
    "H6": mt5.TIMEFRAME_H6,
    "H8": mt5.TIMEFRAME_H8,
    "H12": mt5.TIMEFRAME_H12,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}


class MT5Bridge:
    def __init__(self, cfg, logger):
        self.cfg = cfg
        self.logger = logger
        self.connected = False

    def connect(self):
        if not self.cfg.get("mt5_enabled", False):
            self.logger.info("MT5 disabled by config")
            return False

        login_raw = os.getenv(self.cfg.get("mt5_login_env", "MT5_LOGIN"), "")
        password = os.getenv(self.cfg.get("mt5_password_env", "MT5_PASSWORD"), "")
        server = os.getenv(self.cfg.get("mt5_server_env", "MT5_SERVER"), "")
        path = os.getenv(self.cfg.get("mt5_path_env", "MT5_PATH"), "") or None
        try:
            login = int(login_raw)
        except (ValueError, TypeError):
            login = None

        ok = mt5.initialize(
            path=path,
            login=login or None,
            password=password or None,
            server=server or None,
        )
        if not ok:
            self.logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False

        self.connected = True
        self.logger.info("MT5 connected")
        return True

    def get_bars(self, symbol, timeframe, count=200):
        if not self.connected:
            return pd.DataFrame()
        tf = TIMEFRAME_MAP.get(timeframe, timeframe) if isinstance(timeframe, str) else timeframe
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None:
            self.logger.warning(f"No bars for {symbol}")
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        if not df.empty:
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            df = df.rename(columns={"tick_volume": "volume"})
        return df

    def fetch_bars_timed(self, symbol, timeframe, count):
        t0 = time.time()
        bars = self.get_bars(symbol, timeframe, count)
        dur = (time.time() - t0) * 1000.0
        return bars, dur

    def check_connection(self):
        try:
            if not self.connected:
                return False
            info = mt5.terminal_info()
            return info is not None
        except Exception:
            return False

    def positions_get(self, symbol=None):
        if not self.connected:
            return []
        try:
            symbols = [symbol] if symbol else (self.cfg.get("market", {}).get("symbols", []))
            seen = set()
            all_positions = []
            for sym in symbols:
                raw = mt5.positions_get(symbol=sym)
                if raw is None:
                    continue
                for p in raw:
                    if p.ticket not in seen:
                        seen.add(p.ticket)
                        all_positions.append(p)
            return all_positions
        except Exception as e:
            self.logger.error(f"positions_get exception: {e}")
            return []

    def close_position(self, ticket):
        if not self.connected:
            return False
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False
        pos = pos[0]
        order_type = mt5.ORDER_TYPE_BUY if pos.type == 1 else mt5.ORDER_TYPE_SELL
        price = mt5.symbol_info_tick(pos.symbol).bid if order_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(pos.symbol).ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": float(pos.volume),
            "type": order_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 10,
            "magic": 123456,
            "comment": "alphasystem close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            self.logger.error(f"close {pos.ticket} {pos.symbol}: retcode={result.retcode if result else 'NONE'}")
            return False
        self.logger.info(f"CLOSED {pos.symbol} ticket={pos.ticket} profit={pos.profit:.2f}")
        return True

    def buy(self, symbol, qty, sl=None, tp=None):
        if not self.connected:
            return False
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            self.logger.error(f"buy {symbol}: no tick")
            return False
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(qty),
            "type": mt5.ORDER_TYPE_BUY,
            "price": tick.ask,
            "deviation": 10,
            "magic": 123456,
            "comment": "alphasystem live",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if sl is not None:
            request["sl"] = round(float(sl), 5)
        if tp is not None:
            request["tp"] = round(float(tp), 5)
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            self.logger.error(f"buy {symbol} {qty}: retcode={result.retcode if result else 'NONE'}")
            return False
        self.logger.info(f"BUY {symbol} qty={qty} price={tick.ask} ticket={result.order} sl={sl} tp={tp}")
        return True

    def sell(self, symbol, qty, sl=None, tp=None):
        if not self.connected:
            return False
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            self.logger.error(f"sell {symbol}: no tick")
            return False
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(qty),
            "type": mt5.ORDER_TYPE_SELL,
            "price": tick.bid,
            "deviation": 10,
            "magic": 123456,
            "comment": "alphasystem live",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        if sl is not None:
            request["sl"] = round(float(sl), 5)
        if tp is not None:
            request["tp"] = round(float(tp), 5)
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            self.logger.error(f"sell {symbol} {qty}: retcode={result.retcode if result else 'NONE'}")
            return False
        self.logger.info(f"SELL {symbol} qty={qty} price={tick.bid} ticket={result.order} sl={sl} tp={tp}")
        return True

    def modify_sl_tp(self, ticket, symbol, sl=None, tp=None):
        if not self.connected:
            return False
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": symbol,
            "sl": round(float(sl), 5) if sl is not None else 0.0,
            "tp": round(float(tp), 5) if tp is not None else 0.0,
            "magic": 123456,
            "comment": "alphasystem modify",
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            self.logger.error(f"modify sl/tp {symbol} ticket={ticket}: retcode={result.retcode if result else 'NONE'}")
            return False
        self.logger.info(f"MODIFIED {symbol} ticket={ticket} sl={sl} tp={tp}")
        return True

    def reconnect(self, timeout=5):
        old = self.connected
        self.shutdown()
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                ok = mt5.initialize(
                    path=self.cfg.get("mt5_path") or None,
                    login=self.cfg.get("mt5_login") or None,
                    password=self.cfg.get("mt5_password") or None,
                    server=self.cfg.get("mt5_server") or None,
                )
                if ok:
                    self.connected = True
                    self.logger.info("MT5 reconnected")
                    return True
            except Exception:
                pass
            time.sleep(1)
        self.connected = False
        self.logger.error("MT5 reconnect failed")
        return False

    def symbol_info(self, symbol: str):
        """Obtém info de um símbolo."""
        if not self.connected:
            return None
        try:
            return mt5.symbol_info(symbol)
        except Exception as e:
            self.logger.debug(f"symbol_info {symbol}: {e}")
            return None

    def symbol_info_tick(self, symbol: str):
        """Obtém tick atual de um símbolo."""
        if not self.connected:
            return None
        try:
            return mt5.symbol_info_tick(symbol)
        except Exception as e:
            self.logger.debug(f"symbol_info_tick {symbol}: {e}")
            return None

    def symbol_select(self, symbol: str, enable: bool = True):
        """Adiciona/remove símbolo do Market Watch."""
        if not self.connected:
            return False
        try:
            return mt5.symbol_select(symbol, enable)
        except Exception as e:
            self.logger.debug(f"symbol_select {symbol}: {e}")
            return False

    def get_all_ticks(self, symbols: list) -> dict:
        """Obtém ticks de múltiplos símbolos de uma vez."""
        result = {}
        if not self.connected:
            return result
        for sym in symbols:
            try:
                tick = mt5.symbol_info_tick(sym)
                if tick is not None:
                    result[sym] = tick
            except Exception:
                pass
        return result

    def shutdown(self):
        if self.connected:
            mt5.shutdown()
            self.connected = False
            self.logger.info("MT5 shutdown")
