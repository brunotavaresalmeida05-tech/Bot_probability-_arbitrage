"""
Volatility-Based Position Sizing
Ajusta lot inversamente à volatilidade
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class VolatilityScaler:
    """
    Volatility scaling: lot menor em alta vol, maior em baixa vol
    """
    
    def __init__(self, min_scale: float = 0.5, max_scale: float = 2.0):
        self.min_scale = min_scale
        self.max_scale = max_scale
        
        logger.info(f"📊 Volatility Scaler iniciado | Range: {min_scale}x - {max_scale}x")
    
    def calculate_scaled_lot(
        self, 
        current_atr: float, 
        historical_atr_median: float, 
        base_lot: float
    ) -> float:
        """
        Ajusta lot baseado em ATR relativo
        
        Args:
            current_atr: ATR atual
            historical_atr_median: Mediana histórica do ATR
            base_lot: Lot base
            
        Returns:
            Lot ajustado
        """
        if historical_atr_median == 0 or current_atr == 0:
            logger.warning("⚠️ ATR inválido, usando lot base")
            return base_lot
        
        # Ratio ATR (atual / mediana)
        atr_ratio = current_atr / historical_atr_median
        
        # Inverter: alta vol = ratio baixo
        scaling_factor = 1.0 / atr_ratio
        
        # Cap entre min e max
        scaling_factor = max(self.min_scale, min(scaling_factor, self.max_scale))
        
        # Aplicar ao lot
        scaled_lot = base_lot * scaling_factor
        
        logger.debug(
            f"Vol Scaling: ATR ratio={atr_ratio:.2f} | "
            f"Factor={scaling_factor:.2f} | Lot={scaled_lot:.2f}"
        )
        
        return round(scaled_lot, 2)
    
    def get_volatility_regime(self, current_atr: float, historical_atr_median: float) -> str:
        """
        Classifica regime de volatilidade
        """
        if historical_atr_median == 0:
            return "UNKNOWN"
        
        ratio = current_atr / historical_atr_median
        
        if ratio > 1.5:
            return "EXTREME_HIGH"
        elif ratio > 1.2:
            return "HIGH"
        elif ratio > 0.8:
            return "NORMAL"
        elif ratio > 0.5:
            return "LOW"
        else:
            return "EXTREME_LOW"
