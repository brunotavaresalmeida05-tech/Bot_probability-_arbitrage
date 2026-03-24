"""
tests/test_risk.py
Testa a lógica pura de risco de src/strategy.py.
Cobre: DailyState, daily_loss_ok, atr_sanity_ok, filtros de trades.
Zero dependência de MT5 ou de qualquer API externa.
"""
import sys
import os
import pytest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mockar mt5_connector antes de importar strategy
mt5_mock = MagicMock()
mt5_mock.get_spread_points.return_value = 1.5
sys.modules.setdefault("src.mt5_connector", mt5_mock)

import src.strategy as strat
import config.settings as cfg


# ─── daily_loss_ok ─────────────────────────────────────────

class TestDailyLossOk:
    """
    cfg.MAX_DAILY_LOSS_PCT = 4.0
    Limite absoluto = -(4/100) * balance_inicial
    """

    def _state(self, balance=10_000.0):
        return strat.DailyState(balance)

    def test_no_loss_allowed(self):
        assert strat.daily_loss_ok(self._state(10_000), 0.0) is True

    def test_small_loss_allowed(self):
        assert strat.daily_loss_ok(self._state(10_000), -100.0) is True

    def test_exactly_at_limit_allowed(self):
        # -4% de 10_000 = -400 → limite exacto é permitido
        assert strat.daily_loss_ok(self._state(10_000), -400.0) is True

    def test_below_limit_blocked(self):
        # -401 < -400 → bloqueado
        assert strat.daily_loss_ok(self._state(10_000), -401.0) is False

    def test_large_loss_blocked(self):
        assert strat.daily_loss_ok(self._state(10_000), -1_000.0) is False

    def test_profit_allowed(self):
        assert strat.daily_loss_ok(self._state(10_000), +500.0) is True

    def test_different_balance(self):
        # 4% de 5_000 = -200
        assert strat.daily_loss_ok(self._state(5_000), -199.0) is True
        assert strat.daily_loss_ok(self._state(5_000), -201.0) is False


# ─── atr_sanity_ok ─────────────────────────────────────────

class TestAtrSanityOk:
    """
    cfg.ATR_MIN_MULT = 0.5, cfg.ATR_MAX_MULT = 3.0
    ratio = atr_last / atr_base_last deve estar em [0.5, 3.0]
    """

    def test_normal_ratio_ok(self):
        assert strat.atr_sanity_ok(0.001, 0.001) is True

    def test_ratio_at_min_ok(self):
        assert strat.atr_sanity_ok(0.0005, 0.001) is True   # ratio = 0.5

    def test_ratio_at_max_ok(self):
        assert strat.atr_sanity_ok(0.003, 0.001) is True    # ratio = 3.0

    def test_ratio_below_min_blocked(self):
        assert strat.atr_sanity_ok(0.0004, 0.001) is False  # ratio = 0.4

    def test_ratio_above_max_blocked(self):
        assert strat.atr_sanity_ok(0.004, 0.001) is False   # ratio = 4.0

    def test_zero_base_blocked(self):
        assert strat.atr_sanity_ok(0.001, 0.0) is False

    def test_zero_atr_blocked(self):
        # ratio = 0 < 0.5 → bloqueado
        assert strat.atr_sanity_ok(0.0, 0.001) is False


# ─── DailyState: reset_if_new_day ──────────────────────────

class TestDailyStateReset:
    def test_no_reset_same_day(self):
        ds = strat.DailyState(10_000.0)
        ds.trades_today = 10
        ds.consecutive_losses = 3
        changed = ds.reset_if_new_day(12_000.0)
        assert not changed
        assert ds.trades_today == 10
        assert ds.consecutive_losses == 3

    def test_reset_on_new_day(self):
        ds = strat.DailyState(10_000.0)
        ds.trades_today = 10
        ds.consecutive_losses = 3
        ds.date = date.today() - timedelta(days=1)
        changed = ds.reset_if_new_day(12_000.0)
        assert changed is True
        assert ds.trades_today == 0
        assert ds.consecutive_losses == 0
        assert ds.start_balance == 12_000.0
        assert ds.date == date.today()

    def test_reset_two_days_later(self):
        ds = strat.DailyState(10_000.0)
        ds.date = date.today() - timedelta(days=2)
        ds.trades_today = 25
        changed = ds.reset_if_new_day(9_500.0)
        assert changed is True
        assert ds.trades_today == 0
        assert ds.start_balance == 9_500.0


