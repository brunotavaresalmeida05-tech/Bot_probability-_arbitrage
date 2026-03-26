"""
Telegram Bot - Push notifications para alertas de trading.
"""

import requests


class TelegramBot:
    def __init__(self, bot_token: str, chat_id: str):
        """
        Args:
            bot_token: Token do bot (obtém com @BotFather)
            chat_id: Teu chat ID
        """
        self.token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send_message(self, text: str, parse_mode='Markdown'):
        """Envia mensagem."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': parse_mode,
        }

        try:
            response = requests.post(url, json=payload, timeout=5)
            return response.json()
        except Exception as e:
            print(f"Telegram error: {e}")
            return None

    def send_trade_alert(self, trade: dict):
        """Alerta de trade executado."""
        direction_emoji = "🟢" if trade['direction'] in ('LONG', 'BUY') else "🔴"

        text = (
            f"{direction_emoji} *TRADE OPENED*\n\n"
            f"*Symbol:* {trade['symbol']}\n"
            f"*Direction:* {trade['direction']}\n"
            f"*Size:* {trade['size']} lots\n"
            f"*Entry:* {trade['entry_price']:.5f}\n"
            f"*Stop:* {trade['stop_loss']:.5f}\n"
            f"*Strategy:* {trade['strategy']}\n"
            f"*Risk:* €{trade['risk_money']:.2f}"
        )

        return self.send_message(text)

    def send_trade_close_alert(self, trade: dict):
        """Alerta de trade fechado."""
        pnl = trade.get('pnl', 0)
        emoji = "✅" if pnl >= 0 else "❌"

        text = (
            f"{emoji} *TRADE CLOSED*\n\n"
            f"*Symbol:* {trade['symbol']}\n"
            f"*Direction:* {trade['direction']}\n"
            f"*Entry:* {trade['entry_price']:.5f}\n"
            f"*Exit:* {trade['exit_price']:.5f}\n"
            f"*P&L:* €{pnl:.2f}\n"
            f"*Reason:* {trade.get('reason', '-')}"
        )

        return self.send_message(text)

    def send_drawdown_warning(self, dd_pct: float):
        """Alerta de drawdown."""
        text = (
            "⚠️ *DRAWDOWN ALERT*\n\n"
            f"Current DD: {dd_pct:.1f}%\n\n"
            "Risk reduced to 50%.\n"
            "Entering protection mode."
        )

        return self.send_message(text)

    def send_daily_summary(self, summary: dict):
        """Resumo diário."""
        text = (
            "📊 *DAILY SUMMARY*\n\n"
            f"*Trades:* {summary['total_trades']}\n"
            f"*Wins:* {summary['wins']} | *Losses:* {summary['losses']}\n"
            f"*Win Rate:* {summary['win_rate']:.1f}%\n\n"
            f"*P&L:* €{summary['pnl']:.2f} ({summary['pnl_pct']:+.2f}%)\n"
            f"*Balance:* €{summary['balance']:.2f}\n\n"
            f"*Best Trade:* {summary.get('best_symbol', '-')} (+€{summary.get('best_trade', 0):.2f})\n"
            f"*Worst Trade:* {summary.get('worst_symbol', '-')} (-€{abs(summary.get('worst_trade', 0)):.2f})"
        )

        return self.send_message(text)

    def send_weekly_summary(self, summary: dict):
        """Resumo semanal."""
        text = (
            "📈 *WEEKLY SUMMARY*\n\n"
            f"*Total Trades:* {summary['total_trades']}\n"
            f"*Win Rate:* {summary['win_rate']:.1f}%\n"
            f"*Weekly P&L:* €{summary['pnl']:.2f} ({summary['pnl_pct']:+.2f}%)\n"
            f"*Balance:* €{summary['balance']:.2f}\n"
            f"*Sharpe:* {summary.get('sharpe', 0):.2f}\n"
            f"*Max DD:* {summary.get('max_dd', 0):.1f}%"
        )

        return self.send_message(text)
