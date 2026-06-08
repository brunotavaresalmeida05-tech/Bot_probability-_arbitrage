from __future__ import annotations
"""
Market Session Manager — V9

Sessions (UTC):
  Asia/Sydney: 22:00 - 08:00
  London:      08:00 - 17:00  (primary)
  New York:    13:00 - 22:00  (primary)
  Overlap:     13:00 - 17:00  (highest liquidity)

Tradeability is PER-ASSET, driven by asset_profiler.session_focus.
This is the single source of truth — no hardcoded lists here.

Examples:
  USDJPY  session_focus=[asia, london, new_york]  -> trades all sessions
  Ger40   session_focus=[london]                  -> only London (Frankfurt hours)
  Usa500  session_focus=[new_york]                -> only NY cash + futures
  GOLD    session_focus=[asia, london, new_york]  -> trades all sessions
  EURUSD  session_focus=[london, new_york]        -> London + NY only

Sleep intervals per session:
  Overlap:  60s  (max liquidity, signals frequent)
  London:   90s  (primary FX + EU indices)
  NY:       90s  (primary equities + commodities)
  Asia:    180s  (fewer instruments, slower market)
  Closed:  300s  (nothing trades)
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Session(str, Enum):
    ASIA     = "asia"
    LONDON   = "london"
    NEW_YORK = "new_york"
    OVERLAP  = "london_ny_overlap"
    CLOSED   = "closed"


@dataclass
class SessionState:
    active: list[str]  = field(default_factory=list)
    primary: str       = "closed"
    peak_liquidity: bool = False
    london_open: bool  = False
    ny_open: bool      = False
    asia_open: bool    = False
    hour_utc: int      = 0
    tradeable: bool    = False   # True when any session is live
    sleep_seconds: int = 300


def current_sessions() -> SessionState:
    now = datetime.now(timezone.utc)
    h   = now.hour
    s   = SessionState(hour_utc=h)

    s.asia_open    = (h >= 22 or h < 8)
    s.london_open  = (8 <= h < 17)
    s.ny_open      = (13 <= h < 22)
    s.peak_liquidity = (13 <= h < 17)

    active = []
    if s.asia_open:    active.append(Session.ASIA)
    if s.london_open:  active.append(Session.LONDON)
    if s.ny_open:      active.append(Session.NEW_YORK)
    if s.peak_liquidity: active.append(Session.OVERLAP)

    s.active = [x.value for x in active]

    if s.peak_liquidity:
        s.primary       = Session.OVERLAP.value
        s.sleep_seconds = 60
    elif s.london_open:
        s.primary       = Session.LONDON.value
        s.sleep_seconds = 90
    elif s.ny_open:
        s.primary       = Session.NEW_YORK.value
        s.sleep_seconds = 90
    elif s.asia_open:
        s.primary       = Session.ASIA.value
        s.sleep_seconds = 180
    else:
        s.primary       = Session.CLOSED.value
        s.sleep_seconds = 300

    s.tradeable = s.london_open or s.ny_open or s.asia_open
    return s


def is_tradeable_for(symbol: str, session: SessionState | None = None) -> bool:
    """
    Per-asset tradeability: symbol is tradeable only during its session_focus sessions.
    Uses asset_profiler as single source of truth — no hardcoded lists.
    """
    if session is None:
        session = current_sessions()

    # Import here to avoid circular imports
    from src.analysis.asset_profiler import get_profile
    profile = get_profile(symbol)
    focus   = set(profile.session_focus)   # e.g. {"london", "new_york"}

    # Check each active session against the asset's focus
    if session.london_open  and "london"   in focus: return True
    if session.ny_open      and "new_york" in focus: return True
    if session.asia_open    and "asia"     in focus: return True

    return False


def get_sleep_seconds(session: SessionState | None = None) -> int:
    if session is None:
        session = current_sessions()
    return session.sleep_seconds


def active_symbols_for(symbols: list[str], session: SessionState | None = None) -> list[str]:
    """Filter a list of symbols to only those tradeable in the current session."""
    if session is None:
        session = current_sessions()
    return [s for s in symbols if is_tradeable_for(s, session)]


def session_info() -> dict:
    s = current_sessions()
    return {
        "active_sessions":  s.active,
        "primary":          s.primary,
        "peak_liquidity":   s.peak_liquidity,
        "tradeable":        s.tradeable,
        "hour_utc":         s.hour_utc,
        "sleep_seconds":    s.sleep_seconds,
    }
