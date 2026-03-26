"""
Data Health Monitor
Monitoriza estado de todas as APIs e gera relatorios de uptime.
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Optional
import pandas as pd


class DataHealthMonitor:
    def __init__(self, api_aggregator):
        """
        Args:
            api_aggregator: instancia de MultiAPIAggregator
        """
        self.api_agg = api_aggregator
        self.health_log = []
        self._max_log_entries = 1000

    def check_all_sources(self) -> dict:
        """
        Testa todas as APIs e retorna estado.

        Returns: {
            'healthy': int,
            'degraded': int,
            'down': int,
            'sources': {name: {'status': str, 'latency_ms': float}},
            'timestamp': datetime,
        }
        """
        results = {
            'healthy': 0,
            'degraded': 0,
            'down': 0,
            'sources': {},
            'timestamp': datetime.now(),
        }

        tests = {
            'binance': self._test_binance,
            'coingecko': self._test_coingecko,
            'alpha_vantage': self._test_alpha_vantage,
            'twelve_data': self._test_twelve_data,
            'fixer': self._test_fixer,
            'eodhd': self._test_eodhd,
            'yahoo': self._test_yahoo,
            'newsapi': self._test_newsapi,
            'finnhub': self._test_finnhub,
            'marketaux': self._test_marketaux,
            'currents': self._test_currents,
            'mediastack': self._test_mediastack,
            'fred': self._test_fred,
        }

        for name, test_fn in tests.items():
            results['sources'][name] = test_fn()

        for data in results['sources'].values():
            if data['status'] == 'healthy':
                results['healthy'] += 1
            elif data['status'] == 'degraded':
                results['degraded'] += 1
            else:
                results['down'] += 1

        self.health_log.append(results)
        if len(self.health_log) > self._max_log_entries:
            self.health_log.pop(0)

        return results

    def _timed_test(self, fn, *args, healthy_ms=1000, degraded_ms=5000) -> dict:
        """Helper generico para testar uma API."""
        start = time.time()
        try:
            result = fn(*args)
            latency = (time.time() - start) * 1000

            if result is not None and latency < healthy_ms:
                return {'status': 'healthy', 'latency_ms': round(latency, 1)}
            elif result is not None:
                return {'status': 'degraded', 'latency_ms': round(latency, 1)}
            else:
                return {'status': 'down', 'latency_ms': round(latency, 1)}
        except Exception:
            return {'status': 'down', 'latency_ms': 0}

    def _test_binance(self) -> dict:
        return self._timed_test(
            self.api_agg.get_crypto_price_binance, 'BTCUSD',
            healthy_ms=1000,
        )

    def _test_coingecko(self) -> dict:
        return self._timed_test(
            self.api_agg.get_crypto_price_coingecko, 'BTCUSD',
            healthy_ms=2000,
        )

    def _test_alpha_vantage(self) -> dict:
        if not self.api_agg.config.get('alpha_vantage_key'):
            return {'status': 'down', 'latency_ms': 0, 'reason': 'no key'}
        return self._timed_test(
            self.api_agg.get_forex_price_alpha_vantage, 'EURUSD',
            healthy_ms=5000,
        )

    def _test_yahoo(self) -> dict:
        return self._timed_test(
            self.api_agg.get_stock_price_yahoo, 'AAPL',
            healthy_ms=2000,
        )

    def _test_newsapi(self) -> dict:
        if not self.api_agg.config.get('newsapi_key'):
            return {'status': 'down', 'latency_ms': 0, 'reason': 'no key'}
        return self._timed_test(
            self.api_agg._get_newsapi_sentiment, 'BTCUSD', 24,
            healthy_ms=3000,
        )

    def _test_twelve_data(self) -> dict:
        if not self.api_agg.config.get('twelve_data_key'):
            return {'status': 'down', 'latency_ms': 0, 'reason': 'no key'}
        return self._timed_test(
            self.api_agg.get_forex_price_twelve_data, 'EURUSD',
            healthy_ms=3000,
        )

    def _test_fixer(self) -> dict:
        if not self.api_agg.config.get('fixer_key'):
            return {'status': 'down', 'latency_ms': 0, 'reason': 'no key'}
        return self._timed_test(
            self.api_agg.get_forex_price_fixer, 'EURUSD',
            healthy_ms=3000,
        )

    def _test_eodhd(self) -> dict:
        if not self.api_agg.config.get('eodhd_key'):
            return {'status': 'down', 'latency_ms': 0, 'reason': 'no key'}
        return self._timed_test(
            self.api_agg.get_eodhd_price, 'AAPL.US',
            healthy_ms=3000,
        )

    def _test_marketaux(self) -> dict:
        if not self.api_agg.config.get('marketaux_key'):
            return {'status': 'down', 'latency_ms': 0, 'reason': 'no key'}
        return self._timed_test(
            self.api_agg._get_marketaux_sentiment, 'BTCUSD', 24,
            healthy_ms=5000,
        )

    def _test_currents(self) -> dict:
        if not self.api_agg.config.get('currents_key'):
            return {'status': 'down', 'latency_ms': 0, 'reason': 'no key'}
        return self._timed_test(
            self.api_agg._get_currents_sentiment, 'BTCUSD', 24,
            healthy_ms=5000,
        )

    def _test_mediastack(self) -> dict:
        if not self.api_agg.config.get('mediastack_key'):
            return {'status': 'down', 'latency_ms': 0, 'reason': 'no key'}
        return self._timed_test(
            self.api_agg._get_mediastack_sentiment, 'BTCUSD', 24,
            healthy_ms=5000,
        )

    def _test_fred(self) -> dict:
        if not self.api_agg.config.get('fred_key'):
            return {'status': 'down', 'latency_ms': 0, 'reason': 'no key'}
        return self._timed_test(
            self.api_agg.get_fred_indicator, 'DFF',
            healthy_ms=5000,
        )

    def _test_finnhub(self) -> dict:
        if not self.api_agg.config.get('finnhub_key'):
            return {'status': 'down', 'latency_ms': 0, 'reason': 'no key'}

        start = time.time()
        try:
            events = self.api_agg._get_finnhub_calendar()
            latency = (time.time() - start) * 1000

            if len(events) > 0 and latency < 3000:
                return {'status': 'healthy', 'latency_ms': round(latency, 1)}
            elif len(events) > 0:
                return {'status': 'degraded', 'latency_ms': round(latency, 1)}
            else:
                return {'status': 'down', 'latency_ms': round(latency, 1)}
        except Exception:
            return {'status': 'down', 'latency_ms': 0}

    def get_uptime_report(self, hours=24) -> pd.DataFrame:
        """Relatorio de uptime."""
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_logs = [l for l in self.health_log
                       if l['timestamp'] >= cutoff]

        if not recent_logs:
            return pd.DataFrame()

        uptime_data = {}
        for entry in recent_logs:
            for source, data in entry['sources'].items():
                if source not in uptime_data:
                    uptime_data[source] = {'healthy': 0, 'degraded': 0, 'total': 0,
                                           'total_latency': 0}
                uptime_data[source]['total'] += 1
                uptime_data[source]['total_latency'] += data.get('latency_ms', 0)
                if data['status'] == 'healthy':
                    uptime_data[source]['healthy'] += 1
                elif data['status'] == 'degraded':
                    uptime_data[source]['degraded'] += 1

        rows = []
        for source, counts in uptime_data.items():
            total = counts['total']
            rows.append({
                'Source': source,
                'Uptime %': round(counts['healthy'] / total * 100, 1) if total else 0,
                'Degraded %': round(counts['degraded'] / total * 100, 1) if total else 0,
                'Avg Latency': round(counts['total_latency'] / total, 0) if total else 0,
                'Checks': total,
            })

        df = pd.DataFrame(rows)
        return df.sort_values('Uptime %', ascending=False).reset_index(drop=True)

    def get_latest_health(self) -> Optional[dict]:
        """Retorna o ultimo health check."""
        return self.health_log[-1] if self.health_log else None

    def to_dashboard_json(self) -> dict:
        """Formata para o dashboard."""
        latest = self.get_latest_health()
        if not latest:
            return {'sources': {}, 'healthy': 0, 'degraded': 0, 'down': 0}

        # Calcular uptime 24h por source
        report = self.get_uptime_report(hours=24)
        uptime_map = {}
        if not report.empty:
            uptime_map = dict(zip(report['Source'], report['Uptime %']))

        sources = {}
        for name, data in latest['sources'].items():
            sources[name] = {
                'status': data['status'],
                'latency_ms': data.get('latency_ms', 0),
                'uptime_24h': uptime_map.get(name, 0),
            }

        return {
            'sources': sources,
            'healthy': latest['healthy'],
            'degraded': latest['degraded'],
            'down': latest['down'],
        }
