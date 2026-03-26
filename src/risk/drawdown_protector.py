"""
Drawdown Protection System
Auto-reduce após perdas / Recovery mode
"""

from datetime import datetime, timedelta

class DrawdownProtector:
    def __init__(self, 
                 max_daily_loss_pct=5.0,
                 max_weekly_loss_pct=10.0,
                 recovery_threshold_pct=3.0):
        """
        Args:
            max_daily_loss_pct: % perda diária máxima antes de parar
            max_weekly_loss_pct: % perda semanal máxima
            recovery_threshold_pct: % ganho necessário para recovery mode
        """
        self.max_daily_loss = max_daily_loss_pct
        self.max_weekly_loss = max_weekly_loss_pct
        self.recovery_threshold = recovery_threshold_pct
        
        self.starting_balance_today = None
        self.starting_balance_week = None
        self.peak_balance = None
        self.mode = 'NORMAL'  # NORMAL, REDUCED, RECOVERY, STOPPED
    
    def check_drawdown(self, current_balance: float) -> dict:
        """
        Verifica estado de drawdown.
        
        Returns: {
            'action': 'CONTINUE' | 'REDUCE' | 'STOP',
            'mode': str,
            'daily_dd_pct': float,
            'weekly_dd_pct': float,
            'risk_multiplier': float
        }
        """
        # Inicializar se necessário
        if self.starting_balance_today is None:
            self.starting_balance_today = current_balance
            self.starting_balance_week = current_balance
            self.peak_balance = current_balance
        
        # Reset diário (simplificado para demonstração, idealmente via scheduler ou timestamp)
        now = datetime.now()
        if now.hour == 0 and now.minute < 5:
            self.starting_balance_today = current_balance
        
        # Reset semanal (segunda-feira)
        if now.weekday() == 0 and now.hour == 0:
            self.starting_balance_week = current_balance
        
        # Update peak
        if current_balance > self.peak_balance:
            self.peak_balance = current_balance
        
        # Calcular drawdowns
        daily_dd = ((current_balance - self.starting_balance_today) 
                    / self.starting_balance_today * 100)
        
        weekly_dd = ((current_balance - self.starting_balance_week) 
                     / self.starting_balance_week * 100)
        
        peak_dd = ((current_balance - self.peak_balance) 
                   / self.peak_balance * 100)
        
        # Determinar ação
        action = 'CONTINUE'
        risk_multiplier = 1.0
        
        # Stop trading se perda diária exceder
        if daily_dd < -self.max_daily_loss:
            action = 'STOP'
            self.mode = 'STOPPED'
            risk_multiplier = 0.0
        
        # Stop se perda semanal exceder
        elif weekly_dd < -self.max_weekly_loss:
            action = 'STOP'
            self.mode = 'STOPPED'
            risk_multiplier = 0.0
        
        # Reduzir risco se em drawdown significativo (ex: > 5% do pico)
        elif peak_dd < -5.0:
            action = 'REDUCE'
            self.mode = 'REDUCED'
            risk_multiplier = 0.5  # Metade do risco
        
        # Recovery mode (ganhou após DD mas ainda não bateu novo pico)
        elif self.mode == 'REDUCED' and peak_dd > -self.recovery_threshold:
            self.mode = 'RECOVERY'
            risk_multiplier = 0.75
        
        # Voltar ao normal
        elif self.mode == 'RECOVERY' and current_balance >= self.peak_balance:
            self.mode = 'NORMAL'
            risk_multiplier = 1.0
        
        return {
            'action': action,
            'mode': self.mode,
            'daily_dd_pct': daily_dd,
            'weekly_dd_pct': weekly_dd,
            'peak_dd_pct': peak_dd,
            'risk_multiplier': risk_multiplier
        }
    
    def reset_daily(self):
        """Reset manual do contador diário."""
        self.starting_balance_today = None
    
    def reset_all(self, new_balance: float):
        """Reset completo (novo capital)."""
        self.starting_balance_today = new_balance
        self.starting_balance_week = new_balance
        self.peak_balance = new_balance
        self.mode = 'NORMAL'
