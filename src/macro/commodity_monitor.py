from __future__ import annotations
"""
Commodity Monitor — V9

Tracks core commodities and their relationship with DXY:
  XAU/USD (Gold spot): inverse correlation with USD
  WTI Crude:           inverse correlation with USD
  Brent Crude:         inverse correlation with USD
  Iron Ore 62% (TIOC1): China yuan reference — scraped from Sina/fallback yfinance

Data sources (priority order):
  1. yfinance (GC=F, CL=F, BZ=F, TIO=F) — fast, no API key needed
  2. MT5 if available (GOLD, Brent, LCrude symbols)
  3. Sina Finance scraping for Iron Ore (China yuan)

Thread daemon — updates every 60 seconds.
"""
import logging
import threading
import time
from dataclasses import dataclass

import requests

from src.macro.macro_context import MacroContext

logger = logging.getLogger(__name__)


@dataclass
class CommodityState:
    gold: float = 0.0
    gold_prev: float = 0.0
    gold_change_pct: float = 0.0
    wti: float = 0.0
    wti_prev: float = 0.0
    wti_change_pct: float = 0.0
    brent: float = 0.0
    brent_prev: float = 0.0
    brent_change_pct: float = 0.0
    iron_ore_yuan: float = 0.0
    iron_ore_settle: float = 0.0


# yfinance tickers
_TICKERS = {
    "gold":  "GC=F",
    "wti":   "CL=F",
    "brent": "BZ=F",
    "iron":  "TIO=F",
}


def _fetch_yfinance(tickers: dict) -> dict[str, dict]:
    try:
        import yfinance as yf
        result = {}
        for key, ticker_sym in tickers.items():
            try:
                t = yf.Ticker(ticker_sym)
                info = t.info
                price = info.get("regularMarketPrice") or info.get("currentPrice") or 0.0
                prev  = info.get("previousClose") or info.get("regularMarketPreviousClose") or price
                result[key] = {"price": float(price), "prev": float(prev)}
            except Exception:
                result[key] = {"price": 0.0, "prev": 0.0}
        return result
    except Exception as e:
        logger.warning(f"yfinance commodity fetch error: {e}")
        return {}


def _fetch_iron_ore_sina() -> dict:
    """
    Scrape Iron Ore 62% Fe (I2205 or I0) from Sina Finance.
    Returns last price and settlement in Yuan (CNY).
    Falls back to yfinance TIO=F if Sina fails.
    """
    try:
        url = "https://hq.sinajs.cn/list=nf_I0"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://finance.sina.com.cn/",
        }
        r = requests.get(url, headers=headers, timeout=8, encoding="gbk")
        if r.status_code == 200 and "," in r.text:
            parts = r.text.split(",")
            if len(parts) > 13:
                last = float(parts[8])
                settle = float(parts[13])
                return {"last": last, "settle": settle, "source": "sina"}
    except Exception as e:
        logger.debug(f"Sina iron ore fetch failed: {e}")

    # Fallback: yfinance
    try:
        import yfinance as yf
        t = yf.Ticker("TIO=F")
        hist = t.history(period="2d")
        if len(hist) >= 1:
            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else last
            return {"last": last, "settle": prev, "source": "yfinance"}
    except Exception as e:
        logger.debug(f"yfinance iron ore fallback failed: {e}")

    return {"last": 0.0, "settle": 0.0, "source": "unavailable"}


class CommodityMonitor:
    """
    Background thread monitoring Gold, WTI, Brent and Iron Ore.
    Updates MacroContext on every refresh cycle.
    """

    def __init__(self, macro: MacroContext, update_interval: int = 60):
        self._macro = macro
        self._interval = update_interval
        self._state = CommodityState()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def state(self) -> CommodityState:
        with self._lock:
            return self._state

    def start(self):
        self._running = True
        self._update()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="commodity-monitor"
        )
        self._thread.start()
        logger.info("CommodityMonitor started")

    def stop(self):
        self._running = False

    def _update(self):
        data = _fetch_yfinance(_TICKERS)
        iron = _fetch_iron_ore_sina()

        def chg(price, prev):
            if prev and prev != 0:
                return round((price - prev) / prev, 6)
            return 0.0

        with self._lock:
            g = data.get("gold", {})
            w = data.get("wti", {})
            b = data.get("brent", {})

            self._state.gold = g.get("price", 0.0)
            self._state.gold_prev = g.get("prev", 0.0)
            self._state.gold_change_pct = chg(self._state.gold, self._state.gold_prev)

            self._state.wti = w.get("price", 0.0)
            self._state.wti_prev = w.get("prev", 0.0)
            self._state.wti_change_pct = chg(self._state.wti, self._state.wti_prev)

            self._state.brent = b.get("price", 0.0)
            self._state.brent_prev = b.get("prev", 0.0)
            self._state.brent_change_pct = chg(self._state.brent, self._state.brent_prev)

            self._state.iron_ore_yuan = iron.get("last", 0.0)
            self._state.iron_ore_settle = iron.get("settle", 0.0)

        # Push to macro context
        self._macro.gold_price = self._state.gold
        self._macro.gold_change_pct = self._state.gold_change_pct
        self._macro.wti_price = self._state.wti
        self._macro.wti_change_pct = self._state.wti_change_pct
        self._macro.brent_price = self._state.brent
        self._macro.brent_change_pct = self._state.brent_change_pct

        logger.debug(
            f"Commodities: GOLD={self._state.gold:.1f}({self._state.gold_change_pct*100:+.2f}%) "
            f"WTI={self._state.wti:.1f} BRENT={self._state.brent:.1f} "
            f"IRON={self._state.iron_ore_yuan:.0f}CNY src={iron.get('source')}"
        )

    def _loop(self):
        while self._running:
            time.sleep(self._interval)
            try:
                self._update()
            except Exception as e:
                logger.error(f"CommodityMonitor update error: {e}")
