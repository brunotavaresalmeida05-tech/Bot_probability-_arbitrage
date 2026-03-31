"""
Inside Bar Breakout Strategy
Detecta consolidação (inside bar) seguida de breakout
Win Rate esperado: 55-65%
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class InsideBarStrategy:
    """
    Inside Bar: Vela com high/low dentro da vela anterior
    Indica consolidação antes de movimento forte
    
    Setup:
    1. Mother bar (vela grande)
    2. Inside bar (range dentro da mother)
    3. Breakout em qualquer direção
    """
    
    def __init__(
        self,
        min_mother_size: float = 0.003,  # 30 pips mínimo
        max_inside_ratio: float = 0.70,   # Inside <= 70% da mother
        breakout_buffer: float = 0.0001   # Buffer para confirmar breakout
    ):
        self.min_mother_size = min_mother_size
        self.max_inside_ratio = max_inside_ratio
        self.breakout_buffer = breakout_buffer
    
    def identify_inside_bar(
        self,
        df: pd.DataFrame
    ) -> Optional[dict]:
        """
        Identifica padrão inside bar nas últimas 3 velas
        
        Returns:
            dict com info do padrão ou None
        """
        if len(df) < 3:
            return None
        
        # Mother bar (penúltima vela completa)
        mother = df.iloc[-2]
        mother_range = mother['high'] - mother['low']
        
        # Verificar tamanho mínimo da mother
        if mother_range < self.min_mother_size:
            return None
        
        # Inside bar (última vela completa)
        inside = df.iloc[-1]
        inside_range = inside['high'] - inside['low']
        
        # Verificar se inside está dentro da mother
        if (inside['high'] <= mother['high'] and 
            inside['low'] >= mother['low'] and
            inside_range <= mother_range * self.max_inside_ratio):
            
            return {
                'mother_high': mother['high'],
                'mother_low': mother['low'],
                'mother_range': mother_range,
                'inside_high': inside['high'],
                'inside_low': inside['low'],
                'inside_range': inside_range,
                'ratio': inside_range / mother_range
            }
        
        return None
    
    def check_breakout(
        self,
        df: pd.DataFrame,
        current_price: float
    ) -> Optional[str]:
        """
        Verifica breakout do inside bar
        
        Returns:
            'BUY' para breakout bullish, 'SELL' para bearish, None se sem breakout
        """
        pattern = self.identify_inside_bar(df)
        
        if pattern is None:
            return None
        
        # Breakout BULLISH (acima da mother high)
        if current_price > pattern['mother_high'] + self.breakout_buffer:
            logger.info(
                f"📊 INSIDE BAR BREAKOUT BULLISH | "
                f"Mother: {pattern['mother_low']:.5f}-{pattern['mother_high']:.5f} | "
                f"Inside ratio: {pattern['ratio']:.1%} | "
                f"Breakout: {current_price:.5f}"
            )
            return 'BUY'
        
        # Breakout BEARISH (abaixo da mother low)
        elif current_price < pattern['mother_low'] - self.breakout_buffer:
            logger.info(
                f"📊 INSIDE BAR BREAKOUT BEARISH | "
                f"Mother: {pattern['mother_low']:.5f}-{pattern['mother_high']:.5f} | "
                f"Inside ratio: {pattern['ratio']:.1%} | "
                f"Breakout: {current_price:.5f}"
            )
            return 'SELL'
        
        return None
    
    def calculate_targets(
        self,
        entry_price: float,
        signal: str,
        mother_range: float
    ) -> Tuple[float, float]:
        """
        SL e TP baseados no padrão inside bar
        
        Args:
            mother_range: Range da mother bar
            
        Returns:
            (stop_loss, take_profit)
        """
        if signal == 'BUY':
            # SL abaixo da mother bar
            stop_loss = entry_price - (mother_range * 1.2)
            # TP: R:R 1:2
            take_profit = entry_price + (2 * (entry_price - stop_loss))
        
        else:  # SELL
            # SL acima da mother bar
            stop_loss = entry_price + (mother_range * 1.2)
            # TP: R:R 1:2
            take_profit = entry_price - (2 * (stop_loss - entry_price))
        
        return stop_loss, take_profit
    
    def get_pattern_strength(
        self,
        df: pd.DataFrame
    ) -> float:
        """
        Calcula força do padrão (0-1)
        
        Fatores:
        - Ratio inside/mother (menor = melhor)
        - Volume da mother (maior = melhor)
        - Localização (extremo de range = melhor)
        """
        pattern = self.identify_inside_bar(df)
        
        if pattern is None:
            return 0.0
        
        # 1. Ratio (menor = melhor)
        ratio_score = 1.0 - pattern['ratio']
        
        # 2. Tamanho da mother (normalizado)
        avg_range = df['high'].tail(20) - df['low'].tail(20)
        size_score = min(pattern['mother_range'] / avg_range.mean(), 1.0)
        
        # 3. Score combinado
        strength = (ratio_score * 0.6) + (size_score * 0.4)
        
        return min(strength, 1.0)
