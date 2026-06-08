from __future__ import annotations
import logging
import math
import threading
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# Pesos oficiais do DXY (ICE formula)
_WEIGHTS: dict[str, float] = {
    "EURUSD": -0.576,  # negativo: EUR/USD sobe → DXY desce
    "USDJPY":  0.136,
    "GBPUSD": -0.119,
    "USDCAD":  0.091,
    "USDSEK":  0.042,
    "USDCHF":  0.036,
}

# DXY de referência (valor base normalizado para z-score)
_DXY_REF = 100.0

# Z-score thresholds para regime
_RISK_OFF_Z =  1.5
_RISK_ON_Z  = -1.5


@dataclass
class DXYState:
    index_value: float = 101.0
    prev_value: float = 101.0
    daily_change_pct: float = 0.0
    zscore: float = 0.0
    regime: str = "neutral"    # "risk_off" | "neutral" | "risk_on"
    updated_at: str = ""


class DXYBasket:
    """
    Calcula um DXY sintético a partir de taxas forex (Finnhub).
    Thread daemon — loop principal lê da memória em zero latência.

    Regimes:
      risk_off (DXY forte)  → USD a drenar liquidez → penaliza índices + crypto
      neutral               → sem impacto direccional
      risk_on  (DXY fraco)  → liquidez a expandir   → favorece activos de risco
    """

    _RISK_MULTIPLIERS = {"risk_off": 0.60, "neutral": 1.0, "risk_on": 1.0}

    # Default rates (market averages)
    _DEFAULT_RATES = {
        "EURUSD": 1.08, "GBPUSD": 1.27,
        "USDJPY": 150.0, "USDCAD": 1.36,
        "USDSEK": 10.5, "USDCHF": 0.89,
    }

    def __init__(
        self,
        finnhub_key: str = "",
        update_interval: int = 1800,  # 30min
    ):
        self._finnhub_key = finnhub_key
        self._update_interval = update_interval
        self._lock = threading.Lock()
        self._rates: dict[str, float] = dict(self._DEFAULT_RATES)
        # Rolling buffer for z-score (last 48 readings ≈ 24h at 30min)
        self._history: list[float] = []
        self._state = self._compute_state()
        self._running = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API (thread-safe, zero I/O)
    # ------------------------------------------------------------------

    @property
    def state(self) -> DXYState:
        with self._lock:
            return self._state

    def risk_multiplier(self) -> float:
        return self._RISK_MULTIPLIERS.get(self.state.regime, 1.0)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="DXYBasket"
        )
        self._thread.start()
        logger.info("DXYBasket started.")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def _set_rates(self, rates: dict[str, float]) -> None:
        with self._lock:
            self._rates.update(rates)
            self._state = self._compute_state()

    def _set_state_direct(
        self,
        index_value: float,
        zscore: float,
        prev_value: float | None = None,
    ) -> None:
        with self._lock:
            prev = prev_value if prev_value is not None else index_value
            chg = ((index_value - prev) / prev * 100) if prev else 0.0
            regime = self._classify(zscore)
            self._state = DXYState(
                index_value=round(index_value, 4),
                prev_value=round(prev, 4),
                daily_change_pct=round(chg, 4),
                zscore=round(zscore, 4),
                regime=regime,
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        while self._running:
            for pair in list(_WEIGHTS.keys()):
                self._fetch_rate(pair, pair)
            with self._lock:
                self._state = self._compute_state()
            time.sleep(self._update_interval)

    def _fetch_rate(self, pair: str, key: str) -> None:
        if not self._finnhub_key:
            return
        # Finnhub forex quote: GET /quote?symbol=<from><to>
        symbol = pair.replace("USD", "").replace("USD", "")
        # Build Finnhub forex symbol e.g. OANDA:EUR_USD
        from_c = pair[:3]
        to_c   = pair[3:]
        finnhub_sym = f"OANDA:{from_c}_{to_c}"
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": finnhub_sym, "token": self._finnhub_key},
                timeout=4,
            )
            if r.status_code == 200:
                val = r.json().get("c")
                if val and float(val) > 0:
                    with self._lock:
                        self._rates[key] = float(val)
        except Exception as e:
            logger.debug(f"DXYBasket fetch {pair} failed: {e}")

    def _compute_state(self) -> DXYState:
        """Calcula DXY sintético via produto ponderado (log-space)."""
        rates = dict(self._rates)
        try:
            log_dxy = sum(
                w * math.log(rates[pair])
                for pair, w in _WEIGHTS.items()
                if pair in rates and rates[pair] > 0
            )
            # Normalise to roughly 100 scale using reference log value
            ref_log = sum(
                w * math.log(self._DEFAULT_RATES[pair])
                for pair, w in _WEIGHTS.items()
            )
            index_value = _DXY_REF * math.exp(log_dxy - ref_log)
        except Exception:
            index_value = _DXY_REF

        self._history.append(index_value)
        if len(self._history) > 48:
            self._history = self._history[-48:]

        prev = self._state.index_value if hasattr(self, "_state") else index_value
        chg = ((index_value - prev) / prev * 100) if prev else 0.0

        if len(self._history) >= 5:
            import statistics
            mean = statistics.mean(self._history)
            std  = statistics.stdev(self._history) if len(self._history) > 1 else 1.0
            zscore = (index_value - mean) / std if std > 0 else 0.0
        else:
            zscore = 0.0

        regime = self._classify(zscore)
        return DXYState(
            index_value=round(index_value, 4),
            prev_value=round(prev, 4),
            daily_change_pct=round(chg, 4),
            zscore=round(zscore, 4),
            regime=regime,
        )

    @staticmethod
    def _classify(zscore: float) -> str:
        if zscore >= _RISK_OFF_Z:
            return "risk_off"
        if zscore <= _RISK_ON_Z:
            return "risk_on"
        return "neutral"
