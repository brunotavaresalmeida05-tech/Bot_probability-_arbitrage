from __future__ import annotations
from datetime import datetime, time, timezone
from typing import Optional


# All times in UTC
_SESSIONS: dict[str, dict | None] = {
    'sydney':      {'start': time(22, 0), 'end': time(7, 0),   'overnight': True},
    'tokyo':       {'start': time(0, 0),  'end': time(9, 0),   'overnight': False},
    'london':      {'start': time(8, 0),  'end': time(16, 0),  'overnight': False},
    'newyork':     {'start': time(13, 0), 'end': time(22, 0),  'overnight': False},
    'eu_stock':    {'start': time(8, 0),  'end': time(16, 30), 'overnight': False},
    'us_stock':    {'start': time(14, 30),'end': time(21, 0),  'overnight': False},
    'tokyo_stock': {'start': time(0, 0),  'end': time(6, 0),   'overnight': False},
    'futures_cme': {'start': time(23, 0), 'end': time(22, 0),  'overnight': True},
    'crypto':      None,
}

# CME futures: daily pause 22:00–23:00 UTC every day
_CME_PAUSE_START = time(22, 0)
_CME_PAUSE_END   = time(23, 0)

# Tokyo Stock Exchange lunch break 02:30–03:30 UTC
_TSE_LUNCH_START = time(2, 30)
_TSE_LUNCH_END   = time(3, 30)

# Forex weekend: Friday 22:00 UTC → Sunday 22:00 UTC
_FOREX_CLOSE_HOUR = time(22, 0)  # Friday close / Sunday reopen

# Symbol → asset category
_SYMBOL_CATEGORIES: dict[str, str] = {
    # Forex
    'EURUSD': 'forex', 'GBPUSD': 'forex', 'USDCHF': 'forex', 'USDJPY': 'forex',
    'AUDUSD': 'forex', 'NZDUSD': 'forex', 'USDCAD': 'forex', 'EURGBP': 'forex',
    'EURJPY': 'forex', 'GBPJPY': 'forex', 'AUDCAD': 'forex', 'CADJPY': 'forex',
    'AUDNZD': 'forex', 'EURCHF': 'forex', 'GBPCHF': 'forex',
    # Crypto
    'BTCUSD': 'crypto', 'ETHUSD': 'crypto', 'XRPUSD': 'crypto',
    'BNBUSD': 'crypto', 'SOLUSD': 'crypto', 'BTC': 'crypto', 'ETH': 'crypto',
    # US indices / stocks
    'US500': 'us_stock', 'NAS100': 'us_stock', 'US30': 'us_stock',
    'SPX500': 'us_stock', 'NDX': 'us_stock',
    # EU indices
    'GER40': 'eu_stock', 'UK100': 'eu_stock', 'FRA40': 'eu_stock',
    'ESP35': 'eu_stock', 'STOXX50': 'eu_stock',
    # Commodities / precious metals (CME Futures)
    'XAUUSD': 'futures', 'XAGUSD': 'futures', 'USOIL': 'futures',
    'UKOIL': 'futures', 'NATGAS': 'futures',
    # Tokyo Stock Exchange
    'JPN225': 'tokyo_stock',
}

# Category → sessions that allow trading
_CATEGORY_SESSIONS: dict[str, list[str]] = {
    'forex':       ['sydney', 'tokyo', 'london', 'newyork'],
    'crypto':      ['crypto'],
    'us_stock':    ['us_stock'],
    'eu_stock':    ['eu_stock'],
    'futures':     ['futures_cme'],
    'tokyo_stock': ['tokyo_stock'],
}


