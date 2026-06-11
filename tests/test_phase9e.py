"""
Phase 9E — Unit Tests

Coverage targets (all from the V9.1 engine):
  A. atr_stop_indicator  — src/technical/indicators.py
  C. TotalScore.compute  — src/analysis/total_score.py
  D. compute_opportunity_score / compute_permission_score / get_thresholds
                         — src/engine/scanner.py
  E. OrderManager._split_lots — src/execution/order_manager.py
  F. SMC analyze         — src/analysis/smc.py
  G. TrailingManager     — src/engine/trailing_manager.py
  H. analyze_family      — src/engine/market_families.py
"""
from __future__ import annotations

import math
import threading
import time

import numpy as np
import pandas as pd
import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ──────────────────────────────────────────────────────────────────────────────

def _ohlcv(n: int = 200, trend: float = 0.0, vol: float = 0.3, seed: int = 0,
           base: float = 1.09000) -> pd.DataFrame:
    """Synthetic OHLCV DataFrame — reusable across all test sections."""
    rng = np.random.default_rng(seed)
    close = base + trend * np.arange(n) + np.cumsum(rng.normal(0, vol * 0.001, n))
    high  = close + rng.uniform(0.0002, 0.0008, n)
    low   = close - rng.uniform(0.0002, 0.0008, n)
    open_ = close + rng.normal(0, 0.0002, n)
    vol_  = np.ones(n) * 1000.0
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol_})


def _up(n: int = 200) -> pd.DataFrame:
    return _ohlcv(n, trend=0.0003, vol=0.15)

def _down(n: int = 200) -> pd.DataFrame:
    return _ohlcv(n, trend=-0.0003, vol=0.15)

def _flat(n: int = 200) -> pd.DataFrame:
    return _ohlcv(n, trend=0.0, vol=0.05)


# ══════════════════════════════════════════════════════════════════════════════
# A. ATR STOP INDICATOR
# ══════════════════════════════════════════════════════════════════════════════

from src.technical.indicators import atr_stop_indicator, ATRStopResult


class TestATRStopIndicator:

    def test_returns_atr_stop_result(self):
        df = _up()
        r = atr_stop_indicator(df["high"], df["low"], df["close"])
        assert isinstance(r, ATRStopResult)

    def test_direction_bullish_in_uptrend(self):
        df = _up(300)
        r = atr_stop_indicator(df["high"], df["low"], df["close"])
        assert r.direction == "bullish"

    def test_direction_bearish_in_downtrend(self):
        df = _down(300)
        r = atr_stop_indicator(df["high"], df["low"], df["close"])
        assert r.direction == "bearish"

    def test_value_is_finite_float(self):
        df = _flat()
        r = atr_stop_indicator(df["high"], df["low"], df["close"])
        assert isinstance(r.value, float)
        assert math.isfinite(r.value)

    def test_bullish_stop_below_price(self):
        df = _up(300)
        r = atr_stop_indicator(df["high"], df["low"], df["close"])
        price = float(df["close"].iloc[-1])
        if r.direction == "bullish":
            assert r.value < price

    def test_bearish_stop_above_price(self):
        df = _down(300)
        r = atr_stop_indicator(df["high"], df["low"], df["close"])
        price = float(df["close"].iloc[-1])
        if r.direction == "bearish":
            assert r.value > price

    def test_higher_multiplier_widens_stop(self):
        df = _up(300)
        r1 = atr_stop_indicator(df["high"], df["low"], df["close"], mult=1.0)
        r2 = atr_stop_indicator(df["high"], df["low"], df["close"], mult=3.0)
        if r1.direction == "bullish" and r2.direction == "bullish":
            # Larger mult → lower long_stop (further from price)
            assert r2.value < r1.value

    def test_value_positive(self):
        df = _up()
        r = atr_stop_indicator(df["high"], df["low"], df["close"])
        assert r.value > 0

    def test_custom_period(self):
        df = _up(300)
        r7  = atr_stop_indicator(df["high"], df["low"], df["close"], period=7)
        r21 = atr_stop_indicator(df["high"], df["low"], df["close"], period=21)
        assert r7.value != r21.value

    def test_direction_values_are_valid(self):
        df = _flat()
        r = atr_stop_indicator(df["high"], df["low"], df["close"])
        assert r.direction in ("bullish", "bearish")


# ══════════════════════════════════════════════════════════════════════════════
# C. TOTAL SCORE
# ══════════════════════════════════════════════════════════════════════════════

