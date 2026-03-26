"""
Multi-API Data Aggregator
TODAS as APIs gratuitas integradas: Binance, CoinGecko, CryptoCompare,
Alpha Vantage, Twelve Data, Fixer, Yahoo Finance, Polygon, NewsAPI,
Finnhub, CryptoPanic, Blockchain.com, Etherscan.
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import time
from typing import Dict, List, Optional


class MultiAPIAggregator:
    def __init__(self, config: dict):
        self.config = config

        # CACHE com TTL por categoria
        self.cache = {}
        self.cache_duration = {
            'price': 30,          # 30 segundos
            'volume': 60,         # 1 minuto
            'news': 300,          # 5 minutos
            'fundamentals': 3600, # 1 hora
            'onchain': 300,       # 5 minutos
            'calendar': 600,      # 10 minutos
            'orderbook': 15,      # 15 segundos
        }

    # ============================================================
    #  1. CRYPTO PRICES (3 fontes)
    # ============================================================

    def get_crypto_price_binance(self, symbol: str) -> Optional[float]:
        """Binance - GRATIS, sem key."""
        binance_symbol = self._to_binance(symbol)
        url = "https://api.binance.com/api/v3/ticker/price"

        try:
            resp = requests.get(url, params={'symbol': binance_symbol}, timeout=5)
            return float(resp.json()['price'])
        except Exception:
            return None

    def get_crypto_price_coingecko(self, symbol: str) -> Optional[float]:
        """CoinGecko - GRATIS, sem key."""
        coin_id = self._to_coingecko(symbol)
        url = "https://api.coingecko.com/api/v3/simple/price"

        try:
            resp = requests.get(url, params={'ids': coin_id, 'vs_currencies': 'usd'}, timeout=5)
            return float(resp.json()[coin_id]['usd'])
        except Exception:
            return None

    def get_crypto_price_cryptocompare(self, symbol: str) -> Optional[float]:
        """CryptoCompare - GRATIS, sem key."""
        base = symbol.upper().replace('USD', '').replace('USDT', '')
        url = "https://min-api.cryptocompare.com/data/price"

        try:
            resp = requests.get(url, params={'fsym': base, 'tsyms': 'USD'}, timeout=5)
            return float(resp.json()['USD'])
        except Exception:
            return None

    # ============================================================
    #  2. FOREX PRICES (3 fontes)
    # ============================================================

    def get_forex_price_alpha_vantage(self, symbol: str) -> Optional[float]:
        """Alpha Vantage - GRATIS 25 calls/dia."""
        key = self.config.get('alpha_vantage_key')
        if not key:
            return None

        from_cur = symbol[:3]
        to_cur = symbol[3:]

        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'CURRENCY_EXCHANGE_RATE',
            'from_currency': from_cur,
            'to_currency': to_cur,
            'apikey': key,
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            rate = data['Realtime Currency Exchange Rate']['5. Exchange Rate']
            return float(rate)
        except Exception:
            return None

    def get_forex_price_twelve_data(self, symbol: str) -> Optional[float]:
        """Twelve Data - GRATIS 800 calls/dia."""
        key = self.config.get('twelve_data_key')
        if not key:
            return None

        url = "https://api.twelvedata.com/price"
        params = {
            'symbol': f"{symbol[:3]}/{symbol[3:]}",
            'apikey': key,
        }

        try:
            resp = requests.get(url, params=params, timeout=5)
            return float(resp.json()['price'])
        except Exception:
            return None

    def get_forex_price_fixer(self, symbol: str) -> Optional[float]:
        """Fixer.io - GRATIS 100 calls/mes."""
        key = self.config.get('fixer_key')
        if not key:
            return None

        base = symbol[:3]
        target = symbol[3:]

        url = "http://data.fixer.io/api/latest"
        params = {
            'access_key': key,
            'base': base,
            'symbols': target,
        }

        try:
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()
            return float(data['rates'][target])
        except Exception:
            return None

    # ============================================================
    #  2b. EODHD (End of Day Historical Data)
    # ============================================================

    def get_eodhd_price(self, symbol: str) -> Optional[float]:
        """EODHD real-time price."""
        key = self.config.get('eodhd_key')
        if not key:
            return None

        url = f"https://eodhd.com/api/real-time/{symbol}"
        params = {
            'api_token': key,
            'fmt': 'json'
        }

        try:
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()
            return float(data['close'])
        except Exception:
            return None

    def get_eodhd_fundamentals(self, symbol: str) -> Dict:
        """EODHD fundamentals data."""
        key = self.config.get('eodhd_key')
        if not key:
            return {}

        url = f"https://eodhd.com/api/fundamentals/{symbol}"
        params = {'api_token': key}

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()

            highlights = data.get('Highlights', {})
            valuation = data.get('Valuation', {})

            return {
                'pe_ratio': highlights.get('PERatio'),
                'market_cap': highlights.get('MarketCapitalization'),
                'dividend_yield': highlights.get('DividendYield'),
                'eps': highlights.get('EarningsShare'),
                'price_to_book': valuation.get('PriceBookMRQ'),
                'revenue_per_share': highlights.get('RevenuePerShareTTM')
            }
        except Exception:
            return {}

    # ============================================================
    #  3. STOCKS PRICES (3 fontes)
    # ============================================================

    def get_stock_price_yahoo(self, symbol: str) -> Optional[float]:
        """Yahoo Finance - GRATIS."""
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}

        try:
            resp = requests.get(url, headers=headers, timeout=5)
            data = resp.json()
            return float(data['chart']['result'][0]['meta']['regularMarketPrice'])
        except Exception:
            return None

    def get_stock_price_polygon(self, symbol: str) -> Optional[float]:
        """Polygon.io - GRATIS 5 calls/min."""
        key = self.config.get('polygon_key')
        if not key:
            return None

        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev"
        params = {'apiKey': key}

        try:
            resp = requests.get(url, params=params, timeout=5)
            results = resp.json().get('results', [])
            return float(results[0]['c']) if results else None
        except Exception:
            return None

    # ============================================================
    #  4. VOLUME REAL
    # ============================================================

    def get_real_volume(self, symbol: str) -> Dict:
        """Volume real de multiplas fontes."""
        cache_key = f"volume_{symbol}"
        cached = self._cache_get(cache_key, 'volume')
        if cached is not None:
            return cached

        volume_data = {'total_volume': 0, 'sources': []}

        if self._is_crypto(symbol):
            binance_vol = self._get_binance_volume(symbol)
            if binance_vol:
                volume_data['sources'].append({'source': 'binance', 'volume': binance_vol})

            coingecko_vol = self._get_coingecko_volume(symbol)
            if coingecko_vol:
                volume_data['sources'].append({'source': 'coingecko', 'volume': coingecko_vol})

        elif self._is_stock(symbol):
            yahoo_vol = self._get_yahoo_volume(symbol)
            if yahoo_vol:
                volume_data['sources'].append({'source': 'yahoo', 'volume': yahoo_vol})

        if volume_data['sources']:
            volume_data['total_volume'] = float(np.mean(
                [s['volume'] for s in volume_data['sources']]
            ))

        self._cache_set(cache_key, volume_data, 'volume')
        return volume_data

    # ============================================================
    #  5. ORDER BOOK DEPTH (CRYPTO)
    # ============================================================

    def get_order_book(self, symbol: str, levels=20) -> Optional[Dict]:
        """Order book Binance."""
        if not self._is_crypto(symbol):
            return None

        cache_key = f"orderbook_{symbol}"
        cached = self._cache_get(cache_key, 'orderbook')
        if cached is not None:
            return cached

        binance_symbol = self._to_binance(symbol)
        url = "https://api.binance.com/api/v3/depth"

        try:
            resp = requests.get(url, params={'symbol': binance_symbol, 'limit': levels}, timeout=5)
            data = resp.json()

            bid_volume = sum(float(b[1]) for b in data['bids'])
            ask_volume = sum(float(a[1]) for a in data['asks'])
            total = bid_volume + ask_volume

            result = {
                'bids': data['bids'],
                'asks': data['asks'],
                'bid_volume': bid_volume,
                'ask_volume': ask_volume,
                'imbalance': (bid_volume - ask_volume) / total if total > 0 else 0,
                'spread': float(data['asks'][0][0]) - float(data['bids'][0][0]),
            }

            self._cache_set(cache_key, result, 'orderbook')
            return result
        except Exception:
            return None

    # ============================================================
    #  6. NEWS SENTIMENT (3 fontes)
    # ============================================================

    def get_news_sentiment(self, symbol: str, hours=24) -> Dict:
        """Sentiment de 6 fontes de noticias."""
        cache_key = f"news_{symbol}"
        cached = self._cache_get(cache_key, 'news')
        if cached is not None:
            return cached

        sentiments = []

        # NewsAPI
        if self.config.get('newsapi_key'):
            s = self._get_newsapi_sentiment(symbol, hours)
            if s is not None:
                sentiments.append({'source': 'newsapi', 'score': s})

        # Finnhub
        if self.config.get('finnhub_key'):
            s = self._get_finnhub_sentiment(symbol)
            if s is not None:
                sentiments.append({'source': 'finnhub', 'score': s})

        # MarketAux
        if self.config.get('marketaux_key'):
            s = self._get_marketaux_sentiment(symbol, hours)
            if s is not None:
                sentiments.append({'source': 'marketaux', 'score': s})

        # Currents
        if self.config.get('currents_key'):
            s = self._get_currents_sentiment(symbol, hours)
            if s is not None:
                sentiments.append({'source': 'currents', 'score': s})

        # MediaStack
        if self.config.get('mediastack_key'):
            s = self._get_mediastack_sentiment(symbol, hours)
            if s is not None:
                sentiments.append({'source': 'mediastack', 'score': s})

        # CryptoPanic (crypto only)
        if self._is_crypto(symbol) and self.config.get('cryptopanic_key'):
            s = self._get_cryptopanic_sentiment(symbol)
            if s is not None:
                sentiments.append({'source': 'cryptopanic', 'score': s})

        # Calcular media ponderada
        if sentiments:
            scores = [s['score'] for s in sentiments]
            avg_score = float(np.mean(scores))
            std_score = float(np.std(scores))

            if std_score < 0.2:
                confidence = 1.0
            elif std_score < 0.4:
                confidence = 0.8
            else:
                confidence = 0.6
        else:
            avg_score = 0.0
            confidence = 0.0

        result = {
            'score': avg_score,
            'confidence': confidence,
            'sources_count': len(sentiments),
            'sources': sentiments,
            'recommendation': ('STRONG_BULLISH' if avg_score > 0.5 else
                               'BULLISH' if avg_score > 0.2 else
                               'NEUTRAL' if abs(avg_score) <= 0.2 else
                               'BEARISH' if avg_score > -0.5 else
                               'STRONG_BEARISH'),
        }

        self._cache_set(cache_key, result, 'news')
        return result

    def _get_newsapi_sentiment(self, symbol: str, hours: int) -> Optional[float]:
        """NewsAPI sentiment."""
        query = self._symbol_to_query(symbol)
        url = "https://newsapi.org/v2/everything"

        params = {
            'q': query,
            'apiKey': self.config['newsapi_key'],
            'language': 'en',
            'sortBy': 'publishedAt',
            'from': (datetime.now() - timedelta(hours=hours)).isoformat(),
            'pageSize': 20,
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            articles = resp.json().get('articles', [])

            positive = ['surge', 'rally', 'gain', 'rise', 'bullish',
                        'growth', 'breakthrough', 'soar', 'spike']
            negative = ['crash', 'fall', 'drop', 'bear', 'decline',
                        'loss', 'plunge', 'slump', 'tumble']

            score = 0
            for article in articles:
                text = ((article.get('title', '') or '') + ' ' +
                        (article.get('description', '') or '')).lower()
                for w in positive:
                    score += text.count(w) * 2
                for w in negative:
                    score -= text.count(w) * 2

            if len(articles) > 0:
                return max(-1.0, min(1.0, score / (len(articles) * 10)))
            return 0.0
        except Exception:
            return None

    def _get_finnhub_sentiment(self, symbol: str) -> Optional[float]:
        """Finnhub sentiment."""
        url = "https://finnhub.io/api/v1/news-sentiment"
        params = {'symbol': symbol, 'token': self.config['finnhub_key']}

        try:
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json()
            sentiment_score = data.get('sentiment', {}).get('score', 0.5)
            return (sentiment_score - 0.5) * 2  # 0-1 -> -1 a +1
        except Exception:
            return None

    def _get_cryptopanic_sentiment(self, symbol: str) -> Optional[float]:
        """CryptoPanic news (crypto)."""
        coin = symbol.upper().replace('USD', '').replace('USDT', '').lower()
        url = "https://cryptopanic.com/api/v1/posts/"

        params = {
            'auth_token': self.config.get('cryptopanic_key', 'free'),
            'currencies': coin,
            'filter': 'hot',
        }

        try:
            resp = requests.get(url, params=params, timeout=5)
            posts = resp.json().get('results', [])

            score = 0
            for post in posts[:20]:
                votes = post.get('votes', {})
                score += votes.get('positive', 0) - votes.get('negative', 0)

            if len(posts) > 0:
                return max(-1.0, min(1.0, score / (len(posts) * 50)))
            return 0.0
        except Exception:
            return None

    def _get_marketaux_sentiment(self, symbol: str, hours: int) -> Optional[float]:
        """MarketAux news sentiment."""
        key = self.config.get('marketaux_key')
        if not key:
            return None

        query = self._symbol_to_query(symbol)
        url = "https://api.marketaux.com/v1/news/all"

        params = {
            'api_token': key,
            'search': query,
            'language': 'en',
            'limit': 20
        }
        if self._is_stock(symbol):
            params['symbols'] = symbol

        try:
            resp = requests.get(url, params=params, timeout=10)
            articles = resp.json().get('data', [])

            scores = []
            for article in articles:
                entities = article.get('entities', [])
                for entity in entities:
                    if entity.get('symbol') == symbol:
                        sentiment = entity.get('sentiment_score', 0)
                        scores.append(sentiment)

            if scores:
                return float(np.mean(scores))
            return 0.0
        except Exception:
            return None

    def _get_currents_sentiment(self, symbol: str, hours: int) -> Optional[float]:
        """Currents API news sentiment."""
        key = self.config.get('currents_key')
        if not key:
            return None

        query = self._symbol_to_query(symbol)
        url = "https://api.currentsapi.services/v1/search"

        params = {
            'apiKey': key,
            'keywords': query,
            'language': 'en',
            'page_size': 20
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            articles = resp.json().get('news', [])
            return self._simple_sentiment_analysis(articles)
        except Exception:
            return None

    def _get_mediastack_sentiment(self, symbol: str, hours: int) -> Optional[float]:
        """MediaStack news sentiment."""
        key = self.config.get('mediastack_key')
        if not key:
            return None

        query = self._symbol_to_query(symbol)
        url = "http://api.mediastack.com/v1/news"

        params = {
            'access_key': key,
            'keywords': query,
            'languages': 'en',
            'limit': 20
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            articles = resp.json().get('data', [])
            return self._simple_sentiment_analysis(articles)
        except Exception:
            return None

    def _simple_sentiment_analysis(self, articles: list) -> float:
        """Simple keyword-based sentiment for articles without native scores."""
        positive = ['surge', 'rally', 'gain', 'rise', 'bullish',
                    'growth', 'breakthrough', 'soar', 'spike', 'high']
        negative = ['crash', 'fall', 'drop', 'bear', 'decline',
                    'loss', 'plunge', 'slump', 'tumble', 'low']

        score = 0
        for article in articles:
            text = ((article.get('title', '') or '') + ' ' +
                    (article.get('description', '') or '')).lower()
            for w in positive:
                score += text.count(w) * 2
            for w in negative:
                score -= text.count(w) * 2

        if len(articles) > 0:
            return max(-1.0, min(1.0, score / (len(articles) * 10)))
        return 0.0

    # ============================================================
    #  7. ON-CHAIN DATA (CRYPTO)
    # ============================================================

    def get_onchain_metrics(self, symbol: str) -> Optional[Dict]:
        """Metricas on-chain."""
        if not self._is_crypto(symbol):
            return None

        cache_key = f"onchain_{symbol}"
        cached = self._cache_get(cache_key, 'onchain')
        if cached is not None:
            return cached

        metrics = {}

        if symbol.upper() in ('BTCUSD', 'BTCUSDT'):
            metrics.update(self._get_bitcoin_metrics())
        elif symbol.upper() in ('ETHUSD', 'ETHUSDT'):
            metrics.update(self._get_ethereum_metrics())

        if metrics:
            self._cache_set(cache_key, metrics, 'onchain')

        return metrics if metrics else None

    def _get_bitcoin_metrics(self) -> Dict:
        """Bitcoin on-chain (Blockchain.com)."""
        url = "https://blockchain.info/stats?format=json"

        try:
            resp = requests.get(url, timeout=5)
            data = resp.json()
            total_btc = data.get('totalbc', 0) / 1e8

            return {
                'hash_rate': data.get('hash_rate'),
                'difficulty': data.get('difficulty'),
                'mempool_size': data.get('n_tx_mempool'),
                'total_btc': total_btc,
                'market_cap': (data.get('market_price_usd', 0) * total_btc),
            }
        except Exception:
            return {}

    def _get_ethereum_metrics(self) -> Dict:
        """Ethereum on-chain (Etherscan)."""
        key = self.config.get('etherscan_key')
        if not key:
            return {}

        url = "https://api.etherscan.io/api"
        params = {
            'module': 'stats',
            'action': 'ethprice',
            'apikey': key,
        }

        try:
            resp = requests.get(url, params=params, timeout=5)
            data = resp.json().get('result', {})
            return {
                'eth_price': float(data.get('ethusd', 0)),
                'eth_btc': float(data.get('ethbtc', 0)),
            }
        except Exception:
            return {}

    # ============================================================
    #  8. ECONOMIC CALENDAR
    # ============================================================

    def get_economic_events(self, days_ahead=7) -> List[Dict]:
        """Calendario economico."""
        cache_key = 'econ_calendar'
        cached = self._cache_get(cache_key, 'calendar')
        if cached is not None:
            return cached

        events = []

        if self.config.get('finnhub_key'):
            events.extend(self._get_finnhub_calendar())

        cutoff = datetime.now() + timedelta(days=days_ahead)
        filtered = [e for e in events
                     if isinstance(e.get('time'), datetime) and e['time'] <= cutoff]
        filtered.sort(key=lambda x: x['time'])

        self._cache_set(cache_key, filtered, 'calendar')
        return filtered

    def _get_finnhub_calendar(self) -> List[Dict]:
        """Finnhub economic calendar."""
        url = "https://finnhub.io/api/v1/calendar/economic"
        params = {'token': self.config['finnhub_key']}

        try:
            resp = requests.get(url, params=params, timeout=10)
            events = resp.json().get('economicCalendar', [])

            parsed = []
            for event in events:
                try:
                    event_time = datetime.fromisoformat(
                        event.get('time', event.get('date', ''))
                    )
                except (ValueError, TypeError):
                    continue

                parsed.append({
                    'time': event_time,
                    'country': event.get('country', ''),
                    'event': event.get('event', ''),
                    'impact': event.get('impact', 'Medium'),
                    'actual': event.get('actual'),
                    'estimate': event.get('estimate'),
                    'previous': event.get('previous'),
                })
            return parsed
        except Exception:
            return []

    # ============================================================
    #  8b. FRED (Federal Reserve Economic Data)
    # ============================================================

    def get_fred_indicator(self, series_id: str) -> Optional[float]:
        """
        FRED economic indicators.

        Common series:
        - 'DFF': Federal Funds Rate
        - 'UNRATE': Unemployment Rate
        - 'CPIAUCSL': CPI (inflation)
        - 'GDP': GDP
        - 'VIXCLS': VIX Fear index
        """
        key = self.config.get('fred_key')
        if not key:
            return None

        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            'series_id': series_id,
            'api_key': key,
            'file_type': 'json',
            'sort_order': 'desc',
            'limit': 1
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            observations = data.get('observations', [])
            if observations:
                return float(observations[0]['value'])
            return None
        except Exception:
            return None

    def get_macro_indicators(self) -> Dict:
        """Get key macro indicators from FRED."""
        return {
            'fed_funds_rate': self.get_fred_indicator('DFF'),
            'unemployment': self.get_fred_indicator('UNRATE'),
            'cpi': self.get_fred_indicator('CPIAUCSL'),
            'gdp': self.get_fred_indicator('GDP'),
            'vix': self.get_fred_indicator('VIXCLS')
        }

    # ============================================================
    #  9. FUNDAMENTALS (STOCKS)
    # ============================================================

    def get_fundamentals(self, symbol: str) -> Dict:
        """Dados fundamentais (Yahoo Finance)."""
        cache_key = f"fundamentals_{symbol}"
        cached = self._cache_get(cache_key, 'fundamentals')
        if cached is not None:
            return cached

        url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
        params = {'modules': 'defaultKeyStatistics,financialData'}
        headers = {'User-Agent': 'Mozilla/5.0'}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()['quoteSummary']['result'][0]

            key_stats = data.get('defaultKeyStatistics', {})
            fin_data = data.get('financialData', {})

            def _raw(d, key):
                return d.get(key, {}).get('raw') if isinstance(d.get(key), dict) else None

            result = {
                'pe_ratio': _raw(key_stats, 'forwardPE'),
                'peg_ratio': _raw(key_stats, 'pegRatio'),
                'price_to_book': _raw(key_stats, 'priceToBook'),
                'dividend_yield': _raw(key_stats, 'dividendYield'),
                'profit_margin': _raw(fin_data, 'profitMargins'),
                'revenue_growth': _raw(fin_data, 'revenueGrowth'),
                'debt_to_equity': _raw(fin_data, 'debtToEquity'),
                'recommendation': fin_data.get('recommendationKey', 'hold'),
            }

            self._cache_set(cache_key, result, 'fundamentals')
            return result
        except Exception:
            return {}

    # ============================================================
    #  10. CONSENSUS PRICE (COMBINA TUDO)
    # ============================================================

    def get_consensus_price(self, symbol: str) -> Dict:
        """
        Preco de consenso com TODAS as APIs disponiveis.
        """
        cache_key = f"price_{symbol}"
        cached = self._cache_get(cache_key, 'price')
        if cached is not None:
            return cached

        # Crypto sources (4 fontes)
        if self._is_crypto(symbol):
            prices = {
                'binance': self.get_crypto_price_binance(symbol),
                'coingecko': self.get_crypto_price_coingecko(symbol),
                'cryptocompare': self.get_crypto_price_cryptocompare(symbol),
                'eodhd': self.get_eodhd_price(symbol),
            }
            weights = {
                'binance': 0.45, 'coingecko': 0.30,
                'cryptocompare': 0.15, 'eodhd': 0.10,
            }

        # Forex sources (4 fontes)
        elif self._is_forex(symbol):
            prices = {
                'alpha_vantage': self.get_forex_price_alpha_vantage(symbol),
                'twelve_data': self.get_forex_price_twelve_data(symbol),
                'fixer': self.get_forex_price_fixer(symbol),
                'eodhd': self.get_eodhd_price(symbol),
            }
            weights = {
                'alpha_vantage': 0.35, 'twelve_data': 0.35,
                'fixer': 0.20, 'eodhd': 0.10,
            }

        # Stock sources (3 fontes)
        else:
            prices = {
                'yahoo': self.get_stock_price_yahoo(symbol),
                'polygon': self.get_stock_price_polygon(symbol),
                'eodhd': self.get_eodhd_price(symbol),
            }
            weights = {
                'yahoo': 0.45, 'polygon': 0.35, 'eodhd': 0.20,
            }

        valid = {k: v for k, v in prices.items() if v is not None}

        if not valid:
            result = {'price': None, 'confidence': 0.0, 'sources': {},
                      'deviation_pct': 0, 'sources_count': 0,
                      'agreement_level': 'NONE'}
            self._cache_set(cache_key, result, 'price')
            return result

        total_weight = sum(weights[k] for k in valid)
        consensus = sum(valid[k] * weights[k] for k in valid) / total_weight

        values = list(valid.values())
        avg = float(np.mean(values))
        std = float(np.std(values)) if len(values) > 1 else 0.0

        # Confidence baseado em agreement
        deviation_pct = (std / avg * 100) if avg > 0 else 0
        if avg > 0:
            if deviation_pct < 0.1:
                confidence = 1.0
            elif deviation_pct < 0.5:
                confidence = 0.95
            elif deviation_pct < 1.0:
                confidence = 0.85
            else:
                confidence = max(0.0, 1 - (deviation_pct / 10))
        else:
            confidence = 0.0

        result = {
            'price': consensus,
            'confidence': min(1.0, confidence),
            'sources': valid,
            'deviation_pct': deviation_pct,
            'sources_count': len(valid),
            'agreement_level': ('STRONG' if deviation_pct < 0.5 else
                                'GOOD' if deviation_pct < 1.0 else
                                'WEAK'),
        }

        self._cache_set(cache_key, result, 'price')
        return result

    # ============================================================
    #  CACHE SYSTEM
    # ============================================================

    def _cache_get(self, key: str, category: str):
        """Retorna valor do cache se ainda valido, senao None."""
        entry = self.cache.get(key)
        if entry is None:
            return None
        age = time.time() - entry['ts']
        if age < self.cache_duration.get(category, 60):
            return entry['data']
        return None

    def _cache_set(self, key: str, data, category: str):
        """Guarda em cache."""
        self.cache[key] = {
            'data': data,
            'ts': time.time(),
            'category': category,
        }

    def clear_cache(self):
        """Limpa todo o cache."""
        self.cache.clear()

    # ============================================================
    #  HELPER METHODS
    # ============================================================

    def _is_crypto(self, symbol):
        s = symbol.upper()
        return any(c in s for c in ['BTC', 'ETH', 'XRP', 'SOL', 'ADA', 'DOT', 'DOGE'])

    def _is_forex(self, symbol):
        forex = [
            'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCHF',
            'USDCAD', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY',
            'AUDJPY', 'EURAUD', 'EURCHF',
        ]
        return symbol.upper() in forex

    def _is_stock(self, symbol):
        return not (self._is_crypto(symbol) or self._is_forex(symbol))

    def _to_binance(self, symbol):
        mapping = {
            'BTCUSD': 'BTCUSDT', 'ETHUSD': 'ETHUSDT',
            'XRPUSD': 'XRPUSDT', 'SOLUSD': 'SOLUSDT',
        }
        return mapping.get(symbol.upper(), symbol.upper())

    def _to_coingecko(self, symbol):
        mapping = {
            'BTCUSD': 'bitcoin', 'ETHUSD': 'ethereum',
            'XRPUSD': 'ripple', 'SOLUSD': 'solana',
        }
        return mapping.get(symbol.upper(), symbol.lower())

    def _symbol_to_query(self, symbol):
        mapping = {
            'BTCUSD': 'Bitcoin', 'ETHUSD': 'Ethereum',
            'XRPUSD': 'Ripple XRP', 'SOLUSD': 'Solana',
            'EURUSD': 'EUR USD forex', 'GBPUSD': 'GBP USD forex',
            'USDJPY': 'USD JPY forex', 'GOLD': 'Gold price',
            'SILVER': 'Silver price', 'USOIL': 'Crude Oil WTI',
        }
        return mapping.get(symbol.upper(), symbol)

    def _get_binance_volume(self, symbol) -> Optional[float]:
        binance_symbol = self._to_binance(symbol)
        url = "https://api.binance.com/api/v3/ticker/24hr"

        try:
            resp = requests.get(url, params={'symbol': binance_symbol}, timeout=5)
            return float(resp.json()['volume'])
        except Exception:
            return None

    def _get_coingecko_volume(self, symbol) -> Optional[float]:
        coin_id = self._to_coingecko(symbol)
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"

        try:
            resp = requests.get(url, params={'localization': 'false',
                                             'tickers': 'false',
                                             'community_data': 'false',
                                             'developer_data': 'false'}, timeout=5)
            data = resp.json()
            return float(data['market_data']['total_volume']['usd'])
        except Exception:
            return None

    def _get_yahoo_volume(self, symbol) -> Optional[float]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        headers = {'User-Agent': 'Mozilla/5.0'}

        try:
            resp = requests.get(url, headers=headers, timeout=5)
            data = resp.json()
            volume = data['chart']['result'][0]['indicators']['quote'][0]['volume']
            return float(volume[-1]) if volume and volume[-1] else None
        except Exception:
            return None
