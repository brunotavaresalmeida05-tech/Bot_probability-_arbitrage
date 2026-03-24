"""
tests/test_arb_strategy.py
Testa src/arb_strategy.py sem qualquer ligação ao MT5.
Cobre: adf_test, compute_half_life, compute_hedge_ratio,
       compute_spread_zscore, compute_correlation, compute_pair_score.
"""
import sys
import os
import pytest
import numpy as np
import pandas as pd

# path setup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mockar src.external_data antes de importar arb_strategy
from unittest.mock import MagicMock
sys.modules["src.external_data"] = MagicMock()

import src.arb_strategy as arb


# ─── adf_test ──────────────────────────────────────────────

class TestAdfTest:
    def test_stationary_series_is_stationary(self, stationary_spread):
        """Série AR(1) phi=0.85 deve ser reconhecida como estacionária."""
        result = arb.adf_test(stationary_spread)
        assert result["is_stationary"] is True
        assert result["p_value"] <= arb.ADF_PVALUE_THRESHOLD

    def test_random_walk_not_stationary(self, random_walk_spread):
        """Random walk I(1) não deve ser estacionário (com alta probabilidade)."""
        result = arb.adf_test(random_walk_spread)
        # não garantido 100% mas p_value deve ser alto
        assert result["p_value"] >= arb.ADF_PVALUE_THRESHOLD

    def test_too_short_series_returns_no_stationarity(self):
        """Série com <20 obs retorna is_stationary=False."""
        short = pd.Series([1.0, 2.0, 1.5, 1.8])
        result = arb.adf_test(short)
        assert result["is_stationary"] is False
        assert result["p_value"] == 1.0

    def test_returns_required_keys(self, stationary_spread):
        result = arb.adf_test(stationary_spread)
        for key in ("adf_stat", "p_value", "is_stationary", "n_obs", "n_lags"):
            assert key in result

    def test_adf_stat_more_negative_for_stationary(self, stationary_spread, random_walk_spread):
        """Série estacionária deve ter ADF stat mais negativo."""
        stat_stat = arb.adf_test(stationary_spread)["adf_stat"]
        rw_stat   = arb.adf_test(random_walk_spread)["adf_stat"]
        assert stat_stat < rw_stat

    def test_highly_stationary_series(self):
        """Série com phi=0.0 (ruído branco) deve ser estacionária."""
        rng = np.random.default_rng(99)
        white_noise = pd.Series(rng.normal(0, 1, 200))
        result = arb.adf_test(white_noise)
        assert result["is_stationary"] is True


# ─── compute_half_life ─────────────────────────────────────

class TestHalfLife:
    def test_stationary_has_positive_half_life(self, stationary_spread):
        hl = arb.compute_half_life(stationary_spread)
        assert hl is not None
        assert hl > 0

    def test_stationary_half_life_reasonable(self, stationary_spread):
        """phi=0.85 → half_life ≈ ln(2)/ln(1/0.85) ≈ 4.3 barras."""
        hl = arb.compute_half_life(stationary_spread)
        assert 1 < hl < 50  # aceitável para trading

    def test_random_walk_returns_none_or_large(self, random_walk_spread):
        """Random walk: beta_1 pode ser >0 ou >=0, retorna None."""
        hl = arb.compute_half_life(random_walk_spread)
        # Pode retornar None (beta_1>=0) ou valor muito grande (improvável reverter)
        if hl is not None:
            assert hl > arb.MAX_HALF_LIFE_BARS

    def test_too_short_returns_none(self):
        short = pd.Series([0.1, 0.2, -0.1, 0.0])
        assert arb.compute_half_life(short) is None

    def test_constant_series_returns_none(self):
        """Série constante: variância zero → beta indefinido."""
        const = pd.Series([1.0] * 50)
        hl = arb.compute_half_life(const)
        assert hl is None


# ─── compute_hedge_ratio ───────────────────────────────────

class TestHedgeRatio:
    def test_hedge_ratio_known(self):
        """Se B = 2*A, hedge ratio ≈ 0.5."""
        rng = np.random.default_rng(5)
        a   = pd.Series(rng.normal(1.10, 0.01, 100))
        b   = 2.0 * a + rng.normal(0, 0.0001, 100)
        beta = arb.compute_hedge_ratio(a, b, window=80)
        assert beta == pytest.approx(0.5, rel=0.05)   # 5% tolerância

    def test_hedge_ratio_returns_float(self, two_cointegrated_series):
        a, b = two_cointegrated_series
        beta = arb.compute_hedge_ratio(a, b)
        assert isinstance(beta, float)

    def test_zero_variance_returns_one(self):
        a = pd.Series([1.0] * 80)
        b = pd.Series([2.0] * 80)
        assert arb.compute_hedge_ratio(a, b) == 1.0

    def test_hedge_ratio_positive(self, two_cointegrated_series):
        a, b = two_cointegrated_series
        beta = arb.compute_hedge_ratio(a, b)
        assert beta > 0


# ─── compute_spread_zscore ─────────────────────────────────

class TestSpreadZscore:
    def test_returns_tuple(self, two_cointegrated_series):
        a, b = two_cointegrated_series
        result = arb.compute_spread_zscore(a, b)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_zscore_finite_for_good_pair(self, two_cointegrated_series):
        a, b = two_cointegrated_series
        z, beta, spread = arb.compute_spread_zscore(a, b)
        assert np.isfinite(z)

    def test_too_short_returns_nan(self):
        short_a = pd.Series([1.0] * 10)
        short_b = pd.Series([1.1] * 10)
        z, beta, spread = arb.compute_spread_zscore(short_a, short_b)
        assert np.isnan(z)

    def test_standardized_spread_mean_approx_zero(self, two_cointegrated_series):
        """Ao longo de muitas janelas, z-score deve variar em torno de 0."""
        a, b = two_cointegrated_series
        zscores = []
        for i in range(60, len(a), 5):
            z, _, _ = arb.compute_spread_zscore(a[:i], b[:i])
            if np.isfinite(z):
                zscores.append(z)
        assert len(zscores) > 5
        assert abs(np.mean(zscores)) < 2.0  # média próxima de 0


# ─── compute_correlation ───────────────────────────────────

class TestCorrelation:
    def test_perfect_correlation(self):
        rng = np.random.default_rng(10)
        a = pd.Series(rng.normal(0, 1, 100).cumsum() + 1.10)
        b = a.copy()
        corr = arb.compute_correlation(a, b)
        assert corr == pytest.approx(1.0, abs=1e-6)

    def test_negative_correlation(self):
        rng  = np.random.default_rng(11)
        base = pd.Series(rng.normal(0, 1, 100).cumsum())
        a    = base + 1.10
        b    = -base + 1.10
        corr = arb.compute_correlation(a, b)
        assert corr < -0.9

    def test_zero_correlation_for_independent(self):
        rng  = np.random.default_rng(12)
        a    = pd.Series(rng.normal(0, 1, 200))
        b    = pd.Series(rng.normal(0, 1, 200))
        corr = arb.compute_correlation(a, b)
        assert abs(corr) < 0.4  # não há correlação estrutural

    def test_short_series_returns_zero(self):
        a = pd.Series([1.0, 2.0, 1.5])
        b = pd.Series([1.1, 1.9, 1.4])
        assert arb.compute_correlation(a, b) == 0.0

    def test_range_minus_one_to_one(self, two_cointegrated_series):
        a, b   = two_cointegrated_series
        corr   = arb.compute_correlation(a, b)
        assert -1.0 <= corr <= 1.0
