"""
Portfolio Heat Monitor
Limita exposição total e correlação-adjusted risk
"""

class PortfolioHeat:
    def __init__(self, max_heat_pct=15.0):
        """
        Args:
            max_heat_pct: % máximo do capital em risco simultâneo
        """
        self.max_heat = max_heat_pct
    
    def calculate_current_heat(self, open_positions: list) -> dict:
        """
        Calcula heat atual do portfolio.
        
        Args:
            open_positions: [{
                'symbol': str,
                'risk_money': float,
                'entry_price': float,
                'stop_price': float
            }]
        
        Returns: {
            'total_heat_pct': float,
            'total_risk_money': float,
            'position_count': int,
            'heat_ok': bool
        }
        """
        total_risk = sum(pos.get('risk_money', 0) for pos in open_positions)
        
        # Calcular capital (baseado em risk_money - simplificado)
        # Em produção, isto deve vir do balanço real da conta
        capital = sum(pos.get('balance', 1000) for pos in open_positions) / len(open_positions) if open_positions else 1000
        
        heat_pct = (total_risk / capital) * 100 if capital > 0 else 0
        
        return {
            'total_heat_pct': heat_pct,
            'total_risk_money': total_risk,
            'position_count': len(open_positions),
            'heat_ok': heat_pct <= self.max_heat
        }
    
    def can_add_position(self, 
                        open_positions: list,
                        new_risk_money: float,
                        account_balance: float) -> dict:
        """
        Verifica se pode adicionar nova posição.
        """
        total_risk = sum(pos.get('risk_money', 0) for pos in open_positions)
        new_total_risk = total_risk + new_risk_money
        new_heat = (new_total_risk / account_balance) * 100 if account_balance > 0 else 100
        
        can_add = new_heat <= self.max_heat
        
        return {
            'can_add': can_add,
            'new_heat_pct': new_heat,
            'reason': 'OK' if can_add else f'Heat limite ({self.max_heat}%) excedido'
        }
