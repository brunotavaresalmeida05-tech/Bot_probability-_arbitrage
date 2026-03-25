"""
src/strategies/breakout.py
Breakout Strategy

Opera rompimentos de:
- Bollinger Bands
- Support/Resistance levels
- Range consolidation
- Volume confirmation
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import config.settings as cfg


class Breakout:
    """
    Estratégia de Breakout.
    
    Entry:
    - Preço rompe Bollinger Band superior/inferior
    - Volume > média (confirmação)
    - Volatilidade expandindo (ATR crescente)
    
    Exit:
    - Preço volta para dentro das bandas
    - Stop loss fixo (% do ATR)
    - Take profit em múltiplos de ATR
    """
    
    def __init__(self,
                 bb_period: int = 20,
                 bb_std: float = 2.0,
                 volume_mult: float = 1.5,
                 atr_period: int = 14,
                 stop_atr_mult: float = 2.0,
                 tp_atr_mult: float = 4.0):
        
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.volume_mult = volume_mult
        self.atr_period = atr_period
        self.stop_mult = stop_atr_mult
        self.tp_mult = tp_atr_mult
        
        self.positions: Dict[str, Dict] = {}
        self.support_resistance: Dict[str, List[float]] = {}
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula Bollinger Bands, ATR, Volume MA."""
        df = df.copy()
        
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(self.bb_period).mean()
        bb_std_dev = df['close'].rolling(self.bb_period).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std_dev * self.bb_std)
        df['bb_lower'] = df['bb_middle'] - (bb_std_dev * self.bb_std)
        df['bb_width'] = df['bb_upper'] - df['bb_lower']
        
        # ATR
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(self.atr_period).mean()
        
        # Volume
        if 'volume' in df.columns:
            df['volume_ma'] = df['volume'].rolling(20).mean()
        else:
            df['volume'] = 0
            df['volume_ma'] = 0
        
        # Volatilidade (ATR rate of change)
        df['atr_roc'] = df['atr'].pct_change(5)
        
        return df
    
    def detect_support_resistance(self, df: pd.DataFrame, 
                                  window: int = 20,
                                  tolerance: float = 0.001) -> List[float]:
        """
        Detecta níveis de suporte e resistência.
        
        Args:
            df: DataFrame com OHLC
            window: Janela para detectar pivots
            tolerance: % de tolerância para agrupar níveis
            
        Returns:
            Lista de níveis [price1, price2, ...]
        """
        highs = df['high'].values
        lows = df['low'].values
        
        levels = []
        
        # Pivot highs (resistência)
        for i in range(window, len(highs) - window):
            if highs[i] == max(highs[i-window:i+window+1]):
                levels.append(highs[i])
        
        # Pivot lows (suporte)
        for i in range(window, len(lows) - window):
            if lows[i] == min(lows[i-window:i+window+1]):
                levels.append(lows[i])
        
        # Agrupar níveis próximos
        if not levels:
            return []
        
        levels = sorted(levels)
        grouped = [levels[0]]
        
        for level in levels[1:]:
            if abs(level - grouped[-1]) / grouped[-1] > tolerance:
                grouped.append(level)
        
        return grouped
    
    def get_signal(self, df: pd.DataFrame, symbol: str) -> Dict:
        """
        Gera sinal de breakout.
        
        Returns:
            {
                'signal': 'BUY' | 'SELL' | 'EXIT' | None,
                'type': 'BB_BREAKOUT' | 'SR_BREAKOUT' | 'SQUEEZE',
                'entry_price': float,
                'stop_loss': float,
                'take_profit': float,
                'confidence': float
            }
        """
        if len(df) < max(self.bb_period, self.atr_period) + 5:
            return {'signal': None, 'type': 'INSUFFICIENT_DATA'}
        
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        close = current['close']
        bb_upper = current['bb_upper']
        bb_lower = current['bb_lower']
        bb_middle = current['bb_middle']
        bb_width = current['bb_width']
        atr = current['atr']
        volume = current.get('volume', 0)
        volume_ma = current.get('volume_ma', 0)
        atr_roc = current['atr_roc']
        
        signal = None
        breakout_type = None
        confidence = 0.0
        
        # Verificar posição existente
        has_position = symbol in self.positions
        
        if not has_position:
            # ENTRY LOGIC
            
            # 1. Bollinger Band Breakout
            if close > bb_upper and previous['close'] <= previous['bb_upper']:
                # Breakout para cima
                if volume > volume_ma * self.volume_mult and atr_roc > 0:
                    signal = 'BUY'
                    breakout_type = 'BB_UPPER'
                    confidence = min(1.0, (volume / volume_ma) / self.volume_mult)
                    
                    self.positions[symbol] = {
                        'direction': 'LONG',
                        'entry': close,
                        'stop': close - (self.stop_mult * atr),
                        'target': close + (self.tp_mult * atr)
                    }
            
            elif close < bb_lower and previous['close'] >= previous['bb_lower']:
                # Breakout para baixo
                if volume > volume_ma * self.volume_mult and atr_roc > 0:
                    signal = 'SELL'
                    breakout_type = 'BB_LOWER'
                    confidence = min(1.0, (volume / volume_ma) / self.volume_mult)
                    
                    self.positions[symbol] = {
                        'direction': 'SHORT',
                        'entry': close,
                        'stop': close + (self.stop_mult * atr),
                        'target': close - (self.tp_mult * atr)
                    }
            
            # 2. Squeeze Breakout (BB width contracting then expanding)
            elif len(df) > self.bb_period + 10:
                bb_width_prev = df['bb_width'].iloc[-10:-1].mean()
                
                if bb_width < bb_width_prev * 0.8:  # Squeeze (width contracting)
                    if close > bb_middle and atr_roc > 0.1:
                        signal = 'BUY'
                        breakout_type = 'SQUEEZE_UP'
                        confidence = 0.7
                        
                        self.positions[symbol] = {
                            'direction': 'LONG',
                            'entry': close,
                            'stop': bb_lower,
                            'target': close + (bb_width * 2)
                        }
                    
                    elif close < bb_middle and atr_roc > 0.1:
                        signal = 'SELL'
                        breakout_type = 'SQUEEZE_DOWN'
                        confidence = 0.7
                        
                        self.positions[symbol] = {
                            'direction': 'SHORT',
                            'entry': close,
                            'stop': bb_upper,
                            'target': close - (bb_width * 2)
                        }
            
            # 3. Support/Resistance Breakout
            if symbol in self.support_resistance:
                levels = self.support_resistance[symbol]
                
                for level in levels:
                    # Resistência quebrada
                    if previous['close'] < level and close > level:
                        if volume > volume_ma * self.volume_mult:
                            signal = 'BUY'
                            breakout_type = 'RESISTANCE_BREAK'
                            confidence = 0.8
                            
                            self.positions[symbol] = {
                                'direction': 'LONG',
                                'entry': close,
                                'stop': level,
                                'target': close + (close - level) * 2
                            }
                            break
                    
                    # Suporte quebrado
                    elif previous['close'] > level and close < level:
                        if volume > volume_ma * self.volume_mult:
                            signal = 'SELL'
                            breakout_type = 'SUPPORT_BREAK'
                            confidence = 0.8
                            
                            self.positions[symbol] = {
                                'direction': 'SHORT',
                                'entry': close,
                                'stop': level,
                                'target': close - (level - close) * 2
                            }
                            break
        
        else:
            # EXIT LOGIC
            position = self.positions[symbol]
            direction = position['direction']
            stop = position['stop']
            target = position['target']
            
            if direction == 'LONG':
                # Stop loss ou take profit
                if close <= stop:
                    signal = 'EXIT'
                    breakout_type = 'STOP_LOSS'
                    del self.positions[symbol]
                
                elif close >= target:
                    signal = 'EXIT'
                    breakout_type = 'TAKE_PROFIT'
                    del self.positions[symbol]
                
                # Preço volta para dentro das bandas
                elif close < bb_middle:
                    signal = 'EXIT'
                    breakout_type = 'MEAN_REVERSION'
                    del self.positions[symbol]
            
            elif direction == 'SHORT':
                if close >= stop:
                    signal = 'EXIT'
                    breakout_type = 'STOP_LOSS'
                    del self.positions[symbol]
                
                elif close <= target:
                    signal = 'EXIT'
                    breakout_type = 'TAKE_PROFIT'
                    del self.positions[symbol]
                
                elif close > bb_middle:
                    signal = 'EXIT'
                    breakout_type = 'MEAN_REVERSION'
                    del self.positions[symbol]
        
        result = {
            'signal': signal,
            'type': breakout_type,
            'confidence': confidence,
            'entry_price': close,
            'bb_upper': bb_upper,
            'bb_lower': bb_lower,
            'atr': atr
        }
        
        if has_position or signal in ['BUY', 'SELL']:
            pos = self.positions.get(symbol, {})
            result['stop_loss'] = pos.get('stop')
            result['take_profit'] = pos.get('target')
        
        return result
    
    def update_support_resistance(self, symbol: str, df: pd.DataFrame):
        """Atualiza níveis de S/R."""
        levels = self.detect_support_resistance(df)
        self.support_resistance[symbol] = levels


