"""
Pin Bar Reversal Strategy
Identifica pin bars (velas com sombras longas) em extremos
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class PinBarStrategy:
    """
    Estratégia de Pin Bar (Hammer/Shooting Star)
    
    Critérios:
    - Sombra > 2x corpo
    - Sombra > 60% da vela total
    - Ocorre em extremo (suporte/resistência ou Z-score)
    """
    
    def __init__(
        self,
        shadow_to_body_ratio: float = 2.0,
        shadow_to_total_ratio: float = 0.60,
        z_score_threshold: float = 2.0
    ):
        self.shadow_to_body_ratio = shadow_to_body_ratio
        self.shadow_to_total_ratio = shadow_to_total_ratio
        self.z_score_threshold = z_score_threshold
    
    def identify_pin_bar(
        self,
        open_price: float,
        high: float,
        low: float,
        close: float
    ) -> Optional[str]:
        """
        Identifica se vela é pin bar
        
        Returns:
            'BULLISH' (hammer), 'BEARISH' (shooting star), ou None
        """
        body = abs(close - open_price)
        total_range = high - low
        
        if total_range == 0:
            return None
        
        # Bullish Pin Bar (Hammer)
        lower_shadow = min(open_price, close) - low
        upper_shadow = high - max(open_price, close)
        
        # Critérios para Bullish Pin
        if (
            lower_shadow > self.shadow_to_body_ratio * body and
            lower_shadow > self.shadow_to_total_ratio * total_range and
            upper_shadow < 0.3 * total_range  # Sombra superior pequena
        ):
            return 'BULLISH'
        
        # Critérios para Bearish Pin (Shooting Star)
        if (
            upper_shadow > self.shadow_to_body_ratio * body and
            upper_shadow > self.shadow_to_total_ratio * total_range and
            lower_shadow < 0.3 * total_range  # Sombra inferior pequena
        ):
            return 'BEARISH'
        
        return None
    
    def check_signal(
        self,
        df: pd.DataFrame,
        z_score: float
    ) -> Optional[str]:
        """
        Verifica sinal de pin bar em extremo
        
        Returns:
            'BUY' ou 'SELL' se pin bar válido em extremo
        """
        # Analisar última vela
        last_bar = df.iloc[-1]
        
        pin_type = self.identify_pin_bar(
            open_price=last_bar['open'],
            high=last_bar['high'],
            low=last_bar['low'],
            close=last_bar['close']
        )
        
        if pin_type is None:
            return None
        
        # Verificar se em extremo
        if pin_type == 'BULLISH' and z_score < -self.z_score_threshold:
            # Hammer em oversold
            body = abs(last_bar['close'] - last_bar['open'])
            lower_shadow = min(last_bar['open'], last_bar['close']) - last_bar['low']
            
            logger.info(
                f"📌 BULLISH PIN BAR | "
                f"Z={z_score:.2f} | "
                f"Shadow/Body={lower_shadow/body if body > 0 else 0:.1f}x"
            )
            return 'BUY'
        
        elif pin_type == 'BEARISH' and z_score > self.z_score_threshold:
            # Shooting Star em overbought
            body = abs(last_bar['close'] - last_bar['open'])
            upper_shadow = last_bar['high'] - max(last_bar['open'], last_bar['close'])
            
            logger.info(
                f"📌 BEARISH PIN BAR | "
                f"Z={z_score:.2f} | "
                f"Shadow/Body={upper_shadow/body if body > 0 else 0:.1f}x"
            )
            return 'SELL'
        
        return None
    
    def calculate_targets(
        self,
        entry_price: float,
        signal: str,
        pin_bar_range: float
    ) -> Tuple[float, float]:
        """
        SL e TP baseados na pin bar
        
        Args:
            pin_bar_range: high - low da pin bar
        
        Returns:
            (stop_loss, take_profit)
        """
        if signal == 'BUY':
            # SL abaixo da sombra
            stop_loss = entry_price - pin_bar_range
            # TP: R:R 1:2
            take_profit = entry_price + (2 * pin_bar_range)
        else:  # SELL
            # SL acima da sombra
            stop_loss = entry_price + pin_bar_range
            # TP: R:R 1:2
            take_profit = entry_price - (2 * pin_bar_range)
        
        return stop_loss, take_profit
