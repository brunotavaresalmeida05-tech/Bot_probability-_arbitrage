"""
src/strategy_manager.py
Strategy Manager - Integra todas as estratégias

Combina sinais de:
1. Mean Reversion (existente)
2. Pairs Trading
3. Trend Following
4. Breakout
5. Volatility Arbitrage
6. News Trading

Allocation proporcional ao Sharpe de cada estratégia.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg


class StrategyManager:
    """
    Gerencia múltiplas estratégias simultaneamente.
    
    Funcionalidades:
    - Combina sinais de todas as estratégias
    - Aloca capital proporcionalmente ao Sharpe
    - Evita conflitos entre estratégias
    - Tracking de performance individual
    """
    
    def __init__(self):
        self.strategies = {}
        self.strategy_weights = {}
        self.strategy_performance = {}
        
        # Importar estratégias
        self._initialize_strategies()
    
    def _initialize_strategies(self):
        """Inicializa todas as estratégias disponíveis."""
        try:
            from src.strategies.pairs_trading import PairsTrading
            self.strategies['pairs'] = PairsTrading()
            self.strategy_weights['pairs'] = 0.2  # 20% do capital
        except:
            pass
        
        try:
            from src.strategies.trend_following import TrendFollowing
            self.strategies['trend'] = TrendFollowing()
            self.strategy_weights['trend'] = 0.25  # 25%
        except:
            pass
        
        try:
            from src.strategies.breakout import Breakout
            self.strategies['breakout'] = Breakout()
            self.strategy_weights['breakout'] = 0.2  # 20%
        except:
            pass
        
        try:
            from src.strategies.volatility_arbitrage import VolatilityArbitrage
            self.strategies['volatility'] = VolatilityArbitrage()
            self.strategy_weights['volatility'] = 0.15  # 15%
        except:
            pass
        
        try:
            from src.strategies.news_trading import NewsTrading
            self.strategies['news'] = NewsTrading()
            self.strategy_weights['news'] = 0.1  # 10%
        except:
            pass
        
        # Mean reversion (estratégia existente) = 10%
        self.strategy_weights['mean_reversion'] = 0.1
        
        print(f"✅ Strategy Manager: {len(self.strategies)} estratégias carregadas")
    
    def get_combined_signal(self, symbol: str, df: pd.DataFrame,
                           current_datetime: datetime = None) -> Dict:
        """
        Combina sinais de todas as estratégias.
        
        Returns:
            {
                'strategy': str,  # Estratégia escolhida
                'signal': 'BUY' | 'SELL' | 'EXIT' | None,
                'confidence': float,
                'all_signals': {strategy_name: signal_dict}
            }
        """
        if current_datetime is None:
            current_datetime = datetime.now()
        
        all_signals = {}
        
        # Coletar sinais de cada estratégia
        for name, strategy in self.strategies.items():
            try:
                if name == 'pairs':
                    # Pairs precisa de dois símbolos
                    # Skip por enquanto (precisa lógica especial)
                    continue
                
                elif name == 'trend':
                    df_with_indicators = strategy.calculate_indicators(df)
                    signal = strategy.get_signal(df_with_indicators, symbol)
                
                elif name == 'breakout':
                    df_with_indicators = strategy.calculate_indicators(df)
                    signal = strategy.get_signal(df_with_indicators, symbol)
                
                elif name == 'volatility':
                    df_with_indicators = strategy.calculate_volatility_metrics(df)
                    signal = strategy.get_signal(df_with_indicators, symbol)
                
                elif name == 'news':
                    signal = strategy.get_signal(symbol, current_datetime, df)
                
                all_signals[name] = signal
            
            except Exception as e:
                all_signals[name] = {'signal': None, 'error': str(e)}
        
        # Decisão de qual estratégia usar
        chosen_strategy, chosen_signal = self._select_best_signal(all_signals)
        
        return {
            'strategy': chosen_strategy,
            'signal': chosen_signal.get('signal') if chosen_signal else None,
            'confidence': self._calculate_confidence(chosen_signal),
            'all_signals': all_signals
        }
    
    def _select_best_signal(self, all_signals: Dict) -> tuple:
        """
        Seleciona melhor sinal baseado em:
        1. Prioridade por tipo de mercado
        2. Confiança do sinal
        3. Performance histórica da estratégia
        """
        # Prioridades
        priority = {
            'news': 5,  # Eventos têm prioridade máxima
            'breakout': 4,
            'trend': 3,
            'volatility': 2,
            'pairs': 1
        }
        
        best_strategy = None
        best_signal = None
        best_score = -1
        
        for name, signal in all_signals.items():
            if signal.get('signal') in ['BUY', 'SELL', 'EXIT']:
                # Calcular score
                priority_score = priority.get(name, 0)
                confidence = signal.get('confidence', 0.5)
                performance = self.strategy_performance.get(name, {}).get('sharpe', 1.0)
                
                score = priority_score * confidence * performance
                
                if score > best_score:
                    best_score = score
                    best_strategy = name
                    best_signal = signal
        
        return best_strategy, best_signal
    
    def _calculate_confidence(self, signal: Optional[Dict]) -> float:
        """Calcula confiança do sinal (0-1)."""
        if not signal or not signal.get('signal'):
            return 0.0
        
        # Usar confiança da estratégia se disponível
        if 'confidence' in signal:
            return signal['confidence']
        
        # Default baseado em tipo de sinal
        if signal['signal'] == 'EXIT':
            return 0.8
        
        return 0.6
    
    def update_strategy_performance(self, strategy_name: str, trade_result: Dict):
        """
        Atualiza performance de uma estratégia.
        
        Args:
            strategy_name: Nome da estratégia
            trade_result: {'pnl': float, 'return_pct': float}
        """
        if strategy_name not in self.strategy_performance:
            self.strategy_performance[strategy_name] = {
                'trades': 0,
                'wins': 0,
                'total_pnl': 0.0,
                'sharpe': 1.0
            }
        
        perf = self.strategy_performance[strategy_name]
        perf['trades'] += 1
        perf['total_pnl'] += trade_result['pnl']
        
        if trade_result['pnl'] > 0:
            perf['wins'] += 1
        
        # Recalcular Sharpe (simplificado)
        win_rate = perf['wins'] / perf['trades']
        avg_pnl = perf['total_pnl'] / perf['trades']
        
        if avg_pnl > 0:
            perf['sharpe'] = win_rate * 2  # Aproximação
    
    def get_strategy_allocation(self, capital: float) -> Dict[str, float]:
        """
        Retorna alocação de capital por estratégia.
        
        Returns:
            {strategy_name: capital_allocated}
        """
        allocation = {}
        
        for name, weight in self.strategy_weights.items():
            # Ajustar peso pela performance
            perf = self.strategy_performance.get(name, {})
            sharpe = perf.get('sharpe', 1.0)
            
            adjusted_weight = weight * sharpe
            allocation[name] = capital * adjusted_weight
        
        # Normalizar para somar 100%
        total = sum(allocation.values())
        if total > 0:
            allocation = {k: v / total * capital for k, v in allocation.items()}
        
        return allocation
    
    def get_performance_report(self) -> pd.DataFrame:
        """Retorna relatório de performance de todas as estratégias."""
        data = []
        
        for name, perf in self.strategy_performance.items():
            data.append({
                'Strategy': name,
                'Trades': perf['trades'],
                'Win Rate': f"{perf['wins'] / perf['trades'] * 100:.1f}%" if perf['trades'] > 0 else "0%",
                'Total P&L': f"€{perf['total_pnl']:.2f}",
                'Sharpe': f"{perf['sharpe']:.2f}",
                'Weight': f"{self.strategy_weights.get(name, 0) * 100:.1f}%"
            })
        
        return pd.DataFrame(data)


# ============================================================
#  EXEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    manager = StrategyManager()
    
    # Simular dados
    np.random.seed(42)
    df = pd.DataFrame({
        'close': np.cumsum(np.random.randn(100) * 0.5) + 100,
        'high': np.cumsum(np.random.randn(100) * 0.5) + 100.5,
        'low': np.cumsum(np.random.randn(100) * 0.5) + 99.5,
        'open': np.cumsum(np.random.randn(100) * 0.5) + 100
    })
    
    # Obter sinais combinados
    result = manager.get_combined_signal('EURUSD', df)
    
    print("\n📊 STRATEGY MANAGER - Sinais Combinados:\n")
    print(f"Estratégia escolhida: {result['strategy']}")
    print(f"Sinal: {result['signal']}")
    print(f"Confiança: {result['confidence']:.2f}")
    
    print("\n📈 Sinais individuais:")
    for name, signal in result['all_signals'].items():
        print(f"  {name}: {signal.get('signal', 'None')}")
    
    # Alocação de capital
    print("\n💰 Alocação de capital (€10,000):")
    allocation = manager.get_strategy_allocation(10000)
    for name, amount in allocation.items():
        print(f"  {name}: €{amount:,.2f}")
