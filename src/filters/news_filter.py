"""
News Filter - Bloqueia trades antes de eventos económicos
"""

from datetime import datetime, time, timedelta
from typing import Optional, List

class NewsFilter:
    def __init__(self):
        self.events = self._load_calendar()
        self.block_minutes_before = 30
        self.block_minutes_after = 15
    
    def _load_calendar(self) -> List[dict]:
        """Calendário de eventos HIGH impact"""
        return [
            {'name': 'NFP', 'time': time(13, 30), 'day': 'first_friday', 
             'pairs': ['EURUSD', 'GBPUSD', 'USDJPY', 'GOLD']},
            {'name': 'FOMC', 'time': time(19, 0), 'pairs': ['ALL']},
            {'name': 'CPI', 'time': time(13, 30), 'day': 15, 
             'pairs': ['EURUSD', 'GBPUSD', 'GOLD']},
            {'name': 'ECB', 'time': time(12, 45), 'day': 'first_thursday',
             'pairs': ['EURUSD', 'EURGBP', 'EURJPY']},
        ]
    
    def is_blocked(self, symbol: str, current_time: datetime) -> dict:
        """
        Returns: {
            'blocked': bool,
            'reason': str,
            'event_name': str,
            'minutes_until': int
        }
        """
        for event in self.events:
            if 'ALL' not in event['pairs'] and symbol not in event['pairs']:
                continue
            
            # Calcular tempo até evento
            event_datetime = datetime.combine(
                current_time.date(), 
                event['time']
            )
            
            diff_minutes = (event_datetime - current_time).total_seconds() / 60
            
            # Bloquear se dentro da janela
            if -self.block_minutes_after <= diff_minutes <= self.block_minutes_before:
                return {
                    'blocked': True,
                    'reason': 'News event approaching',
                    'event_name': event['name'],
                    'minutes_until': int(diff_minutes)
                }
        
        return {'blocked': False}