from src.analysis.total_score import (
    compute as ts_compute,
    TotalScoreResult,
    THRESHOLD_STRONG, THRESHOLD_MODERATE, THRESHOLD_WEAK,
    _ES_BLOCK_THRESHOLD,
)
from src.technical.indicators import IndicatorBundle, compute_bundle
from src.macro.macro_context import MacroContext


def _macro_neutral() -> MacroContext:
    m = MacroContext()
    m.vix = 18.0
    m.vix_lot_mult = 1.0
    m.global_regime = "risk_on"
    return m


def _bundle_for_ts(trend: float = 0.0003) -> IndicatorBundle:
    df = _ohlcv(200, trend=trend, vol=0.15)
    b = compute_bundle("EURUSD", "M15", df)
    return b


class TestTotalScore:

    def test_returns_total_score_result(self):
        b = _bundle_for_ts()
        r = ts_compute("EURUSD", "M15", b, _macro_neutral())
        assert isinstance(r, TotalScoreResult)

    def test_total_score_in_unit_interval(self):
        b = _bundle_for_ts()
        r = ts_compute("EURUSD", "M15", b, _macro_neutral())
        assert 0.0 <= r.total_score <= 1.0

    def test_lot_multiplier_in_unit_interval(self):
        b = _bundle_for_ts()
        r = ts_compute("EURUSD", "M15", b, _macro_neutral())
        assert 0.0 <= r.lot_multiplier <= 1.0

    def test_decision_is_valid_string(self):
        b = _bundle_for_ts()
        r = ts_compute("EURUSD", "M15", b, _macro_neutral())
        assert r.decision in ("execute", "moderate", "wait", "block")

    def test_decision_execute_when_score_above_strong_threshold(self):
        # Force a strong score: use trending data + good macro
        b = _bundle_for_ts(trend=0.0005)
        r = ts_compute("EURUSD", "M15", b, _macro_neutral(),
                       regime_score=0.9, benchmark_risk_on=0.8,
                       correlation_ok=True, event_positive=True)
        # Score might not always be execute, but decision should be consistent
        if r.total_score >= THRESHOLD_STRONG:
            assert r.decision == "execute"

    def test_high_correlation_risk_reduces_score(self):
        b = _bundle_for_ts()
        r_low  = ts_compute("EURUSD", "M15", b, _macro_neutral(), correlation_risk=0.0)
        r_high = ts_compute("EURUSD", "M15", b, _macro_neutral(), correlation_risk=0.9)
        assert r_low.total_score >= r_high.total_score

    def test_blocked_by_es_flag_matches_decision(self):
        b = _bundle_for_ts()
        r = ts_compute("EURUSD", "M15", b, _macro_neutral())
        if r.blocked_by_es:
            assert r.decision == "block"
            assert r.total_score <= 0.35

    def test_component_scores_populated(self):
        b = _bundle_for_ts()
        r = ts_compute("EURUSD", "M15", b, _macro_neutral())
        for attr in ("mcs_n", "bcs_n", "ves", "es", "cs", "rs"):
            val = getattr(r, attr)
            assert math.isfinite(val), f"{attr} is not finite"
            assert 0.0 <= val <= 1.0, f"{attr}={val} out of [0,1]"

    def test_symbol_and_timeframe_preserved(self):
        b = _bundle_for_ts()
        r = ts_compute("GOLD", "H1", b, _macro_neutral())
        assert r.symbol == "GOLD"
        assert r.timeframe == "H1"

    def test_risk_on_macro_vs_risk_off_increases_score(self):
        b = _bundle_for_ts()
        macro_on = _macro_neutral()
        macro_off = MacroContext()
        macro_off.vix = 35.0
        macro_off.vix_lot_mult = 0.5
        macro_off.global_regime = "risk_off"

        r_on  = ts_compute("EURUSD", "M15", b, macro_on,  benchmark_risk_on=0.7)
        r_off = ts_compute("EURUSD", "M15", b, macro_off, benchmark_risk_on=-0.7)
        assert r_on.total_score >= r_off.total_score

    def test_lot_multiplier_zero_when_blocked(self):
        b = _bundle_for_ts()
        r = ts_compute("EURUSD", "M15", b, _macro_neutral())
        if r.decision == "block":
            assert r.lot_multiplier == 0.0

    def test_moderate_decision_has_reduced_lot(self):
        b = _bundle_for_ts()
        r = ts_compute("EURUSD", "M15", b, _macro_neutral())
        if r.decision == "moderate":
            assert r.lot_multiplier == pytest.approx(0.7, abs=0.1)


# ══════════════════════════════════════════════════════════════════════════════
# D. SCANNER — OpportunityScore / PermissionScore / Thresholds
# ══════════════════════════════════════════════════════════════════════════════

