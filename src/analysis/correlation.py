from __future__ import annotations
"""
Correlation Matrix — V9

Dynamic real-time correlation tracking:
  Dollar (DXY) × Interest Rates (10Y) × Equity Indices × Commodities

Key structural correlations (theoretical):
  DXY ↑ → Gold ↓, Oil ↓, Emerging Markets ↓
  DXY ↑ → USD pairs react: EURUSD ↓, GBPUSD ↓, USDJPY ↑
  Yields ↑ → Equities ↓ (discounting effect), Gold ↓ (opportunity cost)
  VIX ↑ → Risk assets ↓, Treasuries ↑ (safe haven), Gold ↑ (safe haven)
  Gold ↑ → DXY ↓ (inverse relationship)
  Oil ↑ → CAD ↑, NOK ↑ (petrocurrencies)

The matrix computes rolling 20-period correlation on actual returns.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Known structural correlation directions (sign: +1 or -1)
# These are used when live data is insufficient
STRUCTURAL_CORRELATIONS: dict[tuple[str, str], float] = {
    ("DXY", "GOLD"):      -0.80,
    ("DXY", "EURUSD"):    -0.90,
    ("DXY", "GBPUSD"):    -0.75,
    ("DXY", "AUDUSD"):    -0.65,
    ("DXY", "WTI"):       -0.60,
    ("DXY", "BRENT"):     -0.60,
    ("DXY", "SPX"):       -0.40,
    ("YIELDS_10Y", "SPX"): -0.50,
    ("YIELDS_10Y", "GOLD"): -0.55,
    ("VIX", "SPX"):       -0.85,
    ("VIX", "GOLD"):       0.40,
    ("VIX", "TREASURY"):   0.70,
    ("GOLD", "SILVER"):    0.85,
    ("WTI", "BRENT"):      0.95,
    ("SPX", "NAS100"):     0.92,
    ("SPX", "EURUSD"):     0.35,
}


@dataclass
class CorrelationState:
    """Rolling correlation matrix state."""
    pairs: dict[str, float] = field(default_factory=dict)      # "A_B" -> correlation coefficient
    regime_stress: float = 0.0      # 0-1 stress index (high = correlations breaking down)
    breakdown_detected: bool = False


class CorrelationMatrix:
    """
    Tracks price returns and computes rolling correlations.
    Uses structural correlations as priors when data is insufficient.
    """

    def __init__(self, window: int = 20):
        self._window = window
        self._returns: dict[str, list[float]] = {}
        self._state = CorrelationState()

    def update(self, symbol: str, pct_change: float):
        """Add a new return observation for a symbol."""
        if symbol not in self._returns:
            self._returns[symbol] = []
        buf = self._returns[symbol]
        buf.append(pct_change)
        if len(buf) > self._window:
            buf.pop(0)

    def get_correlation(self, a: str, b: str) -> float:
        """
        Get correlation between two symbols.
        Uses live rolling correlation if enough data; else structural prior.
        """
        ra = self._returns.get(a, [])
        rb = self._returns.get(b, [])
        n = min(len(ra), len(rb))
        if n >= 5:
            arr_a = np.array(ra[-n:])
            arr_b = np.array(rb[-n:])
            if arr_a.std() > 0 and arr_b.std() > 0:
                corr = float(np.corrcoef(arr_a, arr_b)[0, 1])
                if not np.isnan(corr):
                    return round(corr, 4)
        # Fallback to structural
        key = (a.upper(), b.upper())
        rev_key = (b.upper(), a.upper())
        return STRUCTURAL_CORRELATIONS.get(key) or STRUCTURAL_CORRELATIONS.get(rev_key) or 0.0

    def compute_state(self) -> CorrelationState:
        """Compute current correlation state for all tracked symbols."""
        pairs = {}
        syms = list(self._returns.keys())
        for i, a in enumerate(syms):
            for b in syms[i + 1:]:
                corr = self.get_correlation(a, b)
                pairs[f"{a}_{b}"] = corr

        # Stress: how much correlations deviate from structural (breakdown = risk-off)
        deviations = []
        for (a, b), structural in STRUCTURAL_CORRELATIONS.items():
            live = self.get_correlation(a, b)
            if live != structural:  # has live data
                deviations.append(abs(live - structural))

        stress = float(np.mean(deviations)) if deviations else 0.0
        breakdown = stress > 0.30   # significant correlation breakdown

        self._state = CorrelationState(
            pairs=pairs,
            regime_stress=round(stress, 4),
            breakdown_detected=breakdown,
        )
        return self._state

    def is_correlated_trade(self, new_symbol: str, open_symbols: list[str], threshold: float = 0.70) -> bool:
        """
        Returns True if new_symbol is highly correlated with any open position.
        Used to prevent doubling up on the same exposure.
        """
        for existing in open_symbols:
            corr = abs(self.get_correlation(new_symbol, existing))
            if corr >= threshold:
                logger.debug(f"Correlation veto: {new_symbol} vs {existing} = {corr:.2f}")
                return True
        return False

    def correlation_penalty(self, new_symbol: str, open_symbols: list[str]) -> float:
        """
        Returns a lot size multiplier [0.35, 1.0] based on correlation.
        Blueprint spec: correlated signal gets 65% lot cut (0.35×).
        """
        if self.is_correlated_trade(new_symbol, open_symbols, threshold=0.60):
            return 0.35   # 65% reduction as per blueprint
        return 1.0
