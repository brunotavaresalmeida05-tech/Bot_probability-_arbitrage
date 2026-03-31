"""
Automation System - Notificações, Auto-restart, Relatórios
"""

import logging
import asyncio
import requests
from datetime import datetime, timedelta
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sys
import os
import subprocess
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    import config.settings as _cfg
except ImportError:
    _cfg = None

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Envia notificações via Telegram Bot
    """
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    def send_message(self, message: str, parse_mode: str = "Markdown"):
        """Envia mensagem simples"""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.info("✅ Telegram enviado")
                return True
            else:
                logger.error(f"❌ Telegram falhou: {response.text}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Erro Telegram: {e}")
            return False
    
    def notify_trade_opened(self, symbol: str, direction: str, entry: float, sl: float, tp: float):
        """Notifica abertura de trade"""
        message = f"""
🟢 *TRADE ABERTO*

📊 *{symbol}* {direction}
💰 Entry: `{entry:.5f}`
🛡️ SL: `{sl:.5f}`
🎯 TP: `{tp:.5f}`

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send_message(message)
    
    def notify_trade_closed(self, symbol: str, profit: float, pips: float, reason: str):
        """Notifica fechamento de trade"""
        emoji = "✅" if profit > 0 else "❌"
        message = f"""
{emoji} *TRADE FECHADO*

📊 *{symbol}*
{'💰' if profit > 0 else '💸'} P&L: `€{profit:.2f}` ({'+' if pips > 0 else ''}{pips:.1f} pips)
📝 Motivo: {reason}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        self.send_message(message)
    
    def notify_milestone(self, milestone: str, balance: float):
        """Notifica milestone atingido"""
        message = f"""
🎉 *MILESTONE ATINGIDO!*

🏆 *{milestone}*
💰 Balance: `€{balance:.2f}`

Parabéns! 🚀
"""
        self.send_message(message)
    
    def notify_drawdown_warning(self, drawdown_pct: float, balance: float):
        """Notifica drawdown alto"""
        message = f"""
⚠️ *DRAWDOWN ALERT*

📉 Drawdown: `{drawdown_pct:.1f}%`
💰 Balance: `€{balance:.2f}`

Atenção necessária!
"""
        self.send_message(message)
    
    def send_daily_report(self, stats: dict):
        """Envia relatório diário"""
        message = f"""
📊 *RELATÓRIO DIÁRIO*

💰 Balance: `€{stats['balance']:.2f}`
📈 P&L: `{'+' if stats['pnl'] > 0 else ''}€{stats['pnl']:.2f}`
📊 Trades: {stats['num_trades']}
✅ Win Rate: {stats['win_rate']:.1%}

⏰ {datetime.now().strftime('%d/%m/%Y')}
"""
        self.send_message(message)


class EmailNotifier:
    """
    Envia notificações via Email
    """
    
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
        """Envia relatório diário por email"""
        subject = f"Trading Bot - Relatório Diário {datetime.now().strftime('%d/%m/%Y')}"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>📊 Relatório Diário - Trading Bot</h2>
            <hr>
            <table style="border-collapse: collapse; width: 100%;">
                <tr>
                    <td style="padding: 8px;"><strong>Balance:</strong></td>
                    <td style="padding: 8px;">€{stats['balance']:.2f}</td>
                </tr>
                <tr style="background-color: #f2f2f2;">
                    <td style="padding: 8px;"><strong>P&L Diário:</strong></td>
                    <td style="padding: 8px; color: {'green' if stats['pnl'] > 0 else 'red'};">
                        {'+' if stats['pnl'] > 0 else ''}€{stats['pnl']:.2f}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px;"><strong>Trades:</strong></td>
                    <td style="padding: 8px;">{stats['num_trades']}</td>
                </tr>
                <tr style="background-color: #f2f2f2;">
                    <td style="padding: 8px;"><strong>Win Rate:</strong></td>
                    <td style="padding: 8px;">{stats['win_rate']:.1%}</td>
                </tr>
            </table>
            <hr>
            <p style="color: #666; font-size: 12px;">
                Gerado automaticamente em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
            </p>
        </body>
        </html>
        """
        
        self.send_email(subject, body)


