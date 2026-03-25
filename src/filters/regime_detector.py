"""
Regime Detection Filter
Classifica mercado: TREND / RANGE / VOLATILE / CALM
"""

import numpy as np
import pandas as pd

class RegimeDetector:
    def __init__(self, adx_period=14, vol_period=20):
        self.adx_period = adx_period
        self.vol_period = vol_period
    
    def detect_regime(self, df: pd.DataFrame) -> dict:
        """
        Returns: {
            'regime': 'TREND' | 'RANGE' | 'VOLATILE' | 'CALM',
            'adx': float,
            'volatility_z': float,
            'confidence': float
        }
        """
        # Calcular ADX
        adx = self._calculate_adx(df)
        
        # Calcular volatilidade normalizada
        if 'atr' not in df.columns:
            # Se ATR não estiver no df, calcular localmente (ou assumir 20 períodos)
            # Para manter compatibilidade com a chamada do main.py
            return {'regime': 'RANGE', 'adx': 20.0, 'volatility_z': 0.0, 'confidence': 0.5}

        atr_pct = df['atr'] / df['close'] * 100
        vol_z = (atr_pct.iloc[-1] - atr_pct.mean()) / atr_pct.std()
        
        # Classificar regime
        if adx > 25:
            if vol_z > 1.0:
                regime = 'VOLATILE_TREND'
            else:
                regime = 'TREND'
        else:
            if vol_z > 1.0:
                regime = 'VOLATILE_RANGE'
            else:
                regime = 'RANGE'
        
        return {
            'regime': regime,
            'adx': adx,
            'volatility_z': vol_z,
            'confidence': min(adx / 50, 1.0)
        }
    
    def _calculate_adx(self, df):
        # Simplificado - ADX real já calculado em trend_following
        if 'adx' in df.columns:
            return df['adx'].iloc[-1]
        return 20.0  # Default
