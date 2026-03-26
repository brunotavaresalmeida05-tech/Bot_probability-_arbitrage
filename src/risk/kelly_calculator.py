"""
Kelly Criterion - Optimal Position Sizing
Formula: f* = (p*b - q) / b
onde:
  f* = fração do capital
  p = win rate
  b = payoff ratio (avg win / avg loss)
  q = 1 - p
"""

import numpy as np

class KellyCalculator:
    def __init__(self, fractional_kelly=0.25):
        """
        Args:
            fractional_kelly: Fração do Kelly (0.25 = Quarter Kelly)
                             Mais conservador que Full Kelly
        """
        self.fraction = fractional_kelly
    
    def calculate_position_size(self, 
                               win_rate: float,
                               avg_win: float,
                               avg_loss: float,
                               capital: float) -> dict:
        """
        Calcula tamanho ótimo da posição.
        
        Returns: {
            'kelly_fraction': float,
            'position_size': float (em €),
            'risk_pct': float,
            'recommendation': str
        }
        """
        if avg_loss == 0 or win_rate <= 0:
            return {
                'kelly_fraction': 0.0,
                'position_size': 0.0,
                'risk_pct': 0.0,
                'recommendation': 'SKIP - Dados insuficientes'
            }
        
        # Payoff ratio
        b = abs(avg_win / avg_loss)
        
        # Win/Loss probabilities
        p = win_rate
        q = 1 - p
        
        # Kelly formula
        kelly = (p * b - q) / b
        
        # Se negativo, não apostar
        if kelly <= 0:
            return {
                'kelly_fraction': 0.0,
                'position_size': 0.0,
                'risk_pct': 0.0,
                'recommendation': 'SKIP - Edge negativo'
            }
        
        # Aplicar fração (Quarter Kelly = mais seguro)
        adjusted_kelly = kelly * self.fraction
        
        # Limitar a 10% max
        adjusted_kelly = min(adjusted_kelly, 0.10)
        
        position_size = capital * adjusted_kelly
        
        # Recomendação
        if adjusted_kelly < 0.01:
            rec = 'VERY SMALL'
        elif adjusted_kelly < 0.03:
            rec = 'SMALL'
        elif adjusted_kelly < 0.06:
            rec = 'MEDIUM'
        else:
            rec = 'LARGE'
        
        return {
            'kelly_fraction': adjusted_kelly,
            'position_size': position_size,
            'risk_pct': adjusted_kelly * 100,
            'recommendation': rec
        }
    
    def update_from_trades(self, trades: list) -> dict:
        """
        Calcula Kelly baseado em histórico de trades.
        
        Args:
            trades: [{'pnl': float, 'symbol': str}, ...]
        """
        if not trades:
            return {'win_rate': 0.5, 'avg_win': 0, 'avg_loss': 0}
        
        wins = [t['pnl'] for t in trades if t['pnl'] > 0]
        losses = [abs(t['pnl']) for t in trades if t['pnl'] < 0]
        
        win_rate = len(wins) / len(trades) if trades else 0.5
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 1
        
        return {
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_trades': len(trades)
        }