class AutoRestarter:
    """
    Sistema de auto-restart em caso de erro
    """
    
    def __init__(self, script_path: str, max_restarts: int = 5, cooldown_minutes: int = 5):
        self.script_path = script_path
        self.max_restarts = max_restarts
        self.cooldown_minutes = cooldown_minutes
        
        self.restart_count = 0
        self.last_restart = None
    
    def should_restart(self) -> bool:
        """Verifica se deve reiniciar"""
        if self.restart_count >= self.max_restarts:
            logger.error(f"❌ Máximo de {self.max_restarts} restarts atingido!")
            return False
        
        if self.last_restart:
            elapsed = datetime.now() - self.last_restart
            if elapsed < timedelta(minutes=self.cooldown_minutes):
                logger.warning(f"⏳ Cooldown ativo ({self.cooldown_minutes}min)")
                return False
        
        return True
    
    def restart(self):
        """Reinicia o bot"""
        if not self.should_restart():
            return False
        
        logger.warning("🔄 Reiniciando bot...")
        
        self.restart_count += 1
        self.last_restart = datetime.now()
        
        try:
            # Reiniciar processo
            python = sys.executable
            subprocess.Popen([python, self.script_path])
            
            logger.info("✅ Bot reiniciado com sucesso")
            time.sleep(2)
            sys.exit(0)  # Terminar processo atual
        
        except Exception as e:
            logger.error(f"❌ Falha ao reiniciar: {e}")
            return False
    
    def reset_counter(self):
        """Reset contador de restarts"""
        self.restart_count = 0
        logger.info("✅ Contador de restarts resetado")


