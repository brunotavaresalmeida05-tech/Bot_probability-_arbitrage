"""
Performance Tracker - Enhanced analytics for the dashboard.
Calcula métricas em tempo real, milestones de capital scaling e projeções.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional


class PerformanceTracker:
    def __init__(self, initial_balance: float = 0.0):
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.equity_history = []
        self.trade_history = []
        
        # Milestones de Capital Scaling (Granular para o dashboard)
        self.milestones = [
            {"name": "Nano", "target": 100},
            {"name": "Micro", "target": 250},
            {"name": "Iniciante", "target": 500},
            {"name": "Intermediário", "target": 1000},
            {"name": "Avançado", "target": 2500},
            {"name": "Pro", "target": 5000},
            {"name": "Elite", "target": 10000},
        ]

    def update_data(self, balance: float, equity: float, trades: List[Dict]):
        """Atualiza dados base para cálculos."""
        self.current_balance = balance
        self.trade_history = trades
        self.equity_history.append({
            "timestamp": datetime.now(),
            "equity": equity
        })
        if len(self.equity_history) > 1000:
            self.equity_history.pop(0)

    def get_capital_scaling_progress(self) -> Dict:
        """Calcula progresso do capital scaling."""
        current = self.current_balance
        
        current_milestone = "Início"
        next_milestone = self.milestones[0]["name"]
        target = self.milestones[0]["target"]
        prev_target = 0
        
        for i, m in enumerate(self.milestones):
            if current >= m["target"]:
                current_milestone = m["name"]
                if i + 1 < len(self.milestones):
                    next_milestone = self.milestones[i+1]["name"]
                    target = self.milestones[i+1]["target"]
                    prev_target = m["target"]
                else:
                    next_milestone = "Máximo"
                    target = current * 2 # Placeholder
                    prev_target = m["target"]
            else:
                next_milestone = m["name"]
                target = m["target"]
                prev_target = self.milestones[i-1]["target"] if i > 0 else 0
                break
        
        progress = 0
        if target > prev_target:
            progress = min(100, max(0, (current - prev_target) / (target - prev_target) * 100))
            
        remaining = max(0, target - current)
        
        return {
            "current_milestone": current_milestone,
            "next_milestone": next_milestone,
            "progress_to_next": progress,
            "target": target,
            "remaining": remaining,
            "current": current,
            "days_to_milestone": self.estimate_days_to_milestone(target)
        }

    def estimate_days_to_milestone(self, target: float) -> int:
        """Estima dias para atingir o próximo milestone baseado no lucro diário médio."""
        if len(self.equity_history) < 5:
            return 30 # Default if not enough data
            
        # Calcular lucro diário médio dos últimos 7 dias ou disponível
        df = pd.DataFrame(self.equity_history)
        df['date'] = df['timestamp'].dt.date
        daily_equity = df.groupby('date')['equity'].last()
        daily_returns = daily_equity.diff().dropna()
        
        avg_daily_profit = daily_returns.mean()
        
        if avg_daily_profit <= 0:
            return 999 # Tendência negativa ou flat
            
        remaining = target - self.current_balance
        # Proteger contra divisão por zero e NaN
        if avg_daily_profit > 0 and not np.isnan(avg_daily_profit):
            days = int(remaining / avg_daily_profit)
        else:
            days = 999  # Valor placeholder quando não há dados
        return max(1, days)

    def get_projections(self, months: int = 12) -> Dict:
        """Gera projeções de crescimento para 12 meses."""
        conservative_rate = 0.15 # 15% ao mês
        aggressive_rate = 0.25   # 25% ao mês
        
        projections = {
            "conservative": [],
            "aggressive": []
        }
        
        for m in [1, 3, 6, 12]:
            cons = self.current_balance * (1 + conservative_rate) ** m
            aggr = self.current_balance * (1 + aggressive_rate) ** m
            
            projections["conservative"].append({
                "month": m,
                "value": cons,
                "pct": (cons / self.current_balance - 1) * 100 if self.current_balance > 0 else 0
            })
            projections["aggressive"].append({
                "month": m,
                "value": aggr,
                "pct": (aggr / self.current_balance - 1) * 100 if self.current_balance > 0 else 0
            })
            
        return projections

    def get_strategy_performance(self) -> List[Dict]:
        """Calcula métricas por estratégia."""
        if not self.trade_history:
            return []
            
        df = pd.DataFrame(self.trade_history)
        if 'strategy' not in df.columns:
            return []
            
        stats = []
        for name, group in df.groupby('strategy'):
            wins = group[group['pnl'] > 0]
            win_rate = (len(wins) / len(group)) * 100 if len(group) > 0 else 0
            avg_pnl = group['pnl'].mean()
            
            # Sharpe simplificado para o dashboard
            returns = group['pnl']
            sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if len(returns) > 1 and returns.std() != 0 else 0
            
            stats.append({
                "name": name,
                "trades": len(group),
                "win_rate": win_rate,
                "avg_pnl": avg_pnl,
                "sharpe": sharpe
            })
            
        return sorted(stats, key=lambda x: x['win_rate'], reverse=True)

    def get_realtime_tracking(self, open_positions: List[Dict]) -> Dict:
        """Status em tempo real das posições e estratégias."""
        # Isto seria alimentado pelo log de sinais e estado do bot
        # Por agora, simplificado com dados das posições
        
        active_trades = []
        for p in open_positions:
            active_trades.append({
                "symbol": p.get('symbol'),
                "pnl": p.get('pnl', 0),
                "status": "OPEN"
            })
            
        return {
            "active_positions_count": len(open_positions),
            "total_pnl": sum(p.get('pnl', 0) for p in open_positions),
            "max_profit": max([p.get('pnl', 0) for p in open_positions]) if open_positions else 0,
            "max_loss": min([p.get('pnl', 0) for p in open_positions]) if open_positions else 0,
            "pyramiding": "Ativo", # Exemplo
            "trailing_stops": f"{len([p for p in open_positions if p.get('trailing')])} ativos"
        }