# ============================================================
#  EXEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    strategy = Breakout()
    
    # Simular dados com breakout
    np.random.seed(42)
    
    # Range consolidation seguido de breakout
    consolidation = np.random.randn(50) * 0.5 + 100
    breakout_move = np.linspace(0, 10, 30)
    prices = np.concatenate([consolidation, 100 + breakout_move])
    
    df = pd.DataFrame({
        'close': prices,
        'high': prices + abs(np.random.randn(len(prices)) * 0.3),
        'low': prices - abs(np.random.randn(len(prices)) * 0.3),
        'open': prices + np.random.randn(len(prices)) * 0.2,
        'volume': abs(np.random.randn(len(prices)) * 1000 + 5000)
    })
    
    df = strategy.calculate_indicators(df)
    
    print("\n💥 BREAKOUT STRATEGY - Sinais:\n")
    
    for i in range(max(strategy.bb_period, strategy.atr_period) + 5, len(df)):
        df_slice = df.iloc[:i]
        signal = strategy.get_signal(df_slice, 'TEST')
        
        if signal['signal']:
            print(f"Bar {i}: {signal['signal']} - {signal['type']}")
            print(f"  Price: {signal['entry_price']:.2f}")
            print(f"  Confidence: {signal['confidence']:.2f}")
            if signal.get('stop_loss'):
                print(f"  Stop: {signal['stop_loss']:.2f}")
                print(f"  Target: {signal['take_profit']:.2f}")
