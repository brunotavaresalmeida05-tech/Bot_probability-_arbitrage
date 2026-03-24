"""
src/macro_engine.py
Macro Intelligence Engine — 7 camadas de análise global.

Camada 1: Carry Trade        — diferenciais de juros por par FX
Camada 2: Bonds/Yields       — curva de rendimentos 2Y/10Y/30Y, inversão
Camada 3: Políticas monetárias — stance Fed/BCE/BOJ/BOE/RBA
Camada 4: DXY / força relativa — cesta USD sintética, RSI de moedas
Camada 5: Notícias/sentimento — NLP score por activo
Camada 6: Correlações sectores — equity/bonds/FX/commodities
Camada 7: Divergências        — pares, cross-asset, rolling beta

Saída: MacroContext por símbolo com score -1.0 a +1.0
  score > +0.3  → macro favorável ao trade
  score < -0.3  → macro adverso → bloqueia ou reduz lot
  |score| < 0.3 → neutro → usa só sinais técnicos
"""

import requests
import pandas as pd
import numpy as np
import threading
import time
from datetime import datetime, timedelta
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg

# ── Cache global ─────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()

def _get_cache(key: str, ttl: int = 3600):
    with _cache_lock:
        if key in _cache:
            if time.time() - _cache[key]["ts"] < ttl:
                return _cache[key]["data"]
    return None

def _set_cache(key: str, data):
    with _cache_lock:
        _cache[key] = {"ts": time.time(), "data": data}

def _fetch_json(url: str, params: dict = None, ttl: int = 3600) -> Optional[dict]:
    key = url + str(sorted((params or {}).items()))
    cached = _get_cache(key, ttl)
    if cached is not None:
        return cached
    try:
        r = requests.get(url, params=params, timeout=12)
        data = r.json()
        _set_cache(key, data)
        return data
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
#  CAMADA 1 — CARRY TRADE
#  Diferencial de taxas entre duas moedas de um par FX
#  Score: positivo se carry favorece a moeda base
# ═══════════════════════════════════════════════════════════════

# Taxas de juro de referência por moeda (FRED series IDs)
RATE_SERIES = {
    "USD": "FEDFUNDS",          # Fed Funds Rate
    "EUR": "ECBDFR",            # BCE Deposit Facility Rate
    "GBP": "IUDSOIA",           # SONIA overnight UK
    "JPY": "IRSTCI01JPM156N",   # BOJ rate
    "AUD": "IRSTCI01AUM156N",   # RBA rate
    "CHF": "IRSTCI01CHM156N",   # SNB rate
    "CAD": "IRSTCI01CAM156N",   # BOC rate
    "NZD": "IRSTCI01NZM156N",   # RBNZ rate
}

def get_policy_rate(currency: str) -> Optional[float]:
    """Taxa de política monetária actual para uma moeda."""
    series_id = RATE_SERIES.get(currency)
    if not series_id or not cfg.FRED_API_KEY:
        return None
    data = _fetch_json(
        "https://api.stlouisfed.org/fred/series/observations",
        {"series_id": series_id, "api_key": cfg.FRED_API_KEY,
         "file_type": "json", "sort_order": "desc", "limit": 1},
        ttl=86400
    )
    if not data or "observations" not in data:
        return None
    obs = [o for o in data["observations"] if o["value"] != "."]
    return float(obs[0]["value"]) if obs else None


def compute_carry_score(symbol: str) -> dict:
    """
    Score de carry trade para um par FX.
    Positivo → posição long na moeda base é favorecida pelo carry.
    Negativo → posição short na moeda base é favorecida.
    """
    result = {"score": 0.0, "rate_base": None, "rate_quote": None,
              "differential": None, "signal": None}

    # Índices e metais não têm carry trade FX
    NON_FX = {"Usa500", "US500", "US100", "Ger40", "GER40", "UK100",
              "GOLD", "SILVER", "XAUUSD", "XAGUSD"}
    if symbol in NON_FX or len(symbol) < 6:
        return result

    base  = symbol[:3].upper()
    quote = symbol[3:6].upper()

    r_base  = get_policy_rate(base)
    r_quote = get_policy_rate(quote)

    if r_base is None or r_quote is None:
        return result

    diff = r_base - r_quote
    result.update({
        "rate_base":    r_base,
        "rate_quote":   r_quote,
        "differential": round(diff, 4),
    })

    # Normalizar: cada 1% de diferencial = 0.2 de score (cap ±1.0)
    score = np.clip(diff * 0.2, -1.0, 1.0)
    result["score"]  = round(float(score), 4)
    result["signal"] = "BUY_BASE" if score > 0.2 else ("SELL_BASE" if score < -0.2 else "NEUTRAL")
    return result


