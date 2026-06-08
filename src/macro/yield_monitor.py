from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

# FRED series IDs
_SERIES = {"us10y": "DGS10", "us2y": "DGS2", "us3m": "DTB3"}

# Curve regime thresholds (10Y - 2Y spread in pp)
# Curva positiva >= 0.25pp → steep (expansão normal)
# 0 <= spread < 0.25pp   → flat (compressão / transição)
# spread < 0             → inverted (recessão clássica)
_FLAT_MAX = 0.25


@dataclass
class YieldState:
    us10y: float = 4.5
    us2y: float  = 4.0
    us3m: float  = 5.2
    spread_10y_2y: float = 0.5
    spread_10y_3m: float = -0.7
    curve_regime: str = "flat"   # "steep" | "flat" | "inverted"
    updated_at: str = ""

    def __post_init__(self):
        self._recompute()

    def _recompute(self):
        self.spread_10y_2y = round(self.us10y - self.us2y, 4)
        self.spread_10y_3m = round(self.us10y - self.us3m, 4)
        if self.spread_10y_2y < 0:
            self.curve_regime = "inverted"
        elif self.spread_10y_2y < _FLAT_MAX:
            self.curve_regime = "flat"
        else:
            self.curve_regime = "steep"


class YieldMonitor:
    """
    Monitoriza a curva de yields do Tesouro americano via FRED API.
    Thread daemon — loop principal lê da memória em zero latência.

    Regimes e impacto no sistema:
      steep    → curva normal, expansão económica   → risk_multiplier = 1.0
      flat     → transição / aperto monetário       → risk_multiplier = 0.75
      inverted → sinal clássico de recessão         → risk_multiplier = 0.50
    """

    _RISK_MULTIPLIERS = {"steep": 1.0, "flat": 0.75, "inverted": 0.50}

    def __init__(
        self,
        fred_key: str = "",
        update_interval: int = 3600,  # 1h
    ):
        self._fred_key = fred_key
        self._update_interval = update_interval
        self._lock = threading.Lock()
        self._state = YieldState()
        self._running = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API (thread-safe, zero I/O)
    # ------------------------------------------------------------------

    @property
    def state(self) -> YieldState:
        with self._lock:
            return self._state

    def risk_multiplier(self) -> float:
        return self._RISK_MULTIPLIERS.get(self.state.curve_regime, 1.0)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="YieldMonitor"
        )
        self._thread.start()
        logger.info("YieldMonitor started.")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def _set_yields(self, us10y: float, us2y: float, us3m: float) -> None:
        with self._lock:
            self._state = YieldState(us10y=us10y, us2y=us2y, us3m=us3m)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        while self._running:
            for attr, series in _SERIES.items():
                self._fetch_fred_series(series, attr)
            with self._lock:
                self._state._recompute()
            time.sleep(self._update_interval)

    def _fetch_fred_series(self, series_id: str, attr: str) -> None:
        if not self._fred_key:
            return
        try:
            r = requests.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id":  series_id,
                    "api_key":    self._fred_key,
                    "file_type":  "json",
                    "sort_order": "desc",
                    "limit":      1,
                },
                timeout=5,
            )
            if r.status_code == 200:
                obs = r.json().get("observations", [])
                if obs:
                    raw = obs[0].get("value", "")
                    if raw and raw != ".":
                        with self._lock:
                            setattr(self._state, attr, float(raw))
        except Exception as e:
            logger.debug(f"YieldMonitor FRED {series_id} failed: {e}")
