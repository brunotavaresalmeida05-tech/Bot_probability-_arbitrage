"""
src/strategies/pairs_trading.py
Pairs Trading / Statistical Arbitrage Strategy

Opera pares correlacionados quando o spread se desvia da média.
Market-neutral, baixa correlação com direção do mercado.
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List, Tuple, Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import config.settings as cfg


class PairsTrading:
    """
    Estratégia de Pairs Trading.
    
    Procura pares com:
    - Alta correlação histórica (>0.7)
    - Cointegração (ADF test p-value <0.05)
    - Spread mean-reverting
    """
    
    def __init__(self, lookback_period: int = 60):
        self.lookback = lookback_period
        self.pairs: Dict[str, Dict] = {}  # {(sym1, sym2): {beta, spread_mean, spread_std}}
        self.active_pairs: List[Tuple] = []
        
    def find_pairs(self, symbols: List[str], price_data: Dict[str, pd.DataFrame]) -> List[Tuple]:
        """
        Encontra pares cointegrados.
        
        Args:
            symbols: Lista de símbolos
            price_data: {symbol: DataFrame com 'close'}
            
        Returns:
            Lista de tuplas (sym1, sym2, correlation, p_value)
        """
        valid_pairs = []
        
        # Testar todas as combinações
        for i, sym1 in enumerate(symbols):
            for sym2 in symbols[i+1:]:
                
                if sym1 not in price_data or sym2 not in price_data:
                    continue
                
                df1 = price_data[sym1]
                df2 = price_data[sym2]
                
                if len(df1) < self.lookback or len(df2) < self.lookback:
                    continue
                
                # Alinhar dados
                close1 = df1['close'].iloc[-self.lookback:].values
                close2 = df2['close'].iloc[-self.lookback:].values
                
                if len(close1) != len(close2):
                    continue
                
                # 1. Correlação
                corr = np.corrcoef(close1, close2)[0, 1]
                
                if abs(corr) < 0.7:  # Mínimo 0.7 correlação
                    continue
                
                # 2. Cointegração (ADF test no spread)
                beta = self._calculate_beta(close1, close2)
                spread = close1 - beta * close2
                
                adf_result = self._adf_test(spread)
                
                if adf_result['p_value'] < 0.05:  # Cointegrado
                    valid_pairs.append({
                        'pair': (sym1, sym2),
                        'correlation': corr,
                        'p_value': adf_result['p_value'],
                        'beta': beta,
                        'spread_mean': np.mean(spread),
                        'spread_std': np.std(spread)
                    })
        
        # Guardar pares válidos
        for pair_data in valid_pairs:
            pair = pair_data['pair']
            self.pairs[pair] = {
                'beta': pair_data['beta'],
                'spread_mean': pair_data['spread_mean'],
                'spread_std': pair_data['spread_std'],
                'correlation': pair_data['correlation']
            }
        
        return valid_pairs
    
    def _calculate_beta(self, y: np.ndarray, x: np.ndarray) -> float:
        """Calcula beta da regressão linear."""
        return np.polyfit(x, y, 1)[0]
    
    def _adf_test(self, series: np.ndarray) -> Dict:
        """
        Augmented Dickey-Fuller test para estacionariedade.
        
        Returns:
            {'statistic': float, 'p_value': float, 'is_stationary': bool}
        """
        try:
            from statsmodels.tsa.stattools import adfuller
            result = adfuller(series)
            return {
                'statistic': result[0],
                'p_value': result[1],
                'is_stationary': result[1] < 0.05
            }
        except:
            # Fallback: teste simples baseado em autocorrelação
            autocorr = np.corrcoef(series[:-1], series[1:])[0, 1]
            return {
                'statistic': autocorr,
                'p_value': 1.0 - abs(autocorr),
                'is_stationary': abs(autocorr) < 0.8
            }
    
    def get_signals(self, pair: Tuple[str, str], 
                   price1: float, price2: float,
                   z_entry: float = 2.0, z_exit: float = 0.5) -> Dict:
        """
        Gera sinais de trading para um par.
        
        Args:
            pair: (sym1, sym2)
            price1: Preço atual do sym1
            price2: Preço atual do sym2
            z_entry: Z-score para entrada (default 2.0)
            z_exit: Z-score para saída (default 0.5)
            
        Returns:
            {
                'signal': 'LONG_PAIR' | 'SHORT_PAIR' | 'EXIT' | None,
                'z_score': float,
                'spread': float,
                'leg1': 'BUY' | 'SELL' | None,
                'leg2': 'BUY' | 'SELL' | None
            }
        """
        if pair not in self.pairs:
            return {'signal': None}
        
        params = self.pairs[pair]
        
        # Calcular spread atual
        spread = price1 - params['beta'] * price2
        
        # Z-score do spread
        z_score = (spread - params['spread_mean']) / params['spread_std']
        
        signal = None
        leg1 = None
        leg2 = None
        
        # Lógica de entrada
        if z_score > z_entry:
            # Spread muito alto → SHORT spread
            signal = 'SHORT_PAIR'
            leg1 = 'SELL'  # Vender sym1 (caro)
            leg2 = 'BUY'   # Comprar sym2 (barato)
            
        elif z_score < -z_entry:
            # Spread muito baixo → LONG spread
            signal = 'LONG_PAIR'
            leg1 = 'BUY'   # Comprar sym1 (barato)
            leg2 = 'SELL'  # Vender sym2 (caro)
        
        # Lógica de saída
        elif abs(z_score) < z_exit:
            signal = 'EXIT'
        
        return {
            'signal': signal,
            'z_score': z_score,
            'spread': spread,
            'leg1': leg1,
            'leg2': leg2,
            'beta': params['beta']
        }
    
    def calculate_position_sizes(self, pair: Tuple[str, str],
                                capital: float,
                                risk_pct: float = 2.0) -> Dict:
        """
        Calcula tamanho das posições para as duas pernas.
        
        Market-neutral: valor das duas pernas deve ser igual.
        
        Args:
            pair: (sym1, sym2)
            capital: Capital disponível
            risk_pct: % do capital em risco
            
        Returns:
            {'sym1_size': float, 'sym2_size': float}
        """
        if pair not in self.pairs:
            return {'sym1_size': 0.0, 'sym2_size': 0.0}
        
        beta = self.pairs[pair]['beta']
        
        # Capital para cada perna (market neutral)
        capital_per_leg = (capital * risk_pct / 100) / 2
        
        return {
            'sym1_capital': capital_per_leg,
            'sym2_capital': capital_per_leg,
            'beta': beta
        }
    
    def get_pair_performance(self, pair: Tuple[str, str]) -> Dict:
        """Retorna métricas de performance de um par."""
        if pair not in self.pairs:
            return {}
        
        return {
            'correlation': self.pairs[pair]['correlation'],
            'spread_mean': self.pairs[pair]['spread_mean'],
            'spread_std': self.pairs[pair]['spread_std'],
            'beta': self.pairs[pair]['beta']
        }


# ============================================================
#  EXEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    # Exemplo
    strategy = PairsTrading(lookback_period=60)
    
    # Simular dados
    np.random.seed(42)
    
    price_data = {
        'EURUSD': pd.DataFrame({
            'close': np.cumsum(np.random.randn(100) * 0.01) + 1.16
        }),
        'GBPUSD': pd.DataFrame({
            'close': np.cumsum(np.random.randn(100) * 0.012) + 1.34
        }),
        'USDJPY': pd.DataFrame({
            'close': np.cumsum(np.random.randn(100) * 0.5) + 158
        })
    }
    
    # Encontrar pares
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY']
    pairs = strategy.find_pairs(symbols, price_data)
    
    print(f"\n📊 Pares encontrados: {len(pairs)}")
    for p in pairs:
        print(f"  {p['pair']}: corr={p['correlation']:.3f}, p={p['p_value']:.4f}")
    
    # Gerar sinais
    if pairs:
        pair = pairs[0]['pair']
        price1 = price_data[pair[0]]['close'].iloc[-1]
        price2 = price_data[pair[1]]['close'].iloc[-1]
        
        signal = strategy.get_signals(pair, price1, price2)
        print(f"\n🎯 Sinal para {pair}:")
        print(f"  Z-score: {signal['z_score']:.2f}")
        print(f"  Signal: {signal['signal']}")
        print(f"  Leg1: {signal['leg1']}, Leg2: {signal['leg2']}")
