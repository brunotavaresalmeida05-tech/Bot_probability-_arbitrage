"""
src/news_engine.py
Motor de notícias e sentimento — 5 fontes em cascata.
Prioridade: Finnhub → MarketAux → EODHD → Currents → Mediastack
"""

import requests
import time
import threading
from datetime import datetime, timedelta
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg

# ── Cache ─────────────────────────────────────────────────────
_cache: dict = {}
_cache_lock  = threading.Lock()

def _get_cache(key, ttl=600):
    with _cache_lock:
        if key in _cache and time.time() - _cache[key]["ts"] < ttl:
            return _cache[key]["data"]
    return None

def _set_cache(key, data):
    with _cache_lock:
        _cache[key] = {"ts": time.time(), "data": data}

def _fetch(url, params=None, headers=None, ttl=600):
    key = url + str(sorted((params or {}).items()))
    cached = _get_cache(key, ttl)
    if cached is not None:
        return cached
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        data = r.json()
        _set_cache(key, data)
        return data
    except Exception:
        return None

# ── Palavras para NLP simples ─────────────────────────────────
POS = ["rise","gain","surge","rally","beat","strong","bullish","recovery",
       "hawkish","hike","growth","accelerate","outperform","positive","upgrade",
       "higher","above","exceeds","optimism","confidence","expansion"]
NEG = ["fall","drop","decline","crash","miss","weak","bearish","recession",
       "dovish","cut","slowdown","disappoint","underperform","negative","downgrade",
       "lower","below","concern","fear","contraction","risk","warning"]

def _score_text(text: str) -> float:
    t = text.lower()
    p = sum(1 for w in POS if w in t)
    n = sum(1 for w in NEG if w in t)
    total = p + n
    return (p - n) / total if total > 0 else 0.0

# Keywords por símbolo
KEYWORDS = {
    "EURUSD": ["EUR USD", "euro dollar", "ECB rate", "eurozone"],
    "GBPUSD": ["GBP USD", "pound sterling", "Bank of England"],
    "USDJPY": ["USD JPY", "yen dollar", "Bank of Japan", "BOJ"],
    "AUDUSD": ["AUD USD", "australian dollar", "RBA"],
    "USDCHF": ["USD CHF", "swiss franc", "SNB"],
    "USDCAD": ["USD CAD", "canadian dollar", "BOC"],
    "XAUUSD": ["gold price", "gold USD", "safe haven"],
    "US500":  ["S&P 500", "SPX", "Fed rate", "US economy"],
    "US100":  ["Nasdaq", "tech stocks", "AI earnings"],
    "GER40":  ["DAX", "Germany", "ECB", "eurozone"],
}


# ═══════════════════════════════════════════════════════════════
#  FONTE 1 — FINNHUB (melhor para trading)
#  60 req/min grátis — notícias, sentimento, calendário económico
# ═══════════════════════════════════════════════════════════════

def finnhub_news(symbol: str, hours: int = 12) -> list:
    if not getattr(cfg, "USE_FINNHUB", False) or not getattr(cfg, "FINNHUB_KEY", ""):
        return []

    # Mapa para categoria Finnhub
    category = "forex" if len(symbol) == 6 else "general"

    data = _fetch(
        "https://finnhub.io/api/v1/news",
        params={"category": category, "token": cfg.FINNHUB_KEY},
        ttl=600
    )
    if not isinstance(data, list):
        return []

    keywords = KEYWORDS.get(symbol, [symbol[:6]])
    cutoff   = time.time() - hours * 3600
    articles = []
    for a in data:
        if a.get("datetime", 0) < cutoff:
            continue
        text = (a.get("headline","") + " " + a.get("summary","")).lower()
        if any(kw.lower() in text for kw in keywords):
            articles.append({
                "title":   a.get("headline",""),
                "summary": a.get("summary",""),
                "source":  "finnhub",
            })
    return articles[:15]


