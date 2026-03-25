"""
src/strategies/news_trading.py
News Trading / Event-Driven Strategy

Opera eventos econômicos conhecidos:
- NFP (Non-Farm Payroll)
- FOMC (Federal Reserve)
- CPI, GDP, etc
- Earnings (stocks)

Pre-position antes do evento, exit após movimento inicial.
"""

import numpy as np
import pandas as pd
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import config.settings as cfg


class NewsTrading:
    """
    Estratégia de News Trading.
    
    Calendário de eventos:
    - USD: NFP (1st Friday), FOMC (8x/year), CPI
    - EUR: ECB rate decision, CPI
    - GBP: BoE rate decision, employment
    - JPY: BoJ rate decision
    
    Entry:
    - 15-30 min antes do evento
    - Straddle ou direção baseada em consensus
    
    Exit:
    - 5-15 min após release
    - Stop loss apertado
    """
    
    def __init__(self):
        # Calendário econômico (simplificado)
        self.events = self._load_economic_calendar()
        self.positions: Dict[str, Dict] = {}
        self.event_window_minutes = 30  # Janela antes do evento
        self.exit_minutes = 15  # Exit após evento
    
    def _load_economic_calendar(self) -> List[Dict]:
        """
        Carrega calendário de eventos econômicos.
        
        Na prática, isso viria de uma API (ForexFactory, Investing.com, etc)
        """
        # Exemplo estático (em produção, usar API)
        events = [
            # NFP (primeira sexta-feira do mês, 8:30 AM ET)
            {
                'name': 'Non-Farm Payroll',
                'currency': 'USD',
                'impact': 'HIGH',
                'frequency': 'monthly',
                'day_of_month': 'first_friday',
                'time': time(13, 30),  # 8:30 AM ET = 13:30 UTC
                'affected_pairs': ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCHF', 'USDCAD']
            },
            # FOMC (8x por ano, horário variável)
            {
                'name': 'FOMC Rate Decision',
                'currency': 'USD',
                'impact': 'HIGH',
                'frequency': 'irregular',
                'dates': [],  # Precisa ser preenchido manualmente
                'time': time(19, 0),  # 2:00 PM ET
                'affected_pairs': ['EURUSD', 'GBPUSD', 'USDJPY', 'GOLD', 'SILVER']
            },
            # CPI (meio do mês, 8:30 AM ET)
            {
                'name': 'US CPI',
                'currency': 'USD',
                'impact': 'HIGH',
                'frequency': 'monthly',
                'day_of_month': 15,  # Aproximadamente
                'time': time(13, 30),
                'affected_pairs': ['EURUSD', 'GBPUSD', 'USDJPY', 'GOLD']
            },
            # ECB (uma quinta-feira por mês)
            {
                'name': 'ECB Rate Decision',
                'currency': 'EUR',
                'impact': 'HIGH',
                'frequency': 'monthly',
                'day_of_month': 'first_thursday',
                'time': time(12, 45),
                'affected_pairs': ['EURUSD', 'EURGBP', 'EURJPY']
            }
        ]
        
        return events
    
    def is_event_approaching(self, current_datetime: datetime,
                            event: Dict) -> Optional[Dict]:
        """
        Verifica se evento está próximo.
        
        Returns:
            {'event_name': str, 'minutes_until': int, 'pairs': list} ou None
        """
        event_time = event['time']
        window = self.event_window_minutes
        
        # Construir datetime do evento
        event_datetime = datetime.combine(current_datetime.date(), event_time)
        
        # Diferença em minutos
        diff = (event_datetime - current_datetime).total_seconds() / 60
        
        # Evento está na janela?
        if 0 < diff <= window:
            return {
                'event_name': event['name'],
                'currency': event['currency'],
                'impact': event['impact'],
                'minutes_until': int(diff),
                'affected_pairs': event['affected_pairs'],
                'event_time': event_datetime
            }
        
        return None
    
    def get_signal(self, symbol: str, current_datetime: datetime,
                  df: pd.DataFrame) -> Dict:
        """
        Gera sinal baseado em eventos próximos.
        
        Returns:
            {
                'signal': 'PRE_EVENT' | 'POST_EVENT' | 'EXIT' | None,
                'event': str,
                'strategy': 'STRADDLE' | 'DIRECTIONAL' | 'FADE',
                'entry_type': 'BREAKOUT' | 'MEAN_REVERSION',
                'minutes_until': int
            }
        """
        signal = None
        event_info = None
        strategy = None
        
        # Verificar eventos próximos
        for event in self.events:
            if symbol in event.get('affected_pairs', []):
                event_check = self.is_event_approaching(current_datetime, event)
                
                if event_check:
                    event_info = event_check
                    break
        
        has_position = symbol in self.positions
        
        if event_info and not has_position:
            # PRE-EVENT POSITIONING
            
            minutes_until = event_info['minutes_until']
            
            if 15 <= minutes_until <= 30:
                # Entrar 15-30 min antes
                
                # Estratégia baseada no tipo de evento
                if event_info['event_name'] in ['Non-Farm Payroll', 'FOMC Rate Decision']:
                    # Eventos de alta volatilidade → Straddle
                    signal = 'PRE_EVENT'
                    strategy = 'STRADDLE'
                    
                    self.positions[symbol] = {
                        'entry_time': current_datetime,
                        'event_time': event_info['event_time'],
                        'event_name': event_info['event_name'],
                        'strategy': strategy
                    }
                
                elif event_info['event_name'] == 'US CPI':
                    # CPI → Direcional (baseado em expectativas)
                    # Em produção, comparar com consensus
                    signal = 'PRE_EVENT'
                    strategy = 'DIRECTIONAL'
                    
                    self.positions[symbol] = {
                        'entry_time': current_datetime,
                        'event_time': event_info['event_time'],
                        'event_name': event_info['event_name'],
                        'strategy': strategy
                    }
        
        elif has_position:
            # POST-EVENT EXIT
            
            position = self.positions[symbol]
            event_time = position['event_time']
            
            minutes_since_event = (current_datetime - event_time).total_seconds() / 60
            
            # Exit após movimento inicial
            if minutes_since_event > self.exit_minutes:
                signal = 'EXIT'
                strategy = 'POST_EVENT'
                del self.positions[symbol]
            
            # Stop loss: evento passou mas posição não se moveu
            elif minutes_since_event > 5:
                # Verificar se houve movimento
                if len(df) > 10:
                    recent_volatility = df['close'].iloc[-10:].std()
                    normal_volatility = df['close'].iloc[-60:-10].std()
                    
                    if recent_volatility < normal_volatility * 1.2:
                        # Não houve movimento esperado
                        signal = 'EXIT'
                        strategy = 'NO_MOVEMENT'
                        del self.positions[symbol]
        
        return {
            'signal': signal,
            'event': event_info['event_name'] if event_info else None,
            'strategy': strategy,
            'minutes_until': event_info['minutes_until'] if event_info else None,
            'impact': event_info['impact'] if event_info else None
        }
    
    def get_next_events(self, symbol: str, 
                       current_datetime: datetime,
                       days_ahead: int = 7) -> List[Dict]:
        """
        Retorna próximos eventos para o símbolo.
        
        Útil para planejar trades.
        """
        upcoming = []
        
        for event in self.events:
            if symbol in event.get('affected_pairs', []):
                # Simplificado: assumir próxima ocorrência
                upcoming.append({
                    'name': event['name'],
                    'currency': event['currency'],
                    'impact': event['impact'],
                    'estimated_date': 'TBD'  # Em produção, calcular data real
                })
        
        return upcoming
    
    def get_event_statistics(self, event_name: str, symbol: str,
                            historical_df: pd.DataFrame) -> Dict:
        """
        Analisa comportamento histórico durante eventos.
        
        Args:
            event_name: Nome do evento
            symbol: Par de moedas
            historical_df: DataFrame com histórico
            
        Returns:
            {
                'avg_move_pips': float,
                'direction_bias': 'UP' | 'DOWN' | 'NEUTRAL',
                'success_rate': float
            }
        """
        # Placeholder - em produção, analisar dados históricos
        return {
            'avg_move_pips': 50,
            'direction_bias': 'NEUTRAL',
            'success_rate': 0.65,
            'avg_duration_minutes': 15
        }


# ============================================================
#  EXEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    strategy = NewsTrading()
    
    # Simular data/hora próxima a NFP
    # NFP: primeira sexta-feira do mês, 8:30 AM ET (13:30 UTC)
    test_datetime = datetime(2024, 6, 7, 13, 10)  # 20 min antes
    
    print("\n📰 NEWS TRADING - Eventos próximos:\n")
    
    # Testar EURUSD
    signal = strategy.get_signal('EURUSD', test_datetime, pd.DataFrame())
    
    if signal['signal']:
        print(f"Sinal: {signal['signal']}")
        print(f"Evento: {signal['event']}")
        print(f"Estratégia: {signal['strategy']}")
        print(f"Minutos até evento: {signal['minutes_until']}")
        print(f"Impacto: {signal['impact']}")
    
    # Próximos eventos
    print("\n📅 Próximos eventos para EURUSD:")
    events = strategy.get_next_events('EURUSD', test_datetime, days_ahead=30)
    
    for event in events:
        print(f"  • {event['name']} ({event['currency']}) - Impacto: {event['impact']}")
