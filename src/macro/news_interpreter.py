from __future__ import annotations
"""
News Interpreter — V9

Classifies macro news into: bullish | neutral | bearish
Scoring model: each headline contributes -1, 0, or +1.
Final score: normalized to [-1.0, +1.0] then bucketed.

Sources: Finnhub news API (already integrated), FRED press releases.
Also parses structured economic calendar events vs expectations.
"""
import logging
import threading
import time
from dataclasses import dataclass, field

import requests

from src.macro.macro_context import MacroContext

logger = logging.getLogger(__name__)

# Keyword weights for news sentiment
_BULLISH_KEYWORDS = [
    "beats", "beat", "better than expected", "stronger", "surge", "rise", "rally",
    "above forecast", "exceeds", "record high", "expansion", "growth", "recovery",
    "hawkish", "rate hike", "tightening", "optimism", "confidence", "hiring",
]
_BEARISH_KEYWORDS = [
    "misses", "miss", "worse than expected", "weaker", "falls", "decline", "crash",
    "below forecast", "recession", "contraction", "layoffs", "unemployment", "inflation",
    "dovish", "rate cut", "easing", "panic", "fear", "geopolitical", "war", "crisis",
    "default", "downgrade", "disappointment",
]

# Economic indicator comparison: actual vs expected
_INDICATOR_DIRECTION = {
    # Positive surprise = bullish for risk (stocks up, USD reaction depends on type)
    "nonfarm payroll": "higher_is_bullish",
    "adp employment": "higher_is_bullish",
    "gdp": "higher_is_bullish",
    "retail sales": "higher_is_bullish",
    "ism manufacturing": "higher_is_bullish",
    "pmi": "higher_is_bullish",
    # For inflation: higher CPI = bearish (more rate hikes = risk off)
    "cpi": "higher_is_bearish",
    "pce": "higher_is_bearish",
    "inflation": "higher_is_bearish",
    # For unemployment: higher = bearish
    "unemployment": "higher_is_bearish",
    "jobless claims": "higher_is_bearish",
}


@dataclass
class NewsScore:
    headline_score: float = 0.0         # [-1, +1]
    event_score: float = 0.0            # [-1, +1]
    combined_score: float = 0.0         # [-1, +1]
    classification: str = "neutral"     # bullish | neutral | bearish
    headlines_analyzed: int = 0
    events_analyzed: int = 0
    top_headlines: list[str] = field(default_factory=list)


def _score_headline(text: str) -> int:
    text_lower = text.lower()
    bull = sum(1 for kw in _BULLISH_KEYWORDS if kw in text_lower)
    bear = sum(1 for kw in _BEARISH_KEYWORDS if kw in text_lower)
    if bull > bear:
        return 1
    elif bear > bull:
        return -1
    return 0


def _score_event(title: str, actual: str, forecast: str) -> int:
    """Score an economic event based on actual vs forecast."""
    if not actual or not forecast:
        return 0
    title_lower = title.lower()
    direction = None
    for kw, d in _INDICATOR_DIRECTION.items():
        if kw in title_lower:
            direction = d
            break
    if direction is None:
        return 0
    try:
        a = float(actual.replace("%", "").replace("K", "000").replace("M", "000000").strip())
        f = float(forecast.replace("%", "").replace("K", "000").replace("M", "000000").strip())
        if direction == "higher_is_bullish":
            return 1 if a > f else (-1 if a < f else 0)
        else:  # higher_is_bearish
            return -1 if a > f else (1 if a < f else 0)
    except (ValueError, AttributeError):
        return 0


class NewsInterpreter:
    """
    Background thread that fetches and classifies macro news.
    Updates MacroContext.news_score every N minutes.
    """

    def __init__(
        self,
        macro: MacroContext,
        finnhub_key: str = "",
        update_interval: int = 300,     # 5 min
    ):
        self._macro = macro
        self._finnhub_key = finnhub_key
        self._interval = update_interval
        self._lock = threading.Lock()
        self._score = NewsScore()
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def score(self) -> NewsScore:
        with self._lock:
            return self._score

    def start(self):
        self._running = True
        self._update()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="news-interpreter"
        )
        self._thread.start()
        logger.info("NewsInterpreter started")

    def stop(self):
        self._running = False

    def _fetch_finnhub_headlines(self) -> list[dict]:
        if not self._finnhub_key:
            return []
        try:
            from datetime import datetime, timedelta, timezone
            today = datetime.now(timezone.utc)
            yesterday = today - timedelta(days=1)
            r = requests.get(
                "https://finnhub.io/api/v1/news",
                params={
                    "category": "general",
                    "token": self._finnhub_key,
                    "minId": 0,
                },
                timeout=8,
            )
            if r.status_code == 200:
                return r.json()[:50]   # last 50 headlines
        except Exception as e:
            logger.debug(f"Finnhub news error: {e}")
        return []

    def _update(self):
        headlines = self._fetch_finnhub_headlines()
        scores = []
        top = []

        for h in headlines:
            text = f"{h.get('headline', '')} {h.get('summary', '')}"
            s = _score_headline(text)
            scores.append(s)
            if s != 0:
                top.append(h.get("headline", "")[:100])

        # Aggregate
        if scores:
            headline_score = sum(scores) / len(scores)
        else:
            headline_score = 0.0

        # Bucket into classification
        if headline_score >= 0.15:
            classification = "bullish"
        elif headline_score <= -0.15:
            classification = "bearish"
        else:
            classification = "neutral"

        ns = NewsScore(
            headline_score=round(headline_score, 4),
            combined_score=round(headline_score, 4),
            classification=classification,
            headlines_analyzed=len(scores),
            top_headlines=top[:5],
        )

        with self._lock:
            self._score = ns

        self._macro.news_score = classification
        logger.debug(
            f"News: {classification} score={headline_score:.3f} "
            f"headlines={len(scores)}"
        )

    def _loop(self):
        while self._running:
            time.sleep(self._interval)
            try:
                self._update()
            except Exception as e:
                logger.error(f"NewsInterpreter update error: {e}")
