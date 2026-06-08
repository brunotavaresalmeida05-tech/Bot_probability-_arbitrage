"""
src/macro/policy_shock.py — Central Bank Policy Shock Layer.

Maps central bank events to the symbols most affected by each bank's policy.
When the NewsGate detects a CB event, this module provides:
  - Which symbols are most sensitive to that bank
  - How much to reduce the lot multiplier for each
  - Whether to block entries entirely in the most sensitive pairs

Central Banks monitored (via NewsGate's calendar):
  Fed (US), ECB (EU), BoJ (JP), BoE (GB), BoC (CA), RBA (AU), RBNZ (NZ),
  SNB (CH), Riksbank (SE), PBoC (CN)

Usage:
    shock = PolicyShockLayer()
    mults = shock.get_symbol_mults("ECB Rate Decision", "EUR")
    # → {"EURUSD": 0.0, "GER40": 0.3, "EURJPY": 0.0, ...}
"""
from __future__ import annotations

from dataclasses import dataclass

# ── Central Bank → Sensitive Symbols ──────────────────────────────────────────
# Each CB has a dict of symbol → multiplier during its event.
# 0.0 = full block; 0.3 = heavy reduction; 0.7 = mild reduction; 1.0 = unaffected

_CB_MAP: dict[str, dict[str, float]] = {

    "fed": {   # Federal Reserve → affects everything USD
        "EURUSD":  0.0,  "GBPUSD":  0.0,  "USDJPY":  0.0,
        "AUDUSD":  0.0,  "NZDUSD":  0.0,  "USDCAD":  0.0,
        "USDCHF":  0.0,  "USDNOK":  0.0,  "USDMXN":  0.0,
        "EURJPY":  0.3,
        "Usa500":  0.0,  "UsaTec":  0.0,  "USA500Jun26": 0.0,
        "GOLD":    0.0,  "BTCUSD":  0.0,  "SILVER":  0.0,
        "LCrude":  0.3,  "Brent":   0.3,
    },

    "ecb": {   # European Central Bank → EUR pairs + EUR indices
        "EURUSD":  0.0,  "GBPUSD":  0.5,  "EURJPY":  0.0,
        "Ger40":   0.0,  "Ger40Jun26": 0.0,
        "UK100":   0.5,
        "USDJPY":  0.7,  "AUDUSD":  0.7,
    },

    "boj": {   # Bank of Japan → JPY pairs + carry trades
        "USDJPY":  0.0,  "EURJPY":  0.0,
        "AUDUSD":  0.5,  "Jp225":   0.0,  "Jp225Jun26": 0.0,
        "GBPUSD":  0.7,
    },

    "boe": {   # Bank of England → GBP pairs + FTSE
        "GBPUSD":  0.0,  "EURJPY":  0.5,
        "UK100":   0.0,  "UK100Jun26": 0.0,
        "EURUSD":  0.5,
    },

    "boc": {   # Bank of Canada → CAD pairs + oil-correlated
        "USDCAD":  0.0,
        "LCrude":  0.5,  "Brent":   0.5,
        "AUDUSD":  0.7,
    },

    "rba": {   # Reserve Bank of Australia
        "AUDUSD":  0.0,  "NZDUSD":  0.5,
        "GOLD":    0.5,
    },

    "rbnz": {  # Reserve Bank of New Zealand
        "NZDUSD":  0.0,  "AUDUSD":  0.5,
    },

    "snb": {   # Swiss National Bank
        "USDCHF":  0.0,  "EURUSD":  0.5,
        "GOLD":    0.3,
    },

    "pboc": {  # People's Bank of China (indirect — data/rate surprises)
        "AUDUSD":  0.3,  "NZDUSD":  0.3,
        "GOLD":    0.5,  "LCrude":  0.5,
        "Usa500":  0.5,
    },
}

# ── Event name → CB key ────────────────────────────────────────────────────────
# Maps Finnhub event name fragments to the CB identifier
_EVENT_KEYWORDS: dict[str, str] = {
    "fed rate":       "fed", "fomc":           "fed", "federal reserve": "fed",
    "ecb rate":       "ecb", "european central": "ecb", "lagarde":      "ecb",
    "boj rate":       "boj", "bank of japan":  "boj",  "ueda":         "boj",
    "boe rate":       "boe", "bank of england":"boe",  "bailey":       "boe",
    "boc rate":       "boc", "bank of canada": "boc",
    "rba rate":       "rba", "reserve bank of australia": "rba",
    "rbnz rate":      "rbnz","reserve bank of new zealand":"rbnz",
    "snb rate":       "snb", "swiss national": "snb",
    "pboc":           "pboc","peoples bank of china": "pboc",
}


@dataclass
class PolicyShockResult:
    cb:           str              # central bank key
    event_name:   str
    symbol_mults: dict[str, float]  # {symbol → multiplier}
    is_active:    bool

    def get_mult(self, symbol: str) -> float:
        return self.symbol_mults.get(symbol, 1.0)


class PolicyShockLayer:
    """
    Stateless mapper.
    identify_cb(event_name) → CB key
    get_symbol_mults(event_name) → PolicyShockResult
    """

    def identify_cb(self, event_name: str) -> str | None:
        name_lower = event_name.lower()
        for keyword, cb in _EVENT_KEYWORDS.items():
            if keyword in name_lower:
                return cb
        return None

    def get_symbol_mults(self, event_name: str, is_active: bool = True) -> PolicyShockResult:
        cb = self.identify_cb(event_name)
        if not cb or not is_active:
            return PolicyShockResult(
                cb="none", event_name=event_name,
                symbol_mults={}, is_active=False,
            )
        mults = dict(_CB_MAP.get(cb, {}))
        return PolicyShockResult(
            cb=cb, event_name=event_name,
            symbol_mults=mults, is_active=True,
        )

    def combined_mult(self, symbol: str, event_name: str, is_active: bool) -> float:
        """Returns the most restrictive multiplier for this symbol given a CB event."""
        result = self.get_symbol_mults(event_name, is_active)
        return result.get_mult(symbol)


# ── Convenience: known CB → most sensitive symbols (for logging/UI) ─────────────

CB_PRIMARY_SYMBOLS: dict[str, list[str]] = {
    "fed":  ["EURUSD","GBPUSD","USDJPY","GOLD","Usa500","BTCUSD"],
    "ecb":  ["EURUSD","EURJPY","Ger40"],
    "boj":  ["USDJPY","EURJPY","Jp225"],
    "boe":  ["GBPUSD","UK100"],
    "boc":  ["USDCAD","LCrude"],
    "rba":  ["AUDUSD"],
    "rbnz": ["NZDUSD"],
    "snb":  ["USDCHF"],
    "pboc": ["AUDUSD","GOLD"],
}
