"""
Trade Logger - Persistent SQLite database for trade history.
"""

import sqlite3
import os
import pandas as pd
from datetime import datetime


class TradeLogger:
    def __init__(self, db_path='data/trades.db'):
        """
        Args:
            db_path: Caminho para o ficheiro SQLite
        """
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Cria tabelas se não existirem."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                direction TEXT NOT NULL,
                lot_size REAL NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                stop_loss REAL,
                take_profit REAL,
                pnl REAL,
                pnl_pct REAL,
                commission REAL,
                duration_minutes INTEGER,
                exit_reason TEXT,
                notes TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS equity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                balance REAL NOT NULL,
                equity REAL NOT NULL,
                margin_used REAL,
                free_margin REAL,
                drawdown_pct REAL
            )
        ''')

        conn.commit()
        conn.close()

    def log_trade_open(self, trade: dict) -> int:
        """
        Registra abertura de trade.

        Returns: trade_id
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO trades (
                timestamp, symbol, strategy, direction,
                lot_size, entry_price, stop_loss, take_profit
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            trade['symbol'],
            trade.get('strategy', 'unknown'),
            trade['direction'],
            trade['lot_size'],
            trade['entry_price'],
            trade.get('stop_loss'),
            trade.get('take_profit'),
        ))

        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return trade_id

    def log_trade_close(self, trade_id: int, close_data: dict):
        """Atualiza trade com dados de fecho."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE trades
            SET exit_price = ?,
                pnl = ?,
                pnl_pct = ?,
                duration_minutes = ?,
                exit_reason = ?,
                notes = ?
            WHERE id = ?
        ''', (
            close_data['exit_price'],
            close_data['pnl'],
            close_data.get('pnl_pct'),
            close_data.get('duration_minutes'),
            close_data.get('exit_reason'),
            close_data.get('notes'),
            trade_id,
        ))

        conn.commit()
        conn.close()

    def log_equity_snapshot(self, snapshot: dict):
        """Registra snapshot de equity."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO equity_snapshots (
                timestamp, balance, equity,
                margin_used, free_margin, drawdown_pct
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            snapshot['balance'],
            snapshot['equity'],
            snapshot.get('margin_used'),
            snapshot.get('free_margin'),
            snapshot.get('drawdown_pct'),
        ))

        conn.commit()
        conn.close()

    def get_trades(self, start_date=None, end_date=None,
                   symbol=None, strategy=None) -> pd.DataFrame:
        """Obtém trades filtrados."""
        conn = sqlite3.connect(self.db_path)

        query = "SELECT * FROM trades WHERE 1=1"
        params = []

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        if strategy:
            query += " AND strategy = ?"
            params.append(strategy)

        query += " ORDER BY timestamp DESC"

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        return df

    def get_equity_history(self, start_date=None) -> pd.DataFrame:
        """Obtém histórico de equity."""
        conn = sqlite3.connect(self.db_path)

        query = "SELECT * FROM equity_snapshots"
        params = []

        if start_date:
            query += " WHERE timestamp >= ?"
            params.append(start_date)

        query += " ORDER BY timestamp ASC"

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        return df

    def export_to_csv(self, filename: str) -> str:
        """Exporta trades para CSV."""
        df = self.get_trades()
        df.to_csv(filename, index=False)
        return filename

    def get_summary_stats(self) -> dict:
        """Estatísticas resumidas."""
        conn = sqlite3.connect(self.db_path)

        total = pd.read_sql_query(
            "SELECT COUNT(*) as count FROM trades WHERE pnl IS NOT NULL",
            conn,
        )['count'].iloc[0]

        wins = pd.read_sql_query(
            "SELECT COUNT(*) as count FROM trades WHERE pnl > 0",
            conn,
        )['count'].iloc[0]

        pnl_result = pd.read_sql_query(
            "SELECT COALESCE(SUM(pnl), 0) as total FROM trades",
            conn,
        )['total'].iloc[0]

        conn.close()

        return {
            'total_trades': int(total),
            'wins': int(wins),
            'win_rate': wins / total * 100 if total > 0 else 0,
            'total_pnl': float(pnl_result),
        }