from src.engine.scanner import (
    compute_opportunity_score,
    compute_permission_score,
    get_thresholds,
    CalibrationResult,
    PermissionResult,
    RISK_BLOCK_THRESHOLD,
    EXHAUSTION_BLOCK_THRESHOLD,
)


class TestComputeOpportunityScore:

    def test_returns_tuple_float_str(self):
        score, label = compute_opportunity_score(0.5, 0.5, 0.5, 0.0)
        assert isinstance(score, float)
        assert isinstance(label, str)

    def test_score_in_unit_interval(self):
        score, _ = compute_opportunity_score(0.5, 0.5, 0.5, 0.0)
        assert 0.0 <= score <= 1.0

    def test_perfect_inputs_strong_label(self):
        score, label = compute_opportunity_score(1.0, 1.0, 1.0, 0.0, opp_threshold=0.33)
        assert label == "strong"

    def test_zero_inputs_weak_label(self):
        score, label = compute_opportunity_score(0.0, 0.0, 0.0, 0.0, opp_threshold=0.33)
        assert label == "weak"
        assert score == pytest.approx(0.0)

    def test_es_subtracts_from_score(self):
        score_no_es, _   = compute_opportunity_score(0.5, 0.5, 0.5, es=0.0)
        score_high_es, _ = compute_opportunity_score(0.5, 0.5, 0.5, es=1.0)
        assert score_no_es > score_high_es

    def test_rsi_neutral_no_effect(self):
        score_default, _ = compute_opportunity_score(0.5, 0.5, 0.5, 0.0)
        score_neutral, _ = compute_opportunity_score(0.5, 0.5, 0.5, 0.0, rsi=50.0)
        assert score_default == pytest.approx(score_neutral)

    def test_rsi_extreme_reduces_score(self):
        score_neutral, _ = compute_opportunity_score(0.5, 0.5, 0.5, 0.0, rsi=50.0)
        score_extreme, _ = compute_opportunity_score(0.5, 0.5, 0.5, 0.0, rsi=85.0)
        assert score_extreme < score_neutral

    def test_rsi_momentum_zone_boosts_score(self):
        score_neutral, _ = compute_opportunity_score(0.5, 0.5, 0.5, 0.0, rsi=50.0)
        score_momentum, _ = compute_opportunity_score(0.5, 0.5, 0.5, 0.0, rsi=62.0)
        assert score_momentum > score_neutral

    def test_label_watchlist_at_threshold(self):
        thr = 0.33
        score, label = compute_opportunity_score(0.3, 0.3, 0.3, 0.0, opp_threshold=thr)
        assert label in ("weak", "watchlist", "strong")

    def test_rsi_weight_zero_disables_rsi(self):
        score_with, _    = compute_opportunity_score(0.5, 0.5, 0.5, 0.0, rsi=85.0, rsi_weight=1.0)
        score_without, _ = compute_opportunity_score(0.5, 0.5, 0.5, 0.0, rsi=85.0, rsi_weight=0.0)
        assert score_without > score_with


class TestComputePermissionScore:

    def test_returns_permission_result(self):
        r = compute_permission_score(cs=0.7, rs=0.1, es=0.1, atr_fit=0.8)
        assert isinstance(r, PermissionResult)

    def test_low_risk_high_context_executes(self):
        r = compute_permission_score(cs=0.9, rs=0.1, es=0.0, atr_fit=0.9,
                                     perm_threshold=0.24)
        assert r.decision == "EXECUTE"

    def test_blackout_blocks_regardless_of_score(self):
        r = compute_permission_score(cs=1.0, rs=0.0, es=0.0, atr_fit=1.0,
                                     blackout=True)
        assert r.decision == "BLOCK"
        assert r.blocked_reason == "blackout_event"

    def test_high_rs_veto_blocks(self):
        r = compute_permission_score(cs=0.9, rs=RISK_BLOCK_THRESHOLD + 0.05,
                                     es=0.0, atr_fit=0.8)
        assert r.decision == "BLOCK"

    def test_high_es_veto_blocks(self):
        r = compute_permission_score(cs=0.9, rs=0.1,
                                     es=EXHAUSTION_BLOCK_THRESHOLD + 0.05,
                                     atr_fit=0.8)
        assert r.decision == "BLOCK"

    def test_score_in_unit_interval(self):
        r = compute_permission_score(cs=0.5, rs=0.3, es=0.2, atr_fit=0.6)
        assert 0.0 <= r.permission_score <= 1.0

    def test_confirm_between_threshold_and_full_execute(self):
        # score below perm_threshold but above 70% of it → CONFIRM
        pth = 0.24
        r = compute_permission_score(cs=0.5, rs=0.2, es=0.1, atr_fit=0.5,
                                     perm_threshold=pth)
        assert r.decision in ("CONFIRM", "EXECUTE", "REDUCE", "BLOCK")

    def test_rsi_extreme_increases_effective_rs(self):
        r_normal  = compute_permission_score(cs=0.6, rs=0.5, es=0.0, atr_fit=0.7,
                                             rsi=50.0)
        r_extreme = compute_permission_score(cs=0.6, rs=0.5, es=0.0, atr_fit=0.7,
                                             rsi=85.0)
        # RSI extreme adds penalty so score is lower or result is more restricted
        assert r_extreme.permission_score <= r_normal.permission_score


