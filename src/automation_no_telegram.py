"""
Automation System - Email, Auto-restart, Relatórios (SEM TELEGRAM)
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import sys
import os
import subprocess
import time

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Envia notificações via Email (OPCIONAL)"""
    
    def __init__(self, smtp_server: str, smtp_port: int, email: str, password: str, to_email: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.email = email
        self.password = password
        self.to_email = to_email
    
    def send_email(self, subject: str, body: str):
        """Envia email"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email
            msg['To'] = self.to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'html'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email, self.password)
                server.send_message(msg)
            
            logger.info("✅ Email enviado")
            return True
        except Exception as e:
            logger.error(f"❌ Erro Email: {e}")
            return False
    
    def send_daily_report(self, stats: dict):
        """Envia relatório diário"""
        subject = f"📊 Relatório Diário - {datetime.now().strftime('%d/%m/%Y')}"
        pnl_color = 'green' if stats['pnl'] > 0 else 'red'
        
        body = f"""
        <html><body style="font-family: Arial;">
        <h2>📊 Relatório Diário</h2><hr>
        <table style="border-collapse: collapse; width: 100%;">
        <tr><td style="padding: 8px;"><strong>Balance:</strong></td><td>€{stats['balance']:.2f}</td></tr>
        <tr style="background-color: #f2f2f2;"><td style="padding: 8px;"><strong>P&L:</strong></td>
        <td style="color: {pnl_color};">{'+' if stats['pnl'] > 0 else ''}€{stats['pnl']:.2f}</td></tr>
        <tr><td style="padding: 8px;"><strong>Trades:</strong></td><td>{stats['num_trades']}</td></tr>
        <tr style="background-color: #f2f2f2;"><td style="padding: 8px;"><strong>Win Rate:</strong></td>
        <td>{stats['win_rate']:.1%}</td></tr>
        </table><hr>
        <p style="color: #666; font-size: 12px;">{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
        </body></html>
        """
        self.send_email(subject, body)


class AutoRestarter:
    """Auto-restart em caso de erro"""
    
    def __init__(self, script_path: str, max_restarts: int = 5, cooldown_minutes: int = 5):
        self.script_path = script_path
        self.max_restarts = max_restarts
        self.cooldown_minutes = cooldown_minutes
        self.restart_count = 0
        self.last_restart = None
    
    def should_restart(self) -> bool:
        if self.restart_count >= self.max_restarts:
            logger.error(f"❌ Máximo de {self.max_restarts} restarts")
            return False
        if self.last_restart:
            elapsed = datetime.now() - self.last_restart
            if elapsed < timedelta(minutes=self.cooldown_minutes):
                logger.warning(f"⏳ Cooldown ativo")
                return False
        return True
    
    def restart(self):
        if not self.should_restart():
            return False
        logger.warning("🔄 Reiniciando...")
        self.restart_count += 1
        self.last_restart = datetime.now()
        try:
            subprocess.Popen([sys.executable, self.script_path])
            logger.info("✅ Reiniciado")
            time.sleep(2)
            sys.exit(0)
        except Exception as e:
            logger.error(f"❌ Falha: {e}")
            return False


class ConfigBackup:
    """Backup automático"""
    
    def __init__(self, backup_dir: str = "backups"):
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
    
    def backup_config(self):
        import shutil
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(self.backup_dir, f"config_{timestamp}")
        try:
            shutil.copytree("config", backup_path)
            logger.info(f"✅ Backup: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Backup erro: {e}")
            return False
    
    def auto_backup(self, interval_hours: int = 24):
        last_backup_file = os.path.join(self.backup_dir, "last_backup.txt")
        should_backup = True
        if os.path.exists(last_backup_file):
            with open(last_backup_file, 'r') as f:
                last_backup = datetime.fromisoformat(f.read().strip())
                if datetime.now() - last_backup < timedelta(hours=interval_hours):
                    should_backup = False
        if should_backup:
            if self.backup_config():
                with open(last_backup_file, 'w') as f:
                    f.write(datetime.now().isoformat())
