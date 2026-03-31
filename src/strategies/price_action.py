"""
Price Action Setups
Baseado em bibliotecadesetups.com.br
"""

import pandas as pd
import numpy as np

class PriceActionStrategy:
    def __init__(self):
        self.name = "price_action"
        
    def detect_inside_bar(self, df):
        """
        Inside bar: high/low dentro da barra anterior
        Breakout: entrada na quebra
        """
        if len(df) < 2: return None
        prev_high = df['high'].iloc[-2]
        prev_low = df['low'].iloc[-2]
        curr_high = df['high'].iloc[-1]
        curr_low = df['low'].iloc[-1]
        
        if curr_high < prev_high and curr_low > prev_low:
            # Inside bar detectado
            return {
                'trigger_buy': prev_high,
                'trigger_sell': prev_low,
                'stop_distance': prev_high - prev_low
            }
        return None
        
    def detect_engulfing(self, df):
        """
        Bullish: candle atual engole anterior (low/high)
        """
        if len(df) < 2: return None
        prev = df.iloc[-2]
        curr = df.iloc[-1]
        
        # Bullish engulfing
        if (curr['close'] > curr['open'] and 
            prev['close'] < prev['open'] and
            curr['open'] < prev['close'] and
            curr['close'] > prev['open']):
            return 'BUY'
        
        # Bearish engulfing
        if (curr['close'] < curr['open'] and 
            prev['close'] > prev['open'] and
            curr['open'] > prev['close'] and
            curr['close'] < prev['open']):
            return 'SELL'
        return None
        
    def detect_pin_bar(self, df):
        """
        Pin bar: pavio 2x+ body, rejection forte
        """
        if len(df) < 1: return None
        curr = df.iloc[-1]
        body = abs(curr['close'] - curr['open'])
        if body == 0: body = 0.00001
        
        # Bullish pin (long wick down)
        lower_wick = curr['open'] - curr['low'] if curr['close'] > curr['open'] else curr['close'] - curr['low']
        if lower_wick > body * 2:
            return 'BUY'
        
        # Bearish pin (long wick up)
        upper_wick = curr['high'] - curr['open'] if curr['close'] < curr['open'] else curr['high'] - curr['close']
        if upper_wick > body * 2:
            return 'SELL'
        return None
        
    def detect_supply_demand(self, df, lookback=100):
        """
        Zones: áreas de reversão histórica forte
        """
        if len(df) < lookback: return None
        highs = df['high'].rolling(20).max()
        lows = df['low'].rolling(20).min()
        
        # Supply zone (resistência)
        supply_zone = highs.iloc[-lookback:].quantile(0.95)
        
        # Demand zone (suporte)
        demand_zone = lows.iloc[-lookback:].quantile(0.05)
        
        current_price = df['close'].iloc[-1]
        
        if current_price <= demand_zone * 1.005:  # 0.5% tolerance
            return 'BUY'
        elif current_price >= supply_zone * 0.995:
            return 'SELL'
        return None
        
    def generate_signals(self, df):
        """Combina todos os setups"""
        signals = []
        
        # Inside bar
        ib = self.detect_inside_bar(df)
        if ib:
            signals.append(('inside_bar', ib))
        
        # Engulfing
        eng = self.detect_engulfing(df)
        if eng:
            signals.append(('engulfing', eng))
        
        # Pin bar
        pin = self.detect_pin_bar(df)
        if pin:
            signals.append(('pin_bar', pin))
        
        # Supply/demand
        sd = self.detect_supply_demand(df)
        if sd:
            signals.append(('supply_demand', sd))
        
        return signals