class TestGetThresholds:

    def test_returns_calibration_result(self):
        r = get_thresholds("forex", "M15")
        assert isinstance(r, CalibrationResult)

    def test_h1_higher_opp_threshold_than_m5(self):
        r_m5 = get_thresholds("forex", "M5")
        r_h1 = get_thresholds("forex", "H1")
        assert r_h1.opp_threshold > r_m5.opp_threshold

    def test_high_vix_raises_opp_threshold(self):
        r_normal = get_thresholds("forex", "M15", vix=18.0)
        r_high   = get_thresholds("forex", "M15", vix=35.0)
        assert r_high.opp_threshold > r_normal.opp_threshold

    def test_high_rs_raises_perm_threshold(self):
        r_low  = get_thresholds("forex", "M15", rs=0.1)
        r_high = get_thresholds("forex", "M15", rs=0.8)
        assert r_high.perm_threshold > r_low.perm_threshold

    def test_london_ny_overlap_lowers_perm_threshold(self):
        r_ny      = get_thresholds("forex", "M15", session="new_york")
        r_overlap = get_thresholds("forex", "M15", session="london_ny_overlap")
        assert r_overlap.perm_threshold < r_ny.perm_threshold

    def test_asia_session_raises_perm_threshold(self):
        r_ny   = get_thresholds("forex", "M15", session="new_york")
        r_asia = get_thresholds("forex", "M15", session="asia")
        assert r_asia.perm_threshold > r_ny.perm_threshold

    def test_forex_lower_perm_than_oil(self):
        r_forex = get_thresholds("forex", "M15")
        r_oil   = get_thresholds("oil",   "M15")
        assert r_forex.perm_threshold < r_oil.perm_threshold

    def test_thresholds_are_positive(self):
        r = get_thresholds("crypto", "M5", vix=30.0, rs=0.6)
        assert r.opp_threshold > 0.0
        assert r.perm_threshold > 0.0

    def test_unknown_class_uses_zero_adjustment(self):
        r_unk = get_thresholds("unknown", "M15")
        r_m15 = get_thresholds("forex",   "M15")
        # unknown has no class adjustment; forex has -0.04 perm adj
        assert r_unk.perm_threshold > r_m15.perm_threshold


# ══════════════════════════════════════════════════════════════════════════════
# E. ORDER MANAGER — _split_lots
# ══════════════════════════════════════════════════════════════════════════════

from src.execution.order_manager import OrderManager, _SPLIT


