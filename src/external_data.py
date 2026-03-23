"""
src/external_data.py
Conector para APIs externas: FRED, Alpha Vantage, Polygon, NewsAPI.
Fornece dados mais limpos e precisos que o MT5 CFD para certos activos.
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import sys, os, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import (
    FRED_API_KEY, ALPHA_VANTAGE_KEY, POLYGON_KEY, NEWSAPI_KEY
)

# ─── Cache simples em memória (evita bater nos limites das APIs) ───
_cache: dict = {}
CACHE_TTL = 60  # segundos


def _cached(key: str, fn, ttl: int = CACHE_TTL):
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < ttl:
        return _cache[key]["data"]
    data = fn()
    if data is not None:
        _cache[key] = {"ts": now, "data": data}
    return data


# ══════════════════════════════════════════════════
#  POLYGON  — preços tick precisos (FX + stocks)
# ══════════════════════════════════════════════════

POLYGON_BASE = "https://api.polygon.io"

# Mapa símbolo MT5 → ticker Polygon
POLYGON_FX_MAP = {
    "EURUSD": "C:EURUSD", "GBPUSD": "C:GBPUSD",
    "USDJPY": "C:USDJPY", "AUDUSD": "C:AUDUSD",
    "USDCHF": "C:USDCHF", "USDCAD": "C:USDCAD",
    "NZDUSD": "C:NZDUSD", "EURGBP": "C:EURGBP",
}
POLYGON_STOCK_MAP = {
    "US500": "SPY", "US100": "QQQ",
    "GER40": "EWG", "UK100":  "EWU",
}


def polygon_get_bars(symbol: str, timespan: str = "minute",
                     multiplier: int = 5, days: int = 5) -> Optional[pd.DataFrame]:
    """
    Devolve OHLCV do Polygon para FX ou índices.
    timespan: 'minute','hour','day'  multiplier: N (ex: 5 min)
    """
    ticker = POLYGON_FX_MAP.get(symbol) or POLYGON_STOCK_MAP.get(symbol)
    if not ticker:
        return None

    date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    date_to   = datetime.now().strftime("%Y-%m-%d")

    url = (f"{POLYGON_BASE}/v2/aggs/ticker/{ticker}/range"
           f"/{multiplier}/{timespan}/{date_from}/{date_to}"
           f"?adjusted=true&sort=asc&limit=5000&apiKey={POLYGON_KEY}")

    def _fetch():
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            if data.get("resultsCount", 0) == 0:
                return None
            df = pd.DataFrame(data["results"])
            df["time"] = pd.to_datetime(df["t"], unit="ms")
            df = df.rename(columns={"o":"open","h":"high","l":"low","c":"close","v":"volume"})
            df.set_index("time", inplace=True)
            return df[["open","high","low","close","volume"]]
        except Exception as e:
            print(f"[Polygon] erro {symbol}: {e}")
            return None

    return _cached(f"poly_{symbol}_{timespan}{multiplier}", _fetch, ttl=30)


def polygon_get_last_price(symbol: str) -> Optional[float]:
    """Último preço real do Polygon (mais preciso que MT5 CFD)."""
    ticker = POLYGON_FX_MAP.get(symbol) or POLYGON_STOCK_MAP.get(symbol)
    if not ticker:
        return None

    def _fetch():
        try:
            url = f"{POLYGON_BASE}/v2/last/trade/{ticker}?apiKey={POLYGON_KEY}"
            r = requests.get(url, timeout=5)
            return r.json().get("results", {}).get("p")
        except:
            return None

    return _cached(f"poly_last_{symbol}", _fetch, ttl=5)


def polygon_get_spread_bbo(symbol: str) -> Optional[dict]:
    """Bid/Ask real do Polygon (melhor que MT5 CFD para FX)."""
    ticker = POLYGON_FX_MAP.get(symbol)
    if not ticker:
        return None

    def _fetch():
        try:
            url = f"{POLYGON_BASE}/v3/trades/{ticker}?limit=1&apiKey={POLYGON_KEY}"
            r = requests.get(url, timeout=5)
            results = r.json().get("results", [])
            if not results:
                return None
            return {"price": results[0].get("price")}
        except:
            return None

    return _cached(f"poly_bbo_{symbol}", _fetch, ttl=5)


# ══════════════════════════════════════════════════
#  ALPHA VANTAGE  — FX + stocks + crypto
# ══════════════════════════════════════════════════

AV_BASE = "https://www.alphavantage.co/query"

AV_FX_MAP = {
    "EURUSD": ("EUR","USD"), "GBPUSD": ("GBP","USD"),
    "USDJPY": ("USD","JPY"), "AUDUSD": ("AUD","USD"),
    "USDCHF": ("USD","CHF"), "USDCAD": ("USD","CAD"),
    "NZDUSD": ("NZD","USD"), "EURGBP": ("EUR","GBP"),
}


def av_get_fx_bars(symbol: str, interval: str = "5min",
                   outputsize: str = "full") -> Optional[pd.DataFrame]:
    """Barras FX intraday da Alpha Vantage."""
    pair = AV_FX_MAP.get(symbol)
    if not pair:
        return None

    def _fetch():
        try:
            params = {
                "function": "FX_INTRADAY",
                "from_symbol": pair[0], "to_symbol": pair[1],
                "interval": interval, "outputsize": outputsize,
                "apikey": ALPHA_VANTAGE_KEY,
            }
            r = requests.get(AV_BASE, params=params, timeout=15)
            data = r.json()
            key = f"Time Series FX ({interval})"
            if key not in data:
                return None
            df = pd.DataFrame(data[key]).T
            df.index = pd.to_datetime(df.index)
            df = df.rename(columns={
                "1. open":"open","2. high":"high",
                "3. low":"low","4. close":"close"
            }).astype(float).sort_index()
            return df
        except Exception as e:
            print(f"[AlphaVantage] erro {symbol}: {e}")
            return None

    return _cached(f"av_{symbol}_{interval}", _fetch, ttl=60)


def av_get_fx_daily(symbol: str) -> Optional[pd.DataFrame]:
    """Barras diárias FX — útil para correlações de longo prazo."""
    pair = AV_FX_MAP.get(symbol)
    if not pair:
        return None

    def _fetch():
        try:
            params = {
                "function": "FX_DAILY",
                "from_symbol": pair[0], "to_symbol": pair[1],
                "outputsize": "full", "apikey": ALPHA_VANTAGE_KEY,
            }
            r = requests.get(AV_BASE, params=params, timeout=15)
            data = r.json()
            if "Time Series FX (Daily)" not in data:
                return None
            df = pd.DataFrame(data["Time Series FX (Daily)"]).T
            df.index = pd.to_datetime(df.index)
            df = df.rename(columns={
                "1. open":"open","2. high":"high",
                "3. low":"low","4. close":"close"
            }).astype(float).sort_index()
            return df
        except Exception as e:
            print(f"[AV Daily] erro {symbol}: {e}")
            return None

    return _cached(f"av_daily_{symbol}", _fetch, ttl=3600)


# ══════════════════════════════════════════════════
#  FRED  — dados macro (taxas, inflação, emprego)
# ══════════════════════════════════════════════════

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Séries macro úteis para contexto de arbitragem
FRED_SERIES = {
    "USD_RATE":     "FEDFUNDS",      # taxa Fed Funds
    "EUR_RATE":     "ECBDFR",        # taxa BCE deposit facility
    "US_CPI":       "CPIAUCSL",      # inflação US
    "US_UNEMP":     "UNRATE",        # desemprego US
    "VIX":          "VIXCLS",        # volatilidade implícita S&P
    "US10Y":        "DGS10",         # yield 10 anos US
    "DE10Y":        "IRLTLT01DEM156N", # yield 10 anos Alemanha
    "USD_INDEX":    "DTWEXBGS",      # USD index broad
    "OIL_WTI":      "DCOILWTICO",    # petróleo WTI
    "GOLD":         "GOLDPMGBD228NLBM", # ouro (London PM fix)
}


def fred_get_series(series_id: str, periods: int = 60) -> Optional[pd.Series]:
    """Devolve série temporal FRED (últimos N períodos)."""
    def _fetch():
        try:
            params = {
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": periods,
            }
            r = requests.get(FRED_BASE, params=params, timeout=10)
            obs = r.json().get("observations", [])
            if not obs:
                return None
            s = pd.Series(
                {o["date"]: float(o["value"]) for o in obs
                 if o["value"] != "."}
            )
            s.index = pd.to_datetime(s.index)
            return s.sort_index()
        except Exception as e:
            print(f"[FRED] erro {series_id}: {e}")
            return None

    return _cached(f"fred_{series_id}", _fetch, ttl=3600)


def fred_get_macro_context() -> dict:
    """Snapshot macro rápido — para filtrar trades em ambientes adversos."""
    result = {}
    for name, sid in FRED_SERIES.items():
        s = fred_get_series(sid, periods=2)
        if s is not None and len(s) > 0:
            result[name] = float(s.iloc[-1])
    return result


def fred_get_rate_differential(ccy1: str, ccy2: str) -> Optional[float]:
    """
    Diferencial de taxas entre duas moedas.
    Útil para filtrar trades contra o carry trade dominante.
    Exemplo: fred_get_rate_differential('USD', 'EUR')
    """
    rate_map = {
        "USD": "FEDFUNDS",
        "EUR": "ECBDFR",
        "GBP": "IUDSOIA",   # SONIA overnight
        "JPY": "IRSTCI01JPM156N",
        "AUD": "IRSTCI01AUM156N",
        "CHF": "IRSTCI01CHM156N",
    }
    s1_id = rate_map.get(ccy1)
    s2_id = rate_map.get(ccy2)
    if not s1_id or not s2_id:
        return None

    s1 = fred_get_series(s1_id, periods=1)
    s2 = fred_get_series(s2_id, periods=1)
    if s1 is None or s2 is None:
        return None
    return float(s1.iloc[-1]) - float(s2.iloc[-1])


# ══════════════════════════════════════════════════
#  NEWSAPI  — sentimento de mercado
# ══════════════════════════════════════════════════

NEWSAPI_BASE = "https://newsapi.org/v2/everything"

SYMBOL_KEYWORDS = {
    "EURUSD": "EUR USD euro dollar ECB Fed",
    "GBPUSD": "GBP USD pound sterling Bank of England",
    "USDJPY": "USD JPY yen Bank of Japan BOJ Fed",
    "AUDUSD": "AUD USD australian dollar RBA",
    "USDCHF": "USD CHF swiss franc SNB",
    "US500":  "S&P 500 SPX stock market Fed",
    "US100":  "Nasdaq QQQ tech stocks",
    "GER40":  "DAX Germany ECB euro",
}


def news_get_sentiment(symbol: str, hours: int = 6) -> dict:
    """
    Conta artigos positivos vs negativos sobre um símbolo.
    Retorna: {'positive': N, 'negative': N, 'total': N, 'score': -1..1}
    score > 0.3 → sentimento positivo
    score < -0.3 → sentimento negativo
    """
    keywords = SYMBOL_KEYWORDS.get(symbol, symbol)
    from_dt  = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")

    def _fetch():
        try:
            params = {
                "q": keywords, "from": from_dt,
                "language": "en", "sortBy": "publishedAt",
                "pageSize": 20, "apiKey": NEWSAPI_KEY,
            }
            r = requests.get(NEWSAPI_BASE, params=params, timeout=10)
            articles = r.json().get("articles", [])

            pos_words = ["rise","gain","surge","rally","bull","strong","beat","recovery","up"]
            neg_words = ["fall","drop","decline","crash","bear","weak","miss","recession","down"]

            pos, neg = 0, 0
            for a in articles:
                text = ((a.get("title") or "") + " " + (a.get("description") or "")).lower()
                p = sum(1 for w in pos_words if w in text)
                n = sum(1 for w in neg_words if w in text)
                if p > n: pos += 1
                elif n > p: neg += 1

            total = len(articles)
            score = (pos - neg) / total if total > 0 else 0.0
            return {"positive": pos, "negative": neg, "total": total, "score": round(score, 3)}
        except Exception as e:
            print(f"[NewsAPI] erro {symbol}: {e}")
            return {"positive": 0, "negative": 0, "total": 0, "score": 0.0}

    return _cached(f"news_{symbol}_{hours}h", _fetch, ttl=600)


# ══════════════════════════════════════════════════
#  UTILITÁRIOS COMBINADOS
# ══════════════════════════════════════════════════

def get_best_price_source(symbol: str, mt5_price: float) -> dict:
    """
    Compara preço MT5 com Polygon. Devolve a melhor fonte e o desvio.
    Útil para detectar spikes ou spreads anómalos no CFD.
    """
    poly_price = polygon_get_last_price(symbol)

    result = {
        "mt5":      mt5_price,
        "polygon":  poly_price,
        "deviation": None,
        "best":     mt5_price,
        "source":   "mt5",
    }

    if poly_price and mt5_price:
        dev = abs(mt5_price - poly_price) / poly_price
        result["deviation"] = round(dev, 6)
        # Se desvio > 0.5% → usar Polygon como referência
        if dev > 0.005:
            result["best"]   = poly_price
            result["source"] = "polygon"
        else:
            result["best"]   = mt5_price
            result["source"] = "mt5"

    return result


def get_enriched_bars(symbol: str, timeframe: str = "M5",
                      use_polygon: bool = True) -> Optional[pd.DataFrame]:
    """
    Tenta obter barras do Polygon primeiro (mais precisas).
    Fallback automático para MT5 se Polygon falhar.
    """
    import src.mt5_connector as mt5c
    import config.settings as cfg

    if use_polygon:
        tf_map = {"M1":("minute",1),"M5":("minute",5),"M15":("minute",15),
                  "M30":("minute",30),"H1":("hour",1),"H4":("hour",4),"D1":("day",1)}
        ts, mult = tf_map.get(timeframe, ("minute", 5))
        df = polygon_get_bars(symbol, ts, mult, days=10)
        if df is not None and len(df) > 50:
            return df

    # Fallback MT5
    needed = max(cfg.MA_PERIOD, cfg.STDDEV_PERIOD, cfg.ATR_PERIOD, cfg.ATR_BASE_PERIOD) + 10
    return mt5c.get_bars(symbol, timeframe, needed)
