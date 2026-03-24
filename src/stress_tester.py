"""
src/stress_tester.py
Auditoria e Stress Testing: Monte Carlo, Slippage e Análise de Risco.
Lê os dados reais de 'logs/trades.csv' para validar a robustez do sistema.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os

class StressTester:
    def __init__(self, trades_csv="logs/trades.csv", initial_balance=10000):
        self.trades_csv = trades_csv
        self.initial_balance = initial_balance
        self.df = self._load_data()

    def _load_data(self):
        """Carrega os trades reais ou gera dados sintéticos para teste."""
        if not os.path.exists(self.trades_csv):
            print(f"⚠️ Arquivo {self.trades_csv} não encontrado. Gerando dados sintéticos para demonstração.")
            # Dados sintéticos: 100 trades com média 50$ e volatilidade 150$
            np.random.seed(42)
            data = {
                'profit': np.random.normal(50, 150, 100),
                'symbol': ['EURUSD'] * 100,
                'timestamp': pd.date_range(start="2024-01-01", periods=100, freq="D")
            }
            return pd.DataFrame(data)
        
        try:
            df = pd.read_csv(self.trades_csv)
            # Garante que a coluna profit existe (pode ser 'profit' ou 'profit_currency')
            if 'profit_currency' in df.columns:
                df['profit'] = df['profit_currency']
            elif 'pnl' in df.columns:
                df['profit'] = df['pnl']
                
            if 'profit' not in df.columns:
                raise ValueError("Coluna de lucro não encontrada no CSV.")
            return df
        except Exception as e:
            print(f"❌ Erro ao ler CSV: {e}")
            return pd.DataFrame()

    def run_monte_carlo(self, iterations=1000):
        """Baralha os trades para simular 1000 caminhos possíveis da banca."""
        if self.df.empty: return None, None
        
        all_paths = []
        final_returns = []
        profits = self.df['profit'].values
        
        for _ in range(iterations):
            shuffled = np.random.permutation(profits)
            path = np.cumsum(shuffled) + self.initial_balance
            all_paths.append(path)
            final_returns.append(path[-1])
            
        return np.array(all_paths), np.array(final_returns)

    def simulate_slippage(self, loss_per_trade=5.0):
        """Simula o impacto de custos extras ou execução lenta (slippage)."""
        if self.df.empty: return None
        adjusted_profits = self.df['profit'] - loss_per_trade 
        return np.cumsum(adjusted_profits) + self.initial_balance

    def generate_stress_report(self):
        if self.df.empty:
            print("❌ Sem dados para gerar relatório.")
            return

        paths, finals = self.run_monte_carlo()
        slippage_path = self.simulate_slippage(loss_per_trade=2.0)
        
        # Estatísticas
        prob_of_loss = (finals < self.initial_balance).sum() / len(finals) * 100
        worst_case = np.min(finals)
        avg_case = np.mean(finals)
        best_case = np.max(finals)

        # Dashboard com Subplots
        fig = make_subplots(
            rows=1, cols=2, 
            subplot_titles=("Simulação de Monte Carlo (1000 Caminhos)", "Distribuição de Retorno Final"),
            column_widths=[0.7, 0.3]
        )

        # 1. Caminhos de Monte Carlo (Equity Paths)
        # Plotamos apenas 100 para performance do browser
        x_axis = np.arange(len(self.df))
        for i in range(min(100, len(paths))):
            fig.add_trace(go.Scatter(
                x=x_axis, y=paths[i], mode='lines', 
                line=dict(width=0.5, color='#58a6ff'), 
                opacity=0.2, showlegend=False
            ), row=1, col=1)

        # Adicionar a linha de Slippage para comparação
        fig.add_trace(go.Scatter(
            x=x_axis, y=slippage_path, mode='lines',
            name="Com Slippage (-2$)", line=dict(color='#f85149', width=2, dash='dash')
        ), row=1, col=1)

        # 2. Histograma de Retornos Finais
        fig.add_trace(go.Histogram(
            x=finals, nbinsx=30, 
            marker_color='#00ff88', opacity=0.7,
            name="Freq. Retorno"
        ), row=1, col=2)

        # Layout Dark Mode
        fig.update_layout(
            title=f"📊 Stress Test & Monte Carlo Auditor - {len(self.df)} Trades",
            template="plotly_dark",
            paper_bgcolor="#0d1117",
            plot_bgcolor="#0d1117",
            showlegend=True,
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )

        os.makedirs("reports", exist_ok=True)
        report_file = "reports/stress_test_report.html"
        fig.write_html(report_file)
        
        print(f"\n{'='*40}")
        print(f"✅ AUDITORIA CONCLUÍDA ({len(self.df)} trades)")
        print(f" » Probabilidade de Prejuízo: {prob_of_loss:.2f}%")
        print(f" » Pior Cenário Simulado: ${worst_case:.2f}")
        print(f" » Retorno Médio Esperado: ${avg_case:.2f}")
        print(f" » Melhor Cenário Simulado: ${best_case:.2f}")
        print(f"📂 Relatório visual salvo em: {report_file}")
        print(f"{'='*40}\n")

if __name__ == "__main__":
    tester = StressTester()
    tester.generate_stress_report()