# ═══════════════════════════════════════════════════════════════
#  CAMADA 2 — BONDS E YIELDS
#  Curva de rendimentos: 2Y, 10Y, 30Y
#  Inversão 2Y-10Y = sinal de recessão → risk-off
# ═══════════════════════════════════════════════════════════════

YIELD_SERIES = {
    "US2Y":   "DGS2",
    "US10Y":  "DGS10",
    "US30Y":  "DGS30",
    "DE10Y":  "IRLTLT01DEM156N",
    "JP10Y":  "IRLTLT01JPM156N",
    "GB10Y":  "IRLTLT01GBM156N",
}

def get_yield_curve() -> dict:
    """Devolve yields actuais e spread 2Y-10Y."""
    result = {}
    for name, sid in YIELD_SERIES.items():
        data = _fetch_json(
            "https://api.stlouisfed.org/fred/series/observations",
            {"series_id": sid, "api_key": cfg.FRED_API_KEY,
             "file_type": "json", "sort_order": "desc", "limit": 5},
            ttl=86400
        )
        if data and "observations" in data:
            obs = [o for o in data["observations"] if o["value"] != "."]
            if obs:
                result[name] = float(obs[0]["value"])

    # Calcular spread e inversão
    if "US2Y" in result and "US10Y" in result:
        result["SPREAD_2Y10Y"] = round(result["US10Y"] - result["US2Y"], 4)
        result["INVERTED"]     = result["SPREAD_2Y10Y"] < 0

    return result


def compute_yield_score(symbol: str, yield_data: dict) -> dict:
    """
    Score baseado na curva de yields.
    Curva invertida → risk-off → prejudica pares de risco (AUD, NZD, EM)
    """
    score  = 0.0
    reason = []

    spread = yield_data.get("SPREAD_2Y10Y")
    if spread is not None:
        if spread < -0.5:
            score -= 0.4
            reason.append(f"inversão profunda ({spread:.2f}%) → risk-off")
        elif spread < 0:
            score -= 0.2
            reason.append(f"curva invertida ({spread:.2f}%)")
        elif spread > 1.5:
            score += 0.2
            reason.append(f"curva normal ({spread:.2f}%) → risk-on")

    # USDJPY específico: correlação forte com US10Y
    if "USDJPY" in symbol:
        us10y = yield_data.get("US10Y", 0)
        if us10y > 4.5:
            score += 0.3
            reason.append(f"US10Y={us10y:.2f}% → suporte USDJPY")
        elif us10y < 3.5:
            score -= 0.3
            reason.append(f"US10Y={us10y:.2f}% → pressão USDJPY")

    return {
        "score":  round(np.clip(score, -1.0, 1.0), 4),
        "data":   yield_data,
        "reason": " | ".join(reason),
    }


# ═══════════════════════════════════════════════════════════════
#  CAMADA 3 — POLÍTICAS MONETÁRIAS
#  Stance hawkish/dovish de cada banco central
#  Fontes: FRED + feeds RSS dos bancos centrais (grátis)
# ═══════════════════════════════════════════════════════════════

# Desvio entre taxa actual e "neutral rate" estimada (proxy simples)
CB_NEUTRAL_RATES = {
    "USD": 2.5,   # Fed neutral estimado
    "EUR": 2.0,
    "GBP": 3.0,
    "JPY": 0.1,
    "AUD": 3.0,
    "CHF": 1.0,
    "CAD": 2.5,
    "NZD": 3.0,
}

