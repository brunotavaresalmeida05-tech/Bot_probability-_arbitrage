from __future__ import annotations
"""
Yield Curve Analysis — V9

Full US Treasury yield curve analysis:
  - Shape detection: steep | flat | inverted
  - Carry trade signal: where is institutional money flowing?
  - ADR flow confirmation: EEM, FXI, EWZ vs SPY/QQQ

Treasury reference (yield curve complete):
  Bills:  1M, 3M, 6M
  Notes:  1Y, 2Y, 3Y, 5Y, 7Y, 10Y
  Bonds:  20Y, 30Y

Key spreads:
  10Y - 2Y: primary recession indicator (negative = inverted = risk-off)
  10Y - 3M: secondary indicator (also watched by Fed)
  5Y  - 2Y: short-term momentum
"""
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Yahoo Finance tickers for treasury yields
YIELD_TICKERS = {
    "us1m":  "^IRX",        # 13-week T-Bill (proxy for 1M)
    "us3m":  "^IRX",        # 13-week T-Bill
    "us2y":  "^TYX",        # (proxy — use FRED for precision)
    "us5y":  "^FVX",        # 5-Year T-Note yield
    "us10y": "^TNX",        # 10-Year T-Note yield
    "us30y": "^TYX",        # 30-Year T-Bond yield
}

# ADR ETFs for carry trade detection
CARRY_TICKERS = {
    "eem":  "EEM",          # iShares MSCI Emerging Markets
    "fxi":  "FXI",          # iShares China Large-Cap
    "ewz":  "EWZ",          # iShares MSCI Brazil
    "spy":  "SPY",          # S&P 500 (risk benchmark)
    "qqq":  "QQQ",          # Nasdaq 100 (tech benchmark)
    "dxy_fut": "UUP",       # DXY proxy ETF (DX=F delisted on yfinance)
    "vix_fut": "VIXY",      # VIX proxy ETF (VX=F delisted on yfinance)
    "sp500_fut": "ES=F",    # S&P 500 futures
    "us10y_fut": "ZN=F",    # T-Note 10Y futures
    "us2y_fut":  "ZT=F",    # T-Note 2Y futures
}


@dataclass
class YieldCurveSnapshot:
    us1m: float = 0.0
    us3m: float = 0.0
    us6m: float = 0.0
    us1y: float = 0.0
    us2y: float = 0.0
    us3y: float = 0.0
    us5y: float = 0.0
    us7y: float = 0.0
    us10y: float = 0.0
    us20y: float = 0.0
    us30y: float = 0.0
    # Key spreads
    spread_10y_2y: float = 0.0
    spread_10y_3m: float = 0.0
    spread_5y_2y: float = 0.0
    # Shape
    shape: str = "flat"             # steep | flat | inverted | kinked
    # Risk multiplier
    risk_mult: float = 0.75
    # Carry trade
    carry_trade_active: bool = False
    carry_direction: str = "none"   # em_inflow | em_outflow | neutral


@dataclass
class MarketPreparationData:
    """Key futures data for market preparation (6-step workflow)."""
    dxy_fut_last: float = 0.0
    dxy_fut_prior_settle: float = 0.0
    dxy_fut_open: float = 0.0
    dxy_fut_high: float = 0.0
    dxy_fut_low: float = 0.0
    vix_fut_last: float = 0.0
    vix_fut_prior_settle: float = 0.0
    sp500_fut_last: float = 0.0
    sp500_fut_prior_settle: float = 0.0
    us10y_fut_last: float = 0.0
    us10y_fut_prior_settle: float = 0.0
    us2y_fut_last: float = 0.0
    us2y_fut_prior_settle: float = 0.0
    source: str = ""


