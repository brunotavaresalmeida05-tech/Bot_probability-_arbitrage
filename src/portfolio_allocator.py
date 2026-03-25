"""
portfolio_allocator.py
Sistema de alocação dinâmica de portfolio - SEM LIMITES DE TIER.
Baseado em Renaissance Technologies, Citadel, Two Sigma.

FILOSOFIA:
- Opera QUALQUER ativo
- Aloca capital baseado em SHARPE (performance)
- Risk total fixo (% do capital)
- Escala infinitamente (€100 → €1B+)

RESULTADO:
- Ativos bons recebem MAIS capital
- Ativos fracos recebem MENOS (mas não são bloqueados)
- Multiplicação de capital RÁPIDA via diversificação inteligente
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class AssetMetrics:
    """Métricas de performance de um ativo."""
    symbol: str
    sharpe: float
    win_rate: float
    avg_return_pct: float
    volatility: float
    n_trades: int
    last_updated: datetime


class PortfolioAllocator:
    """
    Alocação dinâmica de portfolio sem limites de tier.
    Escala de €100 a €1B+ automaticamente.
    """
    
    def __init__(self, 
                 total_capital: float,
                 max_total_risk_pct: float = 10.0,
                 min_sharpe_threshold: float = 0.5,
                 rebalance_interval_hours: int = 24):
        """
        Args:
            total_capital: Capital total disponível
            max_total_risk_pct: Risk total máximo (% do capital)
            min_sharpe_threshold: Sharpe mínimo para alocar capital
            rebalance_interval_hours: Frequência de rebalanceamento
        """
        self.total_capital = total_capital
        self.max_total_risk_pct = max_total_risk_pct
        self.min_sharpe_threshold = min_sharpe_threshold
        self.rebalance_interval = timedelta(hours=rebalance_interval_hours)
        
        # Asset database
        self.assets: Dict[str, AssetMetrics] = {}
        self.allocations: Dict[str, float] = {}  # symbol -> risk %
        self.last_rebalance = None
        
        # Performance tracking
        self.total_risk_used = 0.0
        self.n_active_assets = 0
    
    def register_asset(self, 
                      symbol: str,
                      sharpe: float,
                      win_rate: float = 0.5,
                      avg_return_pct: float = 1.0,
                      volatility: float = 1.0,
                      n_trades: int = 0):
        """
        Registra ou atualiza métricas de um ativo.
        """
        self.assets[symbol] = AssetMetrics(
            symbol=symbol,
            sharpe=sharpe,
            win_rate=win_rate,
            avg_return_pct=avg_return_pct,
            volatility=volatility,
            n_trades=n_trades,
            last_updated=datetime.now()
        )
    
    def register_backtest_results(self, results: Dict[str, Dict]):
        """
        Registra resultados de backtests em batch.
        
        Args:
            results: {
                "EURUSD": {"sharpe": 1.83, "win_rate": 0.62, ...},
                "AUDUSD": {"sharpe": 1.66, "win_rate": 0.59, ...},
                ...
            }
        """
        for symbol, metrics in results.items():
            self.register_asset(
                symbol=symbol,
                sharpe=metrics.get("sharpe", 0.0),
                win_rate=metrics.get("win_rate", 0.5),
                avg_return_pct=metrics.get("avg_return_pct", 1.0),
                volatility=metrics.get("volatility", 1.0),
                n_trades=metrics.get("n_trades", 0)
            )
    
    def calculate_allocations(self, method: str = "sharpe_weighted") -> Dict[str, float]:
        """
        Calcula alocação de risco para cada ativo.
        
        Args:
            method: "sharpe_weighted", "equal_weight", "volatility_adjusted"
        
        Returns:
            {symbol: risk_pct}
        """
        # Filtrar ativos válidos
        valid_assets = {
            symbol: metrics 
            for symbol, metrics in self.assets.items()
            if metrics.sharpe >= self.min_sharpe_threshold
        }
        
        if not valid_assets:
            return {}
        
        if method == "sharpe_weighted":
            return self._sharpe_weighted_allocation(valid_assets)
        elif method == "equal_weight":
            return self._equal_weight_allocation(valid_assets)
        elif method == "volatility_adjusted":
            return self._volatility_adjusted_allocation(valid_assets)
        else:
            raise ValueError(f"Unknown method: {method}")
    
    def _sharpe_weighted_allocation(self, assets: Dict[str, AssetMetrics]) -> Dict[str, float]:
        """
        Aloca baseado em Sharpe ratio.
        Ativos com Sharpe maior recebem mais capital.
        """
        # Calcular pesos baseados em Sharpe
        sharpes = {symbol: max(metrics.sharpe, 0.1) for symbol, metrics in assets.items()}
        total_sharpe = sum(sharpes.values())
        
        # Calcular % do risk total para cada ativo
        allocations = {}
        for symbol, sharpe in sharpes.items():
            weight = sharpe / total_sharpe
            risk_pct = weight * self.max_total_risk_pct
            allocations[symbol] = round(risk_pct, 3)
        
        return allocations
    
    def _equal_weight_allocation(self, assets: Dict[str, AssetMetrics]) -> Dict[str, float]:
        """Aloca igualmente entre todos os ativos."""
        n = len(assets)
        risk_per_asset = self.max_total_risk_pct / n
        return {symbol: risk_per_asset for symbol in assets.keys()}
    
    def _volatility_adjusted_allocation(self, assets: Dict[str, AssetMetrics]) -> Dict[str, float]:
        """
        Aloca inversamente à volatilidade.
        Ativos menos voláteis recebem mais.
        """
        inv_vols = {symbol: 1.0 / max(metrics.volatility, 0.1) for symbol, metrics in assets.items()}
        total_inv_vol = sum(inv_vols.values())
        
        allocations = {}
        for symbol, inv_vol in inv_vols.items():
            weight = inv_vol / total_inv_vol
            risk_pct = weight * self.max_total_risk_pct
            allocations[symbol] = round(risk_pct, 3)
        
        return allocations
    
    def rebalance(self, force: bool = False) -> bool:
        """
        Rebalancea portfolio se necessário.
        
        Returns:
            True se rebalanceou, False caso contrário
        """
        now = datetime.now()
        
        # Check se precisa rebalancear
        if not force and self.last_rebalance:
            if now - self.last_rebalance < self.rebalance_interval:
                return False
        
        # Recalcular alocações
        self.allocations = self.calculate_allocations(method="sharpe_weighted")
        self.total_risk_used = sum(self.allocations.values())
        self.n_active_assets = len(self.allocations)
        self.last_rebalance = now
        
        return True
    
    def get_position_size(self, 
                         symbol: str, 
                         sl_distance: float,
                         price: float) -> Tuple[float, float]:
        """
        Calcula tamanho de posição baseado em alocação dinâmica.
        
        Args:
            symbol: Símbolo do ativo
            sl_distance: Distância do SL em preço
            price: Preço atual
        
        Returns:
            (lot_size, risk_money)
        """
        # Rebalancear se necessário
        self.rebalance()
        
        # Get alocação para este ativo
        risk_pct = self.allocations.get(symbol, 0.0)
        
        if risk_pct == 0.0:
            return 0.0, 0.0
        
        # Calcular risk em dinheiro
        risk_money = self.total_capital * risk_pct / 100
        
        # Calcular lot size (simplificado - adaptar ao MT5)
        if sl_distance > 0:
            lot_size = risk_money / (sl_distance * price)
        else:
            lot_size = 0.0
        
        # LIMITE MÁXIMO ABSOLUTO
        if lot_size > 0.10:
            lot_size = 0.10
            
        return lot_size, risk_money
    
    def get_allocation_report(self) -> pd.DataFrame:
        """Retorna relatório de alocação atual."""
        if not self.allocations:
            self.rebalance(force=True)
        
        data = []
        for symbol, risk_pct in sorted(self.allocations.items(), key=lambda x: x[1], reverse=True):
            metrics = self.assets[symbol]
            risk_money = self.total_capital * risk_pct / 100
            
            data.append({
                "Symbol": symbol,
                "Sharpe": metrics.sharpe,
                "Risk %": risk_pct,
                "Risk €": risk_money,
                "Win Rate": f"{metrics.win_rate*100:.1f}%",
                "Avg Return": f"{metrics.avg_return_pct:.2f}%",
                "Trades": metrics.n_trades,
            })
        
        df = pd.DataFrame(data)
        return df
    
    def update_capital(self, new_capital: float):
        """
        Atualiza capital total.
        Sistema escala automaticamente.
        """
        old_capital = self.total_capital
        self.total_capital = new_capital
        
        # Forçar rebalanceamento
        self.rebalance(force=True)
        
        growth_pct = ((new_capital - old_capital) / old_capital * 100) if old_capital > 0 else 0
        
        print(f"\n{'='*60}")
        print(f"💰 CAPITAL UPDATE")
        print(f"{'='*60}")
        print(f"Old: €{old_capital:,.2f}")
        print(f"New: €{new_capital:,.2f}")
        print(f"Growth: {growth_pct:+.2f}%")
        print(f"Total Risk: {self.total_risk_used:.2f}%")
        print(f"Active Assets: {self.n_active_assets}")
        print(f"{'='*60}\n")
    
    def get_summary(self) -> Dict:
        """Sumário do portfolio."""
        if not self.allocations:
            self.rebalance(force=True)
        
        return {
            "total_capital": self.total_capital,
            "max_total_risk_pct": self.max_total_risk_pct,
            "actual_risk_used_pct": self.total_risk_used,
            "n_active_assets": self.n_active_assets,
            "min_sharpe_threshold": self.min_sharpe_threshold,
            "last_rebalance": self.last_rebalance,
            "top_allocation": max(self.allocations.items(), key=lambda x: x[1]) if self.allocations else None,
        }


# ============================================================
#  EXEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    print("="*60)
    print("🚀 DYNAMIC PORTFOLIO ALLOCATOR")
    print("Sistema profissional sem limites de tier")
    print("="*60 + "\n")
    
    # Inicializar com €455
    allocator = PortfolioAllocator(
        total_capital=455.0,
        max_total_risk_pct=10.0,  # 10% risk total
        min_sharpe_threshold=0.5,
    )
    
    # Registrar ativos com suas métricas
    # (normalmente vem de backtests)
    allocator.register_backtest_results({
        "EURUSD": {"sharpe": 1.83, "win_rate": 0.62, "avg_return_pct": 9.6, "volatility": 0.8, "n_trades": 112},
        "AUDUSD": {"sharpe": 1.66, "win_rate": 0.59, "avg_return_pct": 9.0, "volatility": 0.9, "n_trades": 121},
        "GBPUSD": {"sharpe": 0.18, "win_rate": 0.51, "avg_return_pct": 0.9, "volatility": 1.2, "n_trades": 126},
        "USDJPY": {"sharpe": 0.15, "win_rate": 0.49, "avg_return_pct": 0.7, "volatility": 1.1, "n_trades": 170},
        "XAUUSD": {"sharpe": 1.45, "win_rate": 0.58, "avg_return_pct": 7.5, "volatility": 1.5, "n_trades": 89},
        "BTCUSD": {"sharpe": 1.20, "win_rate": 0.55, "avg_return_pct": 12.0, "volatility": 3.0, "n_trades": 45},
    })
    
    # Calcular alocações
    allocator.rebalance(force=True)
    
    # Mostrar relatório
    print("📊 ALLOCATION REPORT:")
    print(allocator.get_allocation_report().to_string(index=False))
    print()
    
    # Sumário
    summary = allocator.get_summary()
    print(f"💼 PORTFOLIO SUMMARY:")
    print(f"  Capital: €{summary['total_capital']:,.2f}")
    print(f"  Risk Used: {summary['actual_risk_used_pct']:.2f}%")
    print(f"  Active Assets: {summary['n_active_assets']}")
    if summary['top_allocation']:
        top_symbol, top_pct = summary['top_allocation']
        print(f"  Top Allocation: {top_symbol} ({top_pct:.2f}%)")
    print()
    
    # Simular crescimento de capital
    print("🔄 SIMULANDO CRESCIMENTO DE CAPITAL...\n")
    
    capital_stages = [455, 1000, 5000, 50000, 500000, 5_000_000, 50_000_000]
    
    for capital in capital_stages:
        allocator.update_capital(capital)
        print(f"📊 ALLOCATION at €{capital:,.0f}:")
        df = allocator.get_allocation_report()
        print(df[["Symbol", "Sharpe", "Risk %", "Risk €"]].to_string(index=False))
        print("\n" + "─"*60 + "\n")
        
        input("Press Enter para próximo estágio...")