class DailyReporter:
    """
    Gera relatórios diários automáticos
    """
    
    def __init__(self, telegram: TelegramNotifier = None, email: EmailNotifier = None):
        self.telegram = telegram
        self.email = email
        
        self.last_report = None
    
    def should_send_report(self) -> bool:
        """Verifica se deve enviar relatório"""
        report_hour = getattr(_cfg, 'REPORT_TIME_HOUR', 18) if _cfg else 18
        now = datetime.now()
        if now.hour == report_hour and now.minute < 5:
            if self.last_report is None or self.last_report.date() < now.date():
                return True
        return False
    
    def collect_stats(self, db_path: str = "data/trades.db") -> dict:
        """Coleta estatísticas do dia"""
        import sqlite3
        
        try:
            conn = sqlite3.connect(db_path)
            
            # Balance atual
            balance_query = "SELECT MAX(balance) FROM equity_curve"
            balance = conn.execute(balance_query).fetchone()[0] or 0
            
            # Trades de hoje
            today = datetime.now().date()
            trades_query = """
                SELECT profit
                FROM trades
                WHERE DATE(close_time) = ?
            """
            trades = conn.execute(trades_query, (today,)).fetchall()
            
            conn.close()
            
            num_trades = len(trades)
            if num_trades > 0:
                profits = [t[0] for t in trades]
                pnl = sum(profits)
                winners = [p for p in profits if p > 0]
                win_rate = len(winners) / num_trades
            else:
                pnl = 0
                win_rate = 0
            
            # Best performers today
            best_query = """
                SELECT symbol, SUM(profit) as total_pnl
                FROM trades WHERE DATE(close_time) = ?
                GROUP BY symbol ORDER BY total_pnl DESC LIMIT 3
            """
            best = conn.execute(best_query, (today,)).fetchall()
            best_strategies = [{'symbol': r[0], 'pnl': r[1]} for r in best]

            conn.close()

            initial_balance = getattr(_cfg, 'INITIAL_CAPITAL', balance) if _cfg else balance
            daily_pnl_pct = (pnl / initial_balance * 100) if initial_balance > 0 else 0
            dd_alert = getattr(_cfg, 'REPORT_DRAWDOWN_ALERT_PCT', 2.0) if _cfg else 2.0
            drawdown_alert = pnl < 0 and abs(daily_pnl_pct) >= dd_alert

            return {
                'balance': balance,
                'pnl': pnl,
                'daily_pnl': pnl,
                'daily_pnl_pct': daily_pnl_pct,
                'num_trades': num_trades,
                'wins': len([p for p in (profits if num_trades > 0 else []) if p > 0]),
                'losses': len([p for p in (profits if num_trades > 0 else []) if p <= 0]),
                'win_rate': win_rate,
                'best_strategies': best_strategies,
                'drawdown_alert': drawdown_alert,
            }

        except Exception as e:
            logger.error(f"❌ Erro ao coletar stats: {e}")
            return {
                'balance': 0,
                'pnl': 0,
                'daily_pnl': 0,
                'daily_pnl_pct': 0,
                'num_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'best_strategies': [],
                'drawdown_alert': False,
            }
    
    def send_report(self):
        """Envia relatório"""
        if not self.should_send_report():
            return

        logger.info("📊 Gerando relatório diário...")

        stats = self.collect_stats()

        # Drawdown alert
        if stats.get('drawdown_alert'):
            dd_pct = abs(stats.get('daily_pnl_pct', 0))
            logger.warning(f"⚠ DRAWDOWN ALERT: -{dd_pct:.1f}% hoje")
            if self.telegram:
                self.telegram.notify_drawdown_warning(dd_pct, stats['balance'])

        if self.telegram:
            self.telegram.send_daily_report(stats)

        if self.email:
            # EmailNotifier (automation.py) path
            self.email.send_daily_report(stats)
        elif _cfg and getattr(_cfg, 'REPORT_EMAIL_FROM', ''):
            # Fallback: use EmailReporter from notifications
            try:
                from src.notifications.email_reporter import EmailReporter
                reporter = EmailReporter(
                    smtp_server=_cfg.REPORT_SMTP_SERVER,
                    smtp_port=_cfg.REPORT_SMTP_PORT,
                    email=_cfg.REPORT_EMAIL_FROM,
                    password=_cfg.REPORT_EMAIL_PASSWORD,
                )
                html = reporter.generate_daily_report(stats)
                subject = (
                    f"Trading Bot V6 — Relatório {datetime.now().strftime('%d/%m/%Y')} | "
                    f"P&L: {'%+.2f' % stats['pnl']}€"
                )
                reporter.send_report(_cfg.REPORT_EMAIL_TO, subject, html)
                logger.info("✅ Email diário enviado!")
            except Exception as e:
                logger.error(f"❌ Falha ao enviar email: {e}")

        self.last_report = datetime.now()
        logger.info(f"✅ Relatório enviado! | Balance: €{stats['balance']:.2f} | P&L: {stats['pnl']:+.2f}€")


class ConfigBackup:
    """
    Backup automático de configurações
    """
    
    def __init__(self, backup_dir: str = "backups"):
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
    
    def backup_config(self):
        """Faz backup das configurações"""
        import shutil
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(self.backup_dir, f"config_{timestamp}")
        
        try:
            # Copiar pasta config
            shutil.copytree("config", backup_path)
            logger.info(f"✅ Backup salvo em {backup_path}")
            return True
        
        except Exception as e:
            logger.error(f"❌ Erro no backup: {e}")
            return False
    
    def auto_backup(self, interval_hours: int = 24):
        """Backup automático a cada X horas"""
        last_backup_file = os.path.join(self.backup_dir, "last_backup.txt")
        
        should_backup = True
        
        if os.path.exists(last_backup_file):
            with open(last_backup_file, 'r') as f:
                last_backup_str = f.read().strip()
                last_backup = datetime.fromisoformat(last_backup_str)
                
                elapsed = datetime.now() - last_backup
                if elapsed < timedelta(hours=interval_hours):
                    should_backup = False
        
        if should_backup:
            if self.backup_config():
                with open(last_backup_file, 'w') as f:
                    f.write(datetime.now().isoformat())


# Exemplo de uso
if __name__ == "__main__":
    # Configurar notificações
    telegram = TelegramNotifier(
        bot_token="YOUR_BOT_TOKEN",
        chat_id="YOUR_CHAT_ID"
    )
    
    # Teste
    telegram.send_message("🤖 Bot iniciado com sucesso!")