def compute_cb_stance(currency: str) -> dict:
    """
    Stance do banco central: hawkish (+) ou dovish (-).
    Baseado no desvio entre taxa actual e taxa neutral estimada.
    """
    rate    = get_policy_rate(currency)
    neutral = CB_NEUTRAL_RATES.get(currency, 2.0)

    if rate is None:
        return {"stance": "unknown", "score": 0.0, "rate": None}

    deviation = rate - neutral

    # Hawkish: taxa > neutral → moeda tende a apreciar
    # Dovish:  taxa < neutral → moeda tende a depreciar
    score = np.clip(deviation * 0.15, -1.0, 1.0)

    stance = ("hawkish" if deviation > 0.5
              else "dovish" if deviation < -0.5
              else "neutral")

    return {
        "stance":    stance,
        "score":     round(float(score), 4),
        "rate":      rate,
        "neutral":   neutral,
        "deviation": round(deviation, 4),
    }


def compute_monetary_score(symbol: str) -> dict:
    """Score de política monetária para um par FX."""
    NON_FX = {"Usa500", "US500", "US100", "Ger40", "GER40", "UK100",
              "GOLD", "SILVER", "XAUUSD", "XAGUSD"}
    if symbol in NON_FX or len(symbol) < 6:
        return {"score": 0.0}

    base  = symbol[:3].upper()
    quote = symbol[3:6].upper()

    base_cb  = compute_cb_stance(base)
    quote_cb = compute_cb_stance(quote)

    # Score relativo: base hawkish vs quote dovish → BUY base
    score = base_cb["score"] - quote_cb["score"]
    score = round(np.clip(score, -1.0, 1.0), 4)

    return {
        "score":       score,
        "base_stance": base_cb.get("stance"),
        "quote_stance": quote_cb.get("stance"),
        "base_rate":   base_cb.get("rate"),
        "quote_rate":  quote_cb.get("rate"),
    }


# ═══════════════════════════════════════════════════════════════
#  CAMADA 4 — DXY E FORÇA RELATIVA DE MOEDAS
#  DXY sintético calculado a partir dos pares FX
#  RSI de 14 períodos sobre as moedas principais
# ═══════════════════════════════════════════════════════════════

# Pesos do DXY real (aprox.)
DXY_WEIGHTS = {
    "EURUSD": -0.576,   # negativo porque EUR/USD (USD denominador)
    "USDJPY": +0.136,
    "GBPUSD": -0.119,
    "USDCAD": +0.091,
    "USDSEK": +0.042,
    "USDCHF": +0.036,
}

def compute_synthetic_dxy(prices: dict) -> Optional[float]:
    """
    Calcula DXY sintético a partir dos preços actuais.
    Valores > 105 = USD muito forte
    Valores < 95  = USD fraco
    """
    dxy_base = 100.0
    score    = 0.0
    count    = 0

    for pair, weight in DXY_WEIGHTS.items():
        price = prices.get(pair)
        if price and price > 0:
            # Contribuição normalizada
            score += weight * price
            count += 1

    if count < 3:
        return None

    return round(dxy_base + score * 10, 2)


def compute_currency_rsi(symbol: str, bars_df) -> Optional[float]:
    """RSI de 14 períodos sobre os retornos da moeda."""
    if bars_df is None or len(bars_df) < 16:
        return None
    close  = bars_df["close"]
    delta  = close.diff()
    gain   = delta.clip(lower=0).rolling(14).mean()
    loss   = (-delta.clip(upper=0)).rolling(14).mean()
    rs     = gain / loss.replace(0, np.nan)
    rsi    = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else None


