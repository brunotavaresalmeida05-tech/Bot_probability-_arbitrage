"""
Performance Analytics
Métricas institucionais: Sharpe, Sortino, Calmar, etc.
"""

import numpy as np
import pandas as pd
from datetime import datetime


class PerformanceAnalyzer:
    def __init__(self):
        self.equity_history = []
        self.trade_history = []
        self.daily_returns = []

    def add_equity_point(self, equity: float, timestamp=None):
        """Adiciona ponto à equity curve."""
        if timestamp is None:
            timestamp = datetime.now()

        self.equity_history.append({
            'time': timestamp,
            'equity': equity,
        })

        # Calcular daily return se houver ponto anterior
        if len(self.equity_history) >= 2:
            prev = self.equity_history[-2]['equity']
            if prev > 0:
                self.daily_returns.append((equity - prev) / prev)

    def add_trade(self, trade: dict):
        """Adiciona trade ao histórico."""
        self.trade_history.append(trade)

    def calculate_sharpe(self, risk_free_rate=0.02) -> float:
        """
        Sharpe Ratio = (Return - RiskFreeRate) / Volatility

        Args:
            risk_free_rate: Taxa livre de risco anual (default 2%)
        """
        if len(self.daily_returns) < 2:
            return 0.0

        returns = np.array(self.daily_returns)

        # Anualizar
        annual_return = np.mean(returns) * 252
        annual_vol = np.std(returns) * np.sqrt(252)

        if annual_vol == 0:
            return 0.0

        return (annual_return - risk_free_rate) / annual_vol

    def calculate_sortino(self, risk_free_rate=0.02) -> float:
        """
        Sortino Ratio - Similar ao Sharpe mas usa apenas downside volatility.
        """
        if len(self.daily_returns) < 2:
            return 0.0

        returns = np.array(self.daily_returns)

        # Downside returns (só negativos)
        downside = returns[returns < 0]

        if len(downside) == 0:
            return float('inf')

        annual_return = np.mean(returns) * 252
        downside_vol = np.std(downside) * np.sqrt(252)

        if downside_vol == 0:
            return float('inf')

        return (annual_return - risk_free_rate) / downside_vol

    def calculate_calmar(self) -> float:
        """
        Calmar Ratio = Annual Return / Max Drawdown
        """
        if len(self.equity_history) < 2:
            return 0.0

        equity = [e['equity'] for e in self.equity_history]

        # Annual return
        total_return = (equity[-1] - equity[0]) / equity[0]
        days = (self.equity_history[-1]['time'] -
                self.equity_history[0]['time']).days
        annual_return = total_return * (365 / days) if days > 0 else 0

        # Max drawdown
        max_dd = self.calculate_max_drawdown()['max_dd_pct']

        if max_dd == 0:
            return float('inf')

        return annual_return / abs(max_dd / 100)

    def calculate_max_drawdown(self) -> dict:
        """
        Max Drawdown - Maior queda do peak.
        """
        if not self.equity_history:
            return {'max_dd_pct': 0, 'max_dd_duration': 0}

        equity = [e['equity'] for e in self.equity_history]

        peak = equity[0]
        max_dd = 0
        max_dd_duration = 0
        current_dd_duration = 0

        for e in equity:
            if e > peak:
                peak = e
                current_dd_duration = 0
            else:
                dd = (e - peak) / peak * 100
                max_dd = min(max_dd, dd)
                current_dd_duration += 1
                max_dd_duration = max(max_dd_duration, current_dd_duration)

        return {
            'max_dd_pct': max_dd,
            'max_dd_duration': max_dd_duration,
        }

    def calculate_win_loss_stats(self) -> dict:
        """Estatísticas de wins/losses."""
        if not self.trade_history:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'expectancy': 0,
            }

        wins = [t['pnl'] for t in self.trade_history if t.get('pnl', 0) > 0]
        losses = [t['pnl'] for t in self.trade_history if t.get('pnl', 0) < 0]

        total_trades = len(self.trade_history)
        n_wins = len(wins)
        n_losses = len(losses)

        win_rate = n_wins / total_trades if total_trades > 0 else 0
        avg_win = float(np.mean(wins)) if wins else 0
        avg_loss = abs(float(np.mean(losses))) if losses else 0

        # Profit Factor
        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # Expectancy
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

        return {
            'total_trades': total_trades,
            'wins': n_wins,
            'losses': n_losses,
            'win_rate': win_rate * 100,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
        }

    def get_strategy_breakdown(self) -> pd.DataFrame:
        """Performance por estratégia."""
        if not self.trade_history:
            return pd.DataFrame()

        df = pd.DataFrame(self.trade_history)

        if 'strategy' not in df.columns:
            return pd.DataFrame()

        results = []
        for name, group in df.groupby('strategy'):
            pnl_vals = group['pnl']
            results.append({
                'strategy': name,
                'trades': len(group),
                'total_pnl': pnl_vals.sum(),
                'avg_pnl': pnl_vals.mean(),
                'win_rate': (pnl_vals > 0).sum() / len(group) * 100,
                'std_pnl': pnl_vals.std(),
            })

        return pd.DataFrame(results).round(2)

    def generate_report(self) -> dict:
        """Relatório completo de performance."""
        wl_stats = self.calculate_win_loss_stats()
        dd_stats = self.calculate_max_drawdown()

        return {
            'sharpe': self.calculate_sharpe(),
            'sortino': self.calculate_sortino(),
            'calmar': self.calculate_calmar(),
            'win_rate': wl_stats['win_rate'],
            'profit_factor': wl_stats['profit_factor'],
            'expectancy': wl_stats['expectancy'],
            'max_dd': dd_stats['max_dd_pct'],
            'total_trades': wl_stats['total_trades'],
            'avg_win': wl_stats['avg_win'],
            'avg_loss': wl_stats['avg_loss'],
        }