def finnhub_sentiment(symbol: str) -> Optional[dict]:
    """Sentimento agregado do Finnhub para um símbolo."""
    if not getattr(cfg, "USE_FINNHUB", False) or not getattr(cfg, "FINNHUB_KEY", ""):
        return None

    # Mapa símbolo FX → ticker para Finnhub
    ticker_map = {
        "EURUSD": "OANDA:EUR_USD", "GBPUSD": "OANDA:GBP_USD",
        "USDJPY": "OANDA:USD_JPY", "AUDUSD": "OANDA:AUD_USD",
        "USDCHF": "OANDA:USD_CHF", "XAUUSD": "OANDA:XAU_USD",
    }
    ticker = ticker_map.get(symbol)
    if not ticker:
        return None

    data = _fetch(
        "https://finnhub.io/api/v1/news-sentiment",
        params={"symbol": ticker, "token": cfg.FINNHUB_KEY},
        ttl=3600
    )
    if not data or "buzz" not in data:
        return None

    return {
        "buzz":          data.get("buzz", {}).get("buzz", 0),
        "sentiment":     data.get("sentiment", {}).get("bullishPercent", 0.5) * 2 - 1,
        "articles_last_week": data.get("buzz", {}).get("articlesInLastWeek", 0),
    }


def finnhub_economic_calendar(hours_ahead: int = 48) -> list:
    """Calendário económico — eventos macro próximos."""
    if not getattr(cfg, "USE_FINNHUB", False) or not getattr(cfg, "FINNHUB_KEY", ""):
        return []

    now  = datetime.now()
    end  = now + timedelta(hours=hours_ahead)
    data = _fetch(
        "https://finnhub.io/api/v1/calendar/economic",
        params={"from": now.strftime("%Y-%m-%d"),
                "to":   end.strftime("%Y-%m-%d"),
                "token": cfg.FINNHUB_KEY},
        ttl=3600
    )
    if not data or "economicCalendar" not in data:
        return []

    # Filtrar eventos de alto impacto
    events = []
    for e in data.get("economicCalendar", []):
        impact = str(e.get("impact","")).lower()
        if impact in ("high", "3", "medium", "2"):
            events.append({
                "event":    e.get("event", ""),
                "country":  e.get("country", ""),
                "impact":   impact,
                "time":     e.get("time", ""),
            })
    return events[:10]


# ═══════════════════════════════════════════════════════════════
#  FONTE 2 — MARKETAUX
#  100 req/dia grátis — notícias financeiras com entidades
# ═══════════════════════════════════════════════════════════════

# Mapa símbolo → ticker MarketAux
MARKETAUX_SYMBOLS = {
    "EURUSD": "EUR/USD", "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY", "AUDUSD": "AUD/USD",
    "XAUUSD": "XAU/USD", "US500":  "SPY",
}

def marketaux_news(symbol: str, limit: int = 5) -> list:
    if not getattr(cfg, "USE_MARKETAUX", False) or not getattr(cfg, "MARKETAUX_KEY", ""):
        return []

    ticker = MARKETAUX_SYMBOLS.get(symbol, "")
    if not ticker:
        return []

    data = _fetch(
        "https://api.marketaux.com/v1/news/all",
        params={"symbols": ticker, "api_token": cfg.MARKETAUX_KEY,
                "limit": limit, "language": "en"},
        ttl=600
    )
    if not data or "data" not in data:
        return []

    return [{"title": a.get("title",""), "summary": a.get("description",""),
             "source": "marketaux",
             "sentiment": a.get("entities",[{}])[0].get("sentiment_score", 0)
             if a.get("entities") else 0}
            for a in data["data"]]


# ═══════════════════════════════════════════════════════════════
#  FONTE 3 — EODHD
#  Notícias financeiras + dados fundamentais
# ═══════════════════════════════════════════════════════════════

EODHD_SYMBOLS = {
    "EURUSD": "EURUSD.FOREX", "GBPUSD": "GBPUSD.FOREX",
    "USDJPY": "USDJPY.FOREX", "AUDUSD": "AUDUSD.FOREX",
    "XAUUSD": "GLD.US",       "US500":  "SPY.US",
}