def compute_dxy_score(symbol: str, prices: dict) -> dict:
    """
    Score baseado na força do USD via DXY sintético.
    USD forte → pressão sobre pares como EURUSD, GBPUSD, AUDUSD
    """
    dxy   = compute_synthetic_dxy(prices)
    score = 0.0
    reason = []

    if dxy:
        if dxy > 105:
            score = -0.4   # USD muito forte → EURUSD/GBPUSD/AUDUSD sofrem
            reason.append(f"DXY={dxy:.1f} → USD dominante")
        elif dxy > 102:
            score = -0.2
            reason.append(f"DXY={dxy:.1f} → USD forte")
        elif dxy < 97:
            score = +0.3
            reason.append(f"DXY={dxy:.1f} → USD fraco")
        elif dxy < 100:
            score = +0.1
            reason.append(f"DXY={dxy:.1f} → USD moderado")

    # Inverter para pares onde USD é moeda base (USDJPY, USDCHF, USDCAD)
    # Índices e metais: USD forte → pressão sobre GOLD; neutro para Usa500
    NON_FX = {"Usa500", "US500", "US100", "Ger40", "GER40", "UK100",
              "GOLD", "SILVER", "XAUUSD", "XAGUSD"}
    if symbol in ("GOLD", "XAUUSD", "SILVER", "XAGUSD"):
        pass  # DXY forte → negativo para ouro/prata (manter score como está)
    elif symbol in NON_FX:
        score = score * 0.3  # impacto reduzido em índices
    elif symbol[:3].upper() == "USD":
        score = -score

    return {
        "score":  round(np.clip(score, -1.0, 1.0), 4),
        "dxy":    dxy,
        "reason": " | ".join(reason),
    }


# ═══════════════════════════════════════════════════════════════
#  CAMADA 5 — NOTÍCIAS E SENTIMENTO
#  NLP score por activo usando múltiplas fontes gratuitas
#  NewsAPI + GNews + feeds RSS oficiais (Fed, ECB, BOJ)
# ═══════════════════════════════════════════════════════════════

# Keywords por símbolo/moeda
SYMBOL_KEYWORDS = {
    "EURUSD": ["EUR USD", "euro dollar", "ECB rate", "Fed decision"],
    "GBPUSD": ["GBP USD", "pound sterling", "Bank of England", "BOE"],
    "USDJPY": ["USD JPY", "yen dollar", "Bank of Japan", "BOJ", "intervention"],
    "AUDUSD": ["AUD USD", "australian dollar", "RBA rate", "China trade"],
    "USDCHF": ["USD CHF", "swiss franc", "SNB", "safe haven"],
    "USDCAD": ["USD CAD", "canadian dollar", "BOC", "oil price"],
    "XAUUSD": ["gold price", "gold USD", "safe haven", "inflation"],
    "GOLD":   ["gold price", "gold USD", "safe haven", "inflation"],
    "SILVER": ["silver price", "silver USD", "precious metals"],
    "US500":  ["S&P 500", "SPX", "Fed rate", "US economy", "earnings"],
    "Usa500": ["S&P 500", "SPX", "Fed rate", "US economy", "earnings"],
    "US100":  ["Nasdaq", "tech stocks", "Fed rate", "AI earnings"],
    "GER40":  ["DAX", "Germany GDP", "ECB", "euro zone"],
    "Ger40":  ["DAX", "Germany GDP", "ECB", "euro zone"],
    "UK100":  ["FTSE", "UK economy", "Bank of England", "pound"],
}

POSITIVE_WORDS = [
    "rise","gain","surge","rally","beat","strong","bullish","recovery",
    "hawkish","hike","growth","accelerate","outperform","positive","upgrade"
]
NEGATIVE_WORDS = [
    "fall","drop","decline","crash","miss","weak","bearish","recession",
    "dovish","cut","slowdown","disappoint","underperform","negative","downgrade"
]


def fetch_gnews(symbol: str, hours: int = 12) -> list:
    """GNews API — completamente gratuito, sem registo necessário."""
    keywords = SYMBOL_KEYWORDS.get(symbol, [symbol[:6]])
    query    = " OR ".join(f'"{kw}"' for kw in keywords[:2])

    data = _fetch_json(
        "https://gnews.io/api/v4/search",
        {"q": query, "lang": "en", "max": 10,
         "apikey": cfg.GNEWS_API_KEY if hasattr(cfg, "GNEWS_API_KEY") else ""},
        ttl=600
    )
    if data and "articles" in data:
        return data["articles"]
    return []


def fetch_newsapi(symbol: str, hours: int = 12) -> list:
    """NewsAPI — 100 req/dia grátis."""
    keywords = SYMBOL_KEYWORDS.get(symbol, [symbol])
    query    = " OR ".join(keywords[:2])
    from_dt  = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")

    data = _fetch_json(
        "https://newsapi.org/v2/everything",
        {"q": query, "from": from_dt, "language": "en",
         "sortBy": "publishedAt", "pageSize": 10,
         "apiKey": cfg.NEWSAPI_KEY},
        ttl=600
    )
    if data and data.get("status") == "ok":
        return data.get("articles", [])
    return []


