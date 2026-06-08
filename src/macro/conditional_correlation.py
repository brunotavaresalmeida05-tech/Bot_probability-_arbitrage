"""
src/macro/conditional_correlation.py — Regime-Conditional Correlation Map.

Correlations between assets are NOT static — they change with macro regime.
This module defines the expected direction of each symbol in each regime.

Used by MacroCorrelationPolicyEngine to determine if a signal is:
  ALIGNED    → signal direction matches expected regime direction → allow / confirm
  NEUTRAL    → no strong directional expectation in this regime → proceed normally
  CONTRARY   → signal direction opposes expected regime direction → reduce or block

Regime definitions:
  risk_on    — equities/crypto/cyclicals rise; USD/JPY/CHF weaken
  risk_off   — USD/JPY/CHF rise; equities/crypto/commodities fall; correlations converge
  inflation  — oil/yields lead up; growth/duration/crypto fall; USD firm
  deflation  — yields fall; bonds up; equities and commodities fall; JPY/CHF/USD mixed
  crisis     — correlations converge (everything down except USD/JPY/GOLD)
  neutral    — no dominant direction
"""
from __future__ import annotations

# ── Regime-Conditional Signal Bias ───────────────────────────────────────────
# Format: {regime: {symbol: expected_signal}}
# "BUY"  = asset expected to go UP in this regime
# "SELL" = asset expected to go DOWN in this regime
# None   = no directional bias in this regime

_REGIME_BIAS: dict[str, dict[str, str | None]] = {

    "risk_on": {
        # FX: USD weakens, risk currencies strengthen
        "EURUSD": "BUY",   "GBPUSD": "BUY",   "AUDUSD": "BUY",
        "NZDUSD": "BUY",   "USDCAD": "SELL",  "USDCHF": "SELL",
        "USDJPY": None,    "EURJPY": "BUY",   "USDNOK": "SELL",
        "USDMXN": "SELL",
        # Indices: risk assets up
        "Usa500": "BUY",   "UsaTec": "BUY",   "USA500Jun26": "BUY",
        "US100Jun26": "BUY","Ger40":  "BUY",   "Ger40Jun26": "BUY",
        "UK100":  "BUY",   "UK100Jun26": "BUY","Jp225": "BUY",
        "Jp225Jun26": "BUY",
        # Commodities: demand-driven
        "GOLD":   None,    "SILVER": "BUY",   "LCrude": "BUY",
        "Brent":  "BUY",   "NGas":   None,    "Coffee": "BUY",
        # Crypto: high beta risk asset
        "BTCUSD": "BUY",   "ETHUSD": "BUY",
    },

    "risk_off": {
        # FX: safe havens (USD/JPY/CHF) strengthen
        "EURUSD": "SELL",  "GBPUSD": "SELL",  "AUDUSD": "SELL",
        "NZDUSD": "SELL",  "USDCAD": None,    "USDCHF": "BUY",
        "USDJPY": "SELL",  "EURJPY": "SELL",  "USDNOK": "BUY",
        "USDMXN": "BUY",
        # Indices: fall
        "Usa500": "SELL",  "UsaTec": "SELL",  "USA500Jun26": "SELL",
        "US100Jun26": "SELL","Ger40": "SELL",  "Ger40Jun26": "SELL",
        "UK100":  "SELL",  "UK100Jun26": "SELL","Jp225": "SELL",
        "Jp225Jun26": "SELL",
        # Commodities: demand destruction except gold
        "GOLD":   "BUY",   "SILVER": None,    "LCrude": "SELL",
        "Brent":  "SELL",  "NGas":   None,
        # Crypto: falls with risk assets
        "BTCUSD": "SELL",  "ETHUSD": "SELL",
    },

    "inflation": {
        # FX: USD firms; oil exporters (CAD/NOK) benefit
        "EURUSD": "SELL",  "GBPUSD": "SELL",  "AUDUSD": None,
        "NZDUSD": None,    "USDCAD": "SELL",  "USDCHF": None,
        "USDJPY": "BUY",   "USDNOK": "SELL",  "USDMXN": None,
        # Indices: growth/duration heavy sectors pressured
        "Usa500": "SELL",  "UsaTec": "SELL",  "USA500Jun26": "SELL",
        "US100Jun26": "SELL","Ger40": "SELL",  "Ger40Jun26": "SELL",
        "UK100":  None,
        # Commodities: energy/metals benefit from inflation
        "GOLD":   "BUY",   "SILVER": "BUY",   "LCrude": "BUY",
        "Brent":  "BUY",   "NGas":   "BUY",   "Coffee": "BUY",
        # Crypto: pressured by rate expectations
        "BTCUSD": "SELL",  "ETHUSD": "SELL",
    },

    "deflation": {
        # FX: USD / JPY / CHF tend to benefit
        "EURUSD": None,    "GBPUSD": None,    "AUDUSD": "SELL",
        "NZDUSD": "SELL",  "USDCAD": "BUY",   "USDCHF": None,
        "USDJPY": "SELL",  "USDNOK": "BUY",
        # Indices: mixed; bonds up
        "Usa500": "SELL",  "UsaTec": None,
        "Ger40":  "SELL",  "UK100":  "SELL",
        # Commodities: fall on demand concerns
        "GOLD":   "BUY",   "SILVER": None,    "LCrude": "SELL",
        "Brent":  "SELL",
        # Crypto: no strong bias
        "BTCUSD": None,    "ETHUSD": None,
    },

    "crisis": {
        # All correlations converge — almost everything falls
        # Only true safe havens and defensive shorts make sense
        "EURUSD": "SELL",  "GBPUSD": "SELL",  "AUDUSD": "SELL",
        "NZDUSD": "SELL",  "USDCAD": None,    "USDCHF": "BUY",
        "USDJPY": "SELL",  "EURJPY": "SELL",
        "Usa500": "SELL",  "UsaTec": "SELL",
        "Ger40":  "SELL",  "UK100":  "SELL",  "Jp225":  "SELL",
        "GOLD":   "BUY",   "SILVER": None,    "LCrude": "SELL",
        "Brent":  "SELL",
        "BTCUSD": "SELL",  "ETHUSD": "SELL",
    },

    "neutral": {},  # No directional bias — all signals proceed normally
}


