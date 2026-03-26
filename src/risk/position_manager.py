"""
Position Management
- Partial closes
- Scale in/out
- Pyramiding
"""
from datetime import datetime

class PositionManager:
    def __init__(self):
        self.positions = {}  # {symbol: {lots: [], avg_price: float, direction: str}}
    
    def open_position(self, 
                     symbol: str,
                     lot_size: float,
                     entry_price: float,
                     direction: str):
        """Registra abertura de posição."""
        if symbol not in self.positions:
            self.positions[symbol] = {
                'lots': [],
                'total_lots': 0.0,
                'avg_price': 0.0,
                'direction': direction
            }
        
        pos = self.positions[symbol]
        pos['lots'].append({
            'size': lot_size,
            'price': entry_price,
            'opened_at': datetime.now()
        })
        
        # Recalcular média
        total_value = sum(l['size'] * l['price'] for l in pos['lots'])
        pos['total_lots'] = sum(l['size'] for l in pos['lots'])
        pos['avg_price'] = total_value / pos['total_lots']
    
    def can_pyramid(self, 
                   symbol: str,
                   current_price: float,
                   min_profit_pct=2.0) -> dict:
        """
        Verifica se pode adicionar à posição (pyramiding).
        
        Rules:
        - Posição atual em lucro > min_profit_pct
        - Máximo 3 entradas
        """
        if symbol not in self.positions:
            return {'can_pyramid': False, 'reason': 'No position'}
        
        pos = self.positions[symbol]
        
        # Max 3 entradas
        if len(pos['lots']) >= 3:
            return {'can_pyramid': False, 'reason': 'Max entries (3)'}
        
        # Calcular P&L atual
        if pos['direction'] == 'LONG':
            pnl_pct = ((current_price - pos['avg_price']) 
                      / pos['avg_price'] * 100)
        else:
            pnl_pct = ((pos['avg_price'] - current_price) 
                      / pos['avg_price'] * 100)
        
        if pnl_pct < min_profit_pct:
            return {
                'can_pyramid': False, 
                'reason': f'Profit {pnl_pct:.1f}% < {min_profit_pct}%'
            }
        
        return {
            'can_pyramid': True,
            'current_profit_pct': pnl_pct,
            'entry_count': len(pos['lots'])
        }
    
    def partial_close(self,
                     symbol: str,
                     close_pct=50.0) -> dict:
        """
        Fecha parcialmente a posição.
        
        Args:
            close_pct: % da posição a fechar (50 = metade)
        """
        if symbol not in self.positions:
            return {'closed_lots': 0.0}
        
        pos = self.positions[symbol]
        total = pos['total_lots']
        close_lots = total * (close_pct / 100)
        
        # Fechar FIFO (First In First Out)
        remaining = close_lots
        
        for lot in pos['lots'][:]:
            if remaining <= 0:
                break
            
            if lot['size'] <= remaining:
                # Fechar completamente este lote
                remaining -= lot['size']
                pos['lots'].remove(lot)
            else:
                # Fechar parcialmente este lote
                lot['size'] -= remaining
                remaining = 0
        
        # Recalcular
        if pos['lots']:
            total_value = sum(l['size'] * l['price'] for l in pos['lots'])
            pos['total_lots'] = sum(l['size'] for l in pos['lots'])
            pos['avg_price'] = total_value / pos['total_lots']
        else:
            del self.positions[symbol]
        
        return {
            'closed_lots': close_lots,
            'remaining_lots': pos['total_lots'] if symbol in self.positions else 0
        }
    
    def scale_out_on_profit(self,
                           symbol: str,
                           current_price: float,
                           profit_targets: list = [3.0, 5.0, 8.0]) -> dict:
        """
        Scale out automático em níveis de lucro.
        
        Args:
            profit_targets: [3%, 5%, 8%] → fechar uma parte em cada nível
        """
        if symbol not in self.positions:
            return {'action': None}
        
        pos = self.positions[symbol]
        
        # Calcular lucro atual
        if pos['direction'] == 'LONG':
            profit_pct = ((current_price - pos['avg_price']) 
                         / pos['avg_price'] * 100)
        else:
            profit_pct = ((pos['avg_price'] - current_price) 
                         / pos['avg_price'] * 100)
        
        # Verificar targets
        for target in profit_targets:
            if profit_pct >= target:
                # Fechar uma fração proporcional da posição
                close_pct = 100 / len(profit_targets)
                result = self.partial_close(symbol, close_pct)
                
                return {
                    'action': 'SCALE_OUT',
                    'profit_target': target,
                    'closed_pct': close_pct,
                    'closed_lots': result['closed_lots']
                }
        
        return {'action': None}