def compute_news_score(symbol: str) -> dict:
    """Score de sentimento via NLP simples."""
    articles = fetch_newsapi(symbol, 12)
    if not articles:
        articles = fetch_gnews(symbol, 12)

    pos, neg, total = 0, 0, len(articles)
    headlines = []

    for a in articles:
        text = ((a.get("title") or "") + " " + (a.get("description") or "")).lower()
        p    = sum(1 for w in POSITIVE_WORDS if w in text)
        n    = sum(1 for w in NEGATIVE_WORDS if w in text)
        if p > n:    pos += 1
        elif n > p:  neg += 1
        if a.get("title"):
            headlines.append(a["title"][:80])

    score = (pos - neg) / total if total > 0 else 0.0

    return {
        "score":     round(np.clip(score * 0.8, -1.0, 1.0), 4),
        "positive":  pos,
        "negative":  neg,
        "total":     total,
        "headlines": headlines[:3],
    }


# ═══════════════════════════════════════════════════════════════
#  CAMADA 6 — CORRELAÇÕES DE SECTORES E ACTIVOS
#  Matriz de correlação: FX vs equities vs bonds vs commodities
#  Fontes: Yahoo Finance via yfinance (grátis) ou Stooq
# ═══════════════════════════════════════════════════════════════

# Activos de referência por classe (tickers Stooq/Yahoo)
BENCHMARK_TICKERS = {
    "SPY":   "equities_us",       # S&P 500 ETF
    "GLD":   "gold",              # Ouro ETF
    "TLT":   "bonds_long",        # Treasury 20Y+ ETF
    "SHY":   "bonds_short",       # Treasury 1-3Y ETF
    "UUP":   "dxy_etf",           # USD Index ETF
    "USO":   "oil",               # Oil ETF
    "VXX":   "volatility",        # VIX ETF
}

# Mapa símbolo FX → activos correlacionados
SYMBOL_CORRELATIONS = {
    "AUDUSD": ["GLD", "SPY", "USO"],   # AUD correlaciona com commodities/risco
    "USDJPY": ["TLT", "SPY"],          # JPY é safe haven; correlaciona com yields
    "EURUSD": ["SPY", "UUP"],          # EUR vs USD força
    "GBPUSD": ["SPY", "UUP"],
    "USDCHF": ["GLD", "VXX"],          # CHF é safe haven
    "XAUUSD": ["TLT", "VXX", "UUP"],  # Ouro vs yields vs USD
}


def fetch_stooq_close(ticker: str, days: int = 30) -> Optional[pd.Series]:
    """Obtém preços históricos via Stooq (100% grátis, sem API key)."""
    end   = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days + 5)).strftime("%Y%m%d")

    # Stooq suporta alguns tickers americanos
    stooq_map = {
        "SPY": "spy.us", "GLD": "gld.us", "TLT": "tlt.us",
        "SHY": "shy.us", "UUP": "uup.us", "USO": "uso.us",
    }
    stooq_ticker = stooq_map.get(ticker, ticker.lower() + ".us")

    data = _fetch_json(
        f"https://stooq.com/q/d/l/?s={stooq_ticker}&d1={start}&d2={end}&i=d",
        ttl=86400
    )
    # Stooq retorna CSV, não JSON — tratamento especial
    try:
        import io
        r = requests.get(
            f"https://stooq.com/q/d/l/?s={stooq_ticker}&d1={start}&d2={end}&i=d",
            timeout=10
        )
        df = pd.read_csv(io.StringIO(r.text))
        if "Close" in df.columns and len(df) > 5:
            df["Date"] = pd.to_datetime(df["Date"])
            df.set_index("Date", inplace=True)
            return df["Close"].sort_index()
    except Exception:
        pass
    return None


