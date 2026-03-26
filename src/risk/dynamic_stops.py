"""
Dynamic Stop Loss Manager
- Trailing stops
- Time-based exits
- Volatility-adjusted stops
"""

from datetime import datetime, timedelta
import numpy as np

class DynamicStops:
    def __init__(self):
        self.positions = {}  # {symbol: {entry_time, entry_price, stop, etc}}
    
    def calculate_stop(self, 
                      symbol: str,
                      entry_price: float,
                      direction: str,
                      atr: float,
                      strategy: str) -> dict:
        """
        Calcula stop loss inicial.
        
        Args:
            direction: 'LONG' ou 'SHORT'
            atr: Average True Range
            strategy: Nome da estratégia
        
        Returns: {
            'initial_stop': float,
            'stop_distance': float,
            'atr_multiple': float
        }
        """
        # Multiplier por estratégia
        atr_multiples = {
            'mean_reversion': 2.0,  # Stops apertados
            'trend': 3.0,           # Stops largos
            'breakout': 2.5,
            'pairs': 1.5,
            'volatility': 2.0,
            'news': 1.5             # Muito apertado
        }
        
        mult = atr_multiples.get(strategy, 2.0)
        stop_distance = atr * mult
        
        if direction == 'LONG':
            initial_stop = entry_price - stop_distance
        else:  # SHORT
            initial_stop = entry_price + stop_distance
        
        # Registar posição
        self.positions[symbol] = {
            'entry_time': datetime.now(),
            'entry_price': entry_price,
            'direction': direction,
            'stop': initial_stop,
            'trailing_stop': initial_stop,
            'highest_price': entry_price,
            'lowest_price': entry_price,
            'strategy': strategy
        }
        
        return {
            'initial_stop': initial_stop,
            'stop_distance': stop_distance,
            'atr_multiple': mult
        }
    
    def update_trailing_stop(self,
                            symbol: str,
                            current_price: float,
                            atr: float) -> dict:
        """
        Atualiza trailing stop.
        
        Returns: {
            'new_stop': float,
            'stop_hit': bool,
            'time_exit': bool
        }
        """
        if symbol not in self.positions:
            return {'stop_hit': False}
        
        pos = self.positions[symbol]
        direction = pos['direction']
        
        # Update high/low
        pos['highest_price'] = max(pos['highest_price'], current_price)
        pos['lowest_price'] = min(pos['lowest_price'], current_price)
        
        # Calcular novo trailing stop
        if direction == 'LONG':
            # Trail se preço subiu
            new_trail = pos['highest_price'] - (atr * 2.5)
            
            # Só atualizar se trailing stop subiu
            if new_trail > pos['trailing_stop']:
                pos['trailing_stop'] = new_trail
            
            # Check se stop foi hit
            stop_hit = current_price <= pos['trailing_stop']
        
        else:  # SHORT
            new_trail = pos['lowest_price'] + (atr * 2.5)
            
            if new_trail < pos['trailing_stop']:
                pos['trailing_stop'] = new_trail
            
            stop_hit = current_price >= pos['trailing_stop']
        
        # Time-based exit (24h max para mean reversion)
        time_exit = False
        if pos['strategy'] == 'mean_reversion':
            hours_held = (datetime.now() - pos['entry_time']).total_seconds() / 3600
            if hours_held > 24:
                time_exit = True
        
        return {
            'new_stop': pos['trailing_stop'],
            'stop_hit': stop_hit,
            'time_exit': time_exit,
            'hours_held': (datetime.now() - pos['entry_time']).total_seconds() / 3600
        }
    
    def should_exit(self, symbol: str, current_price: float, atr: float) -> dict:
        """
        Verifica todos os critérios de saída.
        """
        update = self.update_trailing_stop(symbol, current_price, atr)
        
        exit_signal = False
        exit_reason = None
        
        if update.get('stop_hit'):
            exit_signal = True
            exit_reason = 'TRAILING_STOP'
        
        elif update.get('time_exit'):
            exit_signal = True
            exit_reason = 'TIME_BASED'
        
        return {
            'exit': exit_signal,
            'reason': exit_reason,
            'stop_price': update.get('new_stop')
        }
    
    def close_position(self, symbol: str):
        """Remove posição do tracking."""
        if symbol in self.positions:
            del self.positions[symbol]
