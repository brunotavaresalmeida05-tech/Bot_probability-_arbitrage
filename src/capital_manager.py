"""
src/capital_manager.py
Gestão automática de capital com suporte para crypto CFD e EUR.
Integra com capital_scaling.py para ajustes dinâmicos.
"""

from typing import Dict, List, Tuple
from datetime import datetime, date
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg
from src.capital_scaling import CapitalScaling
import src.mt5_connector as mt5c


class CapitalManager:
    """
    Gestão avançada de capital com:
    - Auto-ajuste baseado em balance atual
    - Suporte para múltiplas moedas (EUR/USD/GBP)
    - Gestão específica para crypto CFD
    - Tracking de crescimento e drawdowns
    """
    
    def __init__(self, initial_balance: float = None, currency: str = "EUR"):
        self.scaler = CapitalScaling()
        self.currency = currency
        
        # Balance tracking
        self.initial_balance = initial_balance
        self.peak_balance = initial_balance
        self.current_balance = initial_balance
        self.tier_entry_balance = initial_balance
        
        # History
        self.balance_history = []
        self.tier_changes = []
        
        # Crypto CFD settings
        self.crypto_multiplier = 0.5  # Crypto usa 50% do risk normal
        self.crypto_max_positions = 1  # Máximo 1 posição crypto no tier MICRO
        
    def update_balance(self, new_balance: float):
        """Atualiza balance e recalcula tier se necessário."""
        old_tier = self.scaler.get_tier(self.current_balance) if self.current_balance else None
        self.current_balance = new_balance
        new_tier = self.scaler.get_tier(new_balance)
        
        # Track peak
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance
        
        # Track balance history
        self.balance_history.append({
            "timestamp": datetime.now(),
            "balance": new_balance,
            "tier": new_tier
        })
        
        # Tier change detection
        if old_tier and old_tier != new_tier:
            self.tier_changes.append({
                "timestamp": datetime.now(),
                "old_tier": old_tier,
                "new_tier": new_tier,
                "balance": new_balance,
                "change_type": "upgrade" if self._tier_index(new_tier) > self._tier_index(old_tier) else "downgrade"
            })
            self.tier_entry_balance = new_balance
            print(f"\n{'='*60}")
            print(f"🔔 TIER CHANGE ALERT")
            print(f"{'='*60}")
            print(f"From: {old_tier.upper()} → To: {new_tier.upper()}")
            print(f"Balance: {self.currency}{new_balance:,.2f}")
            print(f"{'='*60}\n")
        
        return new_tier
    
    def _tier_index(self, tier: str) -> int:
        """Helper para comparar tiers."""
        tiers_order = ["micro", "small", "medium", "large", "mega"]
        return tiers_order.index(tier) if tier in tiers_order else 0
    
    def get_position_size(self, symbol: str, sl_distance: float) -> Tuple[float, float]:
        """
        Calcula tamanho de posição ajustado por:
        - Tier atual
        - Tipo de ativo (crypto tem multiplier)
        - Volatilidade
        
        Returns:
            (lot_size, risk_money)
        """
        balance = self.current_balance
        
        # Get base risk from tier
        risk_pct = self.scaler.get_position_size(balance, symbol)
        
        # Ajustar para crypto CFD
        if self._is_crypto(symbol):
            risk_pct *= self.crypto_multiplier
            tier = self.scaler.get_tier(balance)
            
            # Tier MICRO: máximo 1 posição crypto
            if tier == "micro":
                open_crypto = self._count_open_crypto_positions()
                if open_crypto >= self.crypto_max_positions:
                    return 0.0, 0.0
        
        # Calcular risk em dinheiro
        risk_money = balance * risk_pct / 100
        
        # Calcular lot size
        lot_size = mt5c.calculate_lot_size(symbol, risk_money, sl_distance)
        
        return lot_size, risk_money
    
    def _is_crypto(self, symbol: str) -> bool:
        """Verifica se símbolo é crypto CFD."""
        crypto_prefixes = ["BTC", "ETH", "XRP", "SOL", "ADA", "DOT"]
        return any(symbol.startswith(prefix) for prefix in crypto_prefixes)
    
    def _count_open_crypto_positions(self) -> int:
        """Conta posições abertas em crypto."""
        positions = mt5c.get_open_positions(magic=cfg.MAGIC_NUMBER)
        return sum(1 for pos in positions if self._is_crypto(pos.symbol))
    
    def get_max_exposure(self) -> Dict:
        """Retorna limites de exposição atuais."""
        tier_config = self.scaler.get_config(self.current_balance)
        
        return {
            "max_positions": tier_config["max_positions"],
            "max_crypto_positions": self.crypto_max_positions if tier_config["tier"] == "micro" else 2,
            "max_risk_pct": tier_config["risk_per_trade_pct"] * tier_config["max_positions"],
            "recommended_symbols": tier_config["recommended_symbols"],
        }
    
    def should_scale_operations(self) -> Tuple[str, str]:
        """
        Verifica se deve fazer scale up ou down.
        
        Returns:
            (action, reason) onde action = "scale_up", "scale_down", "maintain"
        """
        balance = self.current_balance
        
        # Check scale up
        should_up, reason_up = self.scaler.should_scale_up(balance, self.tier_entry_balance)
        if should_up:
            return "scale_up", reason_up
        
        # Check scale down
        should_down, reason_down = self.scaler.should_scale_down(balance, self.peak_balance)
        if should_down:
            return "scale_down", reason_down
        
        return "maintain", "Operações estáveis"
    
    def get_crypto_config(self) -> Dict:
        """
        Retorna configuração específica para crypto CFD.
        """
        tier = self.scaler.get_tier(self.current_balance)
        
        # Crypto CFD é volátil - settings conservadores
        if tier == "micro":
            return {
                "enabled": True,
                "symbols": ["BTCUSD"],  # Só BTC no tier MICRO
                "risk_multiplier": 0.5,
                "max_positions": 1,
                "max_spread_pct": 0.5,  # 0.5% spread máximo
                "timeframe": "H1",  # H1 ou superior para crypto
                "z_enter": 2.5,  # Mais conservador
            }
        elif tier == "small":
            return {
                "enabled": True,
                "symbols": ["BTCUSD", "ETHUSD"],
                "risk_multiplier": 0.6,
                "max_positions": 2,
                "max_spread_pct": 0.5,
                "timeframe": "H1",
                "z_enter": 2.3,
            }
        else:
            return {
                "enabled": True,
                "symbols": ["BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD"],
                "risk_multiplier": 0.75,
                "max_positions": 3,
                "max_spread_pct": 0.5,
                "timeframe": "M30",
                "z_enter": 2.0,
            }
    
    def get_stats(self) -> Dict:
        """Estatísticas de performance do capital."""
        if not self.balance_history:
            return {}
        
        first_balance = self.balance_history[0]["balance"]
        current_balance = self.current_balance
        
        # Calcular retorno
        total_return_pct = ((current_balance - first_balance) / first_balance * 100) if first_balance > 0 else 0
        
        # Calcular drawdown atual
        current_dd_pct = ((self.peak_balance - current_balance) / self.peak_balance * 100) if self.peak_balance > 0 else 0
        
        return {
            "initial_balance": first_balance,
            "current_balance": current_balance,
            "peak_balance": self.peak_balance,
            "total_return_pct": round(total_return_pct, 2),
            "current_drawdown_pct": round(current_dd_pct, 2),
            "n_tier_changes": len(self.tier_changes),
            "current_tier": self.scaler.get_tier(current_balance),
            "currency": self.currency,
        }
    
    def print_status(self):
        """Print formatado do status atual."""
        stats = self.get_stats()
        tier_config = self.scaler.get_config(self.current_balance)
        exposure = self.get_max_exposure()
        action, reason = self.should_scale_operations()
        
        print(f"\n{'='*60}")
        print(f"💰 CAPITAL MANAGER STATUS")
        print(f"{'='*60}")
        print(f"Balance: {self.currency}{stats['current_balance']:,.2f}")
        print(f"Peak: {self.currency}{stats['peak_balance']:,.2f}")
        print(f"Return: {stats['total_return_pct']:+.2f}%")
        print(f"Drawdown: {stats['current_drawdown_pct']:.2f}%")
        print(f"\n🎯 TIER: {stats['current_tier'].upper()}")
        print(f"Risk/trade: {tier_config['risk_per_trade_pct']:.2f}%")
        print(f"Max positions: {exposure['max_positions']}")
        print(f"Max crypto: {exposure['max_crypto_positions']}")
        
        if action != "maintain":
            print(f"\n⚠️  RECOMMENDATION: {action.upper()}")
            print(f"Reason: {reason}")
        
        print(f"{'='*60}\n")