def eodhd_news(symbol: str, limit: int = 5) -> list:
    if not getattr(cfg, "USE_EODHD", False) or not getattr(cfg, "EODHD_KEY", ""):
        return []

    ticker = EODHD_SYMBOLS.get(symbol, "")
    if not ticker:
        return []

    data = _fetch(
        "https://eodhd.com/api/news",
        params={"api_token": cfg.EODHD_KEY, "s": ticker,
                "limit": limit, "fmt": "json"},
        ttl=600
    )
    if not isinstance(data, list):
        return []

    return [{"title": a.get("title",""), "summary": a.get("content","")[:200],
             "source": "eodhd"} for a in data]


# ═══════════════════════════════════════════════════════════════
#  FONTE 4 — CURRENTS API
# ═══════════════════════════════════════════════════════════════

def currents_news(symbol: str, limit: int = 5) -> list:
    if not getattr(cfg, "USE_CURRENTS", False) or not getattr(cfg, "CURRENTS_KEY", ""):
        return []

    keywords = " ".join(KEYWORDS.get(symbol, [symbol[:6]])[:2])
    data = _fetch(
        "https://api.currentsapi.services/v1/latest-news",
        params={"apiKey": cfg.CURRENTS_KEY, "language": "en",
                "keywords": keywords, "page_size": limit},
        ttl=600
    )
    if not data or data.get("status") != "ok":
        return []

    return [{"title": a.get("title",""), "summary": a.get("description",""),
             "source": "currents"} for a in data.get("news", [])]


# ═══════════════════════════════════════════════════════════════
#  COMBINADOR — score final de sentimento
# ═══════════════════════════════════════════════════════════════

def get_combined_sentiment(symbol: str) -> dict:
    """
    Agrega sentimento de todas as fontes disponíveis.
    Retorna score -1.0 a +1.0 e lista de headlines.
    """
    all_articles = []
    scores       = []
    headlines    = []

    # Finnhub (maior peso — score de sentimento directo)
    fh_sent = finnhub_sentiment(symbol)
    if fh_sent and fh_sent.get("sentiment") is not None:
        scores.append(("finnhub_direct", fh_sent["sentiment"], 0.4))

    fh_articles = finnhub_news(symbol, 12)
    all_articles.extend(fh_articles)

    # MarketAux (tem sentiment score por artigo)
    mx_articles = marketaux_news(symbol, 5)
    for a in mx_articles:
        if "sentiment" in a and a["sentiment"] != 0:
            scores.append(("marketaux", float(a["sentiment"]), 0.15))
    all_articles.extend(mx_articles)

    # EODHD + Currents (NLP simples)
    for source_fn in [eodhd_news, currents_news]:
        arts = source_fn(symbol, 5)
        all_articles.extend(arts)

    # NLP simples em todos os artigos sem score directo
    nlp_scores = []
    for a in all_articles:
        text = (a.get("title","") + " " + a.get("summary",""))
        s    = _score_text(text)
        if s != 0:
            nlp_scores.append(s)
        if a.get("title"):
            headlines.append(a["title"][:80])

    if nlp_scores:
        nlp_mean = sum(nlp_scores) / len(nlp_scores)
        scores.append(("nlp", nlp_mean, 0.3))

    # Score ponderado final
    if not scores:
        return {"score": 0.0, "total_articles": len(all_articles),
                "headlines": headlines[:3], "sources": []}

    total_weight = sum(w for _, _, w in scores)
    if total_weight == 0:
        return {"score": 0.0, "total_articles": len(all_articles),
                "headlines": headlines[:3], "sources": []}

    final_score = sum(s * w for _, s, w in scores) / total_weight

    # Calendário económico — penalizar se há eventos de alto impacto iminentes
    calendar = finnhub_economic_calendar(hours_ahead=4)
    if calendar:
        high_impact = [e for e in calendar if "high" in e.get("impact","")]
        if high_impact:
            final_score *= 0.5  # reduz confiança 50% antes de evento importante

    return {
        "score":         round(float(max(-1.0, min(1.0, final_score))), 4),
        "total_articles": len(all_articles),
        "headlines":      headlines[:3],
        "sources":        [s for s, _, _ in scores],
        "high_impact_events": len([e for e in calendar if "high" in e.get("impact","")]),
    }
