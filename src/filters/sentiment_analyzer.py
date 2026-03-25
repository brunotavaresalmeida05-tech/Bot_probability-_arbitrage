"""
Sentiment Analyzer - Risk-On/Risk-Off Detection
"""

import numpy as np
import pandas as pd

class SentimentAnalyzer:
    def __init__(self):
        self.risk_on_assets = ['AUDUSD', 'NZDUSD', 'BTCUSD', 'ETHUSD']
        self.safe_haven_assets = ['GOLD', 'SILVER', 'USDJPY', 'USDCHF']
    
    def detect_sentiment(self, price_data: dict) -> dict:
        """
        Analisa movimento de risk-on vs safe-haven.
        
        Args:
            price_data: {symbol: {'close': price, 'change_pct': float}}
        
        Returns: {
            'sentiment': 'RISK_ON' | 'RISK_OFF' | 'NEUTRAL',
            'confidence': float,
            'risk_on_score': float,
            'safe_haven_score': float
        }
        """
        # Calcular scores
        risk_on_score = self._calculate_score(
            price_data, 
            self.risk_on_assets
        )
        
        safe_haven_score = self._calculate_score(
            price_data,
            self.safe_haven_assets
        )
        
        # Determinar sentimento
        diff = risk_on_score - safe_haven_score
        
        if diff > 1.0:
            sentiment = 'RISK_ON'
            confidence = min(diff / 2, 1.0)
        elif diff < -1.0:
            sentiment = 'RISK_OFF'
            confidence = min(abs(diff) / 2, 1.0)
        else:
            sentiment = 'NEUTRAL'
            confidence = 0.5
        
        return {
            'sentiment': sentiment,
            'confidence': confidence,
            'risk_on_score': risk_on_score,
            'safe_haven_score': safe_haven_score
        }
    
    def _calculate_score(self, price_data, assets):
        """Média da performance dos ativos."""
        changes = []
        for asset in assets:
            if asset in price_data:
                changes.append(price_data[asset].get('change_pct', 0))
        
        return np.mean(changes) if changes else 0.0
    
    def adjust_strategy(self, sentiment: str, strategy: str) -> dict:
        """
        Ajusta estratégia baseado em sentimento.
        
        Returns: {
            'use_strategy': bool,
            'adjust_size': float (multiplier)
        }
        """
        adjustments = {
            ('RISK_ON', 'trend'): {'use': True, 'size': 1.2},
            ('RISK_ON', 'breakout'): {'use': True, 'size': 1.1},
            ('RISK_OFF', 'volatility'): {'use': True, 'size': 1.3},
            ('RISK_OFF', 'mean_reversion'): {'use': True, 'size': 1.1},
            ('NEUTRAL', 'pairs'): {'use': True, 'size': 1.0},
        }
        
        key = (sentiment, strategy)
        if key in adjustments:
            return {
                'use_strategy': adjustments[key]['use'],
                'adjust_size': adjustments[key]['size']
            }
        
        return {'use_strategy': True, 'adjust_size': 1.0}
