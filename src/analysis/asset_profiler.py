from __future__ import annotations
"""
Asset Profiler — V9

Classifies each symbol into its asset class and defines:
  - Primary macro drivers (weighted)
  - DXY beta (sensitivity to dollar)
  - Benchmark reference asset
  - Weight table index (forex/indices/gold/oil/treasuries/crypto)

This is the "DNA" of each instrument — what makes it move.
The TotalScore engine uses this to apply the right weights per symbol.
"""
from dataclasses import dataclass, field
from enum import Enum


class AssetClass(str, Enum):
    FOREX      = "forex"
    INDICES    = "indices"
    GOLD       = "gold"
    OIL        = "oil"
    TREASURIES = "treasuries"
    CRYPTO     = "crypto"
    UNKNOWN    = "unknown"


@dataclass
class AssetProfile:
    symbol: str
    asset_class: AssetClass
    dxy_beta: float             # sensitivity to DXY (negative = inverse)
    benchmark: str              # primary reference asset
    macro_drivers: list[str]    # ordered list of macro drivers
    session_focus: list[str]    # sessions where this asset is most liquid
    mean_reversion_tendency: float  # 0=pure trend, 1=pure mean revert
    typical_atr_pct: float      # typical ATR as % of price (for context)


# ── Asset registry ─────────────────────────────────────────────────────────

_PROFILES: dict[str, AssetProfile] = {
    # ── Forex ─────────────────────────────────────────────────────────
    "EURUSD": AssetProfile("EURUSD", AssetClass.FOREX, -0.92, "DXY",
        ["DXY", "ECB_rate", "Fed_rate", "inflation_diff", "yield_spread_10y"],
        ["london", "new_york"], 0.6, 0.0060),
    "GBPUSD": AssetProfile("GBPUSD", AssetClass.FOREX, -0.80, "DXY",
        ["DXY", "BOE_rate", "Fed_rate", "UK_macro", "risk_sentiment"],
        ["london", "new_york"], 0.55, 0.0080),
    "USDJPY": AssetProfile("USDJPY", AssetClass.FOREX, 0.75, "US10Y",
        ["BOJ_rate", "Fed_rate", "yield_diff_10y", "risk_off_flow", "DXY"],
        ["asia", "london", "new_york"], 0.5, 0.0060),
    "AUDUSD": AssetProfile("AUDUSD", AssetClass.FOREX, -0.65, "IRON_ORE",
        ["China_growth", "commodities", "DXY", "RBA_rate", "risk_sentiment"],
        ["asia", "london"], 0.55, 0.0070),
    "USDCAD": AssetProfile("USDCAD", AssetClass.FOREX, 0.60, "WTI",
        ["WTI_oil", "BOC_rate", "Fed_rate", "DXY", "trade_balance"],
        ["london", "new_york"], 0.5, 0.0060),
    "USDCHF": AssetProfile("USDCHF", AssetClass.FOREX, 0.55, "DXY",
        ["SNB_rate", "risk_off_flow", "DXY", "EURUSD_proxy", "stress"],
        ["london", "new_york"], 0.6, 0.0060),

    # ── Indices ────────────────────────────────────────────────────────
    "Usa500": AssetProfile("Usa500", AssetClass.INDICES, 0.35, "SP500_FUT",
        ["SP500_futures", "US10Y_yield", "VIX", "Fed_policy", "earnings"],
        ["new_york"], 0.35, 0.0100),
    "UsaTec": AssetProfile("UsaTec", AssetClass.INDICES, 0.30, "QQQ",
        ["Nasdaq_futures", "US10Y_yield", "VIX", "tech_earnings", "Fed_policy"],
        ["new_york"], 0.30, 0.0130),
    "Ger40": AssetProfile("Ger40", AssetClass.INDICES, -0.30, "EURUSD",
        ["EURUSD", "ECB_policy", "Germany_macro", "risk_sentiment", "energy"],
        ["london"], 0.35, 0.0090),
    "US500":  AssetProfile("US500",  AssetClass.INDICES, 0.35, "SP500_FUT",
        ["SP500_futures", "US10Y_yield", "VIX", "Fed_policy"],
        ["new_york"], 0.35, 0.0100),
    "NAS100": AssetProfile("NAS100", AssetClass.INDICES, 0.30, "QQQ",
        ["Nasdaq_futures", "US10Y_yield", "VIX", "tech_earnings"],
        ["new_york"], 0.30, 0.0130),

    # ── Gold ────────────────────────────────────────────────────────────
    "GOLD":   AssetProfile("GOLD",   AssetClass.GOLD, -0.78, "DXY",
        ["DXY", "real_yields_10y", "inflation_breakeven", "risk_off", "geopolitics"],
        ["asia", "london", "new_york"], 0.45, 0.0080),
    "XAUUSD": AssetProfile("XAUUSD", AssetClass.GOLD, -0.78, "DXY",
        ["DXY", "real_yields_10y", "inflation_breakeven", "risk_off", "geopolitics"],
        ["asia", "london", "new_york"], 0.45, 0.0080),
    "XAUEUR": AssetProfile("XAUEUR", AssetClass.GOLD, -0.50, "EURUSD",
        ["EURUSD", "ECB_policy", "real_yields_EU", "DXY", "risk_off"],
        ["london"], 0.45, 0.0090),

    # ── Oil ──────────────────────────────────────────────────────────────
    "Brent":  AssetProfile("Brent",  AssetClass.OIL, -0.55, "WTI",
        ["supply_opec", "geopolitics", "DXY", "global_demand", "inventories"],
        ["london", "new_york"], 0.30, 0.0150),
    "LCrude": AssetProfile("LCrude", AssetClass.OIL, -0.55, "WTI",
        ["supply_opec", "geopolitics", "DXY", "global_demand", "inventories"],
        ["london", "new_york"], 0.30, 0.0150),
    "WTI":    AssetProfile("WTI",    AssetClass.OIL, -0.57, "WTI",
        ["EIA_inventories", "OPEC", "DXY", "US_production", "geopolitics"],
        ["new_york"], 0.30, 0.0150),

    # ── Treasuries ───────────────────────────────────────────────────────
    "TY":  AssetProfile("TY",  AssetClass.TREASURIES, 0.30, "US10Y_YIELD",
        ["Fed_policy", "inflation", "risk_off_flow", "supply_auction", "growth"],
        ["new_york"], 0.55, 0.0030),
    "TU":  AssetProfile("TU",  AssetClass.TREASURIES, 0.20, "US2Y_YIELD",
        ["Fed_expectations", "inflation", "risk_off_flow", "FFR"],
        ["new_york"], 0.55, 0.0015),
    "FV":  AssetProfile("FV",  AssetClass.TREASURIES, 0.25, "US5Y_YIELD",
        ["Fed_expectations", "inflation", "real_yields", "supply"],
        ["new_york"], 0.55, 0.0020),
}

