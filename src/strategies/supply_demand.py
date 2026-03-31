"""
Supply & Demand Zone Strategy
Identifica zonas institucionais de oferta/procura
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)


class SupplyDemandStrategy:
    """
    Estratégia baseada em zonas de Supply/Demand
    
    Lógica:
    - Demand Zone (suporte): área onde preço fez rally forte depois de consolidação
    - Supply Zone (resistência): área onde preço caiu forte depois de consolidação
    - Trade quando preço retesta a zona
    """
    
    def __init__(
        self,
        zone_strength_min: int = 2,
        zone_age_max: int = 50,
        price_move_min: float = 0.015,  # 1.5% movimento mínimo
        consolidation_bars: int = 3
    ):
        self.zone_strength_min = zone_strength_min
        self.zone_age_max = zone_age_max
        self.price_move_min = price_move_min
        self.consolidation_bars = consolidation_bars
        
        self.demand_zones: List[dict] = []
        self.supply_zones: List[dict] = []
    
    def identify_zones(self, df: pd.DataFrame) -> Tuple[List[dict], List[dict]]:
        """
        Identifica zonas de Supply/Demand no histórico
        
        Args:
            df: DataFrame com OHLC
            
        Returns:
            (demand_zones, supply_zones)
        """
        demand_zones = []
        supply_zones = []
        
        for i in range(self.consolidation_bars, len(df) - 10):
            # Verificar consolidação (range pequeno)
            consol_high = df['high'].iloc[i-self.consolidation_bars:i].max()
            consol_low = df['low'].iloc[i-self.consolidation_bars:i].min()
            consol_range = (consol_high - consol_low) / consol_low
            
            if consol_range > 0.005:  # Range > 0.5%
                continue
            
            # Rally depois de consolidação (Demand Zone)
            move_after = (df['close'].iloc[i+5] - df['close'].iloc[i]) / df['close'].iloc[i]
            
            if move_after > self.price_move_min:
                # Demand zone encontrada
                zone = {
                    'type': 'demand',
                    'top': consol_high,
                    'bottom': consol_low,
                    'created_at': i,
                    'strength': 1,  # Incrementa quando retestada
                    'last_test': i
                }
                demand_zones.append(zone)
                logger.debug(f"Demand zone: {consol_low:.5f} - {consol_high:.5f} (bar {i})")
            
            # Drop depois de consolidação (Supply Zone)
            elif move_after < -self.price_move_min:
                # Supply zone encontrada
                zone = {
                    'type': 'supply',
                    'top': consol_high,
                    'bottom': consol_low,
                    'created_at': i,
                    'strength': 1,
                    'last_test': i
                }
                supply_zones.append(zone)
                logger.debug(f"Supply zone: {consol_low:.5f} - {consol_high:.5f} (bar {i})")
        
        return demand_zones, supply_zones
    
    def check_zone_retest(
        self, 
        current_price: float, 
        current_bar: int,
        df: pd.DataFrame
    ) -> Optional[str]:
        """
        Verifica se preço está a retestar zona válida
        
        Returns:
            'BUY' se demand retest, 'SELL' se supply retest, None caso contrário
        """
        # Atualizar zonas
        self.demand_zones, self.supply_zones = self.identify_zones(df)
        
        # Verificar retest de Demand (BUY)
        for zone in self.demand_zones:
            age = current_bar - zone['created_at']
            
            if age > self.zone_age_max:
                continue
            
            if zone['strength'] < self.zone_strength_min:
                continue
            
            # Preço dentro da zona?
            if zone['bottom'] <= current_price <= zone['top']:
                # Confirmação: vela anterior tocou e rejeitou
                prev_low = df['low'].iloc[-2]
                prev_close = df['close'].iloc[-2]
                
                if prev_low <= zone['bottom'] and prev_close > zone['bottom']:
                    logger.info(
                        f"🟢 DEMAND RETEST | "
                        f"Zone: {zone['bottom']:.5f}-{zone['top']:.5f} | "
                        f"Strength: {zone['strength']} | Age: {age}"
                    )
                    zone['strength'] += 1
                    zone['last_test'] = current_bar
                    return 'BUY'
        
        # Verificar retest de Supply (SELL)
        for zone in self.supply_zones:
            age = current_bar - zone['created_at']
            
            if age > self.zone_age_max:
                continue
            
            if zone['strength'] < self.zone_strength_min:
                continue
            
            # Preço dentro da zona?
            if zone['bottom'] <= current_price <= zone['top']:
                # Confirmação: vela anterior tocou e rejeitou
                prev_high = df['high'].iloc[-2]
                prev_close = df['close'].iloc[-2]
                
                if prev_high >= zone['top'] and prev_close < zone['top']:
                    logger.info(
                        f"🔴 SUPPLY RETEST | "
                        f"Zone: {zone['bottom']:.5f}-{zone['top']:.5f} | "
                        f"Strength: {zone['strength']} | Age: {age}"
                    )
                    zone['strength'] += 1
                    zone['last_test'] = current_bar
                    return 'SELL'
        
        return None
    
    def calculate_targets(
        self,
        entry_price: float,
        signal: str,
        atr: float
    ) -> Tuple[float, float]:
        """
        Calcula SL e TP baseado na zona
        
        Returns:
            (stop_loss, take_profit)
        """
        if signal == 'BUY':
            # SL abaixo da zona
            stop_loss = entry_price - (1.5 * atr)
            # TP: R:R 1:2
            take_profit = entry_price + (2 * (entry_price - stop_loss))
        else:  # SELL
            # SL acima da zona
            stop_loss = entry_price + (1.5 * atr)
            # TP: R:R 1:2
            take_profit = entry_price - (2 * (stop_loss - entry_price))
        
        return stop_loss, take_profit
