"""
Correlation Filter - Limita exposição em ativos correlacionados
"""

import numpy as np
import pandas as pd
from typing import Dict, List

class CorrelationFilter:
    def __init__(self, max_correlated_positions=3, correlation_threshold=0.7):
        self.max_correlated = max_correlated_positions
        self.corr_threshold = correlation_threshold
        self.correlation_groups = {
            'USD_STRONG': ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD'],
            'JPY_PAIRS': ['USDJPY', 'EURJPY', 'GBPJPY', 'AUDJPY'],
            'RISK_ON': ['AUDUSD', 'NZDUSD', 'BTCUSD', 'ETHUSD'],
            'SAFE_HAVEN': ['GOLD', 'SILVER', 'USDCHF', 'USDJPY']
        }
    
    def check_exposure(self, symbol: str, open_positions: List[str]) -> dict:
        """
        Verifica se adicionar este símbolo cria over-exposure.
        
        Returns: {
            'allowed': bool,
            'reason': str,
            'correlated_count': int
        }
        """
        # Encontrar grupo do símbolo
        symbol_groups = [
            name for name, symbols in self.correlation_groups.items()
            if symbol in symbols
        ]
        
        if not symbol_groups:
            return {'allowed': True}
        
        # Contar posições correlacionadas
        correlated_count = 0
        for pos_symbol in open_positions:
            for group in symbol_groups:
                if pos_symbol in self.correlation_groups[group]:
                    correlated_count += 1
                    break
        
        if correlated_count >= self.max_correlated:
            return {
                'allowed': False,
                'reason': f'Over-exposure: {correlated_count} posições correlacionadas',
                'correlated_count': correlated_count
            }
        
        return {'allowed': True, 'correlated_count': correlated_count}
