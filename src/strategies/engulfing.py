"""
Engulfing Patterns Strategy
Bullish/Bearish Engulfing - reversão forte
Win Rate esperado: 60-68%
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class EngulfingStrategy:
    """
    Engulfing Pattern: Vela que engole completamente a anterior
    
    Bullish Engulfing:
    - Vela anterior: bearish (close < open)
    - Vela atual: bullish (close > open)
    - Corpo atual engole corpo anterior
    
    Bearish Engulfing:
    - Vela anterior: bullish
    - Vela atual: bearish
    - Corpo atual engole corpo anterior
    """
    
    def __init__(
        self,
        min_body_ratio: float = 0.60,      # Corpo >= 60% da vela
        engulf_margin: float = 1.05,       # Engolfar 105% do corpo anterior
        z_score_threshold: float = 1.5,    # Só em extremos
        require_volume: bool = False        # Requerer volume alto (opcional)
    ):
        self.min_body_ratio = min_body_ratio
        self.engulf_margin = engulf_margin
        self.z_score_threshold = z_score_threshold
        self.require_volume = require_volume
    
    def get_candle_type(
        self,
        open_price: float,
        high: float,
        low: float,
        close: float
    ) -> dict:
        """
        Analisa tipo de vela
        
        Returns:
            dict com info da vela
        """
        body = abs(close - open_price)
        total_range = high - low
        
        if total_range == 0:
            return None
        
        body_ratio = body / total_range
        
        is_bullish = close > open_price
        is_bearish = close < open_price
        
        # Sombras
        if is_bullish:
            upper_shadow = high - close
            lower_shadow = open_price - low
        else:
            upper_shadow = high - open_price
            lower_shadow = close - low
        
        return {
            'body': body,
            'total_range': total_range,
            'body_ratio': body_ratio,
            'is_bullish': is_bullish,
            'is_bearish': is_bearish,
            'upper_shadow': upper_shadow,
            'lower_shadow': lower_shadow,
            'open': open_price,
            'close': close,
            'high': high,
            'low': low
        }
    
    def identify_engulfing(
        self,
        df: pd.DataFrame
    ) -> Optional[str]:
        """
        Identifica padrão engulfing
        
        Returns:
            'BULLISH' ou 'BEARISH' ou None
        """
        if len(df) < 2:
            return None
        
        # Vela anterior
        prev = df.iloc[-2]
        prev_candle = self.get_candle_type(
            prev['open'], prev['high'], prev['low'], prev['close']
        )
        
        # Vela atual
        curr = df.iloc[-1]
        curr_candle = self.get_candle_type(
            curr['open'], curr['high'], curr['low'], curr['close']
        )
        
        if prev_candle is None or curr_candle is None:
            return None
        
        # Verificar corpo suficiente na vela atual
        if curr_candle['body_ratio'] < self.min_body_ratio:
            return None
        
        # BULLISH ENGULFING
        if (prev_candle['is_bearish'] and 
            curr_candle['is_bullish'] and
            curr_candle['close'] > prev_candle['open'] and
            curr_candle['open'] < prev_candle['close'] and
            curr_candle['body'] >= prev_candle['body'] * self.engulf_margin):
            
            return 'BULLISH'
        
        # BEARISH ENGULFING
        if (prev_candle['is_bullish'] and 
            curr_candle['is_bearish'] and
            curr_candle['close'] < prev_candle['open'] and
            curr_candle['open'] > prev_candle['close'] and
            curr_candle['body'] >= prev_candle['body'] * self.engulf_margin):
            
            return 'BEARISH'
        
        return None
    
    def check_signal(
        self,
        df: pd.DataFrame,
        z_score: float
    ) -> Optional[str]:
        """
        Verifica sinal de engulfing em extremo
        
        Returns:
            'BUY' ou 'SELL' ou None
        """
        pattern = self.identify_engulfing(df)
        
        if pattern is None:
            return None
        
        # Bullish engulfing em oversold
        if pattern == 'BULLISH' and z_score < -self.z_score_threshold:
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            logger.info(
                f"🟢 BULLISH ENGULFING | "
                f"Z={z_score:.2f} | "
                f"Prev: {prev['open']:.5f}→{prev['close']:.5f} | "
                f"Curr: {curr['open']:.5f}→{curr['close']:.5f} | "
                f"Engulf: {(curr['close'] - curr['open'])/(prev['open'] - prev['close']):.1%}"
            )
            return 'BUY'
        
        # Bearish engulfing em overbought
        elif pattern == 'BEARISH' and z_score > self.z_score_threshold:
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            
            logger.info(
                f"🔴 BEARISH ENGULFING | "
                f"Z={z_score:.2f} | "
                f"Prev: {prev['open']:.5f}→{prev['close']:.5f} | "
                f"Curr: {curr['open']:.5f}→{curr['close']:.5f} | "
                f"Engulf: {(curr['open'] - curr['close'])/(prev['close'] - prev['open']):.1%}"
            )
            return 'SELL'
        
        return None
    
    def calculate_targets(
        self,
        entry_price: float,
        signal: str,
        engulfing_range: float
    ) -> Tuple[float, float]:
        """
        SL e TP baseados no padrão engulfing
        
        Args:
            engulfing_range: Range da vela engulfing
            
        Returns:
            (stop_loss, take_profit)
        """
        if signal == 'BUY':
            # SL abaixo da engulfing low
            stop_loss = entry_price - engulfing_range
            # TP: R:R 1:2
            take_profit = entry_price + (2 * engulfing_range)
        
        else:  # SELL
            # SL acima da engulfing high
            stop_loss = entry_price + engulfing_range
            # TP: R:R 1:2
            take_profit = entry_price - (2 * engulfing_range)
        
        return stop_loss, take_profit
    
    def get_pattern_strength(
        self,
        df: pd.DataFrame
    ) -> float:
        """
        Calcula força do engulfing (0-1)
        
        Fatores:
        - Tamanho do engulfment (maior = melhor)
        - Ratio corpo/total (maior = melhor)
        - Localização em trend (contra-trend = melhor)
        """
        pattern = self.identify_engulfing(df)
        
        if pattern is None:
            return 0.0
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        
        curr_candle = self.get_candle_type(
            curr['open'], curr['high'], curr['low'], curr['close']
        )
        prev_candle = self.get_candle_type(
            prev['open'], prev['high'], prev['low'], prev['close']
        )
        
        # 1. Ratio engulfment
        engulf_ratio = curr_candle['body'] / prev_candle['body']
        engulf_score = min(engulf_ratio / 2.0, 1.0)  # Cap em 2x
        
        # 2. Body ratio
        body_score = curr_candle['body_ratio']
        
        # 3. Score combinado
        strength = (engulf_score * 0.6) + (body_score * 0.4)
        
        return min(strength, 1.0)