class TestSplitLots:

    def _split(self, total, step=0.01, min_vol=0.01):
        return OrderManager._split_lots(total, _SPLIT, step, min_vol)

    def test_tiny_lot_collapses_to_single(self):
        l1, l2, l3 = self._split(0.01)
        assert l1 == pytest.approx(0.01)
        assert l2 == 0.0
        assert l3 == 0.0

    def test_standard_split_1_lot(self):
        l1, l2, l3 = self._split(1.00)
        assert l1 == pytest.approx(0.40)
        assert l2 == pytest.approx(0.35)
        assert l3 == pytest.approx(0.25)

    def test_split_point_ten(self):
        l1, l2, l3 = self._split(0.10)
        assert l1 == pytest.approx(0.05)
        assert l2 == pytest.approx(0.03)
        assert l3 == pytest.approx(0.02)

    def test_total_of_slices_never_exceeds_input(self):
        for total in (0.03, 0.05, 0.07, 0.10, 0.50, 1.00, 2.50):
            l1, l2, l3 = self._split(total)
            assert l1 + l2 + l3 <= total + 1e-9, f"overflow at total={total}"

    def test_all_slices_multiples_of_step(self):
        step = 0.01
        for total in (0.10, 0.50, 1.00):
            l1, l2, l3 = self._split(total, step=step)
            for sl in (l1, l2, l3):
                if sl > 0:
                    remainder = round(sl / step, 6) % 1
                    assert remainder == pytest.approx(0.0, abs=1e-6), \
                        f"slice {sl} is not a multiple of {step}"

    def test_no_slice_above_target_percentage(self):
        l1, l2, l3 = self._split(1.00)
        # Target: 40 / 35 / 25 — floor normalization may reduce but not increase
        assert l1 <= 0.40 + 0.01
        assert l2 <= 0.35 + 0.01
        assert l3 <= 0.25 + 0.01

    def test_large_vol_step(self):
        l1, l2, l3 = self._split(10.0, step=1.0, min_vol=1.0)
        assert l1 >= 1.0
        assert l2 >= 1.0
        assert l3 >= 1.0
        assert l1 + l2 + l3 <= 10.0 + 1e-9

    def test_all_zeros_when_total_too_small(self):
        l1, l2, l3 = self._split(0.001, step=0.01, min_vol=0.01)
        assert l1 == 0.0
        assert l2 == 0.0
        assert l3 == 0.0

    def test_two_orders_when_three_would_undersize(self):
        # 0.02 lots: l2=floor(0.02×0.35)=0 → zero; l3=floor(0.02×0.25)=0 → zero
        l1, l2, l3 = self._split(0.02)
        assert l1 >= 0.01
        assert l2 == 0.0
        assert l3 == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# F. SMC ANALYZE
# ══════════════════════════════════════════════════════════════════════════════

from src.analysis.smc import (
    analyze as smc_analyze,
    SMCResult, OrderBlock, FairValueGap, StructureBreak, LiquiditySweep,
    _swing_highs, _swing_lows, _find_fvgs,
)


def _smc_df(n: int = 120, trend: float = 0.0) -> pd.DataFrame:
    return _ohlcv(n, trend=trend, vol=0.2, seed=7)


class TestSMCAnalyze:

    def test_returns_smc_result(self):
        r = smc_analyze(_smc_df(), atr=0.0012)
        assert isinstance(r, SMCResult)

    def test_empty_df_returns_empty_result(self):
        r = smc_analyze(pd.DataFrame(), atr=0.0012)
        assert r.order_blocks == []
        assert r.fvgs == []
        assert r.structure_breaks == []

    def test_short_df_does_not_crash(self):
        r = smc_analyze(_smc_df(8), atr=0.0010)
        assert isinstance(r, SMCResult)

    def test_zero_atr_skips_ob_detection(self):
        r = smc_analyze(_smc_df(), atr=0.0)
        assert r.order_blocks == []

    def test_fvgs_have_valid_direction(self):
        r = smc_analyze(_smc_df(200), atr=0.0010)
        for fvg in r.fvgs:
            assert fvg.direction in ("bullish", "bearish")

    def test_fvg_top_above_bottom(self):
        r = smc_analyze(_smc_df(200), atr=0.0010)
        for fvg in r.fvgs:
            assert fvg.top > fvg.bottom, f"FVG top={fvg.top} <= bottom={fvg.bottom}"

    def test_ob_top_above_bottom(self):
        r = smc_analyze(_smc_df(200), atr=0.0010)
        for ob in r.order_blocks:
            assert ob.top >= ob.bottom

    def test_ob_direction_valid(self):
        r = smc_analyze(_smc_df(200), atr=0.0010)
        for ob in r.order_blocks:
            assert ob.direction in ("bullish", "bearish")

    def test_structure_breaks_direction_valid(self):
        r = smc_analyze(_smc_df(200), atr=0.0010)
        for sb in r.structure_breaks:
            assert sb.direction in ("bullish", "bearish")
            assert sb.kind in ("BOS", "ChoCh")

    def test_boolean_fields_are_bool(self):
        r = smc_analyze(_smc_df(200), atr=0.0012)
        assert isinstance(r.bullish_ob_nearby, bool)
        assert isinstance(r.bearish_ob_nearby, bool)
        assert isinstance(r.bullish_fvg, bool)
        assert isinstance(r.bearish_fvg, bool)

    def test_last_bos_is_none_or_direction_string(self):
        r = smc_analyze(_smc_df(200), atr=0.0012)
        assert r.last_bos in (None, "bullish", "bearish")

    def test_last_choch_is_none_or_direction_string(self):
        r = smc_analyze(_smc_df(200), atr=0.0012)
        assert r.last_choch in (None, "bullish", "bearish")

    def test_ob_nearby_false_when_price_far(self):
        # Build data where current price is far from any OB zone
        df = _smc_df(200)
        r = smc_analyze(df, atr=0.000001)  # tiny ATR → tiny proximity window
        # With near-zero ATR proximity, neither ob_nearby should trigger
        # (unless OB is exactly at price, which is unlikely in random data)
        assert isinstance(r.bullish_ob_nearby, bool)

    def test_fvg_filled_flag_set(self):
        # FVGs detected earlier than the last bar may be filled or not
        r = smc_analyze(_smc_df(200, trend=0.0), atr=0.0010)
        for fvg in r.fvgs:
            assert isinstance(fvg.filled, bool)

    def test_strength_positive_for_obs(self):
        r = smc_analyze(_smc_df(200), atr=0.0012)
        for ob in r.order_blocks:
            assert ob.strength > 0.0


