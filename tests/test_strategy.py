"""
tests/test_strategy.py
Testa src/strategy.py sem qualquer ligação ao MT5.
Cobre: compute_ma, compute_stddev, compute_atr, compute_zscore,
       get_signal, should_exit, compute_stop_loss, DailyState.
"""
import sys
import os
import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch
from datetime import date, timedelta

# --- path setup ---
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# Mockar mt5_connector antes de importar strategy (evita import de MetaTrader5)
mt5_mock = MagicMock()
mt5_mock.get_spread_points.return_value = 1.5
sys.modules["src.mt5_connector"] = mt5_mock
import src.strategy as strat


# ─── compute_ma ────────────────────────────────────────────

class TestComputeMA:
    def test_sma_length(self, sample_ohlcv):
        result = strat.compute_ma(sample_ohlcv["close"], period=50, ma_type="SMA")
        assert len(result) == len(sample_ohlcv)

    def test_sma_first_values_nan(self, sample_ohlcv):
        result = strat.compute_ma(sample_ohlcv["close"], period=50, ma_type="SMA")
        assert result.iloc[:49].isna().all()

    def test_sma_known_value(self):
        close = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        ma   = strat.compute_ma(close, period=3, ma_type="SMA")
        assert ma.iloc[2] == pytest.approx(2.0)
        assert ma.iloc[4] == pytest.approx(4.0)

    def test_ema_length(self, sample_ohlcv):
        result = strat.compute_ma(sample_ohlcv["close"], period=20, ma_type="EMA")
        assert len(result) == len(sample_ohlcv)

    def test_ema_no_nan_after_start(self, sample_ohlcv):
        result = strat.compute_ma(sample_ohlcv["close"], period=20, ma_type="EMA")
        # EMA com adjust=False não gera NaN
        assert result.iloc[20:].notna().all()

    def test_default_is_sma(self, sample_ohlcv):
        sma  = strat.compute_ma(sample_ohlcv["close"], period=30, ma_type="SMA")
        dfl  = strat.compute_ma(sample_ohlcv["close"], period=30)
        pd.testing.assert_series_equal(sma, dfl)


# ─── compute_stddev ────────────────────────────────────────

class TestComputeStddev:
    def test_length(self, sample_ohlcv):
        result = strat.compute_stddev(sample_ohlcv["close"], period=30)
        assert len(result) == len(sample_ohlcv)

    def test_non_negative(self, sample_ohlcv):
        result = strat.compute_stddev(sample_ohlcv["close"], period=30)
        assert (result.dropna() >= 0).all()

    def test_constant_series_zero_std(self):
        close = pd.Series([1.5] * 100)
        sd    = strat.compute_stddev(close, period=20)
        assert sd.iloc[19:].max() == pytest.approx(0.0)

    def test_ddof_zero(self):
        """Confirmar que usa ddof=0 (população, não amostra)."""
        close  = pd.Series(range(1, 11), dtype=float)
        sd     = strat.compute_stddev(close, period=5)
        # Janela [6,7,8,9,10] → std poplacional
        expected = np.std([6, 7, 8, 9, 10], ddof=0)
        assert sd.iloc[-1] == pytest.approx(expected, rel=1e-6)


# ─── compute_atr ───────────────────────────────────────────

class TestComputeATR:
    def test_length(self, sample_ohlcv):
        result = strat.compute_atr(sample_ohlcv, period=14)
        assert len(result) == len(sample_ohlcv)

    def test_non_negative(self, sample_ohlcv):
        result = strat.compute_atr(sample_ohlcv, period=14)
        assert (result.dropna() >= 0).all()

    def test_atr_increases_with_volatility(self):
        # Série de baixa vs alta volatilidade
        n  = 100
        df_low = pd.DataFrame({
            "high":  [1.001] * n,
            "low":   [0.999] * n,
            "close": [1.000] * n,
        })
        df_high = pd.DataFrame({
            "high":  [1.010] * n,
            "low":   [0.990] * n,
            "close": [1.000] * n,
        })
        atr_low  = strat.compute_atr(df_low, period=14).iloc[-1]
        atr_high = strat.compute_atr(df_high, period=14).iloc[-1]
        assert atr_high > atr_low


# ─── get_signal ────────────────────────────────────────────

class TestGetSignal:
    """Usa Z_ENTER=2.0 do settings."""

    def test_buy_signal(self):
        # z=-2.5, close < ma → BUY
        assert strat.get_signal(-2.5, ma_last=1.10, close_last=1.09) == "BUY"

    def test_sell_signal(self):
        # z=+2.5, close > ma → SELL
        assert strat.get_signal(+2.5, ma_last=1.10, close_last=1.11) == "SELL"

    def test_no_signal_neutral_z(self):
        assert strat.get_signal(0.5, ma_last=1.10, close_last=1.09) is None

    def test_no_signal_z_buy_but_price_above_ma(self):
        # z extremo mas preço acima de MA → sem sinal BUY
        assert strat.get_signal(-2.5, ma_last=1.10, close_last=1.11) is None

    def test_no_signal_z_sell_but_price_below_ma(self):
        assert strat.get_signal(+2.5, ma_last=1.10, close_last=1.09) is None

    def test_nan_z_returns_none(self):
        assert strat.get_signal(float("nan"), ma_last=1.10, close_last=1.09) is None


# ─── should_exit ───────────────────────────────────────────

