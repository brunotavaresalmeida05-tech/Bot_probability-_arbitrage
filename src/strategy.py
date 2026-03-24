"""
src/strategy.py
Motor da estratégia: calcula Z-score, gera sinais, controla filtros e risco.
"""

import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Optional, Tuple
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg
import src.mt5_connector as mt5c


# ─────────────────────────────────────────────
#  INDICADORES
# ─────────────────────────────────────────────

def compute_ma(close: pd.Series, period: int, ma_type: str = "SMA") -> pd.Series:
    if ma_type == "EMA":
        return close.ewm(span=period, adjust=False).mean()
    return close.rolling(period).mean()


def compute_stddev(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).std(ddof=0)


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c  = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def compute_zscore(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Retorna (zscore, ma, atr) como Series alinhadas ao df."""
    close = df["close"]
    ma    = compute_ma(close, cfg.MA_PERIOD, cfg.MA_TYPE)
    atr   = compute_atr(df, cfg.ATR_PERIOD)
    atr_base = compute_atr(df, cfg.ATR_BASE_PERIOD)
    dev   = close - ma

    if cfg.USE_STDDEV:
        sd = compute_stddev(close, cfg.STDDEV_PERIOD)
        sd = sd.replace(0, np.nan)
        z  = dev / sd
    else:
        denom = (cfg.ATR_MULT_FOR_Z * atr).replace(0, np.nan)
        z = dev / denom

    return z, ma, atr, atr_base


# ─────────────────────────────────────────────
#  ESTADO DIÁRIO (por símbolo)
# ─────────────────────────────────────────────

class DailyState:
    def __init__(self, balance: float):
        self.date              = date.today()
        self.start_balance     = balance
        self.trades_today      = 0
        self.consecutive_losses = 0

    def reset_if_new_day(self, balance: float):
        today = date.today()
        if today != self.date:
            self.date               = today
            self.start_balance      = balance
            self.trades_today       = 0
            self.consecutive_losses = 0
            return True
        return False

    def record_trade_result(self, profit: float):
        self.trades_today += 1
        if profit < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0


# ─────────────────────────────────────────────
#  FILTROS
# ─────────────────────────────────────────────

def is_within_session() -> bool:
    if not cfg.USE_TIME_FILTER:
        return True
    h = datetime.now().hour
    if not (cfg.SESSION_START_HOUR <= h < cfg.SESSION_END_HOUR):
        return False
    # No-trade windows
    s1, e1 = cfg.NO_TRADE_WINDOW_1
    s2, e2 = cfg.NO_TRADE_WINDOW_2
    if s1 != e1 and s1 <= h < e1:
        return False
    if s2 != e2 and s2 <= h < e2:
        return False
    return True


def _get_spread_limit(symbol: str) -> float:
    """Devolve o limite de spread adequado à classe do activo."""
    if symbol in ("Usa500", "Ger40", "UK100", "US500", "GER40", "US100"):
        return cfg.MAX_SPREAD_INDEX
    if symbol in ("GOLD", "SILVER", "XAUUSD", "XAGUSD"):
        return cfg.MAX_SPREAD_METAL
    if symbol in ("BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD"):
        return cfg.MAX_SPREAD_CRYPTO
    return cfg.MAX_SPREAD_FX


def spread_ok(symbol: str) -> bool:
    return mt5c.get_spread_points(symbol) <= _get_spread_limit(symbol)


def atr_sanity_ok(atr_last: float, atr_base_last: float) -> bool:
    if atr_base_last <= 0:
        return False
    ratio = atr_last / atr_base_last
    return cfg.ATR_MIN_MULT <= ratio <= cfg.ATR_MAX_MULT


def daily_loss_ok(state: DailyState, closed_pnl: float) -> bool:
    limit = -(cfg.MAX_DAILY_LOSS_PCT / 100.0) * state.start_balance
    return closed_pnl > limit


def trading_allowed(symbol: str, state: DailyState,
                    atr_last: float, atr_base_last: float,
                    closed_pnl: float) -> Tuple[bool, str]:
    """Retorna (pode_negociar, motivo_se_não)."""
    if not is_within_session():
        return False, "fora da sessão"
    if not spread_ok(symbol):
        return False, f"spread alto ({mt5c.get_spread_points(symbol):.1f} pts)"
    if not atr_sanity_ok(atr_last, atr_base_last):
        return False, f"ATR fora da gama (atr={atr_last:.5f} base={atr_base_last:.5f})"
    if not daily_loss_ok(state, closed_pnl):
        return False, f"limite de perda diária atingido (PnL={closed_pnl:.2f})"
    if state.trades_today >= cfg.MAX_TRADES_PER_DAY:
        return False, f"máximo de trades diários ({state.trades_today})"
    if state.consecutive_losses >= cfg.MAX_CONSECUTIVE_LOSSES:
        return False, f"perdas consecutivas ({state.consecutive_losses})"
    return True, "ok"


# ─────────────────────────────────────────────
#  SINAL
# ─────────────────────────────────────────────

def get_signal(z: float, ma_last: float, close_last: float) -> Optional[str]:
    """
    Retorna "BUY", "SELL", ou None.
    Z <= -Z_ENTER e close < ma → BUY (preço muito abaixo da média)
    Z >= +Z_ENTER e close > ma → SELL
    """
    if pd.isna(z):
        return None
    if z <= -cfg.Z_ENTER and close_last < ma_last:
        return "BUY"
    if z >= cfg.Z_ENTER and close_last > ma_last:
        return "SELL"
    return None


def should_exit(position_type: str, z: float, price: float, ma_last: float) -> Tuple[bool, str]:
    """Retorna (fechar?, motivo)."""
    if pd.isna(z):
        return False, ""
    if position_type == "BUY":
        if z >= -cfg.Z_EXIT:
            return True, f"Z reverteu ({z:.3f} >= -{cfg.Z_EXIT})"
        if price >= ma_last:
            return True, "preço cruzou MA para cima"
    elif position_type == "SELL":
        if z <= cfg.Z_EXIT:
            return True, f"Z reverteu ({z:.3f} <= {cfg.Z_EXIT})"
        if price <= ma_last:
            return True, "preço cruzou MA para baixo"
    return False, ""


# ─────────────────────────────────────────────
#  STOP LOSS
# ─────────────────────────────────────────────

def compute_stop_loss(
    direction: str,
    entry_price: float,
    ma: float,
    stddev: float,
    atr: float,
) -> float:
    if cfg.USE_Z_STOP:
        vol = stddev if cfg.USE_STDDEV else cfg.ATR_MULT_FOR_Z * atr
        if vol <= 0:
            return 0.0
        if direction == "BUY":
            return ma - cfg.Z_STOP * vol
        else:
            return ma + cfg.Z_STOP * vol
    elif cfg.USE_ATR_STOP:
        if direction == "BUY":
            return entry_price - cfg.SL_ATR_MULT * atr
        else:
            return entry_price + cfg.SL_ATR_MULT * atr
    else:
        # fallback
        if direction == "BUY":
            return entry_price - 2.0 * atr
        else:
            return entry_price + 2.0 * atr
