"""
News Momentum Strategy
React fast to major news (NFP, FOMC, CPI)
"""
import time

class NewsMomentumStrategy:
    def __init__(self):
        self.name = "news_momentum"
        self.major_events = ['NFP', 'FOMC', 'CPI', 'ECB']
        
    def is_within_60s_of_event(self, event_time):
        """
        Verifica se estamos dentro dos primeiros 60s após o evento
        event_time deve ser um timestamp Unix
        """
        if event_time is None: return False
        now = time.time()
        return 0 <= (now - event_time) <= 60

    def detect_momentum(self, df, event_time):
        """
        Detecta movimento forte nos primeiros 60s após news
        """
        if not self.is_within_60s_of_event(event_time):
            return None
            
        # Primeiro candle M1 após news
        if len(df) < 1: return None
        first_candle = df.iloc[-1]
        
        # Calcular ATR simples se não existir no DF
        if 'atr' not in df.columns:
            high_low = df['high'] - df['low']
            atr = high_low.rolling(14).mean().iloc[-1]
        else:
            atr = df['atr'].iloc[-1]
        
        range_candle = first_candle['high'] - first_candle['low']
        
        # Se candle > 3x ATR, entrar na direção
        if range_candle > atr * 3:
            if first_candle['close'] > first_candle['open']:
                return 'BUY'
            else:
                return 'SELL'
        return None
