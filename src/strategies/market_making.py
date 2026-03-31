"""
Market Making Strategy
Bid/ask spread capture
"""

class MarketMakingStrategy:
    def __init__(self, spread_target=0.0001):
        self.name = "market_making"
        self.spread_target = spread_target
        
    def calculate_fair_value(self, bid, ask):
        return (bid + ask) / 2
        
    def calculate_quantity(self):
        # Placeholder para cálculo de quantidade baseado em risco/capital
        return 0.01

    def place_orders(self, symbol, fair_value):
        """
        Coloca ordens limite nos dois lados
        """
        spread_half = self.spread_target / 2
        
        buy_price = fair_value - spread_half
        sell_price = fair_value + spread_half
        
        return {
            'buy_limit': buy_price,
            'sell_limit': sell_price,
            'quantity': self.calculate_quantity()
        }
