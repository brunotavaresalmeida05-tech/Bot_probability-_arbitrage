"""
src/backtest_simple.py
QuantBacktester: Motor de backtest robusto com métricas quantitativas e subplots.
Baseado nas fórmulas de performance e estrutura sugeridas pelo utilizador.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import sys, os

# Adiciona o diretório raiz ao path para encontrar os módulos do projeto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import src.strategy as strat
import config.settings as cfg

class QuantBacktester:
    def __init__(self, df, symbol, initial_capital=10000, spread_pts=2.0):
        """
        df: DataFrame com colunas ['open', 'high', 'low', 'close']
        symbol: Nome do ativo (ex: 'EURUSD')
        initial_capital: Capital inicial em USD
        spread_pts: Spread médio em pontos/pips para ajuste de custo
        """
        self.df = df.copy()
        self.symbol = symbol
        self.capital = initial_capital
        self.equity = [initial_capital]
        # Ajuste de spread: assume 5 casas decimais para FX (2.0 pts = 0.00002)
        self.spread_adj = spread_pts / 10000.0 if "JPY" not in symbol else spread_pts / 100.0
        self.trades = []
        
        # Pré-calcula indicadores oficiais
        self._prepare_indicators()

    def _prepare_indicators(self):
        print(f"📊 [{self.symbol}] Calculando indicadores...")
        z, ma, atr, atr_base = strat.compute_zscore(self.df)
        self.df['z_score'] = z
        self.df['ma'] = ma
        self.df['atr'] = atr
        self.df.dropna(inplace=True)

    def calculate_metrics(self):
        """Calcula métricas quantitativas de performance."""
        if not self.trades:
            return {"Error": "Sem trades realizados"}

        equity_ser = pd.Series(self.equity)
        returns = equity_ser.pct_change().dropna()
        
        # Sharpe Ratio (Anualizado assumindo 252 dias úteis)
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() != 0 else 0
        
        # Max Drawdown
        cummax = equity_ser.cummax()
        drawdown = (cummax - equity_ser) / cummax
        max_dd = drawdown.max() * 100
        
        # Profit Factor
        profits = [t['pnl'] for t in self.trades if t['pnl'] > 0]
        losses = [abs(t['pnl']) for t in self.trades if t['pnl'] < 0]
        profit_factor = sum(profits) / sum(losses) if sum(losses) != 0 else float('inf')
        
        total_return = ((self.equity[-1] / self.capital) - 1) * 100
        win_rate = (len(profits) / len(self.trades)) * 100 if self.trades else 0

        return {
            "Total Return": f"{total_return:.2f}%",
            "Sharpe Ratio": f"{sharpe:.2f}",
            "Max Drawdown": f"{max_dd:.2f}%",
            "Profit Factor": f"{profit_factor:.2f}",
            "Win Rate": f"{win_rate:.2f}%",
            "Final Balance": f"${self.equity[-1]:.2f}",
            "Total Trades": len(self.trades)
        }

    def run_simulation(self, z_enter=2.0, z_exit=0.5):
        print(f"🚀 Simulando {self.symbol} (Z:{z_enter} / Exit:{z_exit})...")
        
        balance = self.capital
        current_pos = None # 'BUY', 'SELL'
        entry_price = 0
        
        for i in range(len(self.df)):
            row = self.df.iloc[i]
            z = row['z_score']
            price = row['close']
            ma = row['ma']
            timestamp = self.df.index[i]

            # 1. Lógica de Saída
            if current_pos:
                should_close, reason = strat.should_exit(current_pos, z, price, ma)
                
                # Ajuste de Saída por Z-Score (Parâmetro)
                if not should_close:
                    if current_pos == 'BUY' and z >= -z_exit: should_close, reason = True, "Z Reverteu"
                    elif current_pos == 'SELL' and z <= z_exit: should_close, reason = True, "Z Reverteu"

                if should_close:
                    # Cálculo de P&L com Spread (Custo)
                    pnl_raw = (price - entry_price) if current_pos == 'BUY' else (entry_price - price)
                    pnl_adj = pnl_raw - self.spread_adj
                    
                    # Valor monetário fictício (1.0 lote = 100k unidades, lucro ~10$ por pip em EURUSD)
                    trade_profit = pnl_adj * 100000 
                    balance += trade_profit
                    
                    self.trades.append({
                        'time': timestamp,
                        'type': current_pos,
                        'pnl': trade_profit,
                        'reason': reason
                    })
                    current_pos = None

            # 2. Lógica de Entrada
            else:
                if z <= -z_enter and price < ma:
                    current_pos = 'BUY'
                    entry_price = price + (self.spread_adj / 2) # Paga metade do spread na entrada
                elif z >= z_enter and price > ma:
                    current_pos = 'SELL'
                    entry_price = price - (self.spread_adj / 2)

            self.equity.append(balance)

        self.generate_report()

    def generate_report(self):
        metrics = self.calculate_metrics()
        
        # Criar Dashboard com Subplots
        fig = make_subplots(
            rows=2, cols=1, 
            shared_xaxes=True,
            vertical_spacing=0.15,
            subplot_titles=("Curva de Capital (Equity Curve)", "Indicador Z-Score & Sinais")
        )

        # Subplot 1: Equity Curve
        fig.add_trace(
            go.Scatter(y=self.equity, name="Equity", line=dict(color="#00ff88", width=2), fill='tozeroy'),
            row=1, col=1
        )

        # Subplot 2: Z-Score
        fig.add_trace(
            go.Scatter(y=self.df['z_score'], name="Z-Score", line=dict(color="#ff9900", width=1.5)),
            row=2, col=1
        )
        
        # Linhas de Referência (Z-Enter)
        fig.add_hline(y=2.0, line_dash="dash", line_color="#f85149", row=2, col=1, annotation_text="SELL Zone")
        fig.add_hline(y=-2.0, line_dash="dash", line_color="#3fb950", row=2, col=1, annotation_text="BUY Zone")
        fig.add_hline(y=0, line_color="gray", row=2, col=1)

        # Layout Estilizado
        fig.update_layout(
            height=800,
            title_text=f"📊 Relatório Quantitativo: {self.symbol}",
            template="plotly_dark",
            paper_bgcolor='#0d1117',
            plot_bgcolor='#0d1117',
            showlegend=False
        )

        # Criar pasta de relatórios se não existir
        os.makedirs("reports", exist_ok=True)
        report_path = f"reports/backtest_{self.symbol}.html"
        fig.write_html(report_path)
        
        print(f"\n✅ Relatório Gerado para {self.symbol} em: {report_path}")
        print("📈 Métricas Finais:")
        for k, v in metrics.items():
            print(f"  » {k}: {v}")

if __name__ == "__main__":
    # Teste rápido com dados sintéticos
    dates = pd.date_range(start="2024-01-01", periods=600, freq="H")
    # Simula um preço com reversão à média (Random Walk + Drift negativo para média)
    np.random.seed(42)
    prices = 1.0800 + np.cumsum(np.random.randn(600) * 0.0005)
    
    df_test = pd.DataFrame({'open': prices, 'high': prices+0.0002, 'low': prices-0.0002, 'close': prices}, index=dates)
    
    bt = QuantBacktester(df_test, "EURUSD_TEST", spread_pts=1.5)
    bt.run_simulation(z_enter=2.0, z_exit=0.5)
