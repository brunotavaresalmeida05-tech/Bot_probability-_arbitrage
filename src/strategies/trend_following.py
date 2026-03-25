"""
src/strategies/trend_following.py
Trend Following Strategy (CTA Style)

Segue tendências fortes usando:
- Moving Average Crossover
- ADX (trend strength)
- MACD confirmation
- Trailing stops
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import config.settings as cfg


class TrendFollowing:
    """
    Estratégia de Trend Following.
    
    Entry:
    - MA rápida cruza MA lenta
    - ADX > 25 (tendência forte)
    - MACD confirma direção
    
    Exit:
    - MA crossover reverso
    - Trailing stop ativado
    - ADX < 20 (tendência fraca)
    """
    
    def __init__(self, 
                 fast_ma: int = 20,
                 slow_ma: int = 50,
                 adx_period: int = 14,
                 adx_threshold: float = 25.0,
                 trailing_atr_mult: float = 3.0):
        
        self.fast_ma = fast_ma
        self.slow_ma = slow_ma
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.trailing_mult = trailing_atr_mult
        
        self.positions: Dict[str, Dict] = {}  # {symbol: {'direction', 'entry', 'trail_stop'}}
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula indicadores técnicos.
        
        Args:
            df: DataFrame com OHLC
            
        Returns:
            df com colunas adicionadas: ma_fast, ma_slow, adx, macd, atr
        """
        df = df.copy()
        
        # Moving Averages
        df['ma_fast'] = df['close'].rolling(self.fast_ma).mean()
        df['ma_slow'] = df['close'].rolling(self.slow_ma).mean()
        
        # ADX (Average Directional Index)
        df = self._calculate_adx(df, self.adx_period)
        
        # MACD
        df = self._calculate_macd(df)
        
        # ATR para trailing stop
        df = self._calculate_atr(df, 14)
        
        return df
    
    def _calculate_adx(self, df: pd.DataFrame, period: int) -> pd.DataFrame:
        """Calcula ADX (trend strength)."""
        high = df['high']
        low = df['low']
        close = df['close']
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        
        # Directional Movement
        up_move = high - high.shift()
        down_move = low.shift() - low
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        plus_di = 100 * pd.Series(plus_dm).rolling(period).mean() / atr
        minus_di = 100 * pd.Series(minus_dm).rolling(period).mean() / atr
        
        # ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        
        df['adx'] = adx
        df['plus_di'] = plus_di
        df['minus_di'] = minus_di
        
        return df
    
    def _calculate_macd(self, df: pd.DataFrame, 
                       fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
        """Calcula MACD."""
        ema_fast = df['close'].ewm(span=fast).mean()
        ema_slow = df['close'].ewm(span=slow).mean()
        
        df['macd'] = ema_fast - ema_slow
        df['macd_signal'] = df['macd'].ewm(span=signal).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        return df
    
    def _calculate_atr(self, df: pd.DataFrame, period: int) -> pd.DataFrame:
        """Calcula ATR (Average True Range)."""
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        df['atr'] = tr.rolling(period).mean()
        
        return df
    
    def get_signal(self, df: pd.DataFrame, symbol: str) -> Dict:
        """
        Gera sinal de trading.
        
        Args:
            df: DataFrame com indicadores calculados
            symbol: Símbolo do ativo
            
        Returns:
            {
                'signal': 'BUY' | 'SELL' | 'EXIT' | None,
                'reason': str,
                'entry_price': float,
                'stop_loss': float,
                'take_profit': float,
                'trend_strength': float (ADX)
            }
        """
        if len(df) < max(self.slow_ma, self.adx_period * 2):
            return {'signal': None, 'reason': 'Dados insuficientes'}
        
        # Última linha
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        ma_fast_curr = current['ma_fast']
        ma_slow_curr = current['ma_slow']
        ma_fast_prev = previous['ma_fast']
        ma_slow_prev = previous['ma_slow']
        
        adx = current['adx']
        macd = current['macd']
        macd_signal = current['macd_signal']
        
        close = current['close']
        atr = current['atr']
        
        signal = None
        reason = ""
        
        # Verificar se já temos posição
        has_position = symbol in self.positions
        
        if not has_position:
            # ENTRY LOGIC
            
            # Bullish crossover
            if (ma_fast_prev <= ma_slow_prev and 
                ma_fast_curr > ma_slow_curr and
                adx > self.adx_threshold and
                macd > macd_signal):
                
                signal = 'BUY'
                reason = f"MA crossover bullish, ADX={adx:.1f}, MACD bullish"
                
                # Registrar posição
                self.positions[symbol] = {
                    'direction': 'LONG',
                    'entry': close,
                    'trail_stop': close - (self.trailing_mult * atr)
                }
            
            # Bearish crossover
            elif (ma_fast_prev >= ma_slow_prev and 
                  ma_fast_curr < ma_slow_curr and
                  adx > self.adx_threshold and
                  macd < macd_signal):
                
                signal = 'SELL'
                reason = f"MA crossover bearish, ADX={adx:.1f}, MACD bearish"
                
                self.positions[symbol] = {
                    'direction': 'SHORT',
                    'entry': close,
                    'trail_stop': close + (self.trailing_mult * atr)
                }
        
        else:
            # EXIT LOGIC
            position = self.positions[symbol]
            direction = position['direction']
            trail_stop = position['trail_stop']
            
            # Atualizar trailing stop
            if direction == 'LONG':
                new_trail = close - (self.trailing_mult * atr)
                if new_trail > trail_stop:
                    self.positions[symbol]['trail_stop'] = new_trail
                    trail_stop = new_trail
                
                # Exit conditions
                if (close < trail_stop or  # Trailing stop hit
                    ma_fast_curr < ma_slow_curr or  # MA crossover reverso
                    adx < 20):  # Tendência fraca
                    
                    signal = 'EXIT'
                    reason = "Trailing stop / MA reversal / Weak trend"
                    del self.positions[symbol]
            
            elif direction == 'SHORT':
                new_trail = close + (self.trailing_mult * atr)
                if new_trail < trail_stop:
                    self.positions[symbol]['trail_stop'] = new_trail
                    trail_stop = new_trail
                
                if (close > trail_stop or
                    ma_fast_curr > ma_slow_curr or
                    adx < 20):
                    
                    signal = 'EXIT'
                    reason = "Trailing stop / MA reversal / Weak trend"
                    del self.positions[symbol]
        
        return {
            'signal': signal,
            'reason': reason,
            'entry_price': close,
            'stop_loss': self.positions.get(symbol, {}).get('trail_stop'),
            'trend_strength': adx,
            'ma_fast': ma_fast_curr,
            'ma_slow': ma_slow_curr
        }
    
    def get_position_info(self, symbol: str) -> Optional[Dict]:
        """Retorna informação da posição ativa."""
        return self.positions.get(symbol)


# ============================================================
#  EXEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    # Exemplo
    strategy = TrendFollowing()
    
    # Simular dados
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    
    # Tendência sintética
    trend = np.linspace(0, 20, 100)
    noise = np.random.randn(100) * 2
    close = 100 + trend + noise
    
    df = pd.DataFrame({
        'close': close,
        'high': close + abs(np.random.randn(100) * 0.5),
        'low': close - abs(np.random.randn(100) * 0.5),
        'open': close + np.random.randn(100) * 0.2
    }, index=dates)
    
    # Calcular indicadores
    df = strategy.calculate_indicators(df)
    
    # Gerar sinais
    print("\n📈 TREND FOLLOWING - Últimos 5 sinais:\n")
    for i in range(-5, 0):
        df_slice = df.iloc[:i]
        signal = strategy.get_signal(df_slice, 'TEST')
        
        if signal['signal']:
            print(f"Day {len(df_slice)}: {signal['signal']} - {signal['reason']}")
            print(f"  ADX: {signal['trend_strength']:.1f}")
            print(f"  Price: {signal['entry_price']:.2f}")
            if signal['stop_loss']:
                print(f"  Stop: {signal['stop_loss']:.2f}")
