"""
flask_dashboard.py
Flask backend for Trading Bot V6 Dashboard
Serves dashboard_v2/ and provides 10 REST routes + WebSocket (updates every 2s)
"""
import json
import os
import time
import sqlite3
from datetime import datetime

from flask import Flask, jsonify, send_from_directory, request

try:
    from flask_sock import Sock
    _SOCK_OK = True
except ImportError:
    _SOCK_OK = False
    print("[WARNING] flask_sock not installed. Run: pip install flask-sock")

app = Flask(__name__, static_folder='dashboard_v2', static_url_path='')
if _SOCK_OK:
    sock = Sock(app)

LIVE_STATE_PATH = 'data/live_state.json'
DB_PATH = 'data/trades.db'


# ─── Helpers ──────────────────────────────────────────────────

def read_live_state() -> dict:
    try:
        with open(LIVE_STATE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            'timestamp': datetime.now().isoformat(),
            'account': {
                'balance': 0, 'equity': 0, 'margin': 0,
                'free_margin': 0, 'profit': 0, 'currency': 'EUR',
            },
            'positions': [],
            'signals': [],
            'spreads': {},
            'prices': {},
        }


def db_query(sql: str, params: tuple = (), many: bool = True):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if many else cur.fetchone()
        if rows and not many:
            rows = dict(rows)
        conn.close()
        return rows or ([] if many else {})
    except Exception:
        return [] if many else {}


def get_equity_curve(limit: int = 500) -> list:
    sql = """
        SELECT close_time,
               SUM(profit) OVER (ORDER BY close_time) AS cumulative_profit,
               profit
        FROM trades
        WHERE status = 'closed'
        ORDER BY close_time ASC
        LIMIT ?
    """
    return db_query(sql, (limit,))


def get_stats() -> dict:
    sql = """
        SELECT
            COUNT(*)                                              AS total,
            SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END)          AS wins,
            ROUND(SUM(profit), 2)                                 AS total_profit,
            ROUND(AVG(profit), 2)                                 AS avg_profit,
            ROUND(MAX(profit), 2)                                 AS best_trade,
            ROUND(MIN(profit), 2)                                 AS worst_trade
        FROM trades WHERE status = 'closed'
    """
    row = db_query(sql, many=False)
    if row and row.get('total'):
        total = row['total'] or 0
        wins  = row['wins'] or 0
        return {
            'total_trades': total,
            'wins':         wins,
            'losses':       total - wins,
            'win_rate':     round(wins / total * 100, 1) if total > 0 else 0,
            'total_profit': row.get('total_profit') or 0,
            'avg_profit':   row.get('avg_profit') or 0,
            'best_trade':   row.get('best_trade') or 0,
            'worst_trade':  row.get('worst_trade') or 0,
        }
    return {'total_trades': 0, 'wins': 0, 'losses': 0, 'win_rate': 0, 'total_profit': 0}


# ─── REST Routes ──────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('dashboard_v2', 'index.html')


@app.route('/css/<path:path>')
def serve_css(path):
    return send_from_directory('dashboard_v2/css', path)


@app.route('/js/<path:path>')
def serve_js(path):
    return send_from_directory('dashboard_v2/js', path)


@app.route('/api/balance')
def api_balance():
    return jsonify(read_live_state().get('account', {}))


@app.route('/api/positions')
def api_positions():
    return jsonify(read_live_state().get('positions', []))


@app.route('/api/signals')
def api_signals():
    return jsonify(read_live_state().get('signals', []))


@app.route('/api/equity')
def api_equity():
    return jsonify(get_equity_curve())


@app.route('/api/spreads')
def api_spreads():
    return jsonify(read_live_state().get('spreads', {}))


@app.route('/api/prices')
def api_prices():
    return jsonify(read_live_state().get('prices', {}))


@app.route('/api/history')
def api_history():
    limit = request.args.get('limit', 100, type=int)
    sql = """
        SELECT symbol, strategy, profit, open_time, close_time, direction, lots
        FROM trades WHERE status = 'closed'
        ORDER BY close_time DESC LIMIT ?
    """
    return jsonify(db_query(sql, (limit,)))


@app.route('/api/stats')
def api_stats():
    return jsonify(get_stats())


@app.route('/api/strategy_stats')
def api_strategy_stats():
    sql = """
        SELECT strategy,
               COUNT(*) AS total,
               SUM(CASE WHEN profit > 0 THEN 1 ELSE 0 END) AS wins,
               ROUND(SUM(profit), 2) AS total_profit,
               ROUND(AVG(profit), 2) AS avg_profit
        FROM trades WHERE status = 'closed'
        GROUP BY strategy
        ORDER BY total_profit DESC
    """
    return jsonify(db_query(sql))


@app.route('/api/health')
def api_health():
    state = read_live_state()
    ts = state.get('timestamp', '')
    bot_alive = False
    if ts:
        try:
            age = (datetime.now() - datetime.fromisoformat(ts)).total_seconds()
            bot_alive = age < 60
        except Exception:
            pass
    return jsonify({
        'flask': 'ok',
        'bot':   'running' if bot_alive else 'stopped',
        'last_state_update': ts,
    })


# ─── WebSocket ────────────────────────────────────────────────

if _SOCK_OK:
    @sock.route('/ws')
    def websocket_handler(ws):
        while True:
            try:
                state = read_live_state()
                equity = get_equity_curve(50)
                stats  = get_stats()
                payload = {
                    **state,
                    'equity_curve': equity,
                    'stats': stats,
                }
                ws.send(json.dumps(payload, default=str))
                time.sleep(2)
            except Exception:
                break


# ─── Entry point ──────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 50)
    print("  Trading Bot V6 - Flask Dashboard")
    print("  URL: http://localhost:5000")
    if not _SOCK_OK:
        print("  [!] Install flask-sock: pip install flask-sock")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
