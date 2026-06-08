"""
src/notifications/daily_scheduler.py

Envia o relatorio diario uma vez por dia no horario configurado (UTC).
Chamado a cada ciclo do motor — zero I/O se ainda nao for hora.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone

from src.notifications.email_reporter import EmailReporter

logger = logging.getLogger(__name__)


class DailyReportScheduler:
    """
    Envia email de relatorio diario uma vez apos report_hour_utc (ex: 22:00 UTC).
    Design: chamado em cada ciclo do motor; so age quando e hora e ainda nao enviou hoje.
    """

    def __init__(self, report_hour_utc: int | None = None):
        hour = report_hour_utc
        if hour is None:
            hour = int(os.getenv("EMAIL_REPORT_HOUR_UTC", "22"))
        self._report_hour = max(0, min(23, hour))
        self._last_sent: date | None = None
        self._reporter  = self._make_reporter()

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, state: dict) -> bool:
        """
        Chama a cada ciclo do motor.
        Retorna True se enviou o relatorio neste ciclo.
        state: dicionario com campos do motor (account, performance, signals).
        """
        now = datetime.now(timezone.utc)
        today = now.date()

        if now.hour < self._report_hour:
            return False
        if self._last_sent == today:
            return False
        if self._reporter is None:
            return False

        self._last_sent = today
        try:
            self._send(state)
            return True
        except Exception as e:
            logger.error(f"[DailyReport] Envio falhou: {e}")
            return False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _make_reporter(self) -> EmailReporter | None:
        from_addr = os.getenv("EMAIL_FROM", "")
        password  = os.getenv("EMAIL_PASSWORD", "")
        if not from_addr or not password:
            logger.debug("[DailyReport] EMAIL_FROM ou EMAIL_PASSWORD nao configurados — relatorio desactivado.")
            return None
        return EmailReporter(
            smtp_server = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com"),
            smtp_port   = int(os.getenv("EMAIL_SMTP_PORT", "587")),
            email       = from_addr,
            password    = password,
        )

    def _send(self, state: dict) -> None:
        to_addr = os.getenv("EMAIL_TO", os.getenv("EMAIL_FROM", ""))
        if not to_addr:
            return

        account = state.get("account", {})
        perf    = state.get("performance", {})

        data = {
            "balance":          float(account.get("balance", 0)),
            "daily_pnl":        float(account.get("daily_pnl", 0)),
            "daily_pnl_pct":    float(account.get("daily_return_pct", 0)),
            "total_trades":     int(perf.get("trades_today", 0)),
            "wins":             int(perf.get("wins_today", perf.get("trades_today", 0))),
            "losses":           int(perf.get("losses_today", 0)),
            "win_rate":         float(perf.get("win_rate", 0)),
            "best_strategies":  _extract_best(state.get("strategies", [])),
        }

        html    = self._reporter.generate_daily_report(data)
        # Adicionar secao de validacao em papel ao HTML
        html    = _append_validation_section(html, state)
        subject = (
            f"Relatorio diario {datetime.now(timezone.utc).strftime('%Y-%m-%d')} "
            f"P&L {data['daily_pnl']:+.2f}EUR"
        )
        ok = self._reporter.send_report(to_addr, subject, html)
        if ok:
            logger.info(f"[DailyReport] Enviado para {to_addr}: {subject}")
        else:
            logger.error("[DailyReport] Falha no envio SMTP")


def _append_validation_section(html: str, state: dict) -> str:
    """Adiciona progresso da validacao em papel ao HTML do relatorio diario."""
    try:
        from src.monitoring.paper_validator import PaperValidator
        from pathlib import Path
        validator = PaperValidator()
        result    = validator.evaluate()

        color = "#22c55e" if result.all_pass else "#f59e0b"
        rows  = "".join(
            f"<tr><td style='padding:4px 8px'>{line.strip()}</td></tr>"
            for line in result.summary_lines()
        )
        section = f"""
<div style="background:white;border:1px solid #ddd;border-radius:8px;padding:16px;margin:12px 0">
  <h2 style="margin:0 0 10px;font-size:15px;color:#333">Fase 9 — Validacao em Papel</h2>
  <p style="margin:0 0 8px;font-size:13px;color:#666">
    Trades totais: <b>{result.total_trades}</b> &nbsp;|&nbsp;
    P&amp;L: <b style="color:{color}">{result.total_pnl:+.2f} EUR</b> &nbsp;|&nbsp;
    Criterios: <b>{result.criteria_passed}/4</b>
  </p>
  <table style="font-family:monospace;font-size:12px;width:100%;border-collapse:collapse">
    {rows}
  </table>
</div>"""
        # Inserir antes do footer
        return html.replace('<div class="footer">', section + '\n<div class="footer">')
    except Exception:
        return html


def _extract_best(strategies: list[dict]) -> list[dict]:
    active = [s for s in strategies if s.get("pnl_today", 0) != 0]
    active.sort(key=lambda s: s.get("pnl_today", 0), reverse=True)
    return [{"symbol": s["symbol"], "pnl": s["pnl_today"]} for s in active[:5]]