# ============================================================
#  EXEMPLO DE USO
# ============================================================

if __name__ == "__main__":
    # Simular crescimento de capital
    manager = CapitalManager(initial_balance=455.0, currency="EUR")
    
    print("🔄 Simulando crescimento de capital...\n")
    
    # Balances de teste
    test_balances = [455, 500, 800, 1200, 5000, 12000, 50000]
    
    for balance in test_balances:
        manager.update_balance(balance)
        manager.print_status()
        
        # Mostrar config crypto
        crypto_config = manager.get_crypto_config()
        print(f"📊 CRYPTO CONFIG:")
        print(f"  Enabled: {crypto_config['enabled']}")
        print(f"  Symbols: {', '.join(crypto_config['symbols'])}")
        print(f"  Risk mult: {crypto_config['risk_multiplier']:.1f}x")
        print(f"  Max positions: {crypto_config['max_positions']}")
        
        # Test position sizing
        print(f"\n💹 POSITION SIZING EXAMPLES:")
        for symbol in ["EURUSD", "BTCUSD", "ETHUSD"]:
            lot, risk = manager.get_position_size(symbol, sl_distance=0.001)
            if lot > 0:
                print(f"  {symbol}: {lot:.2f} lots = {manager.currency}{risk:.2f} risk")
            else:
                print(f"  {symbol}: BLOCKED (tier limits)")
        
        print("\n" + "─"*60 + "\n")
        
        input("Press Enter para próximo balance...")