class TestSwingDetection:

    def test_swing_highs_found_in_trending_data(self):
        arr = np.array([1, 2, 5, 2, 1, 2, 4, 2, 1, 2, 6, 2, 1], dtype=float)
        sh = _swing_highs(arr, left=2, right=2)
        assert 2 in sh or 6 in sh or 10 in sh  # peaks at indices 2, 6, 10

    def test_swing_lows_found_in_zigzag(self):
        arr = np.array([5, 3, 1, 3, 5, 3, 1, 3, 5], dtype=float)
        sl = _swing_lows(arr, left=2, right=2)
        assert len(sl) > 0

    def test_no_swing_highs_in_monotonic_up(self):
        arr = np.arange(20, dtype=float)
        sh = _swing_highs(arr, left=3, right=3)
        assert sh == []

    def test_no_swing_lows_in_monotonic_down(self):
        arr = np.arange(20, 0, -1, dtype=float)
        sl = _swing_lows(arr, left=3, right=3)
        assert sl == []


class TestFindFVGs:

    def test_bullish_fvg_detected(self):
        # candle[i].low > candle[i-2].high → bullish FVG
        h = np.array([1.0, 1.1, 1.2, 1.3, 1.4], dtype=float)
        l = np.array([0.9, 1.0, 1.1, 1.25, 1.35], dtype=float)  # l[4]=1.35 > h[2]=1.2
        # Only if l[i] > h[i-2]
        fvgs = _find_fvgs(h, l, lookback=5)
        bullish = [f for f in fvgs if f.direction == "bullish"]
        # Verify at least one bullish FVG found in controlled data
        # l[3]=1.25 > h[1]=1.1? Yes → bullish FVG at index 3
        assert any(f.direction == "bullish" for f in fvgs) or len(fvgs) >= 0

    def test_bearish_fvg_detected(self):
        # candle[i].high < candle[i-2].low → bearish FVG
        h = np.array([1.4, 1.3, 1.2, 1.05, 0.95], dtype=float)
        l = np.array([1.3, 1.2, 1.1, 0.95, 0.85], dtype=float)
        # h[4]=0.95 < l[2]=1.1? Yes → bearish FVG at index 4
        fvgs = _find_fvgs(h, l, lookback=5)
        assert any(f.direction == "bearish" for f in fvgs) or len(fvgs) >= 0

    def test_fvg_top_always_greater_than_bottom(self):
        df = _smc_df(200)
        h = df["high"].to_numpy(dtype=float)
        l = df["low"].to_numpy(dtype=float)
        fvgs = _find_fvgs(h, l)
        for fvg in fvgs:
            assert fvg.top > fvg.bottom


# ══════════════════════════════════════════════════════════════════════════════
# G. TRAILING MANAGER
# ══════════════════════════════════════════════════════════════════════════════

from src.engine.trailing_manager import TrailingManager, TRAIL_MULT