def regime_bias(regime: str, symbol: str) -> str | None:
    """Returns expected signal direction for this symbol in this regime, or None."""
    return _REGIME_BIAS.get(regime, {}).get(symbol)


def alignment(regime: str, symbol: str, signal: str) -> str:
    """
    Returns:
      "aligned"   — signal matches regime expectation
      "contrary"  — signal opposes regime expectation
      "neutral"   — no expectation in this regime for this symbol
    """
    bias = regime_bias(regime, symbol)
    if bias is None or signal not in ("BUY", "SELL"):
        return "neutral"
    if signal == bias:
        return "aligned"
    return "contrary"


# ── Central Bank → Regime Interaction Matrix ─────────────────────────────────
# For each (CB, regime), gives extra multiplier applied on top of base mult
# 1.0 = no change; < 1.0 = additional reduction

_CB_REGIME_INTERACTION: dict[str, dict[str, float]] = {
    "fed": {
        "inflation": 0.50,   # Fed tightening + inflation = double headwind for risk
        "risk_off":  0.40,   # Fed in crisis mode = aggressive cut in size
        "risk_on":   1.00,
        "neutral":   0.85,
    },
    "ecb": {
        "inflation": 0.60,
        "risk_off":  0.50,
        "risk_on":   1.00,
        "neutral":   0.90,
    },
    "boj": {
        "inflation": 0.55,   # BoJ hawkish + inflation = carry trade unwind risk
        "risk_off":  0.45,
        "risk_on":   0.90,
        "neutral":   0.85,
    },
    "boe": {
        "inflation": 0.65,
        "risk_off":  0.55,
        "risk_on":   1.00,
        "neutral":   0.90,
    },
}

_DEFAULT_CB_REGIME = {"inflation": 0.70, "risk_off": 0.60, "risk_on": 1.0, "neutral": 0.90}


def cb_regime_mult(cb: str, regime: str) -> float:
    """Extra multiplier when a CB event is active in a specific macro regime."""
    table = _CB_REGIME_INTERACTION.get(cb, _DEFAULT_CB_REGIME)
    return table.get(regime, 0.85)