def compute_sector_correlation(symbol: str, fx_bars: pd.DataFrame) -> dict:
    """
    Correlação rolling entre o símbolo e benchmarks de classe de activos.
    """
    related = SYMBOL_CORRELATIONS.get(symbol, [])
    correlations = {}
    regime_signal = 0.0

    for ticker in related:
        bench = fetch_stooq_close(ticker, 30)
        if bench is None or fx_bars is None:
            continue

        fx_close = fx_bars["close"]
        aligned  = pd.concat([fx_close, bench], axis=1, join="inner").dropna()
        if len(aligned) < 10:
            continue

        corr = aligned.iloc[:, 0].pct_change().corr(aligned.iloc[:, 1].pct_change())
        correlations[ticker] = round(float(corr), 4) if not np.isnan(corr) else None

        # Lógica de regime:
        # SPY a subir + correlação positiva com FX → risk-on → favorece AUD, NZD
        # VXX a subir (volatilidade) → risk-off → favorece JPY, CHF
        if ticker in ("SPY", "GLD") and corr and corr > 0.3:
            regime_signal += 0.2
        elif ticker == "VXX" and corr and corr > 0.3:
            regime_signal -= 0.3  # vol alta → risk-off

    return {
        "score":        round(np.clip(regime_signal, -1.0, 1.0), 4),
        "correlations": correlations,
    }


# ═══════════════════════════════════════════════════════════════
#  CAMADA 7 — DIVERGÊNCIAS E CONVERGÊNCIAS
#  Rolling beta, cointegração, divergências cross-asset
# ═══════════════════════════════════════════════════════════════

def compute_divergence_score(symbol: str, all_bars: dict) -> dict:
    """
    Detecta divergências entre activos correlacionados.
    Ex: EURUSD e GBPUSD divergem → um vai convergir para o outro.
    """
    correlations = {
        "EURUSD": ["GBPUSD", "AUDUSD"],
        "GBPUSD": ["EURUSD", "AUDUSD"],
        "AUDUSD": ["NZDUSD", "GBPUSD"],
        "USDJPY": ["USDCHF"],
    }

    related = correlations.get(symbol, [])
    divergences = []
    score = 0.0

    df_a = all_bars.get(symbol)
    if df_a is None or len(df_a) < 20:
        return {"score": 0.0, "divergences": []}

    for rel in related:
        df_b = all_bars.get(rel)
        if df_b is None or len(df_b) < 20:
            continue

        ret_a = df_a["close"].pct_change().dropna()
        ret_b = df_b["close"].pct_change().dropna()
        aligned = pd.concat([ret_a, ret_b], axis=1, join="inner").dropna()

        if len(aligned) < 15:
            continue

        # Rolling correlation (últimas 20 barras)
        roll_corr = aligned.iloc[:, 0].rolling(15).corr(aligned.iloc[:, 1])
        curr_corr = float(roll_corr.iloc[-1]) if not roll_corr.empty else 0.0

        # Correlação histórica (full window)
        hist_corr = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))

        # Divergência: correlação atual muito diferente da histórica
        divergence = hist_corr - curr_corr
        if abs(divergence) > 0.3:
            divergences.append({
                "pair":      f"{symbol}/{rel}",
                "hist_corr": round(hist_corr, 4),
                "curr_corr": round(curr_corr, 4),
                "divergence": round(divergence, 4),
            })
            # Divergência → oportunidade de convergência
            score += 0.15 * np.sign(divergence)

    return {
        "score":       round(np.clip(score, -1.0, 1.0), 4),
        "divergences": divergences,
    }


# ═══════════════════════════════════════════════════════════════
#  COMBINADOR — MACRO SCORE FINAL
# ═══════════════════════════════════════════════════════════════

# Pesos de cada camada no score final
LAYER_WEIGHTS = {
    "carry":    0.25,   # Camada 1 — mais importante
    "yields":   0.20,   # Camada 2
    "monetary": 0.20,   # Camada 3
    "dxy":      0.15,   # Camada 4
    "news":     0.10,   # Camada 5
    "sector":   0.05,   # Camada 6
    "divergence":0.05,  # Camada 7
}