def fetch_market_prep_data() -> MarketPreparationData:
    """
    Fetch futures data for market preparation calculations.
    Returns: prior settle, last, open, high, low for key futures.
    """
    data = MarketPreparationData()
    try:
        import yfinance as yf
        mapping = {
            "DX=F":  ("dxy_fut", True),
            "VX=F":  ("vix_fut", False),
            "ES=F":  ("sp500_fut", False),
            "ZN=F":  ("us10y_fut", False),
            "ZT=F":  ("us2y_fut", False),
        }
        for ticker_sym, (key, has_ohlc) in mapping.items():
            try:
                t = yf.Ticker(ticker_sym)
                info = t.info
                last  = float(info.get("regularMarketPrice") or 0)
                prev  = float(info.get("previousClose") or info.get("regularMarketPreviousClose") or last)
                setattr(data, f"{key}_last", last)
                setattr(data, f"{key}_prior_settle", prev)
                if has_ohlc:
                    setattr(data, f"{key}_open", float(info.get("regularMarketOpen") or 0))
                    setattr(data, f"{key}_high", float(info.get("regularMarketDayHigh") or 0))
                    setattr(data, f"{key}_low",  float(info.get("regularMarketDayLow") or 0))
            except Exception as e:
                logger.debug(f"Prep data error {ticker_sym}: {e}")
        data.source = "yfinance"
    except Exception as e:
        logger.warning(f"Market prep data fetch error: {e}")
    return data


def fetch_yield_snapshot() -> YieldCurveSnapshot:
    """Fetch full yield curve from Yahoo Finance."""
    snap = YieldCurveSnapshot()
    try:
        import yfinance as yf
        # Yahoo Finance yield tickers
        yt = {
            "us3m": "^IRX", "us5y": "^FVX",
            "us10y": "^TNX", "us30y": "^TYX",
        }
        for key, sym in yt.items():
            try:
                t = yf.Ticker(sym)
                price = t.info.get("regularMarketPrice") or 0.0
                setattr(snap, key, float(price))
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Yield curve fetch error: {e}")

    snap.spread_10y_2y = round(snap.us10y - snap.us2y, 4)
    snap.spread_10y_3m = round(snap.us10y - snap.us3m, 4)
    snap.spread_5y_2y  = round(snap.us5y  - snap.us2y, 4)
    snap.shape = _classify_shape(snap)
    snap.risk_mult = {"steep": 1.0, "flat": 0.75, "inverted": 0.50, "kinked": 0.60}.get(snap.shape, 0.75)
    return snap


def detect_carry_trade() -> dict:
    """
    Detect carry trade activity by comparing EM ETFs vs DXY.
    High EM ETF inflow + weak DXY = carry trade active (risk-on).
    EM outflow + strong DXY = carry trade off (risk-off, flight to USD).
    """
    result = {"active": False, "direction": "neutral", "eem_chg": 0.0, "spy_chg": 0.0, "dxy_chg": 0.0}
    try:
        import yfinance as yf
        tickers = {"EEM": "eem", "SPY": "spy", "DX=F": "dxy"}
        chg = {}
        for sym, key in tickers.items():
            t = yf.Ticker(sym)
            info = t.info
            curr = float(info.get("regularMarketPrice") or 0)
            prev = float(info.get("previousClose") or curr)
            chg[key] = (curr - prev) / prev if prev else 0.0

        result["eem_chg"] = round(chg.get("eem", 0), 4)
        result["spy_chg"] = round(chg.get("spy", 0), 4)
        result["dxy_chg"] = round(chg.get("dxy", 0), 4)

        # Carry trade active: EM rising + DXY falling
        em_positive = chg.get("eem", 0) > 0.003
        dxy_falling = chg.get("dxy", 0) < -0.002
        if em_positive and dxy_falling:
            result["active"] = True
            result["direction"] = "em_inflow"
        elif not em_positive and not dxy_falling:
            result["direction"] = "em_outflow"
    except Exception as e:
        logger.debug(f"Carry trade detect error: {e}")
    return result


def _classify_shape(snap: YieldCurveSnapshot) -> str:
    s = snap.spread_10y_2y
    if s < -0.10:
        return "inverted"
    elif s < 0.25:
        return "flat"
    elif snap.spread_5y_2y < 0 and s >= 0:
        return "kinked"     # inverted short end but positive long end
    else:
        return "steep"
