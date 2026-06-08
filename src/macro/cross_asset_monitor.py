"""
src/macro/cross_asset_monitor.py — Cross-Asset Price Monitor.

Daemon that reads proxy instruments from Finnhub to track:
  GOLD, WTI/Brent, S&P500, Nasdaq, BTC

These prices are used by the MacroCorrelationEngine to classify
the global macro regime without depending on MT5 data being available.

If a price cannot be fetched, the last known value is kept.
The monitor also maintains rolling z-scores (20-period, ~10h at 30min updates).
"""
from __future__ import annotations

import logging
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

_UPDATE_INTERVAL = 1800   # 30 min
_ZSCORE_WINDOW   = 20     # periods for rolling z-score

# Finnhub symbols for each proxy
_SYMBOLS: dict[str, str] = {
    "gold":   "OANDA:XAU_USD",
    "oil":    "OANDA:BCOUSD",      # Brent
    "sp500":  "INDEX:SPX",
    "nasdaq": "INDEX:NDX",
    "btc":    "BINANCE:BTCUSDT",
}

# Safe fallback prices
_DEFAULTS: dict[str, float] = {
    "gold":   2350.0,
    "oil":    82.0,
    "sp500":  5200.0,
    "nasdaq": 18000.0,
    "btc":    68000.0,
}


@dataclass
class AssetSnapshot:
    name:    str
    price:   float
    zscore:  float = 0.0
    mom_1d:  float = 0.0   # 1-period momentum (%)
    regime:  str   = "neutral"  # "up_strong" | "up" | "neutral" | "down" | "down_strong"


@dataclass
class CrossAssetState:
    gold:    AssetSnapshot = field(default_factory=lambda: AssetSnapshot("gold",   _DEFAULTS["gold"]))
    oil:     AssetSnapshot = field(default_factory=lambda: AssetSnapshot("oil",    _DEFAULTS["oil"]))
    sp500:   AssetSnapshot = field(default_factory=lambda: AssetSnapshot("sp500",  _DEFAULTS["sp500"]))
    nasdaq:  AssetSnapshot = field(default_factory=lambda: AssetSnapshot("nasdaq", _DEFAULTS["nasdaq"]))
    btc:     AssetSnapshot = field(default_factory=lambda: AssetSnapshot("btc",    _DEFAULTS["btc"]))
    updated_at: str = ""

    def as_dict(self) -> dict:
        return {
            k: {"price": getattr(self, k).price,
                "zscore": getattr(self, k).zscore,
                "mom_1d": getattr(self, k).mom_1d,
                "regime": getattr(self, k).regime}
            for k in ("gold", "oil", "sp500", "nasdaq", "btc")
        }


def _classify_zscore(z: float) -> str:
    if   z >  1.5: return "up_strong"
    elif z >  0.5: return "up"
    elif z < -1.5: return "down_strong"
    elif z < -0.5: return "down"
    return "neutral"


class CrossAssetMonitor:
    """
    Background thread that keeps cross-asset prices and z-scores fresh.
    Thread-safe: all reads via .state property.

    If finnhub_key is empty, uses static defaults (offline / paper mode).
    The main engine can also inject prices directly via inject_prices()
    when MT5 data is available.
    """

    def __init__(self, finnhub_key: str = "", update_interval: int = _UPDATE_INTERVAL):
        self._key      = finnhub_key
        self._interval = update_interval
        self._lock     = threading.Lock()
        self._state    = CrossAssetState()
        self._history: dict[str, deque] = {k: deque(maxlen=_ZSCORE_WINDOW) for k in _SYMBOLS}
        self._running  = False
        self._thread: threading.Thread | None = None

        for k, v in _DEFAULTS.items():
            self._history[k].append(v)

    @property
    def state(self) -> CrossAssetState:
        with self._lock:
            return self._state

    def inject_prices(self, gold: float = 0, oil: float = 0,
                      sp500: float = 0, nasdaq: float = 0, btc: float = 0) -> None:
        """
        Inject prices from MT5 market state (called by AlphaEngine each cycle).
        Overrides Finnhub data when live MT5 prices are available.
        """
        updates = {"gold": gold, "oil": oil, "sp500": sp500, "nasdaq": nasdaq, "btc": btc}
        with self._lock:
            for key, price in updates.items():
                if price > 0:
                    self._history[key].append(price)
                    snap = self._build_snapshot(key, price)
                    setattr(self._state, key, snap)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True, name="CrossAssetMonitor")
        self._thread.start()
        logger.info("CrossAssetMonitor started.")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _worker(self) -> None:
        while self._running:
            for key, finnhub_sym in _SYMBOLS.items():
                price = self._fetch(finnhub_sym)
                if price and price > 0:
                    with self._lock:
                        self._history[key].append(price)
                        snap = self._build_snapshot(key, price)
                        setattr(self._state, key, snap)
            time.sleep(self._interval)

    def _fetch(self, symbol: str) -> float | None:
        if not self._key:
            return None
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": symbol, "token": self._key},
                timeout=4,
            )
            if r.status_code == 200:
                val = r.json().get("c", 0)
                if val and float(val) > 0:
                    return float(val)
        except Exception as e:
            logger.debug(f"CrossAsset fetch {symbol}: {e}")
        return None

    def _build_snapshot(self, key: str, price: float) -> AssetSnapshot:
        hist = list(self._history[key])
        if len(hist) >= 2:
            mean = statistics.mean(hist)
            std  = statistics.stdev(hist) if len(hist) > 1 else 1.0
            z    = (price - mean) / std if std > 0 else 0.0
            prev = hist[-2] if len(hist) >= 2 else price
            mom  = (price - prev) / prev * 100 if prev > 0 else 0.0
        else:
            z   = 0.0
            mom = 0.0
        return AssetSnapshot(
            name   = key,
            price  = round(price, 4),
            zscore = round(z,   4),
            mom_1d = round(mom, 4),
            regime = _classify_zscore(z),
        )
