"""
Fibonacci Retracements Strategy
Identifica níveis de retração Fibonacci e testa reversões
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)


class FibonacciStrategy:
    """
    Fibonacci Retracements em swing high/low
    
    Níveis principais:
    - 23.6% (fraco)
    - 38.2% (moderado)
    - 50.0% (psicológico)
    - 61.8% (golden ratio - FORTE)
    - 78.6% (muito forte)
    
    Trade quando preço testa nível + confirmação
    """
    
    def __init__(
        self,
        lookback_swing: int = 50,          # Bars para encontrar swing
        fib_tolerance: float = 0.0005,     # 5 pips tolerância ao nível
        key_levels: List[float] = None     # Níveis Fib a usar
    ):
        self.lookback_swing = lookback_swing
        self.fib_tolerance = fib_tolerance
        
        # Níveis Fibonacci (default: 38.2, 50, 61.8)
        if key_levels is None:
            self.key_levels = [0.382, 0.500, 0.618]
        else:
            self.key_levels = key_levels
    
    def find_swing_points(
        self,
        df: pd.DataFrame
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Encontra último swing high e swing low
        
        Returns:
            (swing_high, swing_low)
        """
        if len(df) < self.lookback_swing:
            return None, None
        
        recent = df.tail(self.lookback_swing)
        
        swing_high = recent['high'].max()
        swing_low = recent['low'].min()
        
        return swing_high, swing_low
    
    def calculate_fib_levels(
        self,
        swing_high: float,
        swing_low: float,
        trend: str = 'UPTREND'
    ) -> dict:
        """
        Calcula níveis Fibonacci
        
        Args:
            trend: 'UPTREND' (retração de alta) ou 'DOWNTREND' (retração de baixa)
            
        Returns:
            dict com níveis Fib
        """
        swing_range = swing_high - swing_low
        
        levels = {}
        
        if trend == 'UPTREND':
            # Retração de uptrend (níveis abaixo do high)
            for fib in self.key_levels:
                levels[fib] = swing_high - (swing_range * fib)
        else:  # DOWNTREND
            # Retração de downtrend (níveis acima do low)
            for fib in self.key_levels:
                levels[fib] = swing_low + (swing_range * fib)
        
        return levels
    
    def check_fib_test(
        self,
        df: pd.DataFrame,
        current_price: float
    ) -> Optional[dict]:
        """
        Verifica se preço está testando nível Fibonacci
        
        Returns:
            dict com info do teste ou None
        """
        swing_high, swing_low = self.find_swing_points(df)
        
        if swing_high is None or swing_low is None:
            return None
        
        # Determinar trend (20-bar MA)
        if len(df) >= 20:
            ma20 = df['close'].tail(20).mean()
            is_uptrend = current_price > ma20
        else:
            return None
        
        trend = 'UPTREND' if is_uptrend else 'DOWNTREND'
        
        # Calcular níveis Fib
        fib_levels = self.calculate_fib_levels(swing_high, swing_low, trend)
        
        # Verificar se preço testa algum nível
        for fib_ratio, fib_price in fib_levels.items():
            distance = abs(current_price - fib_price)
            
            if distance <= self.fib_tolerance:
                return {
                    'level': fib_ratio,
                    'price': fib_price,
                    'trend': trend,
                    'swing_high': swing_high,
                    'swing_low': swing_low,
                    'distance': distance
                }
        
        return None
    
    def check_signal(
        self,
        df: pd.DataFrame,
        current_price: float,
        z_score: float
    ) -> Optional[str]:
        """
        Verifica sinal de Fibonacci + confirmação
        
        Confirmações:
        - Z-score extremo
        - Vela de rejeição (pin bar, etc)
        
        Returns:
            'BUY' ou 'SELL' ou None
        """
        fib_test = self.check_fib_test(df, current_price)
        
        if fib_test is None:
            return None
        
        # UPTREND: rejeição em Fib = BUY
        if fib_test['trend'] == 'UPTREND' and z_score < -1.0:
            # Verificar rejeição (low testou Fib, close acima)
            last_candle = df.iloc[-1]
            
            if (last_candle['low'] <= fib_test['price'] and
                last_candle['close'] > fib_test['price']):
                
                logger.info(
                    f"📐 FIB BOUNCE (UPTREND) | "
                    f"Level: {fib_test['level']:.1%} ({fib_test['price']:.5f}) | "
                    f"Z={z_score:.2f} | "
                    f"Swing: {fib_test['swing_low']:.5f} → {fib_test['swing_high']:.5f}"
                )
                return 'BUY'
        
        # DOWNTREND: rejeição em Fib = SELL
        elif fib_test['trend'] == 'DOWNTREND' and z_score > 1.0:
            # Verificar rejeição (high testou Fib, close abaixo)
            last_candle = df.iloc[-1]
            
            if (last_candle['high'] >= fib_test['price'] and
                last_candle['close'] < fib_test['price']):
                
                logger.info(
                    f"📐 FIB REJECTION (DOWNTREND) | "
                    f"Level: {fib_test['level']:.1%} ({fib_test['price']:.5f}) | "
                    f"Z={z_score:.2f} | "
                    f"Swing: {fib_test['swing_low']:.5f} → {fib_test['swing_high']:.5f}"
                )
                return 'SELL'
        
        return None
    
    def calculate_targets(
        self,
        entry_price: float,
        signal: str,
        swing_high: float,
        swing_low: float,
        fib_level: float
    ) -> Tuple[float, float]:
        """
        SL e TP baseados em Fibonacci
        
        Returns:
            (stop_loss, take_profit)
        """
        swing_range = swing_high - swing_low
        
        if signal == 'BUY':
            # SL: próximo nível Fib abaixo ou swing low
            if fib_level == 0.618:
                stop_loss = swing_low - (0.05 * swing_range)
            else:
                stop_loss = entry_price - (0.1 * swing_range)
            
            # TP: swing high ou próximo nível Fib acima
            take_profit = swing_high
        
        else:  # SELL
            # SL: próximo nível Fib acima ou swing high
            if fib_level == 0.618:
                stop_loss = swing_high + (0.05 * swing_range)
            else:
                stop_loss = entry_price + (0.1 * swing_range)
            
            # TP: swing low ou próximo nível Fib abaixo
            take_profit = swing_low
        
        return stop_loss, take_profit
    
    def get_level_strength(
        self,
        fib_level: float
    ) -> float:
        """
        Força do nível Fibonacci (0-1)
        
        61.8% (golden ratio) = mais forte
        50% = moderado
        38.2% = fraco
        """
        strength_map = {
            0.236: 0.3,
            0.382: 0.5,
            0.500: 0.7,
            0.618: 1.0,  # Golden ratio
            0.786: 0.9
        }
        
        return strength_map.get(fib_level, 0.5)
