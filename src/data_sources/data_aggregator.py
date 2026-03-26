"""
Multi-Source Data Aggregator
Combina dados de MT5, Binance, Alpha Vantage, etc.
"""

import time
import requests
import pandas as pd
from datetime import datetime, timedelta
import numpy as np


class DataAggregator:
    def __init__(self, config: dict):
        """
        Args:
            config: {
                'alpha_vantage_key': str,
                'polygon_key': str,
                'newsapi_key': str,
                'finnhub_key': str,
                'fmp_key': str,
            }
        """
        self.config = config
        self.cache = {}
        self._cache_ttl = 30  # seconds

    def _cache_get(self, key: str):
        """Retorna valor do cache se ainda válido."""
        entry = self.cache.get(key)
        if entry and (time.time() - entry['ts']) < self._cache_ttl:
            return entry['value']
        return None

    def _cache_set(self, key: str, value):
        """Guarda valor no cache."""
        self.cache[key] = {'value': value, 'ts': time.time()}

    def get_consensus_price(self, symbol: str, timeframe='5min') -> dict:
        """
        Obtém preço de múltiplas fontes e retorna consenso.

        Returns: {
            'price': float (média ponderada),
            'sources': dict,
            'confidence': float (0-1),
            'deviation_pct': float,
        }
        """
        cached = self._cache_get(f'consensus_{symbol}')
        if cached:
            return cached

        sources = {}

        # 1. MT5 (weight 0.3)
        mt5_price = self._get_mt5_price(symbol)
        if mt5_price:
            sources['mt5'] = {'price': mt5_price, 'weight': 0.3}

        # 2. Binance (weight 0.5 - mais confiável para crypto)
        if self._is_crypto(symbol):
            binance_price = self._get_binance_price(symbol)
            if binance_price:
                sources['binance'] = {'price': binance_price, 'weight': 0.5}

        # 3. Alpha Vantage (weight 0.4 - bom para forex)
        if self._is_forex(symbol) and self.config.get('alpha_vantage_key'):
            av_price = self._get_alpha_vantage_price(symbol)
            if av_price:
                sources['alpha_vantage'] = {'price': av_price, 'weight': 0.4}

        if not sources:
            return {'price': None, 'sources': {}, 'confidence': 0.0, 'deviation_pct': 0}

        # Média ponderada
        total_weight = sum(s['weight'] for s in sources.values())
        consensus_price = sum(
            s['price'] * s['weight'] for s in sources.values()
        ) / total_weight

        # Confidence baseado em concordância
        prices = [s['price'] for s in sources.values()]
        avg = np.mean(prices)
        std = np.std(prices) if len(prices) > 1 else 0
        confidence = 1 - (std / avg) if avg > 0 else 0

        result = {
            'price': consensus_price,
            'sources': sources,
            'confidence': min(max(confidence, 0.0), 1.0),
            'deviation_pct': (std / avg * 100) if avg > 0 else 0,
        }

        self._cache_set(f'consensus_{symbol}', result)
        return result

    def get_real_volume(self, symbol: str) -> dict:
        """Volume REAL (não ticks do MT5)."""
        cached = self._cache_get(f'volume_{symbol}')
        if cached:
            return cached

        if self._is_crypto(symbol):
            result = self._get_binance_volume(symbol)
        elif self._is_stock(symbol):
            result = self._get_polygon_volume(symbol)
        else:
            # Forex não tem volume centralizado
            result = {'volume': 0, 'source': 'N/A'}

        self._cache_set(f'volume_{symbol}', result)
        return result

    def get_order_book_depth(self, symbol: str, levels=10) -> dict:
        """Order book depth (só crypto via Binance)."""
        if not self._is_crypto(symbol):
            return None

        binance_symbol = self._convert_to_binance(symbol)
        url = "https://api.binance.com/api/v3/depth"
        params = {'symbol': binance_symbol, 'limit': levels}

        try:
            response = requests.get(url, params=params, timeout=5)
            data = response.json()

            return {
                'bids': data['bids'],
                'asks': data['asks'],
                'bid_depth': sum(float(b[1]) for b in data['bids']),
                'ask_depth': sum(float(a[1]) for a in data['asks']),
                'imbalance': self._calculate_imbalance(data),
            }
        except Exception:
            return None

    def get_news_sentiment(self, symbol: str, hours=24) -> dict:
        """Sentiment score de notícias recentes."""
        cached = self._cache_get(f'sentiment_{symbol}')
        if cached:
            return cached

        newsapi_key = self.config.get('newsapi_key')
        if not newsapi_key:
            return {'score': 0, 'article_count': 0, 'recommendation': 'NEUTRAL'}

        query = self._symbol_to_query(symbol)
        url = "https://newsapi.org/v2/everything"

        params = {
            'q': query,
            'apiKey': newsapi_key,
            'language': 'en',
            'sortBy': 'publishedAt',
            'from': (datetime.now() - timedelta(hours=hours)).isoformat(),
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()

            articles = data.get('articles', [])
            sentiment_score = self._analyze_sentiment(articles)

            result = {
                'score': sentiment_score,
                'article_count': len(articles),
                'recommendation': ('BULLISH' if sentiment_score > 0.3 else
                                   'BEARISH' if sentiment_score < -0.3 else
                                   'NEUTRAL'),
            }

            self._cache_set(f'sentiment_{symbol}', result)
            return result
        except Exception:
            return {'score': 0, 'article_count': 0, 'recommendation': 'NEUTRAL'}

    def get_economic_calendar(self, days_ahead=7) -> list:
        """Calendário econômico via Finnhub."""
        cached = self._cache_get('econ_calendar')
        if cached:
            return cached

        finnhub_key = self.config.get('finnhub_key')
        if not finnhub_key:
            return []

        url = "https://finnhub.io/api/v1/calendar/economic"
        params = {'token': finnhub_key}

        try:
            response = requests.get(url, params=params, timeout=10)
            events = response.json().get('economicCalendar', [])

            upcoming = []
            cutoff = datetime.now() + timedelta(days=days_ahead)

            for event in events:
                try:
                    event_time = datetime.fromisoformat(
                        event.get('time', event.get('date', ''))
                    )
                except (ValueError, TypeError):
                    continue

                if event_time <= cutoff:
                    upcoming.append({
                        'time': event.get('time', event.get('date')),
                        'country': event.get('country', ''),
                        'event': event.get('event', ''),
                        'impact': event.get('impact', 'Medium'),
                        'actual': event.get('actual'),
                        'estimate': event.get('estimate'),
                    })

            self._cache_set('econ_calendar', upcoming)
            return upcoming
        except Exception:
            return []

    def get_fundamentals(self, symbol: str) -> dict:
        """Dados fundamentais (stocks)."""
        fmp_key = self.config.get('fmp_key')
        if not fmp_key:
            return {}

        url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
        params = {'apikey': fmp_key}

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            if not data:
                return {}
            data = data[0]

            return {
                'pe_ratio': data.get('pe'),
                'market_cap': data.get('mktCap'),
                'beta': data.get('beta'),
                'dividend_yield': data.get('lastDiv'),
                'recommendation': 'BUY' if (data.get('pe') or 100) < 15 else 'HOLD',
            }
        except Exception:
            return {}

    # ============================================================
    #  HELPER METHODS
    # ============================================================

    def _is_crypto(self, symbol):
        cryptos = ['BTCUSD', 'ETHUSD', 'XRPUSD', 'SOLUSD',
                   'BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'SOLUSDT']
        return symbol.upper() in cryptos

    def _is_forex(self, symbol):
        forex_pairs = [
            'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCHF',
            'USDCAD', 'NZDUSD', 'EURGBP', 'EURJPY', 'GBPJPY',
            'AUDJPY',
        ]
        return symbol.upper() in forex_pairs

    def _is_stock(self, symbol):
        return not (self._is_crypto(symbol) or self._is_forex(symbol))

    def _get_mt5_price(self, symbol):
        """Preço via MT5 (requer mt5_connector importado externamente)."""
        try:
            import src.mt5_connector as mt5c
            tick = mt5c.get_tick(symbol)
            if tick:
                return (tick.bid + tick.ask) / 2
        except Exception:
            pass
        return None

    def _get_binance_price(self, symbol):
        """Binance ticker price."""
        binance_symbol = self._convert_to_binance(symbol)
        url = "https://api.binance.com/api/v3/ticker/price"

        try:
            response = requests.get(
                url, params={'symbol': binance_symbol}, timeout=5
            )
            return float(response.json()['price'])
        except Exception:
            return None

    def _get_binance_volume(self, symbol):
        """Binance 24h volume."""
        binance_symbol = self._convert_to_binance(symbol)
        url = "https://api.binance.com/api/v3/ticker/24hr"

        try:
            response = requests.get(
                url, params={'symbol': binance_symbol}, timeout=5
            )
            data = response.json()
            return {
                'volume': float(data['volume']),
                'quote_volume': float(data['quoteVolume']),
                'source': 'binance',
            }
        except Exception:
            return {'volume': 0, 'source': 'error'}

    def _get_polygon_volume(self, symbol):
        """Polygon.io volume (stocks)."""
        polygon_key = self.config.get('polygon_key')
        if not polygon_key:
            return {'volume': 0, 'source': 'N/A'}

        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev"
        params = {'apiKey': polygon_key}

        try:
            response = requests.get(url, params=params, timeout=5)
            data = response.json()
            results = data.get('results', [{}])
            return {
                'volume': results[0].get('v', 0) if results else 0,
                'source': 'polygon',
            }
        except Exception:
            return {'volume': 0, 'source': 'error'}

    def _convert_to_binance(self, symbol):
        """BTCUSD -> BTCUSDT"""
        mapping = {
            'BTCUSD': 'BTCUSDT',
            'ETHUSD': 'ETHUSDT',
            'XRPUSD': 'XRPUSDT',
            'SOLUSD': 'SOLUSDT',
        }
        return mapping.get(symbol.upper(), symbol)

    def _get_alpha_vantage_price(self, symbol):
        """Alpha Vantage forex price."""
        key = self.config.get('alpha_vantage_key')
        if not key:
            return None

        # Converter símbolo: EURUSD -> from=EUR, to=USD
        if len(symbol) == 6:
            from_cur = symbol[:3]
            to_cur = symbol[3:]
        else:
            return None

        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'CURRENCY_EXCHANGE_RATE',
            'from_currency': from_cur,
            'to_currency': to_cur,
            'apikey': key,
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            rate_data = data.get('Realtime Currency Exchange Rate', {})
            price = rate_data.get('5. Exchange Rate')
            return float(price) if price else None
        except Exception:
            return None

    def _calculate_imbalance(self, order_book):
        """Bid/Ask imbalance (-1 a +1)."""
        bid_vol = sum(float(b[1]) for b in order_book.get('bids', []))
        ask_vol = sum(float(a[1]) for a in order_book.get('asks', []))

        total = bid_vol + ask_vol
        if total == 0:
            return 0

        return (bid_vol - ask_vol) / total

    def _symbol_to_query(self, symbol):
        """Convert symbol to news query."""
        mapping = {
            'BTCUSD': 'Bitcoin',
            'ETHUSD': 'Ethereum',
            'XRPUSD': 'Ripple XRP',
            'SOLUSD': 'Solana',
            'EURUSD': 'EUR USD forex',
            'GBPUSD': 'GBP USD forex',
            'USDJPY': 'USD JPY forex',
            'GOLD': 'Gold price',
            'SILVER': 'Silver price',
            'USOIL': 'Crude Oil WTI',
        }
        return mapping.get(symbol.upper(), symbol)

    def _analyze_sentiment(self, articles):
        """Simple keyword-based sentiment analysis."""
        positive_words = [
            'surge', 'rally', 'gain', 'rise', 'bullish', 'growth',
            'soar', 'jump', 'high', 'record', 'profit', 'boost',
        ]
        negative_words = [
            'crash', 'fall', 'drop', 'bear', 'decline', 'loss',
            'plunge', 'slump', 'low', 'fear', 'recession', 'sell-off',
        ]

        score = 0
        for article in articles:
            text = (
                (article.get('title', '') or '') + ' ' +
                (article.get('description', '') or '')
            ).lower()

            for word in positive_words:
                score += text.count(word)
            for word in negative_words:
                score -= text.count(word)

        if len(articles) == 0:
            return 0.0

        # Normalizar -1 a +1
        return max(-1.0, min(1.0, score / (len(articles) * 5)))
