"""
capital_scaling.py
Sistema de scaling de capital institucional com tiers dinâmicos.
À medida que o capital cresce, o sistema ajusta automaticamente:
- Risco por trade
- Número de ativos operados
- Diversificação
- Estratégias ativas
"""

from typing import Dict, Tuple, List
from datetime import datetime


class CapitalScaling:
    """
    Gestão de scaling baseada em tiers de AUM (Assets Under Management).
    Inspirado em práticas de hedge funds institucionais.
    """
    
    # Definição de tiers (valores em USD)
    TIERS = {
        "micro": {
            "min": 0,
            "max": 10_000,
            "risk_per_trade_pct": 2.0,      # Mais agressivo no início
            "max_symbols": 4,
            "max_positions": 2,
            "strategies": ["mean_reversion"],
            "max_correlation": 0.85,
            "description": "Fase inicial - foco em poucos ativos com edge comprovado"
        },
        "small": {
            "min": 10_000,
            "max": 100_000,
            "risk_per_trade_pct": 1.0,
            "max_symbols": 8,
            "max_positions": 4,
            "strategies": ["mean_reversion", "stat_arb"],
            "max_correlation": 0.75,
            "description": "Desenvolvimento - adicionar pairs trading"
        },
        "medium": {
            "min": 100_000,
            "max": 500_000,
            "risk_per_trade_pct": 0.75,
            "max_symbols": 15,
            "max_positions": 8,
            "strategies": ["mean_reversion", "stat_arb", "macro", "multi_timeframe"],
            "max_correlation": 0.70,
            "description": "Consolidação - diversificação completa"
        },
        "large": {
            "min": 500_000,
            "max": 5_000_000,
            "risk_per_trade_pct": 0.5,
            "max_symbols": 30,
            "max_positions": 15,
            "strategies": ["mean_reversion", "stat_arb", "macro", "cta", "market_neutral"],
            "max_correlation": 0.65,
            "description": "Institucional pequeno - múltiplas estratégias"
        },
        "mega": {
            "min": 5_000_000,
            "max": float('inf'),
            "risk_per_trade_pct": 0.3,
            "max_symbols": 50,
            "max_positions": 30,
            "strategies": ["all"],
            "max_correlation": 0.60,
            "description": "Institucional grande - máxima diversificação"
        }
    }
    
    # Símbolos recomendados por tier
    TIER_SYMBOLS = {
        "micro": [
            "EURUSD",  # Melhor Sharpe comprovado
            "AUDUSD",  # Segunda melhor
        ],
        "small": [
            "EURUSD", "AUDUSD", "GBPUSD", "USDJPY",
        ],
        "medium": [
            "EURUSD", "AUDUSD", "GBPUSD", "USDJPY",
            "USDCHF", "USDCAD", "NZDUSD",
            "XAUUSD",  # Gold
        ],
        "large": [
            "EURUSD", "AUDUSD", "GBPUSD", "USDJPY",
            "USDCHF", "USDCAD", "NZDUSD",
            "XAUUSD", "XAGUSD",  # Metals
            "US500", "US100", "GER40",  # Indices
            "BTCUSD",  # Crypto se disponível
        ],
        "mega": [
            # All symbols + commodities + bonds
            "EURUSD", "AUDUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "NZDUSD",
            "EURGBP", "EURJPY", "GBPJPY", "AUDJPY",
            "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD",
            "US500", "US100", "GER40", "UK100", "JP225",
            "BTCUSD", "ETHUSD",
            "USOIL", "UKOIL", "NGAS",  # Commodities
        ]
    }
    
    def __init__(self):
        self.current_tier = None
        self.tier_history = []
    
    def get_tier(self, balance: float) -> str:
        """Determina o tier atual baseado no saldo."""
        for tier_name, tier_config in self.TIERS.items():
            if tier_config["min"] <= balance < tier_config["max"]:
                return tier_name
        return "mega"  # Fallback
    
    def get_config(self, balance: float) -> Dict:
        """
        Retorna configuração completa para o tier atual.
        """
        tier = self.get_tier(balance)
        
        # Track tier changes
        if tier != self.current_tier:
            self.tier_history.append({
                "timestamp": datetime.now(),
                "old_tier": self.current_tier,
                "new_tier": tier,
                "balance": balance
            })
            self.current_tier = tier
        
        config = self.TIERS[tier].copy()
        config["tier"] = tier
        config["balance"] = balance
        config["recommended_symbols"] = self.TIER_SYMBOLS[tier]
        
        return config
    
    def should_scale_up(self, balance: float, entry_balance: float) -> Tuple[bool, str]:
        """
        Verifica se deve fazer scale up (adicionar mais ativos/estratégias).
        Critérios:
        - Balance cresceu >100% desde entrada no tier
        - Está próximo do próximo tier (>80% do max)
        """
        tier = self.get_tier(balance)
        tier_config = self.TIERS[tier]
        
        # Próximo do limite superior
        if balance >= tier_config["max"] * 0.8:
            return True, f"Próximo do tier superior ({balance/tier_config['max']*100:.1f}%)"
        
        # Crescimento significativo
        if entry_balance > 0 and balance >= entry_balance * 2.0:
            return True, f"Balance dobrou desde entrada no tier"
        
        return False, ""
    
    def should_scale_down(self, balance: float, peak_balance: float) -> Tuple[bool, str]:
        """
        Verifica se deve fazer scale down (reduzir exposição).
        Critérios:
        - Drawdown >30% desde peak
        - Caiu para tier inferior
        """
        if balance <= peak_balance * 0.70:
            return True, f"Drawdown de {(1-balance/peak_balance)*100:.1f}% desde peak"
        
        tier = self.get_tier(balance)
        peak_tier = self.get_tier(peak_balance)
        if tier != peak_tier:
            return True, f"Tier mudou de {peak_tier} para {tier}"
        
        return False, ""
    
    def get_position_size(self, balance: float, symbol: str, 
                         volatility_mult: float = 1.0) -> float:
        """
        Calcula tamanho de posição ajustado por tier e volatilidade.
        
        Args:
            balance: Saldo atual
            symbol: Símbolo a negociar
            volatility_mult: Multiplicador de volatilidade (1.0 = normal, >1.0 = mais volátil)
        
        Returns:
            Risk % ajustado para este trade
        """
        config = self.get_config(balance)
        base_risk = config["risk_per_trade_pct"]
        
        # Ajustar por volatilidade
        adjusted_risk = base_risk / volatility_mult
        
        # Ajustar se símbolo não está na lista recomendada
        if symbol not in config["recommended_symbols"]:
            adjusted_risk *= 0.5  # 50% de redução para símbolos fora do tier
        
        return round(adjusted_risk, 3)
    
    def get_max_exposure(self, balance: float) -> Dict:
        """
        Retorna limites de exposição para o tier atual.
        """
        config = self.get_config(balance)
        
        return {
            "max_total_risk_pct": config["risk_per_trade_pct"] * config["max_positions"],
            "max_positions": config["max_positions"],
            "max_symbols": config["max_symbols"],
            "max_correlation": config["max_correlation"],
        }
    
    def get_strategy_allocation(self, balance: float) -> Dict[str, float]:
        """
        Retorna alocação % por estratégia para o tier atual.
        """
        config = self.get_config(balance)
        strategies = config["strategies"]
        
        if "all" in strategies:
            # Mega tier: diversificação máxima
            return {
                "mean_reversion": 0.30,
                "stat_arb": 0.25,
                "macro": 0.20,
                "cta": 0.15,
                "market_neutral": 0.10,
            }
        
        # Distribuir igualmente entre estratégias ativas
        allocation = {s: 1.0/len(strategies) for s in strategies}
        return allocation
    
    def print_tier_info(self, balance: float):
        """Print formatado do tier atual e recomendações."""
        config = self.get_config(balance)
        
        print(f"\n{'='*60}")
        print(f"  TIER ATUAL: {config['tier'].upper()}")
        print(f"{'='*60}")
        print(f"Balance: ${balance:,.2f}")
        print(f"Range: ${config['min']:,.0f} - ${config['max']:,.0f}")
        print(f"\n{config['description']}")
        print(f"\n📊 PARÂMETROS:")
        print(f"  • Risk por trade: {config['risk_per_trade_pct']:.2f}%")
        print(f"  • Max posições: {config['max_positions']}")
        print(f"  • Max símbolos: {config['max_symbols']}")
        print(f"  • Max correlação: {config['max_correlation']:.2f}")
        
        print(f"\n🎯 ESTRATÉGIAS ATIVAS:")
        for strategy in config['strategies']:
            print(f"  ✓ {strategy}")
        
        print(f"\n💹 SÍMBOLOS RECOMENDADOS ({len(config['recommended_symbols'])}):")
        for i, sym in enumerate(config['recommended_symbols'][:10], 1):
            print(f"  {i}. {sym}")
        if len(config['recommended_symbols']) > 10:
            print(f"  ... e mais {len(config['recommended_symbols'])-10}")
        
        print(f"\n{'='*60}\n")


# ============================================================
#  EXEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    scaler = CapitalScaling()
    
    # Simular crescimento de capital
    test_balances = [5000, 15000, 50000, 150000, 600000, 6_000_000]
    
    for balance in test_balances:
        scaler.print_tier_info(balance)
        
        # Mostrar position sizing para alguns símbolos
        print("📈 POSITION SIZING EXAMPLES:")
        for symbol in ["EURUSD", "BTCUSD", "XAUUSD"]:
            risk_pct = scaler.get_position_size(balance, symbol)
            risk_money = balance * risk_pct / 100
            print(f"  {symbol}: {risk_pct:.2f}% = ${risk_money:,.2f}")
        
        print("\n" + "─"*60 + "\n")
