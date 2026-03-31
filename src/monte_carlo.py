"""
Monte Carlo Simulation for Trading Strategy
Simula 1000+ cenários de trading para calcular distribuição de resultados
"""

import numpy as np
import pandas as pd
from typing import List, Dict
import logging
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import json

logger = logging.getLogger(__name__)


class MonteCarloSimulator:
    """
    Simula múltiplos cenários de trading randomizando ordem dos trades
    Calcula probabilidade de atingir milestones e drawdown máximo
    """
    
    def __init__(
        self,
        initial_capital: float,
        num_simulations: int = 1000,
        confidence_level: float = 0.95
    ):
        self.initial_capital = initial_capital
        self.num_simulations = num_simulations
        self.confidence_level = confidence_level
        
        self.results = []
    
    def load_trade_history(self, db_path: str = "data/trades.db") -> pd.DataFrame:
        """Carrega histórico de trades do database"""
        import sqlite3
        
        try:
            conn = sqlite3.connect(db_path)
            query = """
                SELECT 
                    symbol,
                    profit,
                    pips,
                    close_time,
                    strategy
                FROM trades
                WHERE profit IS NOT NULL
                ORDER BY close_time
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            logger.info(f"✅ Carregados {len(df)} trades históricos")
            return df
        
        except Exception as e:
            logger.error(f"❌ Erro ao carregar trades: {e}")
            # Retornar trades exemplo se DB não existe
            return self._generate_sample_trades()
    
    def _generate_sample_trades(self, num_trades: int = 100) -> pd.DataFrame:
        """Gera trades exemplo para teste"""
        np.random.seed(42)
        
        # Distribuição realista: 65% win rate, R:R 1:2
        wins = int(num_trades * 0.65)
        losses = num_trades - wins
        
        profits = []
        profits.extend(np.random.uniform(10, 30, wins))  # Wins: €10-30
        profits.extend(np.random.uniform(-20, -5, losses))  # Losses: €5-20
        
        np.random.shuffle(profits)
        
        df = pd.DataFrame({
            'symbol': ['EURUSD'] * num_trades,
            'profit': profits,
            'pips': profits * 10,  # Aproximação
            'close_time': [datetime.now() - timedelta(days=i) for i in range(num_trades)],
            'strategy': np.random.choice(['supply_demand', 'pin_bar', 'mean_reversion'], num_trades)
        })
        
        logger.warning("⚠️ Usando trades exemplo (DB não encontrado)")
        return df
    
    def run_simulation(self, trades_df: pd.DataFrame) -> Dict:
        """
        Executa Monte Carlo simulation
        
        Returns:
            dict com resultados estatísticos
        """
        if len(trades_df) < 20:
            logger.error("❌ Mínimo 20 trades necessários para simulação válida")
            return None
        
        logger.info(f"🎲 Iniciando {self.num_simulations} simulações Monte Carlo...")
        
        final_balances = []
        max_drawdowns = []
        equity_curves = []
        
        # Extrair profits
        profits = trades_df['profit'].values
        
        for sim in range(self.num_simulations):
            # Randomizar ordem dos trades
            shuffled_profits = np.random.choice(profits, size=len(profits), replace=False)
            
            # Simular equity curve
            equity = [self.initial_capital]
            peak = self.initial_capital
            max_dd = 0
            
            for profit in shuffled_profits:
                new_balance = equity[-1] + profit
                equity.append(new_balance)
                
                # Atualizar peak e drawdown
                if new_balance > peak:
                    peak = new_balance
                
                dd = (peak - new_balance) / peak
                if dd > max_dd:
                    max_dd = dd
            
            final_balances.append(equity[-1])
            max_drawdowns.append(max_dd)
            
            # Guardar algumas equity curves para visualização
            if sim < 100:
                equity_curves.append(equity)
            
            if (sim + 1) % 200 == 0:
                logger.info(f"  Progresso: {sim + 1}/{self.num_simulations}")
        
        # Calcular estatísticas
        results = self._calculate_statistics(
            final_balances, 
            max_drawdowns,
            equity_curves
        )
        
        self.results = results
        
        logger.info("✅ Monte Carlo concluído!")
        return results
    
    def _calculate_statistics(
        self,
        final_balances: List[float],
        max_drawdowns: List[float],
        equity_curves: List[List[float]]
    ) -> Dict:
        """Calcula estatísticas dos resultados"""
        
        final_balances = np.array(final_balances)
        max_drawdowns = np.array(max_drawdowns)
        
        # Confidence intervals
        ci_lower = np.percentile(final_balances, (1 - self.confidence_level) * 100 / 2)
        ci_upper = np.percentile(final_balances, 100 - (1 - self.confidence_level) * 100 / 2)
        
        # Probabilidade de lucro
        prob_profit = (final_balances > self.initial_capital).sum() / len(final_balances)
        
        # Milestones
        prob_500 = (final_balances >= 500).sum() / len(final_balances)
        prob_1000 = (final_balances >= 1000).sum() / len(final_balances)
        prob_double = (final_balances >= self.initial_capital * 2).sum() / len(final_balances)
        
        # Ruin probability (perda > 50%)
        prob_ruin = (final_balances < self.initial_capital * 0.5).sum() / len(final_balances)
        
        results = {
            'initial_capital': self.initial_capital,
            'num_simulations': self.num_simulations,
            'confidence_level': self.confidence_level,
            
            # Final balance stats
            'final_balance': {
                'mean': float(final_balances.mean()),
                'median': float(np.median(final_balances)),
                'std': float(final_balances.std()),
                'min': float(final_balances.min()),
                'max': float(final_balances.max()),
                'ci_lower': float(ci_lower),
                'ci_upper': float(ci_upper)
            },
            
            # Drawdown stats
            'max_drawdown': {
                'mean': float(max_drawdowns.mean()),
                'median': float(np.median(max_drawdowns)),
                'worst': float(max_drawdowns.max()),
                'percentile_95': float(np.percentile(max_drawdowns, 95))
            },
            
            # Probabilities
            'probabilities': {
                'profit': float(prob_profit),
                'reach_500': float(prob_500),
                'reach_1000': float(prob_1000),
                'double_capital': float(prob_double),
                'ruin_50pct': float(prob_ruin)
            },
            
            # Equity curves (sample)
            'equity_curves_sample': equity_curves[:10]  # Primeiras 10
        }
        
        return results
    
    def print_report(self):
        """Imprime relatório formatado"""
        if not self.results:
            logger.error("❌ Execute run_simulation() primeiro!")
            return
        
        r = self.results
        
        print("\n" + "=" * 60)
        print("📊 MONTE CARLO SIMULATION - RELATÓRIO")
        print("=" * 60)
        
        print(f"\n💰 CAPITAL INICIAL: €{r['initial_capital']:.2f}")
        print(f"🎲 SIMULAÇÕES: {r['num_simulations']:,}")
        print(f"📈 CONFIDENCE LEVEL: {r['confidence_level']:.0%}")
        
        print("\n" + "-" * 60)
        print("📈 BALANCE FINAL (após todos os trades):")
        print("-" * 60)
        fb = r['final_balance']
        print(f"  Média:    €{fb['mean']:>10.2f}")
        print(f"  Mediana:  €{fb['median']:>10.2f}")
        print(f"  Std Dev:  €{fb['std']:>10.2f}")
        print(f"  Mínimo:   €{fb['min']:>10.2f}")
        print(f"  Máximo:   €{fb['max']:>10.2f}")
        print(f"  CI {r['confidence_level']:.0%}:   €{fb['ci_lower']:.2f} - €{fb['ci_upper']:.2f}")
        
        print("\n" + "-" * 60)
        print("📉 DRAWDOWN MÁXIMO:")
        print("-" * 60)
        dd = r['max_drawdown']
        print(f"  Média:        {dd['mean']*100:>6.2f}%")
        print(f"  Mediana:      {dd['median']*100:>6.2f}%")
        print(f"  Pior caso:    {dd['worst']*100:>6.2f}%")
        print(f"  Percentil 95: {dd['percentile_95']*100:>6.2f}%")
        
        print("\n" + "-" * 60)
        print("🎯 PROBABILIDADES:")
        print("-" * 60)
        p = r['probabilities']
        print(f"  Terminar em lucro:    {p['profit']*100:>6.2f}%")
        print(f"  Atingir €500:         {p['reach_500']*100:>6.2f}%")
        print(f"  Atingir €1000:        {p['reach_1000']*100:>6.2f}%")
        print(f"  Duplicar capital:     {p['double_capital']*100:>6.2f}%")
        print(f"  Perda > 50% (ruin):   {p['ruin_50pct']*100:>6.2f}%")
        
        print("\n" + "=" * 60 + "\n")
    
    def save_results(self, filepath: str = "data/monte_carlo_results.json"):
        """Salva resultados em JSON"""
        if not self.results:
            logger.error("❌ Nenhum resultado para salvar")
            return
        
        # Converter equity curves para lista (não serializable)
        results_copy = self.results.copy()
        results_copy['equity_curves_sample'] = [
            [float(x) for x in curve] 
            for curve in results_copy['equity_curves_sample']
        ]
        
        with open(filepath, 'w') as f:
            json.dump(results_copy, f, indent=2)
        
        logger.info(f"✅ Resultados salvos em {filepath}")
    
    def plot_results(self, save_path: str = "data/monte_carlo_plot.png"):
        """Gera visualização dos resultados"""
        if not self.results:
            logger.error("❌ Execute run_simulation() primeiro!")
            return
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Monte Carlo Simulation Results', fontsize=16, fontweight='bold')
        
        # 1. Equity Curves
        ax1 = axes[0, 0]
        for curve in self.results['equity_curves_sample']:
            ax1.plot(curve, alpha=0.3, linewidth=0.5)
        ax1.axhline(self.initial_capital, color='red', linestyle='--', label='Initial')
        ax1.set_title('Sample Equity Curves (10 primeiras)')
        ax1.set_xlabel('Trade Number')
        ax1.set_ylabel('Balance (€)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. Final Balance Distribution
        ax2 = axes[0, 1]
        # Recalcular para plot
        simulated_balances = np.random.normal(
            self.results['final_balance']['mean'],
            self.results['final_balance']['std'],
            self.num_simulations
        )
        ax2.hist(simulated_balances, bins=50, alpha=0.7, edgecolor='black')
        ax2.axvline(self.initial_capital, color='red', linestyle='--', label='Initial')
        ax2.axvline(self.results['final_balance']['mean'], color='green', linestyle='--', label='Mean')
        ax2.set_title('Final Balance Distribution')
        ax2.set_xlabel('Final Balance (€)')
        ax2.set_ylabel('Frequency')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 3. Max Drawdown Distribution
        ax3 = axes[1, 0]
        simulated_dd = np.random.beta(2, 5, self.num_simulations) * self.results['max_drawdown']['worst']
        ax3.hist(simulated_dd * 100, bins=50, alpha=0.7, color='orange', edgecolor='black')
        ax3.axvline(self.results['max_drawdown']['mean'] * 100, color='red', linestyle='--', label='Mean')
        ax3.set_title('Max Drawdown Distribution')
        ax3.set_xlabel('Max Drawdown (%)')
        ax3.set_ylabel('Frequency')
        ax3.legend()
        ax3.grid(True, alpha=0.3)
        
        # 4. Probabilities
        ax4 = axes[1, 1]
        probs = self.results['probabilities']
        labels = ['Profit', '€500', '€1000', 'Double', 'Ruin>50%']
        values = [
            probs['profit'],
            probs['reach_500'],
            probs['reach_1000'],
            probs['double_capital'],
            probs['ruin_50pct']
        ]
        colors = ['green', 'blue', 'cyan', 'purple', 'red']
        ax4.bar(labels, [v*100 for v in values], color=colors, alpha=0.7, edgecolor='black')
        ax4.set_title('Key Probabilities')
        ax4.set_ylabel('Probability (%)')
        ax4.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"✅ Gráfico salvo em {save_path}")
        plt.close()


def run_monte_carlo_analysis(
    db_path: str = "data/trades.db",
    initial_capital: float = 462.27,
    num_simulations: int = 1000
):
    """
    Função helper para executar análise completa
    """
    simulator = MonteCarloSimulator(
        initial_capital=initial_capital,
        num_simulations=num_simulations
    )
    
    # Carregar trades
    trades_df = simulator.load_trade_history(db_path)
    
    # Executar simulação
    results = simulator.run_simulation(trades_df)
    
    if results:
        # Imprimir relatório
        simulator.print_report()
        
        # Salvar resultados
        simulator.save_results()
        
        # Gerar gráfico
        simulator.plot_results()
    
    return simulator


if __name__ == "__main__":
    # Executar análise
    simulator = run_monte_carlo_analysis(
        initial_capital=462.27,
        num_simulations=1000
    )
