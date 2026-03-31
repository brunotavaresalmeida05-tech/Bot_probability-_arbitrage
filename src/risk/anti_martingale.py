"""
Anti-Martingale Scaler
Aumenta posição em sequências vencedoras
"""

import logging

logger = logging.getLogger(__name__)


class AntiMartingaleScaler:
    """
    Scaling institucional: aumenta lot em vitórias consecutivas
    Reseta em perda
    """
    
    def __init__(self, base_lot: float = 0.01, max_multiplier: float = 4.0):
        self.base_lot = base_lot
        self.max_multiplier = max_multiplier
        self.consecutive_wins = 0
        
        # Multiplicadores por streak
        self.multipliers = {
            0: 1.0,   # Sem streak
            1: 1.0,   # 1 win
            2: 1.5,   # 2 wins
            3: 2.0,   # 3 wins
            4: 3.0,   # 4 wins
            5: 4.0    # 5+ wins (max)
        }
        
        logger.info("📈 Anti-Martingale iniciado | Max multiplier: %.1fx", max_multiplier)
    
    def update(self, is_winner: bool) -> None:
        """
        Atualiza estado após trade
        """
        if is_winner:
            self.consecutive_wins += 1
            logger.info(f"✅ Win streak: {self.consecutive_wins}")
        else:
            if self.consecutive_wins > 0:
                logger.info(f"❌ Streak resetado (era {self.consecutive_wins})")
            self.consecutive_wins = 0
    
    def get_multiplier(self) -> float:
        """
        Retorna multiplicador atual baseado na streak
        """
        streak = min(self.consecutive_wins, 5)  # Cap em 5
        multiplier = self.multipliers.get(streak, self.max_multiplier)
        
        return min(multiplier, self.max_multiplier)
    
    def calculate_lot(self, base_lot: float = None) -> float:
        """
        Calcula lot ajustado
        """
        if base_lot is None:
            base_lot = self.base_lot
        
        multiplier = self.get_multiplier()
        adjusted_lot = base_lot * multiplier
        
        return round(adjusted_lot, 2)
    
    def reset(self) -> None:
        """Reset manual da streak"""
        self.consecutive_wins = 0
        logger.info("🔄 Anti-Martingale resetado")
    
    def get_stats(self) -> dict:
        """Estatísticas"""
        return {
            'consecutive_wins': self.consecutive_wins,
            'current_multiplier': self.get_multiplier(),
            'base_lot': self.base_lot,
            'max_multiplier': self.max_multiplier
        }