# ─── DailyState: record_trade_result ───────────────────────

class TestDailyStateRecord:
    def test_loss_increments_consecutive(self):
        ds = strat.DailyState(10_000.0)
        ds.record_trade_result(-50)
        ds.record_trade_result(-30)
        assert ds.consecutive_losses == 2
        assert ds.trades_today == 2

    def test_win_resets_consecutive(self):
        ds = strat.DailyState(10_000.0)
        ds.record_trade_result(-50)
        ds.record_trade_result(-30)
        ds.record_trade_result(+100)
        assert ds.consecutive_losses == 0
        assert ds.trades_today == 3

    def test_only_wins(self):
        ds = strat.DailyState(10_000.0)
        for _ in range(5):
            ds.record_trade_result(+20)
        assert ds.consecutive_losses == 0
        assert ds.trades_today == 5

    def test_alternating_win_loss(self):
        ds = strat.DailyState(10_000.0)
        results = [+10, -5, +10, -5, -5]
        for r in results:
            ds.record_trade_result(r)
        # Termina em 2 perdas consecutivas
        assert ds.consecutive_losses == 2
        assert ds.trades_today == 5

    def test_zero_profit_counts_as_win(self):
        """Lucro zero não é perda → consecutive_losses não incrementa."""
        ds = strat.DailyState(10_000.0)
        ds.record_trade_result(-10)
        ds.record_trade_result(0.0)
        assert ds.consecutive_losses == 0


# ─── max trades e consecutive losses em trading_allowed ────

class TestTradingLimits:
    """Testa os limites via trading_allowed com mocks."""

    @patch("src.strategy.is_within_session", return_value=True)
    @patch("src.strategy.spread_ok", return_value=True)
    def test_max_trades_exact_limit(self, *_):
        ds = strat.DailyState(10_000.0)
        ds.trades_today = cfg.MAX_TRADES_PER_DAY - 1  # 1 abaixo do limite
        ok, _ = strat.trading_allowed("EURUSD", ds, 0.001, 0.001, 0.0)
        assert ok  # ainda abaixo → permitido

    @patch("src.strategy.is_within_session", return_value=True)
    @patch("src.strategy.spread_ok", return_value=True)
    def test_max_trades_reached(self, *_):
        ds = strat.DailyState(10_000.0)
        ds.trades_today = cfg.MAX_TRADES_PER_DAY  # no limite → bloqueado
        ok, reason = strat.trading_allowed("EURUSD", ds, 0.001, 0.001, 0.0)
        assert not ok
        assert "trades" in reason.lower() or "máximo" in reason.lower()

    @patch("src.strategy.is_within_session", return_value=True)
    @patch("src.strategy.spread_ok", return_value=True)
    def test_consecutive_losses_exact_limit(self, *_):
        ds = strat.DailyState(10_000.0)
        ds.consecutive_losses = cfg.MAX_CONSECUTIVE_LOSSES - 1
        ok, _ = strat.trading_allowed("EURUSD", ds, 0.001, 0.001, 0.0)
        assert ok

    @patch("src.strategy.is_within_session", return_value=True)
    @patch("src.strategy.spread_ok", return_value=True)
    def test_consecutive_losses_reached(self, *_):
        ds = strat.DailyState(10_000.0)
        ds.consecutive_losses = cfg.MAX_CONSECUTIVE_LOSSES
        ok, reason = strat.trading_allowed("EURUSD", ds, 0.001, 0.001, 0.0)
        assert not ok
        assert "consecutiv" in reason.lower()
