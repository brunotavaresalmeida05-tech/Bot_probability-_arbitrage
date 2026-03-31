"""
Professional Compounding Manager
Escalonamento institucional de capital base
"""

import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class CompoundingManager:
    """
    Gestão profissional de capital com milestones dinâmicos
    Ajusta risk, positions e lot size conforme capital cresce
    """
    
    def __init__(self, initial_capital: float, target_monthly_return: float = 0.15):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.target_monthly_return = target_monthly_return
        
        # Milestones de capital (€)
        self.milestones = {
            500: {
                'risk_per_trade': 0.020,  # 2.0%
                'max_positions': 5,
                'kelly_fraction': 0.25,
                'name': 'Iniciante'
            },
            1000: {
                'risk_per_trade': 0.025,  # 2.5%
                'max_positions': 7,
                'kelly_fraction': 0.25,
                'name': 'Crescimento'
            },
            2500: {
                'risk_per_trade': 0.030,  # 3.0%
                'max_positions': 10,
                'kelly_fraction': 0.30,
                'name': 'Aceleração'
            },
            5000: {
                'risk_per_trade': 0.025,  # 2.5% (reduz risk)
                'max_positions': 12,
                'kelly_fraction': 0.25,
                'name': 'Consolidação'
            },
            10000: {
                'risk_per_trade': 0.020,  # 2.0%
                'max_positions': 15,
                'kelly_fraction': 0.20,
                'name': 'Profissional'
            },
            25000: {
                'risk_per_trade': 0.015,  # 1.5%
                'max_positions': 20,
                'kelly_fraction': 0.15,
                'name': 'Institucional'
            }
        }
        
        logger.info(f"💰 Compounding Manager iniciado | Capital: €{initial_capital:.2f}")
    
    def update_capital(self, new_capital: float) -> Dict[str, Any]:
        """
        Atualiza capital e retorna milestone atual
        """
        old_milestone = self.get_current_milestone_name()
        self.current_capital = new_capital
        new_milestone = self.get_current_milestone_name()
        
        if old_milestone != new_milestone:
            logger.info(f"🎯 MILESTONE ATINGIDO: {new_milestone} | Capital: €{new_capital:.2f}")
        
        return self.get_current_params()
    
    def get_current_params(self) -> Dict[str, Any]:
        """
        Retorna parâmetros baseados no capital atual
        """
        for milestone in sorted(self.milestones.keys(), reverse=True):
            if self.current_capital >= milestone:
                params = self.milestones[milestone].copy()
                params['milestone'] = milestone
                return params
        
        # Default (abaixo do menor milestone)
        return {
            'risk_per_trade': 0.015,
            'max_positions': 3,
            'kelly_fraction': 0.20,
            'name': 'Micro',
            'milestone': 0
        }
    
    def get_current_milestone_name(self) -> str:
        """Retorna nome do milestone atual"""
        return self.get_current_params()['name']
    
    def calculate_position_size(
        self, 
        win_rate: float, 
        avg_win: float, 
        avg_loss: float,
        account_balance: float
    ) -> Dict[str, float]:
        """
        Calcula lot size usando Kelly Criterion + Milestone Risk
        
        Returns:
            {
                'kelly_pct': float,
                'milestone_risk_pct': float,
                'effective_risk_pct': float,
                'risk_amount': float,
                'max_positions': int
            }
        """
        params = self.get_current_params()
        
        # 1. Kelly Criterion
        if avg_loss > 0 and win_rate > 0:
            payoff_ratio = avg_win / avg_loss
            kelly_pct = (win_rate * payoff_ratio - (1 - win_rate)) / payoff_ratio
            kelly_pct = max(0, min(kelly_pct, 0.50))  # Cap 50%
        else:
            kelly_pct = 0
        
        # 2. Fractional Kelly
        fractional_kelly = kelly_pct * params['kelly_fraction']
        
        # 3. Usar menor entre Kelly e milestone risk
        effective_risk = min(fractional_kelly, params['risk_per_trade'])
        
        # 4. Garantir mínimo de 0.5%
        effective_risk = max(effective_risk, 0.005)
        
        return {
            'kelly_pct': kelly_pct,
            'milestone_risk_pct': params['risk_per_trade'],
            'effective_risk_pct': effective_risk,
            'risk_amount': account_balance * effective_risk,
            'max_positions': params['max_positions']
        }
    
    def get_next_milestone(self) -> Dict[str, Any]:
        """
        Retorna info do próximo milestone
        """
        for milestone in sorted(self.milestones.keys()):
            if self.current_capital < milestone:
                progress_pct = (self.current_capital / milestone) * 100
                remaining = milestone - self.current_capital
                
                return {
                    'target': milestone,
                    'name': self.milestones[milestone]['name'],
                    'progress_pct': progress_pct,
                    'remaining': remaining,
                    'params': self.milestones[milestone]
                }
        
        # Já está no último milestone
        return {
            'target': None,
            'name': 'Máximo Atingido',
            'progress_pct': 100,
            'remaining': 0,
            'params': self.milestones[25000]
        }
    
    def project_growth(self, months: int = 12) -> list:
        """
        Projeção de crescimento composto
        
        Returns:
            Lista de dicts com projeções mensais
        """
        projections = []
        capital = self.current_capital
        
        for month in range(1, months + 1):
            # Crescimento mensal composto
            capital *= (1 + self.target_monthly_return)
            
            # Params para este nível de capital
            params_for_capital = self._get_params_for_capital(capital)
            
            projections.append({
                'month': month,
                'capital': capital,
                'growth_pct': ((capital / self.initial_capital) - 1) * 100,
                'params': params_for_capital,
                'milestone': params_for_capital['name']
            })
        
        return projections
    
    def _get_params_for_capital(self, capital: float) -> Dict[str, Any]:
        """Helper interno para projeção"""
        for milestone in sorted(self.milestones.keys(), reverse=True):
            if capital >= milestone:
                params = self.milestones[milestone].copy()
                params['milestone'] = milestone
                return params
        
        return {
            'risk_per_trade': 0.015,
            'max_positions': 3,
            'kelly_fraction': 0.20,
            'name': 'Micro',
            'milestone': 0
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Estatísticas completas do compounding
        """
        current_params = self.get_current_params()
        next_milestone = self.get_next_milestone()
        
        return {
            'current_capital': self.current_capital,
            'initial_capital': self.initial_capital,
            'total_growth_pct': ((self.current_capital / self.initial_capital) - 1) * 100,
            'current_milestone': current_params['name'],
            'current_params': current_params,
            'next_milestone': next_milestone,
            'target_monthly_return': self.target_monthly_return * 100
        }
