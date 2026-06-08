from __future__ import annotations
"""
VaR and Risk Metrics — V9

Implements:
  - Parametric VaR: z * σ * √t * exposure
  - Historical VaR: percentile of return distribution
  - Portfolio exposure tracking
  - Drawdown monitoring
  - Position-level risk decomposition

VaR is used to:
  - Set position size limits per tier
  - Monitor total portfolio risk
  - Trigger emergency reduction if portfolio VaR exceeds limit
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# Confidence levels for VaR
_Z_SCORES = {0.90: 1.282, 0.95: 1.645, 0.99: 2.326}


@dataclass
class VaRResult:
    symbol: str
    confidence: float           # e.g. 0.95
    horizon_days: float         # e.g. 1.0 for 1-day VaR
    var_pct: float              # VaR as % of exposure
    var_currency: float         # VaR in account currency
    exposure: float             # position value
    method: str                 # parametric | historical
    volatility_used: float      # annualized volatility


@dataclass
class PortfolioRiskSnapshot:
    total_var_pct: float                    # total portfolio VaR as % of equity
    total_exposure: float                   # sum of all position values
    diversification_ratio: float            # 1.0 = no diversification benefit
    largest_position: str                   # symbol with highest exposure
    var_by_symbol: dict[str, float] = field(default_factory=dict)
    equity: float = 0.0


def parametric_var(
    exposure: float,
    annualized_vol: float,
    horizon_days: float = 1.0,
    confidence: float = 0.95,
) -> VaRResult:
    """
    Parametric VaR = z * σ_daily * √horizon * exposure

    Where σ_daily = annualized_vol / √252
    """
    z = _Z_SCORES.get(confidence, 1.645)
    sigma_daily = annualized_vol / np.sqrt(252)
    var_pct = z * sigma_daily * np.sqrt(horizon_days)
    var_currency = var_pct * exposure

    return VaRResult(
        symbol="portfolio",
        confidence=confidence,
        horizon_days=horizon_days,
        var_pct=round(var_pct, 6),
        var_currency=round(var_currency, 2),
        exposure=round(exposure, 2),
        method="parametric",
        volatility_used=round(annualized_vol, 6),
    )


def historical_var(
    returns: list[float],
    exposure: float,
    confidence: float = 0.95,
    horizon_days: float = 1.0,
) -> VaRResult:
    """
    Historical VaR: percentile of actual return distribution.
    Returns are daily log-returns.
    """
    if len(returns) < 20:
        sigma = float(np.std(returns)) if returns else 0.01
        return parametric_var(exposure, sigma * np.sqrt(252), horizon_days, confidence)

    arr = np.array(returns)
    # Annualized vol from historical
    ann_vol = float(np.std(arr) * np.sqrt(252))
    # Historical VaR at given confidence
    percentile = (1.0 - confidence) * 100
    hist_var_1d = float(-np.percentile(arr, percentile))
    scaled_var = hist_var_1d * np.sqrt(horizon_days)

    return VaRResult(
        symbol="portfolio",
        confidence=confidence,
        horizon_days=horizon_days,
        var_pct=round(scaled_var, 6),
        var_currency=round(scaled_var * exposure, 2),
        exposure=round(exposure, 2),
        method="historical",
        volatility_used=round(ann_vol, 6),
    )


def calc_annualized_vol(price_returns: list[float]) -> float:
    """Calculate annualized volatility from log-returns."""
    if len(price_returns) < 5:
        return 0.15   # default 15% annualized
    return float(np.std(price_returns) * np.sqrt(252))


@dataclass
class DrawdownTracker:
    """Tracks real-time drawdown from equity peak."""
    peak_equity: float = 0.0
    current_equity: float = 0.0
    max_dd_pct: float = 0.0
    current_dd_pct: float = 0.0
    dd_history: list[float] = field(default_factory=list)

    def update(self, equity: float):
        self.current_equity = equity
        if equity > self.peak_equity:
            self.peak_equity = equity
        if self.peak_equity > 0:
            dd = (self.peak_equity - equity) / self.peak_equity
            self.current_dd_pct = round(dd, 6)
            self.max_dd_pct = max(self.max_dd_pct, dd)
            self.dd_history.append(dd)
            if len(self.dd_history) > 1000:
                self.dd_history.pop(0)

    def in_drawdown(self, threshold: float = 0.05) -> bool:
        return self.current_dd_pct > threshold

    def to_dict(self) -> dict:
        return {
            "peak": round(self.peak_equity, 2),
            "current": round(self.current_equity, 2),
            "current_dd_pct": round(self.current_dd_pct * 100, 3),
            "max_dd_pct": round(self.max_dd_pct * 100, 3),
        }


class PortfolioRiskManager:
    """
    Tracks portfolio-level VaR and exposure.
    Called after each position open/close.
    """

    def __init__(
        self,
        max_portfolio_var_pct: float = 0.05,   # 5% of equity = max daily VaR
        confidence: float = 0.95,
    ):
        self._max_var = max_portfolio_var_pct
        self._confidence = confidence
        self._positions: dict[str, dict] = {}   # symbol -> {exposure, vol, returns}
        self._dd = DrawdownTracker()
        self._equity = 0.0

    def update_equity(self, equity: float):
        self._equity = equity
        self._dd.update(equity)

    def register_position(self, symbol: str, exposure: float, annualized_vol: float):
        self._positions[symbol] = {
            "exposure": exposure,
            "vol": annualized_vol,
            "returns": [],
        }

    def remove_position(self, symbol: str):
        self._positions.pop(symbol, None)

    def update_return(self, symbol: str, pct_return: float):
        if symbol in self._positions:
            r = self._positions[symbol]["returns"]
            r.append(pct_return)
            if len(r) > 252:
                r.pop(0)

    def portfolio_snapshot(self) -> PortfolioRiskSnapshot:
        if not self._positions:
            return PortfolioRiskSnapshot(0.0, 0.0, 1.0, "none", {}, self._equity)

        vars_by_sym = {}
        total_exp = 0.0
        for sym, pos in self._positions.items():
            exp = pos["exposure"]
            vol = pos["vol"] if pos["vol"] > 0 else 0.15
            v = parametric_var(exp, vol, 1.0, self._confidence)
            vars_by_sym[sym] = v.var_currency
            total_exp += exp

        # Simple sum (conservative, ignores correlation benefits)
        total_var = sum(vars_by_sym.values())
        total_var_pct = total_var / self._equity if self._equity > 0 else 0.0

        # Diversification ratio (1 = no benefit, <1 = benefit)
        n = len(self._positions)
        div_ratio = 1.0 / max(1, np.sqrt(n)) if n > 1 else 1.0

        largest = max(self._positions, key=lambda s: self._positions[s]["exposure"]) if self._positions else "none"

        return PortfolioRiskSnapshot(
            total_var_pct=round(total_var_pct, 6),
            total_exposure=round(total_exp, 2),
            diversification_ratio=round(float(div_ratio), 4),
            largest_position=largest,
            var_by_symbol=vars_by_sym,
            equity=self._equity,
        )

    def is_within_var_limit(self) -> bool:
        snap = self.portfolio_snapshot()
        return snap.total_var_pct <= self._max_var

    @property
    def drawdown(self) -> DrawdownTracker:
        return self._dd
