from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import requests

logger = logging.getLogger(__name__)

_HIGH_IMPACT = {"high"}

# Palavras-chave para classificar eventos como alto impacto se "impact" não disponível
_HIGH_KEYWORDS = {
    "nonfarm", "nfp", "cpi", "fomc", "fed rate", "ecb rate", "boe rate",
    "boj rate", "gdp", "unemployment", "payroll", "inflation",
    "interest rate decision", "monetary policy",
}


@dataclass
class NewsState:
    is_blocked: bool = False
    blocking_event: str = ""
    next_event_name: str = ""
    minutes_to_next_event: int = 9999
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class _Event:
    name: str
    impact: str
    event_time: datetime
    country: str


class NewsGate:
    """
    Filtra entradas baseado no calendário económico Finnhub.
    Bloqueia 15min ANTES e 30min DEPOIS de eventos de alto impacto.
    Thread daemon — loop principal lê da memória em zero latência.
    """

    def __init__(
        self,
        finnhub_key: str = "",
        update_interval: int = 120,         # 2min
        blackout_before_min: int = 15,
        blackout_after_min: int = 30,
    ):
        self._finnhub_key = finnhub_key
        self._update_interval = update_interval
        self._before = timedelta(minutes=blackout_before_min)
        self._after  = timedelta(minutes=blackout_after_min)
        self._lock   = threading.Lock()
        self._events: list[_Event] = []
        self._state  = NewsState()
        self._running = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API (thread-safe, zero I/O)
    # ------------------------------------------------------------------

    @property
    def state(self) -> NewsState:
        with self._lock:
            return self._state

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="NewsGate"
        )
        self._thread.start()
        logger.info("NewsGate started.")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def _set_events(self, raw_events: list[dict]) -> None:
        events = []
        for e in raw_events:
            try:
                t = datetime.fromisoformat(e["time"])
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                events.append(_Event(
                    name=e["event"], impact=e.get("impact", "low"),
                    event_time=t, country=e.get("country", ""),
                ))
            except Exception:
                pass
        with self._lock:
            self._events = events
            self._state = self._evaluate(events)

    def _parse_finnhub_response(self, raw: dict) -> list[dict]:
        """Extrai apenas eventos de alto impacto do response Finnhub."""
        results = raw.get("economicCalendar", {}).get("result", [])
        out = []
        for item in results:
            impact = str(item.get("impact", "")).lower()
            event_name = str(item.get("event", ""))
            # Detectar alto impacto por campo ou por keyword
            is_high = (impact == "high") or any(
                kw in event_name.lower() for kw in _HIGH_KEYWORDS
            )
            out.append({
                "event":   event_name,
                "impact":  "high" if is_high else impact,
                "time":    str(item.get("time", "")),
                "country": str(item.get("country", "")),
            })
        return out

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        while self._running:
            self._fetch_calendar()
            with self._lock:
                self._state = self._evaluate(self._events)
            time.sleep(self._update_interval)

    def _fetch_calendar(self) -> None:
        if not self._finnhub_key:
            return
        try:
            now = datetime.now(timezone.utc)
            from_dt = now.strftime("%Y-%m-%d")
            to_dt   = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            r = requests.get(
                "https://finnhub.io/api/v1/calendar/economic",
                params={"from": from_dt, "to": to_dt, "token": self._finnhub_key},
                timeout=5,
            )
            if r.status_code == 200:
                parsed = self._parse_finnhub_response(r.json())
                high_events: list[_Event] = []
                for e in parsed:
                    if e["impact"] == "high":
                        try:
                            t = datetime.fromisoformat(e["time"])
                            if t.tzinfo is None:
                                t = t.replace(tzinfo=timezone.utc)
                            high_events.append(_Event(
                                name=e["event"], impact="high",
                                event_time=t, country=e["country"],
                            ))
                        except Exception:
                            pass
                with self._lock:
                    self._events = high_events
        except Exception as e:
            logger.debug(f"NewsGate calendar fetch failed: {e}")

    def _evaluate(self, events: list[_Event]) -> NewsState:
        now = datetime.now(timezone.utc)
        is_blocked = False
        blocking_event = ""
        next_name = ""
        minutes_to_next = 9999

        high = [e for e in events if e.impact in _HIGH_IMPACT]

        for e in high:
            dt = e.event_time - now
            minutes = dt.total_seconds() / 60.0

            # Dentro da janela de bloqueio (antes ou depois)?
            if -self._after.total_seconds() / 60.0 <= minutes <= self._before.total_seconds() / 60.0:
                is_blocked = True
                blocking_event = e.name

            # Próximo evento futuro
            if 0 < minutes < minutes_to_next:
                minutes_to_next = int(minutes)
                next_name = e.name

        return NewsState(
            is_blocked=is_blocked,
            blocking_event=blocking_event,
            next_event_name=next_name,
            minutes_to_next_event=minutes_to_next,
            updated_at=now.isoformat(),
        )
