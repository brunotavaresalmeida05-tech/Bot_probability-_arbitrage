from __future__ import annotations
"""
Economic Calendar — V9

Fetches macro events and computes blackout windows.
High-impact events block all new entries:
  - 30 min before event
  - 15 min after event

Impact levels: high | medium | low
Sources: ForexFactory (scrape) + FRED release calendar
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from src.macro.macro_context import MacroContext

logger = logging.getLogger(__name__)

# High-impact keywords that always block trading
_HIGH_IMPACT_KEYWORDS = [
    "nonfarm", "payroll", "fomc", "fed rate", "interest rate",
    "cpi", "inflation", "gdp", "adp", "pmi", "unemployment",
    "jobless", "retail sales", "pce", "ecb", "boe",
    "powell", "lagarde", "jackson hole",
]

_BLACKOUT_BEFORE_MIN = 30   # block N min before event
_BLACKOUT_AFTER_MIN = 15    # block N min after event


@dataclass
class CalendarEvent:
    title: str
    dt_utc: datetime
    impact: str             # high | medium | low
    currency: str = "USD"
    actual: str = ""
    forecast: str = ""
    previous: str = ""

    def is_in_blackout(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        delta = (self.dt_utc - now).total_seconds() / 60.0
        return -_BLACKOUT_AFTER_MIN <= delta <= _BLACKOUT_BEFORE_MIN

    def minutes_until(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (self.dt_utc - now).total_seconds() / 60.0


class EconomicCalendar:
    """
    Fetches today's economic events and tracks active blackout windows.
    Thread daemon — refreshes every 30 min.
    """

    def __init__(self, macro: MacroContext, update_interval: int = 1800):
        self._macro = macro
        self._interval = update_interval
        self._lock = threading.Lock()
        self._events: list[CalendarEvent] = []
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def events(self) -> list[CalendarEvent]:
        with self._lock:
            return list(self._events)

    def start(self):
        self._running = True
        self._fetch_and_update()     # immediate first fetch
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="calendar"
        )
        self._thread.start()
        logger.info("EconomicCalendar started")

    def stop(self):
        self._running = False

    def is_blackout(self, currency: str = "USD") -> bool:
        """True if any high-impact event for this currency is in blackout window."""
        now = datetime.now(timezone.utc)
        with self._lock:
            for ev in self._events:
                if ev.impact == "high" and ev.currency == currency:
                    if ev.is_in_blackout(now):
                        return True
        return False

    def next_high_impact(self, currency: str = "USD") -> CalendarEvent | None:
        now = datetime.now(timezone.utc)
        future = [
            e for e in self.events
            if e.impact == "high" and e.currency == currency and e.dt_utc > now
        ]
        return min(future, key=lambda e: e.dt_utc) if future else None

    def today_events(self, impact: str | None = None) -> list[CalendarEvent]:
        today = datetime.now(timezone.utc).date()
        with self._lock:
            evs = [e for e in self._events if e.dt_utc.date() == today]
        if impact:
            evs = [e for e in evs if e.impact == impact]
        return evs

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------

    def _fetch_and_update(self):
        events = self._scrape_forexfactory()
        if not events:
            events = self._fallback_events()
        with self._lock:
            self._events = events
        # Update macro context
        now = datetime.now(timezone.utc)
        high_impact_next_30m = any(
            0 <= e.minutes_until(now) <= 30
            for e in events if e.impact == "high"
        )
        self._macro.high_impact_next_30m = high_impact_next_30m
        self._macro.news_events_today = [
            {"title": e.title, "impact": e.impact, "time_utc": e.dt_utc.isoformat()}
            for e in events if e.impact in ("high", "medium")
        ]
        logger.info(f"Calendar: {len(events)} events fetched, blackout_next_30m={high_impact_next_30m}")

    def _scrape_forexfactory(self) -> list[CalendarEvent]:
        """Scrape ForexFactory for today's economic events."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
            url = "https://www.forexfactory.com/calendar"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, "lxml")
            events = []
            today = datetime.now(timezone.utc)

            rows = soup.select("tr.calendar__row")
            current_date = today
            for row in rows:
                # Date cell (may be empty for subsequent events same day)
                date_cell = row.select_one("td.calendar__date span")
                if date_cell and date_cell.text.strip():
                    try:
                        date_str = date_cell.text.strip()
                        current_date = self._parse_ff_date(date_str, today.year)
                    except Exception:
                        pass

                time_cell = row.select_one("td.calendar__time")
                title_cell = row.select_one("td.calendar__event span.calendar__event-title")
                impact_cell = row.select_one("td.calendar__impact span")
                currency_cell = row.select_one("td.calendar__currency")

                if not title_cell:
                    continue

                title = title_cell.text.strip()
                currency = currency_cell.text.strip() if currency_cell else "USD"
                time_str = time_cell.text.strip() if time_cell else ""

                impact = "low"
                if impact_cell:
                    cls = " ".join(impact_cell.get("class", []))
                    if "high" in cls or "red" in cls:
                        impact = "high"
                    elif "medium" in cls or "orange" in cls:
                        impact = "medium"

                # Auto-classify by keyword
                if any(kw in title.lower() for kw in _HIGH_IMPACT_KEYWORDS):
                    impact = "high"

                try:
                    dt = self._parse_ff_time(time_str, current_date)
                except Exception:
                    dt = current_date

                events.append(CalendarEvent(
                    title=title, dt_utc=dt, impact=impact, currency=currency
                ))

            return events
        except Exception as e:
            logger.warning(f"ForexFactory scrape failed: {e}")
            return []

    def _parse_ff_date(self, s: str, year: int) -> datetime:
        from datetime import datetime
        import re
        # e.g. "Mon Jun 3" or "Tue Jun 4"
        s = re.sub(r"^\w+\s+", "", s)  # remove day-of-week
        dt = datetime.strptime(f"{s} {year}", "%b %d %Y")
        return dt.replace(tzinfo=timezone.utc)

    def _parse_ff_time(self, s: str, base: datetime) -> datetime:
        s = s.strip().upper()
        if not s or s in ("ALL DAY", "TENTATIVE"):
            return base.replace(hour=0, minute=0, second=0)
        from datetime import datetime as dt_cls
        try:
            t = dt_cls.strptime(s, "%I:%M%p")
        except Exception:
            t = dt_cls.strptime(s, "%I%p")
        return base.replace(hour=t.hour, minute=t.minute, second=0)

    def _fallback_events(self) -> list[CalendarEvent]:
        """Minimal fallback: returns empty list if scraping fails."""
        logger.warning("Calendar fallback: no events loaded")
        return []

    def _loop(self):
        while self._running:
            time.sleep(self._interval)
            try:
                self._fetch_and_update()
            except Exception as e:
                logger.error(f"Calendar update error: {e}")
