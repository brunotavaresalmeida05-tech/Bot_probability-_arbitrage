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
import time
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
    - ML predictor filter (RandomForest per symbol)
    """

    def __init__(self):
        self.strategies = {}
        self.strategy_weights = {}
        self.strategy_performance = {}
        self.last_signals = []   # exposed for live_state_writer

        # ML predictors per symbol {symbol: PricePredictor}
        self.ml_predictors: dict = {}
        self._load_ml_predictors()

        # Import strategies
        self._initialize_strategies()

    # ── ML predictor loading ──────────────────────────────────

    def _load_ml_predictors(self):
        """Load trained ML models for each active symbol (if available)."""
        try:
            from src.ml.price_predictor import PricePredictor
            active = getattr(cfg, 'ACTIVE_SYMBOLS', getattr(cfg, 'SYMBOLS', []))
            loaded = 0
            for sym in active:
                path = f'data/models/{sym.lower()}_ml.pkl'
                if os.path.exists(path):
                    p = PricePredictor(model_path=path)
                    if p.is_trained:
                        self.ml_predictors[sym] = p
                        loaded += 1
            if loaded:
                print(f"ML predictors loaded: {loaded}/{len(active)} symbols")
        except Exception as e:
            print(f"ML predictor load skipped: {e}")
    
    def _initialize_strategies(self):
        """Inicializa todas as estratégias disponíveis."""
        try:
            from src.strategies.pairs_trading import PairsTrading
            self.strategies['pairs'] = PairsTrading()
            self.strategy_weights['pairs'] = 0.1
        except: pass
        
        try:
            from src.strategies.trend_following import TrendFollowing
            self.strategies['trend'] = TrendFollowing()
            self.strategy_weights['trend'] = 0.15
        except: pass
        
        try:
            from src.strategies.breakout import Breakout
            self.strategies['breakout'] = Breakout()
            self.strategy_weights['breakout'] = 0.1
        except: pass
        
        try:
            from src.strategies.volatility_arbitrage import VolatilityArbitrage
            self.strategies['volatility'] = VolatilityArbitrage()
            self.strategy_weights['volatility'] = 0.1
        except: pass
        
        try:
            from src.strategies.news_trading import NewsTrading
            self.strategies['news'] = NewsTrading()
            self.strategy_weights['news'] = 0.1
        except: pass

        # NOVAS ESTRATÉGIAS
        try:
            from src.strategies.supply_demand import SupplyDemandStrategy
            self.strategies['supply_demand'] = SupplyDemandStrategy(
                zone_strength_min=cfg.SUPPLY_DEMAND_ZONE_STRENGTH,
                zone_age_max=cfg.SUPPLY_DEMAND_ZONE_AGE,
                price_move_min=cfg.SUPPLY_DEMAND_MIN_MOVE
            )
            self.strategy_weights['supply_demand'] = 0.15
        except Exception as e:
            print(f"Erro ao carregar SupplyDemandStrategy: {e}")

        try:
            from src.strategies.pin_bar import PinBarStrategy
            self.strategies['pin_bar'] = PinBarStrategy(
                shadow_to_body_ratio=cfg.PIN_BAR_SHADOW_RATIO,
                shadow_to_total_ratio=cfg.PIN_BAR_SHADOW_PCT,
                z_score_threshold=cfg.PIN_BAR_Z_THRESHOLD
            )
            self.strategy_weights['pin_bar'] = 0.15
        except Exception as e:
            print(f"Erro ao carregar PinBarStrategy: {e}")

        try:
            from src.strategies.price_action import PriceActionStrategy
            self.strategies['price_action'] = PriceActionStrategy()
            self.strategy_weights['price_action'] = 0.1
        except: pass

        try:
            from src.strategies.market_making import MarketMakingStrategy
            self.strategies['market_making'] = MarketMakingStrategy()
            self.strategy_weights['market_making'] = 0.1
        except: pass

        try:
            from src.strategies.news_momentum import NewsMomentumStrategy
            self.strategies['news_momentum'] = NewsMomentumStrategy()
            self.strategy_weights['news_momentum'] = 0.1
        except: pass
        
        # Mean reversion (estratégia existente via main.py)
        self.strategy_weights['mean_reversion'] = 0.1
        
        print(f"✅ Strategy Manager: {len(self.strategies)} estratégias carregadas")
    
    def get_combined_signal(self, symbol: str, df: pd.DataFrame,
                           current_datetime: datetime = None) -> Dict:
        """
        Combina sinais de todas as estratégias.
        """
        if current_datetime is None:
            current_datetime = datetime.now()
        
        all_signals = {}
        
        # Coletar sinais de cada estratégia
        for name, strategy in self.strategies.items():
            try:
                if name == 'pairs': continue
                
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

                elif name == 'supply_demand':
                    tick = df.iloc[-1]
                    signal_type = strategy.check_zone_retest(tick['close'], len(df), df)
                    signal = {'signal': signal_type, 'confidence': 0.8}

                elif name == 'pin_bar':
                    # Precisamos do z-score, mas como o StrategyManager é genérico, 
                    # vamos calcular um z-score simples se não for passado
                    ma = df['close'].rolling(20).mean()
                    std = df['close'].rolling(20).std()
                    z_score = (df['close'].iloc[-1] - ma.iloc[-1]) / std.iloc[-1] if std.iloc[-1] > 0 else 0
                    signal_type = strategy.check_signal(df, z_score)
                    signal = {'signal': signal_type, 'confidence': 0.75}

                # NOVAS ESTRATÉGIAS
                elif name == 'price_action':
                    pa_signals = strategy.generate_signals(df)
                    if pa_signals:
                        # Pegar o primeiro sinal para simplificar
                        setup_name, side = pa_signals[0]
                        signal = {'signal': side, 'confidence': 0.7, 'setup': setup_name}
                    else:
                        signal = {'signal': None}

                elif name == 'market_making':
                    # Lógica simplificada: sinalizar se spread for atrativo
                    spread = (df['close'].iloc[-1] * 0.0001) # Dummy spread points
                    if spread > strategy.spread_target:
                        signal = {'signal': 'NEUTRAL', 'confidence': 0.5}
                    else:
                        signal = {'signal': None}

                elif name == 'news_momentum':
                    # Simplificação: evento imaginário para teste
                    signal = strategy.detect_momentum(df, time.time() - 30)
                    if signal:
                        signal = {'signal': signal, 'confidence': 0.8}
                    else:
                        signal = {'signal': None}
                
                all_signals[name] = signal
            
            except Exception as e:
                all_signals[name] = {'signal': None, 'error': str(e)}
        
        # Decisão de qual estratégia usar
        chosen_strategy, chosen_signal = self._select_best_signal(all_signals)

        base_signal = chosen_signal.get('signal') if chosen_signal else None
        confidence  = self._calculate_confidence(chosen_signal)

        # ── ML Predictor Filter ───────────────────────────────
        ml_result = self._apply_ml_filter(symbol, df, base_signal, confidence)
        final_signal = ml_result['signal']
        final_conf   = ml_result['confidence']

        # Expose last signals for dashboard
        if final_signal in ('BUY', 'SELL'):
            self.last_signals = [{
                'symbol':     symbol,
                'signal':     final_signal,
                'direction':  final_signal,
                'strategy':   chosen_strategy or 'consensus',
                'confidence': round(final_conf, 3),
            }]

        return {
            'strategy':   chosen_strategy,
            'signal':     final_signal,
            'confidence': final_conf,
            'all_signals': all_signals,
            'ml_result':  ml_result.get('ml_direction'),
        }

    # ── ML filter implementation ──────────────────────────────

    def _apply_ml_filter(self, symbol: str, df, signal: str, confidence: float) -> dict:
        """
        Applies ML predictor as a confirmation filter.
        - If ML agrees:  confidence boosted +20%, signal passes
        - If ML disagrees: signal blocked (returns None)
        - If no model:  signal passes unchanged
        """
        predictor = self.ml_predictors.get(symbol)
        if predictor is None or signal not in ('BUY', 'SELL'):
            return {'signal': signal, 'confidence': confidence, 'ml_direction': None}

        try:
            ml = predictor.predict(df)
            ml_dir = ml['direction']  # 1=UP, -1=DOWN, 0=neutral
            ml_conf = ml['confidence']

            # Only apply filter when ML is confident enough
            if ml_conf < 0.55:
                return {'signal': signal, 'confidence': confidence, 'ml_direction': ml_dir}

            signal_to_ml = {'BUY': 1, 'SELL': -1}
            agrees = (signal_to_ml.get(signal, 0) == ml_dir)

            if agrees:
                boosted = min(confidence * 1.2, 1.0)
                return {'signal': signal, 'confidence': boosted, 'ml_direction': ml_dir}
            else:
                print(f"[ML] {symbol}: {signal} blocked — ML predicts {'UP' if ml_dir==1 else 'DOWN' if ml_dir==-1 else 'NEUTRAL'} "
                      f"(conf={ml_conf:.0%})")
                return {'signal': None, 'confidence': 0.0, 'ml_direction': ml_dir}

        except Exception as e:
            return {'signal': signal, 'confidence': confidence, 'ml_direction': None}
    
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
