"""
Position Management
- Partial closes
- Scale in/out
- Pyramiding
"""
from datetime import datetime

class PositionManager:
    def __init__(self):
        self.positions = {}  # {symbol: {entries: [], avg_price: float, direction: str}}
        self.pyramiding_tracker = {}
        
        # Pyramiding config
        self.max_adds = 3  # Máximo 3 adições
        self.min_profit_pct = 0.02  # 2% lucro entre adds
        self.add_size_multiplier = 0.5  # Cada add = 50% do inicial
    
    def open_position(self, 
                     symbol: str,
                     lot_size: float,
                     entry_price: float,
                     direction: str):
        """Registra abertura de posição."""
        if symbol not in self.positions:
            self.positions[symbol] = {
                'entries': [],
                'total_lots': 0.0,
                'avg_price': 0.0,
                'direction': direction
            }
        
        pos = self.positions[symbol]
        pos['entries'].append({
            'lot': lot_size,
            'price': entry_price,
            'time': datetime.now()
        })
        
        # Recalcular média
        total_value = sum(e['lot'] * e['price'] for e in pos['entries'])
        pos['total_lots'] = sum(e['lot'] for e in pos['entries'])
        pos['avg_price'] = total_value / pos['total_lots']
    
    def can_add_to_position(self, symbol, current_price, avg_price):
        """
        Permite adicionar se:
        1. Menos de max_adds
        2. Lucro > min_profit_pct
        """
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]

        if len(pos['entries']) >= self.max_adds:
            return False

        # Calcular lucro atual
        if pos['direction'] in ['BUY', 'LONG']:
            profit_pct = (current_price - avg_price) / avg_price
        else:
            profit_pct = (avg_price - current_price) / avg_price
        
        return profit_pct >= self.min_profit_pct

    def register_add(self, symbol: str, lot: float):
        """Registra add de pyramiding"""
        if symbol not in self.pyramiding_tracker:
            self.pyramiding_tracker[symbol] = {'adds': 0, 'total_lot': lot}
        self.pyramiding_tracker[symbol]['adds'] += 1
        self.pyramiding_tracker[symbol]['total_lot'] += lot
    
    def add_to_position(self, symbol, price, initial_lot):
        """
        Adiciona à posição vencedora
        """
        if symbol not in self.positions:
            return 0
            
        pos = self.positions[symbol]
        
        # Lot reduzido (50% do inicial)
        add_lot = initial_lot * self.add_size_multiplier
        
        pos['entries'].append({
            'price': price,
            'lot': add_lot,
            'time': datetime.now()
        })
        
        # Recalcular avg price
        pos['total_lots'] = sum(e['lot'] for e in pos['entries'])
        weighted_price = sum(e['price'] * e['lot'] for e in pos['entries'])
        pos['avg_price'] = weighted_price / pos['total_lots']
        
        return add_lot
    
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
        
        for entry in pos['entries'][:]:
            if remaining <= 0:
                break
            
            if entry['lot'] <= remaining:
                # Fechar completamente este lote
                remaining -= entry['lot']
                pos['entries'].remove(entry)
            else:
                # Fechar parcialmente este lote
                entry['lot'] -= remaining
                remaining = 0
        
        # Recalcular
        if pos['entries']:
            total_value = sum(e['lot'] * e['price'] for e in pos['entries'])
            pos['total_lots'] = sum(e['lot'] for e in pos['entries'])
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

    def get_position_adds(self, symbol: str) -> int:
        """
        Retorna número de adds (pyramiding) já feitos numa posição
        """
        if symbol not in self.pyramiding_tracker:
            return 0
        
        return self.pyramiding_tracker[symbol].get('adds', 0)
    
    def track_pyramiding_add(self, symbol: str):
        """Registra um add de pyramiding"""
        if symbol not in self.pyramiding_tracker:
            self.pyramiding_tracker[symbol] = {'adds': 0}
        
        self.pyramiding_tracker[symbol]['adds'] += 1
    
    def reset_pyramiding(self, symbol: str):
        """Reset tracking quando posição fecha"""
        if symbol in self.pyramiding_tracker:
            del self.pyramiding_tracker[symbol]
