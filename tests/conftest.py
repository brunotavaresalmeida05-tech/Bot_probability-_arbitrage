"""
tests/conftest.py
Fixtures partilhadas para toda a suite de testes.
Não requerem MT5, MetaTrader ou qualquer ligação externa.
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def _make_ohlcv(n: int = 250, base: float = 1.10000,
                volatility: float = 0.0010, seed: int = 42) -> pd.DataFrame:
    """Gera um DataFrame OHLCV sintético realístico."""
    rng = np.random.default_rng(seed)
    # Passeio aleatório para close
    returns = rng.normal(0, volatility, n)
    close   = base + np.cumsum(returns)
    # OHLCV derivado de close
    noise   = rng.uniform(0.0001, 0.0005, n)
    high    = close + noise
    low     = close - noise
    open_   = np.roll(close, 1)
    open_[0] = close[0]
    volume  = rng.integers(1000, 10000, n).astype(float)

    idx = pd.date_range(
        start=datetime(2024, 1, 1, 8, 0, 0),
        periods=n,
        freq="5min",
    )
    return pd.DataFrame({
        "open":   open_,
        "high":   high,
        "low":    low,
        "close":  close,
        "volume": volume,
    }, index=idx)


@pytest.fixture
def sample_ohlcv():
    """DataFrame OHLCV genérico com 250 barras (M5)."""
    return _make_ohlcv(n=250)


@pytest.fixture
def short_ohlcv():
    """DataFrame curto (50 barras) para testar casos limite."""
    return _make_ohlcv(n=50)


@pytest.fixture
def stationary_spread(seed: int = 0) -> pd.Series:
    """
    Série AR(1) estacionária (phi=0.85).
    ADF deve rejeitar H0 → is_stationary=True.
    """
    rng = np.random.default_rng(seed)
    n, phi, eps = 200, 0.85, rng.normal(0, 1, 200)
    x = np.zeros(n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + eps[i]
    return pd.Series(x, name="spread")


@pytest.fixture
def random_walk_spread(seed: int = 1) -> pd.Series:
    """
    Random walk I(1) — ADF não deve rejeitar H0 → is_stationary=False.
    """
    rng = np.random.default_rng(seed)
    eps = rng.normal(0, 1, 200)
    return pd.Series(np.cumsum(eps), name="spread")


@pytest.fixture
def two_cointegrated_series(seed: int = 2):
    """
    Par de séries cointegradas (simuladas).
    Retorna (series_a, series_b, spread_esperado).
    """
    rng   = np.random.default_rng(seed)
    n     = 300
    noise = rng.normal(0, 0.5, n)
    trend = np.cumsum(rng.normal(0, 0.1, n))   # passeio comum
    a     = 1.10 + trend + rng.normal(0, 0.001, n)
    b     = 1.10 + 0.95 * trend + noise * 0.01 + rng.normal(0, 0.001, n)
    return (
        pd.Series(a, name="EURUSD"),
        pd.Series(b, name="GBPUSD"),
    )