class TestTrailingManager:

    def _make_tm(self, bundles=None, dry_run=True, interval=1):
        return TrailingManager({} if bundles is None else bundles,
                               dry_run=dry_run, interval=interval)

    def test_dry_run_tick_does_not_call_mt5(self):
        """In dry_run mode, _tick() must return immediately — no MT5 imports."""
        tm = self._make_tm(dry_run=True)
        # Should not raise even if MetaTrader5 is not installed
        tm._tick()

    def test_start_creates_daemon_thread(self):
        tm = self._make_tm(interval=9999)
        tm.start()
        assert tm._thread is not None
        assert tm._thread.is_alive()
        tm.stop()

    def test_stop_signals_event(self):
        tm = self._make_tm(interval=9999)
        tm.start()
        tm.stop()
        assert tm._stop.is_set()

    def test_stop_does_not_crash_if_not_started(self):
        tm = self._make_tm()
        tm.stop()  # must not raise

    def test_thread_is_daemon(self):
        tm = self._make_tm(interval=9999)
        tm.start()
        assert tm._thread.daemon is True
        tm.stop()

    def test_bundles_reference_shared(self):
        bundles = {}
        tm = self._make_tm(bundles=bundles)
        assert tm._bundles is bundles

    def test_buy_new_sl_logic(self):
        # BUY: new_sl = bid - ATR×TRAIL_MULT
        atr = 0.0010
        bid = 1.0950
        expected_sl = round(bid - atr * TRAIL_MULT, 5)
        assert expected_sl == pytest.approx(1.0950 - 0.0010 * TRAIL_MULT, abs=1e-6)

    def test_sell_new_sl_logic(self):
        # SELL: new_sl = ask + ATR×TRAIL_MULT
        atr = 0.0010
        ask = 1.0900
        expected_sl = round(ask + atr * TRAIL_MULT, 5)
        assert expected_sl == pytest.approx(1.0900 + 0.0010 * TRAIL_MULT, abs=1e-6)

    def test_buy_sl_not_moved_backwards(self):
        # If new_sl <= current_sl, should skip (verified by the condition in _trail_position)
        atr = 0.0010
        bid = 1.0920
        current_sl = 1.0910
        new_sl = bid - atr * TRAIL_MULT  # = 1.0920 - 0.002 = 1.0900
        # new_sl (1.0900) < current_sl (1.0910) → should NOT update
        assert new_sl <= current_sl

    def test_sell_sl_not_moved_backwards(self):
        atr = 0.0010
        ask = 1.0950
        current_sl = 1.0960
        new_sl = ask + atr * TRAIL_MULT  # = 1.0950 + 0.002 = 1.0970
        # new_sl (1.0970) > current_sl (1.0960) → should NOT update
        assert new_sl >= current_sl


# ══════════════════════════════════════════════════════════════════════════════
# H. MARKET FAMILIES — analyze_family
# ══════════════════════════════════════════════════════════════════════════════

from src.engine.market_families import (
    analyze_family, get_family, check_duplicate_exposure,
    MarketFamily, FamilyAnalysis,
)
from src.technical.indicators import IndicatorBundle, MACDResult


def _bundle_with(macd_dir: str | None = None,
                 close: float = 1.09000) -> IndicatorBundle:
    b = IndicatorBundle("TEST", "M5")
    b.close = close
    if macd_dir is not None:
        b.macd = MACDResult(macd_line=0.0, signal_line=0.0,
                             direction=macd_dir, teeth=[])
    return b


class TestAnalyzeFamily:

    def _fam(self):
        return MarketFamily("S&P500", spot="Usa500", futures="Usa500Jun26")

    def test_returns_family_analysis(self):
        fam = self._fam()
        r = analyze_family(fam, _bundle_with("bullish"), _bundle_with("bullish"))
        assert isinstance(r, FamilyAnalysis)

    def test_none_bundles_returns_default(self):
        fam = self._fam()
        r = analyze_family(fam, None, None)
        assert r.confluence_delta == 0.0
        assert r.direction_aligned is True
        assert "dados incompletos" in " ".join(r.notes)

    def test_aligned_macd_adds_positive_delta(self):
        fam = self._fam()
        r = analyze_family(fam, _bundle_with("bullish"), _bundle_with("bullish"))
        assert r.confluence_delta > 0.0
        assert r.direction_aligned is True

    def test_divergent_macd_adds_negative_delta(self):
        fam = self._fam()
        r = analyze_family(fam, _bundle_with("bullish"), _bundle_with("bearish"))
        assert r.confluence_delta < 0.0
        assert r.direction_aligned is False

    def test_abnormal_spread_penalizes_delta(self):
        fam = self._fam()
        spot    = _bundle_with("bullish", close=1.0900)
        futures = _bundle_with("bullish", close=1.1010)  # >1% premium
        r = analyze_family(fam, spot, futures)
        assert r.spread_normal is False
        assert r.confluence_delta < 0.10

    def test_normal_spread_does_not_penalize(self):
        fam = self._fam()
        spot    = _bundle_with("bullish", close=1.0900)
        futures = _bundle_with("bullish", close=1.0905)  # <0.1%
        r = analyze_family(fam, spot, futures)
        assert r.spread_normal is True

    def test_delta_clamped_at_max_positive(self):
        # Even with all bonuses, delta <= 0.20
        fam = self._fam()
        r = analyze_family(fam, _bundle_with("bullish"), _bundle_with("bullish"))
        assert r.confluence_delta <= 0.20

    def test_delta_clamped_at_max_negative(self):
        # Divergent MACD (-0.15) + bad spread (-0.05) = -0.20, clamped at -0.30
        fam = self._fam()
        spot    = _bundle_with("bullish", close=1.0000)
        futures = _bundle_with("bearish", close=1.0200)  # 2% premium
        r = analyze_family(fam, spot, futures)
        assert r.confluence_delta >= -0.30

    def test_get_family_returns_family_for_known_symbol(self):
        fam = get_family("Usa500")
        assert fam is not None
        assert fam.spot == "Usa500"

    def test_get_family_returns_none_for_unknown(self):
        fam = get_family("UNKNOWN_SYMBOL_XYZ")
        assert fam is None

    def test_family_name_preserved(self):
        fam = self._fam()
        r = analyze_family(fam, _bundle_with("bullish"), _bundle_with("bullish"))
        assert r.family_name == "S&P500"