class SessionScheduler:
    """
    Determines whether a given market session is active and whether
    a specific symbol can be traded at a given UTC moment.

    All times are treated as UTC. Pass `now` (tz-aware or naive UTC) to
    override the current time — useful for backtesting and unit tests.
    """

    def __init__(self, symbol_categories: dict[str, str] | None = None):
        self._symbol_categories = symbol_categories or _SYMBOL_CATEGORIES

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_now(self, now: datetime | None) -> datetime:
        if now is None:
            return datetime.now(timezone.utc)
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now.astimezone(timezone.utc)

    def _is_session_active(self, session: str, t: time, weekday: int) -> bool:
        """weekday: 0=Mon … 4=Fri, 5=Sat, 6=Sun"""
        if session == 'crypto':
            return True

        cfg = _SESSIONS.get(session)
        if cfg is None:
            return False

        if session == 'futures_cme':
            if weekday == 5:  # Saturday: CME closed all day
                return False
            if weekday == 6 and t < _CME_PAUSE_END:  # Sunday before 23:00
                return False
            if _CME_PAUSE_START <= t < _CME_PAUSE_END:  # daily pause 22-23h
                return False
            return True

        # All other non-crypto sessions follow the Forex weekend calendar:
        #   closed from Friday 22:00 UTC until Sunday 22:00 UTC
        if weekday == 4 and t >= _FOREX_CLOSE_HOUR:  # Friday post-22h
            return False
        if weekday == 5:  # Saturday: all closed
            return False
        if weekday == 6 and t < _FOREX_CLOSE_HOUR:  # Sunday pre-22h
            return False

        if session == 'tokyo_stock':
            start, end = cfg['start'], cfg['end']
            in_session = start <= t < end
            in_lunch = _TSE_LUNCH_START <= t < _TSE_LUNCH_END
            return in_session and not in_lunch

        start, end = cfg['start'], cfg['end']
        if cfg.get('overnight'):
            return t >= start or t < end
        return start <= t < end

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def active_sessions(self, now: datetime | None = None) -> list[str]:
        """Return the list of market sessions currently open."""
        dt = self._resolve_now(now)
        t = dt.time().replace(tzinfo=None)
        weekday = dt.weekday()
        return [s for s in _SESSIONS if self._is_session_active(s, t, weekday)]

    def is_weekend(self, now: datetime | None = None) -> bool:
        """True if it is Saturday or Sunday (calendar weekend)."""
        return self._resolve_now(now).weekday() >= 5

    def get_symbol_category(self, symbol: str) -> str:
        """Resolve the asset category for a symbol. Defaults to 'forex'."""
        sym = symbol.upper().replace(' ', '')
        if sym in self._symbol_categories:
            return self._symbol_categories[sym]
        # Prefix / suffix match (e.g. 'BTCEUR' → matches 'BTC' → crypto)
        for key, cat in self._symbol_categories.items():
            if sym.startswith(key) or sym.endswith(key):
                return cat
        return 'forex'

    def can_trade(self, symbol: str, now: datetime | None = None) -> bool:
        """
        Return True if a new position can be opened for `symbol` at this moment.
        Crypto is always tradeable. All other assets respect their session windows.
        """
        category = self.get_symbol_category(symbol)
        if category == 'crypto':
            return True

        dt = self._resolve_now(now)
        t = dt.time().replace(tzinfo=None)
        weekday = dt.weekday()

        allowed = _CATEGORY_SESSIONS.get(category, ['london', 'newyork'])
        return any(self._is_session_active(s, t, weekday) for s in allowed)

    def session_info(self, now: datetime | None = None) -> dict:
        """
        Return a snapshot dict suitable for logging and API exposure.
        Contains active sessions, peak-liquidity flag, and per-category
        trading-allowed flags.
        """
        dt = self._resolve_now(now)
        active = self.active_sessions(dt)
        return {
            'timestamp_utc': dt.isoformat(),
            'weekday': dt.strftime('%A'),
            'is_weekend': self.is_weekend(dt),
            'active_sessions': active,
            'peak_liquidity': 'london' in active and 'newyork' in active,
            'trading_allowed': {
                'forex':       self.can_trade('EURUSD', dt),
                'crypto':      True,
                'us_stock':    self.can_trade('US500', dt),
                'eu_stock':    self.can_trade('GER40', dt),
                'futures':     self.can_trade('XAUUSD', dt),
                'tokyo_stock': self.can_trade('JPN225', dt),
            },
        }
