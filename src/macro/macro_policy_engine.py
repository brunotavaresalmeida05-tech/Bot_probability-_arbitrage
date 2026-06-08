"""
src/macro/macro_policy_engine.py — Macro Correlation Policy Engine.

Final decision layer combining all macro layers:
  1. Macro regime               (risk_on/off/inflation/deflation/crisis/neutral)
  2. Regime × symbol mult       (sensitivity matrix)
  3. Directional alignment      (signal vs conditional correlation)
  4. CB event × regime          (policy shock × regime interaction)
  5. Interest rate transmission (yield level, real yields, prolonged mode)
  6. Asset macro profile        (per-symbol risk_mode cap)

Priority order (most restrictive wins):
  Crisis regime  → REDUCE_HEAVY (0.25 cap)
  CB blackout    → BLOCK (0.0)
  Contrary align → REDUCE_HEAVY (0.35 × mult)
  Rate env       → additional penalty for high-sensitivity symbols
  Risk_mode cap  → hard cap by symbol sensitivity class

Output:
  MacroPolicyDecision(action, mult, alignment, rate_env, reason)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.macro.conditional_correlation import alignment, cb_regime_mult
from src.macro.policy_shock import PolicyShockLayer
from src.macro.interest_rate_transmission import (
    InterestRateTransmissionEngine, RateEnvironment
)
from src.macro.asset_macro_profile import AssetMacroProfile

logger = logging.getLogger(__name__)

_CONTRARY_MULT  = 0.35
_ALIGNED_MULT   = 1.00
_NEUTRAL_MULT   = 0.85

BLOCK        = "BLOCK"
REDUCE_HEAVY = "REDUCE_HEAVY"
REDUCE_LIGHT = "REDUCE_LIGHT"
NORMAL       = "NORMAL"
CONFIRM      = "CONFIRM"


@dataclass
class MacroPolicyDecision:
    symbol:    str
    direction: str
    regime:    str
    action:    str
    mult:      float
    reason:    str
    alignment: str
    cb_active: str
    cb_key:    str
    rate_env:  Optional[str]  = None
    risk_mode: str            = "medium"
    layers:    dict           = field(default_factory=dict)

    def log_line(self) -> str:
        return (
            f"[MacroPolicy] {self.symbol} {self.direction}  "
            f"regime={self.regime}  align={self.alignment}  "
            f"action={self.action}  mult={self.mult:.3f}  "
            f"risk_mode={self.risk_mode}  "
            f"{'CB=' + self.cb_active + ' ' if self.cb_active else ''}"
            f"reason: {self.reason}"
        )


class MacroCorrelationPolicyEngine:
    """
    Single entry point for the full macro-correlation decision.

    Accepts optional yield/rate data for interest rate transmission layer.
    When yield data is not provided, that layer is skipped.

    Usage in AlphaEngine:
        decision = self._macro_policy.evaluate(
            symbol        = symbol,
            direction     = sig.direction,
            regime        = macro.regime,
            symbol_mult   = macro.symbol_mult(symbol),
            news_event    = macro.news_event,
            news_blocked  = macro.news_blocked,
            yield_state   = yield_monitor.state,
            dxy_zscore    = dxy_basket.state.zscore,
            inflation_score = macro.inflation_score,
        )
    """

    def __init__(self):
        self._policy_shock = PolicyShockLayer()
        self._rate_engine  = InterestRateTransmissionEngine()
        self._asset_profile = AssetMacroProfile()
        self._prev_us10y: float = 0.0   # for momentum detection

    def evaluate(
        self,
        symbol:          str,
        direction:       str,
        regime:          str,
        symbol_mult:     float,
        news_event:      str   = "",
        news_blocked:    bool  = False,
        us10y:           float = 4.5,
        us2y:            float = 4.0,
        dxy_zscore:      float = 0.0,
        inflation_score: float = 0.3,
    ) -> MacroPolicyDecision:

        risk_mode  = self._asset_profile.risk_mode(symbol)
        mode_cap   = self._asset_profile.risk_mode_cap(symbol)
        layers: dict = {}

        # ── 1. Crisis: hard cap ─────────────────────────────────────────────
        if regime == "crisis":
            return MacroPolicyDecision(
                symbol=symbol, direction=direction, regime=regime,
                action=REDUCE_HEAVY, mult=0.25,
                reason="regime=crisis: size cap 0.25",
                alignment="neutral", cb_active="", cb_key="",
                risk_mode=risk_mode, rate_env=None,
            )

        # ── 2. CB policy shock ──────────────────────────────────────────────
        cb_key  = self._policy_shock.identify_cb(news_event) or ""
        cb_mult = self._policy_shock.combined_mult(symbol, news_event, news_blocked)
        layers["cb_mult"] = cb_mult

        if news_blocked and cb_mult == 0.0:
            return MacroPolicyDecision(
                symbol=symbol, direction=direction, regime=regime,
                action=BLOCK, mult=0.0,
                reason=f"CB blackout: {news_event}",
                alignment="neutral", cb_active=news_event, cb_key=cb_key,
                risk_mode=risk_mode, rate_env=None,
            )

        # ── 3. Interest rate transmission ───────────────────────────────────
        rate_env = self._rate_engine.classify(
            us10y=us10y, us2y=us2y,
            dxy_zscore=dxy_zscore,
            inflation_score=inflation_score,
            prev_us10y=self._prev_us10y,
        )
        self._prev_us10y = us10y
        rate_mult = self._rate_engine.symbol_mult(symbol, rate_env)
        layers["rate_mult"] = rate_mult
        layers["rate_env"]  = rate_env.direction

        # ── 4. CB × Regime extra mult ───────────────────────────────────────
        cb_regime = cb_regime_mult(cb_key, regime) if cb_key else 1.0
        layers["cb_regime_mult"] = cb_regime

        # ── 5. Directional alignment check ─────────────────────────────────
        align = alignment(regime, symbol, direction)
        if align == "contrary":
            dir_mult = _CONTRARY_MULT
            action   = REDUCE_HEAVY
            reason   = f"signal {direction} CONTRARY to {regime} regime"
        elif align == "aligned":
            dir_mult = _ALIGNED_MULT
            action   = CONFIRM
            reason   = f"signal {direction} ALIGNED with {regime} regime"
        else:
            dir_mult = _NEUTRAL_MULT
            action   = NORMAL
            reason   = f"signal {direction} NEUTRAL in {regime} regime"
        layers["dir_mult"] = dir_mult

        # ── 6. Combine + apply risk_mode cap ───────────────────────────────
        raw = symbol_mult * dir_mult * cb_mult * cb_regime * rate_mult
        capped = min(raw, mode_cap)           # per-symbol risk_mode ceiling
        final  = round(max(0.0, min(capped, 1.0)), 3)
        layers["symbol_mult"] = symbol_mult
        layers["mode_cap"]    = mode_cap
        layers["final"]       = final

        # Override action from final value
        if final == 0.0:
            action = BLOCK
            reason = f"combined mult=0 ({reason} + CB={cb_key})"
        elif final < 0.30:
            action = REDUCE_HEAVY
        elif final < 0.65:
            action = REDUCE_LIGHT

        # Log rate transmission warning for high-sensitivity symbols
        if rate_mult < 0.70 and risk_mode in ("high", "medium_high"):
            reason += f" [rate_headwind={rate_env.direction} real_up={rate_env.real_yield_up}]"

        return MacroPolicyDecision(
            symbol=symbol, direction=direction, regime=regime,
            action=action, mult=final,
            reason=reason, alignment=align,
            cb_active=news_event if news_blocked else "",
            cb_key=cb_key,
            rate_env=rate_env.direction,
            risk_mode=risk_mode,
            layers=layers,
        )