# Default profiles by class for unmapped symbols
_CLASS_DEFAULTS: dict[AssetClass, AssetProfile] = {
    AssetClass.FOREX:      AssetProfile("_default_fx", AssetClass.FOREX, -0.50, "DXY",
        ["DXY", "rate_diff"], ["london", "new_york"], 0.55, 0.0070),
    AssetClass.INDICES:    AssetProfile("_default_idx", AssetClass.INDICES, 0.30, "SP500_FUT",
        ["SP500_futures", "VIX", "US10Y_yield"], ["new_york"], 0.35, 0.0100),
    AssetClass.GOLD:       AssetProfile("_default_gold", AssetClass.GOLD, -0.78, "DXY",
        ["DXY", "real_yields_10y"], ["london", "new_york"], 0.45, 0.0080),
    AssetClass.OIL:        AssetProfile("_default_oil", AssetClass.OIL, -0.55, "WTI",
        ["supply_opec", "DXY"], ["london", "new_york"], 0.30, 0.0150),
    AssetClass.TREASURIES: AssetProfile("_default_tsy", AssetClass.TREASURIES, 0.25, "US10Y_YIELD",
        ["Fed_policy", "inflation"], ["new_york"], 0.55, 0.0020),
    AssetClass.CRYPTO:     AssetProfile("_default_crypto", AssetClass.CRYPTO, -0.40, "BTC",
        ["DXY", "US10Y_yield", "Nasdaq", "VIX", "risk_sentiment"], ["new_york"], 0.25, 0.0300),
    AssetClass.UNKNOWN:    AssetProfile("_unknown", AssetClass.UNKNOWN, 0.0, "DXY",
        ["macro"], [], 0.5, 0.0100),
}


def _infer_class(symbol: str) -> AssetClass:
    s = symbol.upper()
    if any(k in s for k in ["BTC", "ETH", "XRP", "SOL", "CRYPTO"]):
        return AssetClass.CRYPTO
    if any(k in s for k in ["XAU", "GOLD", "GLTR", "SGOL", "PPLT"]):
        return AssetClass.GOLD
    if any(k in s for k in ["BRENT", "WTI", "OIL", "CRUDE", "LCRUDE"]):
        return AssetClass.OIL
    if any(k in s for k in ["500", "TEC", "GER", "DAX", "NAS", "DJIA", "DOW", "S&P"]):
        return AssetClass.INDICES
    if any(k in s for k in ["TY", "TU", "FV", "ZN", "ZT", "ZF", "TREASURY", "BOND"]):
        return AssetClass.TREASURIES
    # Default: forex if contains 6 chars and no digits
    if len(s) in (6, 7) and any(c.isalpha() for c in s):
        return AssetClass.FOREX
    return AssetClass.UNKNOWN


def get_profile(symbol: str) -> AssetProfile:
    """Get asset profile for a symbol. Falls back to class default if not registered."""
    if symbol in _PROFILES:
        return _PROFILES[symbol]
    asset_class = _infer_class(symbol)
    default = _CLASS_DEFAULTS.get(asset_class, _CLASS_DEFAULTS[AssetClass.UNKNOWN])
    return AssetProfile(
        symbol=symbol,
        asset_class=asset_class,
        dxy_beta=default.dxy_beta,
        benchmark=default.benchmark,
        macro_drivers=default.macro_drivers,
        session_focus=default.session_focus,
        mean_reversion_tendency=default.mean_reversion_tendency,
        typical_atr_pct=default.typical_atr_pct,
    )


def classify(symbol: str) -> AssetClass:
    return get_profile(symbol).asset_class