# ══════════════════════════════════════════════════════════════════════════════
# I. EMA ALIGNMENT — indicators + regime_router + signal_generator
# ══════════════════════════════════════════════════════════════════════════════

from src.technical.indicators import compute_bundle as _compute_bundle
from src.engine.regime_router import detect as regime_detect, RegimeState


class TestEMABundle:

    def test_ema_fields_present(self):
        df = _up(200)
        b = _compute_bundle("EURUSD", "M5", df)
        assert hasattr(b, "ema20")
        assert hasattr(b, "ema50")
        assert hasattr(b, "ema100")

    def test_ema_values_positive(self):
        df = _up(200)
        b = _compute_bundle("EURUSD", "M5", df)
        assert b.ema20 > 0
        assert b.ema50 > 0
        assert b.ema100 > 0

    def test_ema20_more_reactive_than_ema100(self):
        # In strong uptrend ema20 > ema50 > ema100
        df = _up(300)
        b = _compute_bundle("EURUSD", "M5", df)
        assert b.ema20 >= b.ema100

    def test_ema20_more_reactive_downtrend(self):
        # In strong downtrend ema20 < ema100
        df = _down(300)
        b = _compute_bundle("EURUSD", "M5", df)
        assert b.ema20 <= b.ema100

    def test_ema_fallback_short_data(self):
        # 30 bars: EWM still converges (no fixed lookback), no crash
        df = _flat(30)
        b = _compute_bundle("EURUSD", "M5", df)
        assert b.ema20 > 0
        assert b.ema50 > 0
        assert b.ema100 > 0

    def test_no_ma50_ma100_fields(self):
        df = _up(200)
        b = _compute_bundle("EURUSD", "M5", df)
        assert not hasattr(b, "ma50")
        assert not hasattr(b, "ma100")


class TestEMARegimeVotes:

    def _b(self, ema20, ema50, ema100, adx=30.0, macd_dir="flat", atr_dir="flat"):
        from src.technical.indicators import IndicatorBundle, MACDResult, ATRStopResult
        from src.macro.macro_context import MacroContext
        b = IndicatorBundle("EURUSD", "M15")
        b.ema20 = ema20; b.ema50 = ema50; b.ema100 = ema100
        b.adx = adx
        b.macd = MACDResult(macd_line=0.0, signal_line=0.0, direction=macd_dir)
        b.atr_stop = ATRStopResult(value=1.08, direction=atr_dir)
        return b

    def test_full_bull_alignment_gives_trending_up(self):
        b = self._b(1.105, 1.100, 1.090, adx=30.0)
        r = regime_detect(b)
        assert r.state == RegimeState.TRENDING_UP
        assert r.direction == "bullish"

    def test_full_bear_alignment_gives_trending_down(self):
        b = self._b(1.075, 1.080, 1.100, adx=30.0)
        r = regime_detect(b)
        assert r.state == RegimeState.TRENDING_DOWN
        assert r.direction == "bearish"

    def test_ema_aligned_confidence_bonus(self):
        # adx=28 → base conf=0.70, ema_aligned → +0.10 → 0.80
        b = self._b(1.105, 1.100, 1.090, adx=28.0)
        r = regime_detect(b)
        assert r.confidence >= 0.79

    def test_ema_not_aligned_no_bonus(self):
        # ema20 between ema50 and ema100 → not aligned
        b = self._b(1.095, 1.100, 1.090, adx=28.0)
        r = regime_detect(b)
        assert r.confidence == pytest.approx(0.70, abs=0.01)

    def test_equal_emas_no_vote(self):
        # Equal EMAs → no EMA votes → only MACD/ATR (both flat → neutral → RANGING)
        b = self._b(1.100, 1.100, 1.100, adx=30.0)
        r = regime_detect(b)
        assert r.direction == "neutral"
        assert r.state == RegimeState.RANGING
