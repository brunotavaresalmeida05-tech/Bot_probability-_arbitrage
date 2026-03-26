"""
Forex Factory Calendar Scraper + Multi-Source Economic Calendar
Combina scraping FF com APIs oficiais (Finnhub, Trading Economics).
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class ForexFactoryScraper:
    """Scraper para o calendario economico do Forex Factory."""

    def __init__(self):
        self.base_url = "https://www.forexfactory.com"
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
        }

    def get_calendar(self, date: str = None) -> list:
        """
        Scrape calendario economico.

        Args:
            date: 'yyyy-mm-dd' ou None (hoje)

        Returns: lista de eventos
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        url = f"{self.base_url}/calendar?day={date}"

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')

            events = []

            table = soup.find('table', class_='calendar__table')
            if not table:
                return []

            rows = table.find_all('tr', class_='calendar__row')

            current_time = None

            for row in rows:
                time_cell = row.find('td', class_='calendar__time')
                currency_cell = row.find('td', class_='calendar__currency')
                impact_cell = row.find('td', class_='calendar__impact')
                event_cell = row.find('td', class_='calendar__event')
                actual_cell = row.find('td', class_='calendar__actual')
                forecast_cell = row.find('td', class_='calendar__forecast')
                previous_cell = row.find('td', class_='calendar__previous')

                if not event_cell:
                    continue

                # Parse time
                if time_cell and time_cell.text.strip():
                    current_time = time_cell.text.strip()

                # Parse impact
                impact = 'Low'
                if impact_cell:
                    impact_span = impact_cell.find('span')
                    if impact_span:
                        cls = str(impact_span.get('class', []))
                        if 'high' in cls:
                            impact = 'High'
                        elif 'medium' in cls or 'med' in cls:
                            impact = 'Medium'

                event = {
                    'time': self._parse_datetime(date, current_time),
                    'currency': currency_cell.text.strip() if currency_cell else '',
                    'impact': impact,
                    'event': event_cell.text.strip() if event_cell else '',
                    'actual': actual_cell.text.strip() if actual_cell else '',
                    'forecast': forecast_cell.text.strip() if forecast_cell else '',
                    'previous': previous_cell.text.strip() if previous_cell else '',
                    'source': 'ForexFactory',
                }

                events.append(event)

            return events

        except Exception as e:
            print(f"ForexFactory scraping error: {e}")
            return []

    def _parse_datetime(self, date_str: str, time_str: str) -> Optional[datetime]:
        """Converte date + time para datetime."""
        if not time_str:
            return None

        try:
            if 'All Day' in time_str or 'Tentative' in time_str:
                return datetime.strptime(date_str, '%Y-%m-%d')
            dt_str = f"{date_str} {time_str}"
            return datetime.strptime(dt_str, '%Y-%m-%d %I:%M%p')
        except Exception:
            return None

    def get_high_impact_events(self, days_ahead=7) -> list:
        """Eventos HIGH impact dos proximos X dias."""
        all_events = []

        for i in range(days_ahead):
            date = (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d')
            events = self.get_calendar(date)
            high_impact = [e for e in events if e['impact'] == 'High']
            all_events.extend(high_impact)

        return all_events


class ForexFactoryAggregator:
    """Combina Forex Factory + Finnhub + Trading Economics."""

    def __init__(self, config: dict):
        self.config = config
        self.ff_scraper = ForexFactoryScraper()
        self._cache = {}
        self._cache_ts = 0
        self._cache_ttl = 600  # 10 min

    def get_economic_events(self, days_ahead=7) -> list:
        """Calendario economico de multiplas fontes."""
        import time as _time

        # Cache check
        now = _time.time()
        cache_key = f"events_{days_ahead}"
        if cache_key in self._cache and (now - self._cache_ts) < self._cache_ttl:
            return self._cache[cache_key]

        all_events = []

        # 1. Forex Factory (scraping)
        try:
            ff_events = self.ff_scraper.get_high_impact_events(min(days_ahead, 3))
            all_events.extend(ff_events)
        except Exception:
            pass

        # 2. Finnhub (API)
        if self.config.get('finnhub_key'):
            finnhub_events = self._get_finnhub_calendar()
            all_events.extend(finnhub_events)

        # 3. Trading Economics (API)
        if self.config.get('trading_economics_key'):
            te_events = self._get_trading_economics_calendar()
            all_events.extend(te_events)

        # Remover duplicados
        unique_events = self._deduplicate_events(all_events)

        # Filtrar proximos X dias
        cutoff = datetime.now() + timedelta(days=days_ahead)
        filtered = [e for e in unique_events
                     if e.get('time') and e['time'] <= cutoff]
        filtered.sort(key=lambda x: x['time'] if x['time'] else datetime.max)

        self._cache[cache_key] = filtered
        self._cache_ts = now
        return filtered

    def _get_finnhub_calendar(self) -> list:
        """Finnhub economic calendar."""
        url = "https://finnhub.io/api/v1/calendar/economic"
        params = {'token': self.config['finnhub_key']}

        try:
            response = requests.get(url, params=params, timeout=10)
            events = response.json().get('economicCalendar', [])

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
                    'currency': event.get('country', ''),
                    'impact': event.get('impact', 'Medium'),
                    'event': event.get('event', ''),
                    'actual': event.get('actual'),
                    'forecast': event.get('estimate'),
                    'previous': event.get('previous'),
                    'source': 'Finnhub',
                })
            return parsed
        except Exception:
            return []

    def _get_trading_economics_calendar(self) -> list:
        """Trading Economics calendar."""
        key = self.config.get('trading_economics_key')
        if not key:
            return []

        url = "https://api.tradingeconomics.com/calendar"
        params = {
            'c': key,
            'importance': '3',
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            events = response.json()

            parsed = []
            for event in events:
                try:
                    event_time = datetime.fromisoformat(event.get('Date', ''))
                except (ValueError, TypeError):
                    continue

                parsed.append({
                    'time': event_time,
                    'currency': event.get('Country', ''),
                    'impact': 'High',
                    'event': event.get('Event', ''),
                    'actual': event.get('Actual'),
                    'forecast': event.get('Forecast'),
                    'previous': event.get('Previous'),
                    'source': 'TradingEconomics',
                })
            return parsed
        except Exception:
            return []

    def _deduplicate_events(self, events: list) -> list:
        """Remove eventos duplicados."""
        seen = set()
        unique = []

        for event in events:
            t = event.get('time')
            time_key = t.strftime('%Y-%m-%d %H:%M') if t else ''
            key = (time_key, event.get('event', '').lower().strip())

            if key not in seen:
                seen.add(key)
                unique.append(event)

        return unique

    def is_high_impact_event_soon(self, symbol: str,
                                   minutes_before: int = 30,
                                   minutes_after: int = 15) -> dict:
        """
        Verifica se ha evento HIGH impact perto.

        Args:
            symbol: e.g. 'EURUSD'
            minutes_before: bloquear X min antes
            minutes_after: bloquear X min depois
        """
        events = self.get_economic_events(days_ahead=1)

        now = datetime.now()
        window_start = now - timedelta(minutes=minutes_after)
        window_end = now + timedelta(minutes=minutes_before)

        base = symbol[:3].upper()
        quote = symbol[3:6].upper() if len(symbol) >= 6 else ''

        for event in events:
            if not event.get('time'):
                continue

            if event['impact'] != 'High':
                continue

            # Evento afeta esta currency?
            cur = event.get('currency', '').upper()
            if base not in cur and quote not in cur:
                continue

            # Evento dentro da janela?
            if window_start <= event['time'] <= window_end:
                minutes_until = int((event['time'] - now).total_seconds() / 60)
                return {
                    'blocked': True,
                    'event': event['event'],
                    'time': event['time'],
                    'currency': cur,
                    'minutes_until': minutes_until,
                    'source': event.get('source', ''),
                }

        return {'blocked': False}
