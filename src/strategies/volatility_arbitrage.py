"""
src/strategies/volatility_arbitrage.py
Volatility Arbitrage Strategy

Opera mudanças na volatilidade:
- Mean reversion de ATR
- VIX-like indicators
- Bollinger Band width
- Straddle/Strangle logic
"""

import numpy as np
import pandas as pd
from typing import Dict
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import config.settings as cfg


class VolatilityArbitrage:
    """
    Estratégia de Volatility Arbitrage.
    
    Entry:
    - ATR/Volatility extremamente alto ou baixo
    - Bollinger Band width em extremos
    - Reversão esperada
    
    Exit:
    - Volatilidade volta ao normal
    - Time decay (positions older than X days)
    """
    
    def __init__(self,
                 atr_period: int = 14,
                 bb_period: int = 20,
                 vol_z_entry: float = 2.0,
                 vol_z_exit: float = 0.5,
                 max_hold_days: int = 10):
        
        self.atr_period = atr_period
        self.bb_period = bb_period
        self.vol_z_entry = vol_z_entry
        self.vol_z_exit = vol_z_exit
        self.max_hold_days = max_hold_days
        
        self.positions: Dict[str, Dict] = {}
    
    def calculate_volatility_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calcula métricas de volatilidade."""
        df = df.copy()
        
        # ATR
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['atr'] = tr.rolling(self.atr_period).mean()
        
        # ATR como % do preço (volatilidade normalizada)
        df['atr_pct'] = (df['atr'] / df['close']) * 100
        
        # Z-score da ATR
        atr_mean = df['atr_pct'].rolling(60).mean()
        atr_std = df['atr_pct'].rolling(60).std()
        df['atr_z'] = (df['atr_pct'] - atr_mean) / atr_std
        
        # Bollinger Band Width
        bb_middle = df['close'].rolling(self.bb_period).mean()
        bb_std = df['close'].rolling(self.bb_period).std()
        df['bb_width'] = (bb_std * 4) / bb_middle * 100
        
        # Z-score do BB width
        bb_width_mean = df['bb_width'].rolling(60).mean()
        bb_width_std = df['bb_width'].rolling(60).std()
        df['bb_width_z'] = (df['bb_width'] - bb_width_mean) / bb_width_std
        
        # Realized Volatility (return volatility)
        returns = df['close'].pct_change()
        df['realized_vol'] = returns.rolling(20).std() * np.sqrt(252) * 100
        
        # Historical Volatility Z-score
        rv_mean = df['realized_vol'].rolling(60).mean()
        rv_std = df['realized_vol'].rolling(60).std()
        df['rv_z'] = (df['realized_vol'] - rv_mean) / rv_std
        
        return df
    
    def get_signal(self, df: pd.DataFrame, symbol: str) -> Dict:
        """
        Gera sinal baseado em volatilidade.
        
        Strategy logic:
        - Alta volatility (Z > 2.0) → SELL volatility (expect decrease)
        - Baixa volatility (Z < -2.0) → BUY volatility (expect increase)
        
        Returns:
            {
                'signal': 'SELL_VOL' | 'BUY_VOL' | 'EXIT' | None,
                'reason': str,
                'vol_z': float,
                'regime': 'HIGH_VOL' | 'LOW_VOL' | 'NORMAL'
            }
        """
        if len(df) < 80:  # Precisa de histórico para Z-scores
            return {'signal': None, 'reason': 'Dados insuficientes'}
        
        current = df.iloc[-1]
        
        atr_z = current['atr_z']
        bb_width_z = current['bb_width_z']
        rv_z = current['rv_z']
        
        # Média dos Z-scores (consenso de volatilidade)
        vol_z_avg = np.mean([atr_z, bb_width_z, rv_z])
        
        signal = None
        reason = ""
        regime = "NORMAL"
        
        has_position = symbol in self.positions
        
        if not has_position:
            # ENTRY LOGIC
            
            # Alta volatilidade → vender (esperar reversão para baixo)
            if vol_z_avg > self.vol_z_entry:
                signal = 'SELL_VOL'
                regime = 'HIGH_VOL'
                reason = f"Volatilidade extremamente alta (Z={vol_z_avg:.2f})"
                
                self.positions[symbol] = {
                    'type': 'SHORT_VOL',
                    'entry_date': len(df),
                    'entry_vol_z': vol_z_avg,
                    'target_z': 0.0
                }
            
            # Baixa volatilidade → comprar (esperar expansão)
            elif vol_z_avg < -self.vol_z_entry:
                signal = 'BUY_VOL'
                regime = 'LOW_VOL'
                reason = f"Volatilidade extremamente baixa (Z={vol_z_avg:.2f})"
                
                self.positions[symbol] = {
                    'type': 'LONG_VOL',
                    'entry_date': len(df),
                    'entry_vol_z': vol_z_avg,
                    'target_z': 0.0
                }
        
        else:
            # EXIT LOGIC
            position = self.positions[symbol]
            entry_date = position['entry_date']
            days_held = len(df) - entry_date
            pos_type = position['type']
            
            # Time decay
            if days_held > self.max_hold_days:
                signal = 'EXIT'
                reason = f"Max hold period ({self.max_hold_days} dias)"
                del self.positions[symbol]
            
            # Volatilidade voltou ao normal
            elif abs(vol_z_avg) < self.vol_z_exit:
                signal = 'EXIT'
                reason = f"Volatilidade normalizou (Z={vol_z_avg:.2f})"
                del self.positions[symbol]
            
            # Reversão adversa (volatilidade foi na direção errada)
            elif pos_type == 'SHORT_VOL' and vol_z_avg > position['entry_vol_z'] * 1.2:
                signal = 'EXIT'
                reason = "Stop loss: volatilidade aumentou mais"
                del self.positions[symbol]
            
            elif pos_type == 'LONG_VOL' and vol_z_avg < position['entry_vol_z'] * 1.2:
                signal = 'EXIT'
                reason = "Stop loss: volatilidade caiu mais"
                del self.positions[symbol]
        
        return {
            'signal': signal,
            'reason': reason,
            'vol_z': vol_z_avg,
            'atr_z': atr_z,
            'bb_width_z': bb_width_z,
            'rv_z': rv_z,
            'regime': regime,
            'atr_pct': current['atr_pct'],
            'realized_vol': current['realized_vol']
        }
    
    def convert_to_direction_signal(self, vol_signal: str, current_price: float,
                                    atr: float) -> Dict:
        """
        Converte sinal de volatilidade em direção de trading.
        
        Opções:
        1. Delta-neutral straddle (BUY + SELL simultâneo)
        2. Direção baseada em momentum
        3. Mean reversion puro
        
        Args:
            vol_signal: 'BUY_VOL' ou 'SELL_VOL'
            current_price: Preço atual
            atr: ATR atual
            
        Returns:
            {'direction': 'BUY' | 'SELL' | 'STRADDLE', 'size': float}
        """
        if vol_signal == 'BUY_VOL':
            # Espera aumento de volatilidade = movimento grande
            # Pode operar straddle (compra calls e puts)
            # Ou simplesmente esperar breakout
            return {
                'direction': 'STRADDLE',  # Comprar movimento em qualquer direção
                'size': 1.0,
                'strategy': 'Esperar breakout de volatilidade'
            }
        
        elif vol_signal == 'SELL_VOL':
            # Espera diminuição de volatilidade = range-bound
            # Operar mean reversion
            return {
                'direction': 'RANGE_BOUND',  # Vender extremos
                'size': 1.0,
                'strategy': 'Vender picos/fundos (mean reversion)'
            }
        
        return {'direction': None}


# ============================================================
#  EXEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    strategy = VolatilityArbitrage()
    
    # Simular dados com períodos de alta/baixa volatilidade
    np.random.seed(42)
    
    # Período de baixa vol → alta vol → baixa vol
    low_vol = np.cumsum(np.random.randn(50) * 0.3) + 100
    high_vol = np.cumsum(np.random.randn(40) * 2.0) + low_vol[-1]
    low_vol2 = np.cumsum(np.random.randn(50) * 0.4) + high_vol[-1]
    
    prices = np.concatenate([low_vol, high_vol, low_vol2])
    
    df = pd.DataFrame({
        'close': prices,
        'high': prices + abs(np.random.randn(len(prices)) * 0.5),
        'low': prices - abs(np.random.randn(len(prices)) * 0.5),
        'open': prices + np.random.randn(len(prices)) * 0.2
    })
    
    df = strategy.calculate_volatility_metrics(df)
    
    print("\n📊 VOLATILITY ARBITRAGE - Sinais:\n")
    
    for i in range(80, len(df), 5):
        df_slice = df.iloc[:i]
        signal = strategy.get_signal(df_slice, 'TEST')
        
        if signal['signal']:
            print(f"Bar {i}: {signal['signal']} - {signal['regime']}")
            print(f"  Vol Z-score: {signal['vol_z']:.2f}")
            print(f"  Reason: {signal['reason']}")
            print(f"  ATR%: {signal['atr_pct']:.2f}%")
            print()