class TestShouldExit:
    def test_buy_exits_when_z_reverted(self):
        do_exit, reason = strat.should_exit("BUY", z=0.8, price=1.09, ma_last=1.10)
        assert do_exit
        assert "reverteu" in reason.lower() or "Z" in reason

    def test_buy_exits_when_price_above_ma(self):
        do_exit, _ = strat.should_exit("BUY", z=-1.0, price=1.11, ma_last=1.10)
        assert do_exit

    def test_sell_exits_when_z_reverted(self):
        do_exit, _ = strat.should_exit("SELL", z=-0.8, price=1.11, ma_last=1.10)
        assert do_exit

    def test_sell_exits_when_price_below_ma(self):
        do_exit, _ = strat.should_exit("SELL", z=1.5, price=1.09, ma_last=1.10)
        assert do_exit

    def test_buy_does_not_exit_when_z_negative(self):
        do_exit, _ = strat.should_exit("BUY", z=-2.0, price=1.09, ma_last=1.10)
        assert not do_exit

    def test_sell_does_not_exit_when_z_positive(self):
        do_exit, _ = strat.should_exit("SELL", z=2.0, price=1.11, ma_last=1.10)
        assert not do_exit


# ─── compute_stop_loss ─────────────────────────────────────

class TestComputeStopLoss:
    def test_buy_sl_below_entry(self):
        sl = strat.compute_stop_loss("BUY", 1.10, ma=1.09, stddev=0.005, atr=0.001)
        assert sl < 1.10

    def test_sell_sl_above_entry(self):
        sl = strat.compute_stop_loss("SELL", 1.10, ma=1.11, stddev=0.005, atr=0.001)
        assert sl > 1.10

    def test_zero_stddev_returns_zero(self):
        sl = strat.compute_stop_loss("BUY", 1.10, ma=1.09, stddev=0.0, atr=0.001)
        # com USE_Z_STOP=True e stddev=0 → denom=0 → retorna 0.0
        assert sl == 0.0


# ─── DailyState ────────────────────────────────────────────

class TestDailyState:
    def test_initial_state(self):
        ds = strat.DailyState(balance=10000.0)
        assert ds.trades_today == 0
        assert ds.consecutive_losses == 0
        assert ds.start_balance == 10000.0

    def test_record_loss(self):
        ds = strat.DailyState(10000.0)
        ds.record_trade_result(-50.0)
        assert ds.consecutive_losses == 1
        assert ds.trades_today == 1

    def test_record_win_resets_consecutive(self):
        ds = strat.DailyState(10000.0)
        ds.record_trade_result(-50.0)
        ds.record_trade_result(-30.0)
        ds.record_trade_result(+80.0)
        assert ds.consecutive_losses == 0
        assert ds.trades_today == 3

    def test_reset_if_new_day(self):
        ds = strat.DailyState(10000.0)
        ds.trades_today = 5
        ds.consecutive_losses = 3
        # Simular novo dia
        ds.date = date.today() - timedelta(days=1)
        changed = ds.reset_if_new_day(12000.0)
        assert changed
        assert ds.trades_today == 0
        assert ds.consecutive_losses == 0
        assert ds.start_balance == 12000.0

    def test_no_reset_same_day(self):
        ds = strat.DailyState(10000.0)
        ds.trades_today = 7
        changed = ds.reset_if_new_day(10000.0)
        assert not changed
        assert ds.trades_today == 7


# ─── trading_allowed ───────────────────────────────────────

class TestTradingAllowed:
    """
    Usa mocks para evitar dependência do MT5 e do horário do sistema.
    """

    def _make_state(self, balance=10000.0):
        return strat.DailyState(balance)

    @patch("src.strategy.is_within_session", return_value=True)
    @patch("src.strategy.spread_ok", return_value=True)
    def test_allowed_when_all_ok(self, mock_spread, mock_session):
        ds = self._make_state()
        ok, reason = strat.trading_allowed("EURUSD", ds,
                                            atr_last=0.0008, atr_base_last=0.0008,
                                            closed_pnl=0.0)
        assert ok
        assert reason == "ok"

    @patch("src.strategy.is_within_session", return_value=False)
    def test_blocked_outside_session(self, mock_session):
        ds = self._make_state()
        ok, reason = strat.trading_allowed("EURUSD", ds, 0.001, 0.001, 0.0)
        assert not ok
        assert "sessão" in reason

    @patch("src.strategy.is_within_session", return_value=True)
    @patch("src.strategy.spread_ok", return_value=True)
    def test_blocked_by_daily_loss(self, mock_spread, mock_session):
        ds = self._make_state(10000.0)
        # Perda de 5% de 10000 = -500 → limite é -4% = -400
        ok, reason = strat.trading_allowed("EURUSD", ds, 0.001, 0.001, -500.0)
        assert not ok
        assert "perda" in reason.lower()

    @patch("src.strategy.is_within_session", return_value=True)
    @patch("src.strategy.spread_ok", return_value=True)
    def test_blocked_by_max_trades(self, mock_spread, mock_session):
        ds = self._make_state()
        ds.trades_today = 30   # MAX_TRADES_PER_DAY = 30
        ok, reason = strat.trading_allowed("EURUSD", ds, 0.001, 0.001, 0.0)
        assert not ok
        assert "trades" in reason.lower()

    @patch("src.strategy.is_within_session", return_value=True)
    @patch("src.strategy.spread_ok", return_value=True)
    def test_blocked_by_consecutive_losses(self, mock_spread, mock_session):
        ds = self._make_state()
        ds.consecutive_losses = 5   # MAX_CONSECUTIVE_LOSSES = 5
        ok, reason = strat.trading_allowed("EURUSD", ds, 0.001, 0.001, 0.0)
        assert not ok
        assert "consecutiv" in reason.lower()