def compute_macro_context(
    symbol: str,
    bars: pd.DataFrame = None,
    all_bars: dict = None,
    prices: dict = None,
) -> dict:
    """
    Calcula o contexto macro completo para um símbolo.
    Retorna MacroContext com score -1.0 a +1.0 e detalhes por camada.
    """
    ctx = {
        "symbol":    symbol,
        "timestamp": datetime.now().isoformat(),
        "layers":    {},
        "score":     0.0,
        "regime":    "neutral",
        "lot_multiplier": 1.0,
        "trade_allowed":  True,
        "reason":    [],
    }

    try:
        # Camada 1: Carry
        carry = compute_carry_score(symbol)
        ctx["layers"]["carry"] = carry

        # Camada 2: Yields
        yield_data = get_yield_curve()
        yields = compute_yield_score(symbol, yield_data)
        ctx["layers"]["yields"] = yields

        # Camada 3: Política monetária
        monetary = compute_monetary_score(symbol)
        ctx["layers"]["monetary"] = monetary

        # Camada 4: DXY
        dxy = compute_dxy_score(symbol, prices or {})
        ctx["layers"]["dxy"] = dxy

        # Camada 5: Notícias
        news = compute_news_score(symbol)
        ctx["layers"]["news"] = news

        # Camada 6: Correlações de sector
        sector = compute_sector_correlation(symbol, bars)
        ctx["layers"]["sector"] = sector

        # Camada 7: Divergências
        divergence = compute_divergence_score(symbol, all_bars or {})
        ctx["layers"]["divergence"] = divergence

        # Score final ponderado
        scores = {
            "carry":     carry.get("score", 0.0),
            "yields":    yields.get("score", 0.0),
            "monetary":  monetary.get("score", 0.0),
            "dxy":       dxy.get("score", 0.0),
            "news":      news.get("score", 0.0),
            "sector":    sector.get("score", 0.0),
            "divergence": divergence.get("score", 0.0),
        }

        total = sum(scores[k] * LAYER_WEIGHTS[k] for k in scores)
        ctx["score"] = round(float(np.clip(total, -1.0, 1.0)), 4)

        # Regime
        if ctx["score"] >= 0.3:
            ctx["regime"] = "risk_on"
            ctx["lot_multiplier"] = 1.0 + ctx["score"] * 0.5  # até 1.5x
        elif ctx["score"] <= -0.3:
            ctx["regime"] = "risk_off"
            ctx["lot_multiplier"] = max(0.3, 1.0 + ctx["score"])  # reduz até 0.7x
            if ctx["score"] <= -0.6:
                ctx["trade_allowed"] = False
                ctx["reason"].append(f"macro muito adverso (score={ctx['score']:.3f})")
        else:
            ctx["regime"] = "neutral"
            ctx["lot_multiplier"] = 1.0

        # Razões principais
        for layer, data in ctx["layers"].items():
            reason = data.get("reason") or data.get("signal") or ""
            if reason and reason not in ("NEUTRAL", "neutral", ""):
                ctx["reason"].append(f"{layer}: {str(reason)[:60]}")

    except Exception as e:
        ctx["error"] = str(e)

    return ctx


# ═══════════════════════════════════════════════════════════════
#  BACKGROUND REFRESH
# ═══════════════════════════════════════════════════════════════

_macro_store: dict = {}
_macro_lock  = threading.Lock()


def get_macro_context(symbol: str) -> dict:
    """Devolve o último contexto macro calculado (thread-safe)."""
    with _macro_lock:
        return _macro_store.get(symbol, {
            "score": 0.0, "regime": "neutral",
            "lot_multiplier": 1.0, "trade_allowed": True
        })


def start_macro_engine(symbols: list, all_bars_fn, prices_fn):
    """
    Lança o macro engine em background thread.
    Actualiza a cada MACRO_REFRESH_INTERVAL segundos.
    all_bars_fn: callable que devolve dict {symbol: df}
    prices_fn:   callable que devolve dict {symbol: price}
    """
    def _loop():
        while True:
            try:
                bars_dict  = all_bars_fn()
                price_dict = prices_fn()

                for sym in symbols:
                    df  = bars_dict.get(sym)
                    ctx = compute_macro_context(
                        sym,
                        bars=df,
                        all_bars=bars_dict,
                        prices=price_dict,
                    )
                    with _macro_lock:
                        _macro_store[sym] = ctx
            except Exception as e:
                pass  # não interrompe o bot

            interval = getattr(cfg, "MACRO_REFRESH_INTERVAL", 300)
            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True, name="macro_engine")
    t.start()
