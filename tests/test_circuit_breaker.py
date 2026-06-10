"""Tests for src/engine/circuit_breaker.py (Fase 9A)."""
import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
from src.engine.circuit_breaker import CircuitBreaker, CBLevel, CBState


def _cb_with_equity(equity: float = 10_000.0) -> CircuitBreaker:
    cb = CircuitBreaker()
    cb.set_session_equity(equity)
    return cb


# ── LEVELS ────────────────────────────────────────────────────────────────────

class TestLevels:
    def test_green_by_default(self):
        cb = _cb_with_equity(10_000)
        state = cb.update(current_equity=10_000)
        assert state.level == CBLevel.GREEN

    def test_yellow_on_2pct_drawdown(self):
        cb = _cb_with_equity(10_000)
        state = cb.update(current_equity=9_780)   # -2.2%
        assert state.level == CBLevel.YELLOW

    def test_orange_on_3pct_drawdown(self):
        cb = _cb_with_equity(10_000)
        state = cb.update(current_equity=9_650)   # -3.5%
        assert state.level == CBLevel.ORANGE

    def test_red_on_5pct_drawdown(self):
        cb = _cb_with_equity(10_000)
        state = cb.update(current_equity=9_450)   # -5.5%
        assert state.level == CBLevel.RED

    def test_yellow_on_3_consecutive_losses(self):
        cb = _cb_with_equity(10_000)
        for _ in range(3):
            cb.record_trade_result("loss")
        state = cb.update(current_equity=10_000)
        assert state.level == CBLevel.YELLOW

    def test_orange_on_5_consecutive_losses(self):
        cb = _cb_with_equity(10_000)
        for _ in range(5):
            cb.record_trade_result("loss")
        state = cb.update(current_equity=10_000)
        assert state.level == CBLevel.ORANGE

    def test_wins_reset_consecutive_losses(self):
        cb = _cb_with_equity(10_000)
        for _ in range(3):
            cb.record_trade_result("loss")
        cb.record_trade_result("win")
        state = cb.update(current_equity=10_000)
        assert state.consecutive_losses == 0
        assert state.level == CBLevel.GREEN

    def test_drawdown_wins_over_losses_for_higher_level(self):
        # Drawdown triggers ORANGE; only 2 losses → losses alone → YELLOW
        # Combined: ORANGE wins (higher)
        cb = _cb_with_equity(10_000)
        for _ in range(2):
            cb.record_trade_result("loss")
        state = cb.update(current_equity=9_650)   # -3.5%
        assert state.level == CBLevel.ORANGE


# ── LOT MULTIPLIER ────────────────────────────────────────────────────────────

class TestLotMultiplier:
    def test_green_lot_1(self):
        cb = _cb_with_equity(10_000)
        cb.update(10_000)
        assert cb.state.lot_multiplier == 1.0

    def test_yellow_lot_half(self):
        cb = _cb_with_equity(10_000)
        cb.update(9_780)
        assert cb.state.lot_multiplier == 0.5

    def test_orange_lot_zero(self):
        cb = _cb_with_equity(10_000)
        cb.update(9_650)
        assert cb.state.lot_multiplier == 0.0

    def test_red_lot_zero(self):
        cb = _cb_with_equity(10_000)
        cb.update(9_450)
        assert cb.state.lot_multiplier == 0.0


# ── CAN_OPEN ──────────────────────────────────────────────────────────────────

class TestCanOpen:
    def test_green_can_open(self):
        cb = _cb_with_equity(10_000)
        cb.update(10_000)
        assert cb.state.can_open is True

    def test_yellow_can_open(self):
        cb = _cb_with_equity(10_000)
        cb.update(9_780)
        assert cb.state.can_open is True

    def test_orange_cannot_open(self):
        cb = _cb_with_equity(10_000)
        cb.update(9_650)
        assert cb.state.can_open is False

    def test_red_cannot_open(self):
        cb = _cb_with_equity(10_000)
        cb.update(9_450)
        assert cb.state.can_open is False

    def test_red_requests_close_all(self):
        cb = _cb_with_equity(10_000)
        cb.update(9_450)
        assert cb.state.request_close_all is True

    def test_non_red_does_not_request_close(self):
        cb = _cb_with_equity(10_000)
        cb.update(9_780)
        assert cb.state.request_close_all is False


# ── DAILY RESET ───────────────────────────────────────────────────────────────

class TestDailyReset:
    def test_reset_clears_losses_and_level(self):
        cb = _cb_with_equity(10_000)
        for _ in range(3):
            cb.record_trade_result("loss")
        cb.update(10_000)
        assert cb.state.level == CBLevel.YELLOW

        # Force stale date to simulate next day
        cb._date = "2000-01-01"
        state = cb.update(current_equity=10_000)
        assert state.consecutive_losses == 0
        assert state.level == CBLevel.GREEN

    def test_set_session_equity_only_once(self):
        cb = CircuitBreaker()
        cb.set_session_equity(10_000)
        cb.set_session_equity(12_000)   # second call should be ignored
        assert cb.state.daily_start_equity == 10_000


# ── MANUAL RESET ──────────────────────────────────────────────────────────────

class TestManualReset:
    def test_manual_reset_from_red(self):
        cb = _cb_with_equity(10_000)
        cb.update(9_450)
        assert cb.state.level == CBLevel.RED
        cb.manual_reset()
        assert cb.state.level == CBLevel.GREEN

    def test_manual_reset_noop_when_not_red(self):
        cb = _cb_with_equity(10_000)
        cb.update(9_780)
        assert cb.state.level == CBLevel.YELLOW
        cb.manual_reset()
        assert cb.state.level == CBLevel.YELLOW


# ── DAILY DRAWDOWN CALC ───────────────────────────────────────────────────────

class TestDailyDrawdown:
    def test_zero_drawdown_at_start(self):
        cb = _cb_with_equity(10_000)
        cb.update(10_000)
        assert cb.state.daily_drawdown == 0.0

    def test_drawdown_calculation(self):
        cb = _cb_with_equity(10_000)
        cb.update(9_500)
        assert abs(cb.state.daily_drawdown - 0.05) < 1e-6

    def test_no_trigger_on_equity_gain(self):
        # daily_drawdown is negative on gain — triggers nothing
        cb = _cb_with_equity(10_000)
        state = cb.update(10_500)
        assert state.daily_drawdown < 0
        assert state.level == CBLevel.GREEN


# ── THREAD SAFETY (smoke) ─────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_updates_do_not_raise(self):
        import threading
        cb = _cb_with_equity(10_000)
        errors = []

        def worker():
            try:
                for _ in range(50):
                    cb.update(10_000)
                    cb.record_trade_result("win")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
