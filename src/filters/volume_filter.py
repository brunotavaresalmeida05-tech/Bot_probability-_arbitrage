"""
Volume Filter - Volume Profile Analysis
"""

import numpy as np
import pandas as pd

class VolumeFilter:
    def __init__(self, volume_threshold=1.5):
        self.volume_threshold = volume_threshold
    
    def check_volume(self, df: pd.DataFrame) -> dict:
        """
        Verifica se volume confirma movimento.
        
        Returns: {
            'volume_ok': bool,
            'volume_ratio': float,
            'volume_trend': 'INCREASING' | 'DECREASING' | 'STABLE'
        }
        """
        if 'volume' not in df.columns or df['volume'].sum() == 0:
            # Sem dados de volume
            return {
                'volume_ok': True,  # Não bloquear
                'volume_ratio': 1.0,
                'volume_trend': 'UNKNOWN'
            }
        
        current_vol = df['volume'].iloc[-1]
        avg_vol = df['volume'].iloc[-20:-1].mean()
        
        volume_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0
        
        # Volume crescente nos últimos 5 bars?
        recent_vol = df['volume'].iloc[-5:]
        if recent_vol.is_monotonic_increasing:
            trend = 'INCREASING'
        elif recent_vol.is_monotonic_decreasing:
            trend = 'DECREASING'
        else:
            trend = 'STABLE'
        
        # Volume OK se > threshold
        volume_ok = volume_ratio >= self.volume_threshold
        
        return {
            'volume_ok': volume_ok,
            'volume_ratio': volume_ratio,
            'volume_trend': trend
        }
    
    def find_high_volume_nodes(self, df: pd.DataFrame, bins=20) -> list:
        """
        Encontra níveis de preço com alto volume (POC - Point of Control).
        
        Returns: List de preços com alta liquidez
        """
        if 'volume' not in df.columns:
            return []
        
        # Volume Profile
        price_min = df['low'].min()
        price_max = df['high'].max()
        
        price_bins = np.linspace(price_min, price_max, bins)
        volume_profile = np.zeros(bins)
        
        for i, row in df.iterrows():
            # Encontrar bin do preço
            bin_idx = np.digitize(row['close'], price_bins) - 1
            bin_idx = max(0, min(bin_idx, bins - 1))
            volume_profile[bin_idx] += row.get('volume', 0)
        
        # Top 3 nodes
        top_indices = np.argsort(volume_profile)[-3:]
        high_volume_prices = [price_bins[i] for i in top_indices]
        
        return sorted(high_volume_prices)
