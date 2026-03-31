"""
src/monitoring/alert_manager.py
Continuous safety checks for 24/7 autonomous operation.

Conditions monitored:
  1. Daily loss > 2% of balance  → email alert + stop new trades
  2. MT5 disconnected > 5 min    → email alert + reconnect attempt
  3. Margin level < 200%         → close oldest position
  4. Spread > 5x rolling average → skip entries for that symbol
  5. No trades for > 48 h        → email alert (bot may be stuck)
"""

import os
import sys
import smtplib
import logging
from collections import deque
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import config.settings as cfg

log = logging.getLogger(__name__)


# ─── Thresholds ───────────────────────────────────────────────

DAILY_LOSS_ALERT_PCT   = 2.0     # % of balance
MT5_OFFLINE_MINUTES    = 5       # max offline time before alert
MARGIN_LEVEL_MINIMUM   = 200.0   # % below which oldest position is closed
SPREAD_SPIKE_MULT      = 5.0     # × rolling average = anomaly
NO_TRADE_HOURS         = 48      # hours without a trade → alert
SPREAD_HISTORY_LEN     = 20      # rolling window for spread average
EMAIL_DEDUPE_MINUTES   = 60      # don't re-send same alert within N minutes


class AlertManager:
    """
    Run `check_all()` every bot loop.
    Returned `actions` list tells the bot what to do:
      'STOP_TRADING'   — skip all new entries this cycle
      'RECONNECT_MT5'  — attempt MT5 reconnect
      'CLOSE_OLDEST'   — close the least-profitable open position
    `skip_symbols` set — symbols with anomalous spread (skip entries only).
    """

    def __init__(self):
        self.daily_start_balance: Optional[float] = None
        self.daily_start_date: Optional[object]   = None

        self.last_trade_time: Optional[datetime]  = None
        self.mt5_disconnected_since: Optional[datetime] = None

        # {symbol: deque of recent spread values}
        self.spread_history: dict = {}

        # {alert_key: last_sent_datetime} — deduplication
        self._alerts_sent: dict = {}

        log.info("AlertManager initialised")

    # ─── Public API ──────────────────────────────────────────

    def record_trade(self):
        """Call this whenever a trade is opened or closed."""
        self.last_trade_time = datetime.now()

    def set_mt5_connected(self, connected: bool):
        """Notify the manager of MT5 connection state."""
        if not connected:
            if self.mt5_disconnected_since is None:
                self.mt5_disconnected_since = datetime.now()
        else:
            self.mt5_disconnected_since = None

    def check_all(
        self,
        balance: float,
        positions: list,
        spreads: dict,
        margin_level: float = 0.0,
    ) -> dict:
        """
        Run all safety checks.

        Returns:
            {
              'actions':      list[str],   # 'STOP_TRADING', 'RECONNECT_MT5', 'CLOSE_OLDEST'
              'skip_symbols': set[str],    # symbols with anomalous spread
              'alerts':       list[str],   # human-readable triggered alerts
            }
        """
        # Reset daily baseline if new day
        self._refresh_daily_balance(balance)

        actions      = []
        skip_symbols = set()
        alerts       = []

        # 1. Daily loss limit
        if self._check_daily_loss(balance):
            actions.append('STOP_TRADING')
            alerts.append('daily_loss')

        # 2. MT5 connection
        if self._check_mt5_disconnected():
            actions.append('RECONNECT_MT5')
            alerts.append('mt5_disconnected')

        # 3. Margin level
        if margin_level > 0 and self._check_margin_level(margin_level):
            actions.append('CLOSE_OLDEST')
            alerts.append('low_margin')

        # 4. Spread anomaly (per symbol)
        skip_symbols = self._check_spread_anomaly(spreads)
        if skip_symbols:
            alerts.append(f'spread_spike:{",".join(skip_symbols)}')

        # 5. No trades > 48 h
        if self._check_no_trades():
            alerts.append('no_trades_48h')

        return {
            'actions':      actions,
            'skip_symbols': skip_symbols,
            'alerts':       alerts,
        }

    # ─── Individual checks ────────────────────────────────────

    def _refresh_daily_balance(self, balance: float):
        today = datetime.now().date()
        if self.daily_start_date != today:
            self.daily_start_balance = balance
            self.daily_start_date    = today

    def _check_daily_loss(self, balance: float) -> bool:
        if self.daily_start_balance is None or self.daily_start_balance <= 0:
            return False
        loss_pct = (self.daily_start_balance - balance) / self.daily_start_balance * 100
        if loss_pct >= DAILY_LOSS_ALERT_PCT:
            msg = (
                f"Daily loss {loss_pct:.2f}% exceeds {DAILY_LOSS_ALERT_PCT}% threshold. "
                f"Balance: €{balance:.2f} (started: €{self.daily_start_balance:.2f})"
            )
            log.warning(f"[ALERT] {msg}")
            self._send_email_alert(
                "CRITICAL: Daily loss limit reached",
                f"<p>{msg}</p><p>Bot has stopped opening new positions for today.</p>",
                dedupe_key='daily_loss',
            )
            return True
        return False

    def _check_mt5_disconnected(self) -> bool:
        if self.mt5_disconnected_since is None:
            return False
        offline_min = (datetime.now() - self.mt5_disconnected_since).total_seconds() / 60
        if offline_min >= MT5_OFFLINE_MINUTES:
            msg = f"MT5 disconnected for {offline_min:.0f} minutes. Attempting reconnect."
            log.error(f"[ALERT] {msg}")
            self._send_email_alert(
                "CRITICAL: MT5 disconnected",
                f"<p>{msg}</p>",
                dedupe_key='mt5_disconnected',
            )
            return True
        return False

    def _check_margin_level(self, margin_level: float) -> bool:
        if margin_level < MARGIN_LEVEL_MINIMUM:
            msg = f"Margin level {margin_level:.0f}% below {MARGIN_LEVEL_MINIMUM}%. Closing oldest position."
            log.warning(f"[ALERT] {msg}")
            self._send_email_alert(
                "WARNING: Low margin level",
                f"<p>{msg}</p>",
                dedupe_key='low_margin',
            )
            return True
        return False

    def _check_spread_anomaly(self, spreads: dict) -> set:
        """Returns set of symbols with spread > 5× rolling average."""
        anomalous = set()
        for sym, spread in (spreads or {}).items():
            spread = float(spread)
            if sym not in self.spread_history:
                self.spread_history[sym] = deque(maxlen=SPREAD_HISTORY_LEN)
            history = self.spread_history[sym]
            if len(history) >= 5:
                avg = sum(history) / len(history)
                if avg > 0 and spread > avg * SPREAD_SPIKE_MULT:
                    msg = f"{sym} spread {spread:.1f} pts = {spread/avg:.1f}× average ({avg:.1f})"
                    log.warning(f"[ALERT] Spread spike: {msg}")
                    anomalous.add(sym)
            history.append(spread)
        return anomalous

    def _check_no_trades(self) -> bool:
        if self.last_trade_time is None:
            return False
        hours_idle = (datetime.now() - self.last_trade_time).total_seconds() / 3600
        if hours_idle >= NO_TRADE_HOURS:
            msg = f"No trades for {hours_idle:.0f} hours. Bot may be stuck or filters too strict."
            log.warning(f"[ALERT] {msg}")
            self._send_email_alert(
                "WARNING: Bot idle for 48+ hours",
                f"<p>{msg}</p>",
                dedupe_key='no_trades',
            )
            return True
        return False

    # ─── Email helper ─────────────────────────────────────────

    def _can_send(self, key: str) -> bool:
        last = self._alerts_sent.get(key)
        if last is None:
            return True
        return (datetime.now() - last).total_seconds() / 60 >= EMAIL_DEDUPE_MINUTES

    def _send_email_alert(self, subject: str, html_body: str, dedupe_key: str = None):
        if dedupe_key and not self._can_send(dedupe_key):
            return  # already sent recently

        from_addr = getattr(cfg, 'REPORT_EMAIL_FROM', '')
        to_addr   = getattr(cfg, 'REPORT_EMAIL_TO', from_addr)
        password  = getattr(cfg, 'REPORT_EMAIL_PASSWORD', '')
        smtp_srv  = getattr(cfg, 'REPORT_SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = getattr(cfg, 'REPORT_SMTP_PORT', 587)

        if not from_addr or not password:
            log.debug("Email alert skipped — REPORT_EMAIL_FROM not configured")
            return

        full_html = f"""
        <html><body style="font-family:Arial,sans-serif">
          <h2 style="color:#e53935">{subject}</h2>
          {html_body}
          <hr>
          <small>Trading Bot V6 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small>
        </body></html>
        """
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[TradingBot] {subject}"
        msg['From']    = from_addr
        msg['To']      = to_addr
        msg.attach(MIMEText(full_html, 'html'))

        try:
            with smtplib.SMTP(smtp_srv, smtp_port, timeout=10) as srv:
                srv.starttls()
                srv.login(from_addr, password)
                srv.send_message(msg)
            log.info(f"Alert email sent: {subject}")
            if dedupe_key:
                self._alerts_sent[dedupe_key] = datetime.now()
        except Exception as e:
            log.error(f"Alert email failed: {e}")
