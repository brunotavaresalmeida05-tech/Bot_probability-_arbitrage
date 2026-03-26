"""
Email Reporter - Automated HTML reports via SMTP.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


class EmailReporter:
    def __init__(self, smtp_server: str, smtp_port: int, email: str, password: str):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.email = email
        self.password = password

    def send_report(self, to_email: str, subject: str, html: str) -> bool:
        """Envia email HTML."""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.email
        msg['To'] = to_email

        html_part = MIMEText(html, 'html')
        msg.attach(html_part)

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email, self.password)
                server.send_message(msg)
            return True
        except Exception as e:
            print(f"Email error: {e}")
            return False

    def generate_daily_report(self, data: dict) -> str:
        """Gera relatório HTML diário."""
        pnl = data.get('daily_pnl', 0)
        pnl_pct = data.get('daily_pnl_pct', 0)
        pnl_class = 'positive' if pnl >= 0 else 'negative'
        pnl_color = '#22c55e' if pnl >= 0 else '#ef4444'

        best_html = ''
        for s in data.get('best_strategies', []):
            best_html += f"<li>{s['symbol']}: €{s['pnl']:.2f}</li>"

        html = f"""
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 0; }}
        .header {{ background: #667eea; color: white; padding: 20px; text-align: center; }}
        .header h1 {{ margin: 0; }}
        .header p {{ margin: 5px 0 0; opacity: 0.8; }}
        .content {{ max-width: 600px; margin: 20px auto; }}
        .metrics {{ display: flex; gap: 15px; flex-wrap: wrap; margin: 20px 0; }}
        .card {{
            flex: 1; min-width: 150px;
            background: white; border: 1px solid #ddd;
            padding: 15px; border-radius: 8px; text-align: center;
        }}
        .card h3 {{ margin: 0 0 8px; font-size: 13px; color: #666; }}
        .card .val {{ font-size: 24px; font-weight: bold; }}
        .positive {{ color: #22c55e; }}
        .negative {{ color: #ef4444; }}
        .section {{ background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin: 15px 0; }}
        .section h2 {{ margin: 0 0 10px; font-size: 16px; color: #333; }}
        ul {{ padding-left: 20px; }}
        li {{ margin: 5px 0; }}
        .footer {{ text-align: center; color: #999; font-size: 12px; padding: 20px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Daily Trading Report</h1>
        <p>{datetime.now().strftime('%Y-%m-%d')}</p>
    </div>

    <div class="content">
        <div class="metrics">
            <div class="card">
                <h3>Balance</h3>
                <div class="val">€{data.get('balance', 0):.2f}</div>
                <div style="color: {pnl_color}; font-size: 14px;">
                    {pnl:+.2f} ({pnl_pct:+.2f}%)
                </div>
            </div>

            <div class="card">
                <h3>Trades Today</h3>
                <div class="val">{data.get('total_trades', 0)}</div>
                <div style="font-size: 14px; color: #666;">
                    {data.get('wins', 0)}W / {data.get('losses', 0)}L
                </div>
            </div>

            <div class="card">
                <h3>Win Rate</h3>
                <div class="val">{data.get('win_rate', 0):.1f}%</div>
            </div>
        </div>

        <div class="section">
            <h2>Best Performers</h2>
            <ul>{best_html if best_html else '<li>No data</li>'}</ul>
        </div>

        <div class="footer">
            Trading Bot v6 - Automated Report
        </div>
    </div>
</body>
</html>
        """
        return html
