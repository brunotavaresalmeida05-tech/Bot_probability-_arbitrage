from __future__ import annotations
import logging
import threading
import time
from datetime import datetime, timezone

import requests

from src.macro.macro_context import MacroContext

logger = logging.getLogger(__name__)

_VIX_THRESHOLDS = [
    (40.0, "panic",   0.0,  0.0),
    (30.0, "kill",    0.0,  0.0),
    (25.0, "alert",   0.5,  0.5),
    (20.0, "caution", 0.75, 0.75),
    (0.0,  "normal",  1.0,  1.0),
]


def _classify_vix(v: float) -> tuple[str, float]:
    for threshold, regime, lot_mult, _ in _VIX_THRESHOLDS:
        if v >= threshold:
            return regime, lot_mult
    return "normal", 1.0


class VixMonitor:
    """
    Monitoriza VIX e VIX futuro (CBOE) em tempo real via Finnhub.
    Thread daemon — loop principal le da memoria em zero latencia.

    Regimes:
      normal  (VIX <20): mercado calmo, lot_mult=1.0
      caution (20-25):   so forex,      lot_mult=0.75
      alert   (25-30):   sem entradas,  lot_mult=0.5
      kill    (30-40):   bloqueia ciclo, lot_mult=0.0
      panic   (>=40):    fechar tudo,   lot_mult=0.0
    """

    def __init__(
        self,
        macro: MacroContext,
        finnhub_key: str = "",
        update_interval: int = 60,
        vix_default: float = 20.0,
    ):
        self._macro = macro
        self._finnhub_key = finnhub_key
        self._interval = update_interval
        self._default = vix_default
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="vix-monitor")
        self._thread.start()
        logger.info("VixMonitor started")

    def stop(self):
        self._running = False

    def _fetch(self) -> float | None:
        if not self._finnhub_key:
            return None
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": "^VIX", "token": self._finnhub_key},
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                v = data.get("c") or data.get("l")
                if v and float(v) > 0:
                    return float(v)
        except Exception as e:
            logger.warning(f"VIX fetch error: {e}")
        return None

    def _loop(self):
        while self._running:
            value = self._fetch()
            if value is None:
                value = self._macro.vix or self._default
            regime, lot_mult = _classify_vix(value)
            with self._lock:
                self._macro.vix = value
                self._macro.vix_regime = regime
                self._macro.vix_lot_mult = lot_mult
                self._macro.recompute_global()
                self._macro.refresh_timestamp()
            logger.debug(f"VIX={value:.1f} regime={regime} lot_mult={lot_mult}")
            time.sleep(self._interval)
