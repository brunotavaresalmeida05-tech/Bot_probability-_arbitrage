"""
Enhanced Dashboard - Real-time monitoring
Complementa o dashboard_server.py com métricas avançadas e UI melhorada.
"""

import json
import threading
from datetime import datetime
from typing import Optional


class EnhancedDashboard:
    def __init__(self, port=8765):
        self.port = port
        self._lock = threading.Lock()
        self._broadcast_callback = None
        self.metrics = {
            'balance': 0,
            'equity': 0,
            'open_positions': [],
            'daily_pnl': 0,
            'weekly_pnl': 0,
            'total_trades': 0,
            'win_rate': 0,
            'sharpe': 0,
            'drawdown': 0,
            'strategies': {},
            'equity_history': [],
            'data_health': {},
        }

    def set_broadcast_callback(self, callback):
        """Define callback para broadcast via WebSocket."""
        self._broadcast_callback = callback

    def update_metrics(self, data: dict):
        """Atualiza métricas do dashboard."""
        with self._lock:
            self.metrics.update(data)
        if self._broadcast_callback:
            self._broadcast_callback(json.dumps(self.metrics))

    def get_metrics(self) -> dict:
        """Retorna snapshot das métricas atuais."""
        with self._lock:
            return dict(self.metrics)

    def update_from_account(self, account: dict, daily_pnl: float = 0.0,
                            weekly_pnl: float = 0.0):
        """Atualiza métricas a partir dos dados da conta MT5."""
        equity = account.get('equity', 0)
        with self._lock:
            self.metrics['balance'] = account.get('balance', 0)
            self.metrics['equity'] = equity
            self.metrics['daily_pnl'] = daily_pnl
            self.metrics['weekly_pnl'] = weekly_pnl
            self.metrics['equity_history'].append({
                'time': datetime.now().strftime('%H:%M:%S'),
                'equity': equity,
            })
            # Manter max 500 pontos
            if len(self.metrics['equity_history']) > 500:
                self.metrics['equity_history'].pop(0)

    def update_trade_stats(self, total_trades: int, win_rate: float,
                           sharpe: float, drawdown: float):
        """Atualiza estatísticas de trading."""
        with self._lock:
            self.metrics['total_trades'] = total_trades
            self.metrics['win_rate'] = win_rate
            self.metrics['sharpe'] = sharpe
            self.metrics['drawdown'] = drawdown

    def update_positions(self, positions: list):
        """Atualiza lista de posições abertas."""
        with self._lock:
            self.metrics['open_positions'] = positions

    def update_strategy_stats(self, strategies: dict):
        """Atualiza performance por estratégia."""
        with self._lock:
            self.metrics['strategies'] = strategies

    def update_data_health(self, health_data: dict):
        """Atualiza estado de saude das data sources."""
        with self._lock:
            self.metrics['data_health'] = health_data

    def get_html(self) -> str:
        """HTML do dashboard melhorado."""
        return '''
<!DOCTYPE html>
<html>
<head>
    <title>Trading Bot Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0e27;
            color: #fff;
            padding: 20px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 10px;
        }
        .header h1 { font-size: 28px; }
        .status {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        .status-dot {
            width: 12px;
            height: 12px;
            background: #4ade80;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: #1a1f3a;
            padding: 20px;
            border-radius: 10px;
            border: 1px solid #2d3348;
        }
        .card h3 {
            font-size: 14px;
            color: #8b92b0;
            margin-bottom: 10px;
        }
        .card .value {
            font-size: 32px;
            font-weight: bold;
            color: #fff;
        }
        .card .change {
            font-size: 14px;
            margin-top: 5px;
        }
        .positive { color: #4ade80; }
        .negative { color: #f87171; }
        .chart-container {
            background: #1a1f3a;
            padding: 20px;
            border-radius: 10px;
            border: 1px solid #2d3348;
            margin-bottom: 20px;
        }
        .positions-table {
            width: 100%;
            border-collapse: collapse;
        }
        .positions-table th {
            background: #2d3348;
            padding: 12px;
            text-align: left;
            font-size: 12px;
            color: #8b92b0;
        }
        .positions-table td {
            padding: 12px;
            border-bottom: 1px solid #2d3348;
        }
        .strategies-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }
        .strategy-card {
            background: #0a0e27;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #2d3348;
        }
        .strategy-card h4 {
            font-size: 13px;
            color: #667eea;
            margin-bottom: 8px;
        }
        .strategy-card .stat {
            font-size: 12px;
            color: #8b92b0;
            margin-bottom: 4px;
        }
        .no-positions {
            text-align: center;
            color: #8b92b0;
            padding: 30px;
            font-style: italic;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Trading Bot v6</h1>
        <div class="status">
            <div class="status-dot"></div>
            <span>LIVE</span>
            <span id="timestamp"></span>
        </div>
    </div>

    <div class="grid">
        <div class="card">
            <h3>BALANCE</h3>
            <div class="value" id="balance">0.00</div>
            <div class="change" id="balance-change">+0.00%</div>
        </div>
        <div class="card">
            <h3>EQUITY</h3>
            <div class="value" id="equity">0.00</div>
        </div>
        <div class="card">
            <h3>DAILY P&amp;L</h3>
            <div class="value" id="daily-pnl">0.00</div>
            <div class="change" id="daily-pct">+0.00%</div>
        </div>
        <div class="card">
            <h3>WEEKLY P&amp;L</h3>
            <div class="value" id="weekly-pnl">0.00</div>
        </div>
        <div class="card">
            <h3>WIN RATE</h3>
            <div class="value" id="win-rate">0%</div>
        </div>
        <div class="card">
            <h3>SHARPE RATIO</h3>
            <div class="value" id="sharpe">0.0</div>
        </div>
        <div class="card">
            <h3>DRAWDOWN</h3>
            <div class="value negative" id="drawdown">-0.0%</div>
        </div>
        <div class="card">
            <h3>TOTAL TRADES</h3>
            <div class="value" id="total-trades">0</div>
        </div>
    </div>

    <div class="chart-container">
        <h3 style="color:#8b92b0; margin-bottom:15px;">EQUITY CURVE</h3>
        <div id="equity-chart" style="height:300px;"></div>
    </div>

    <div class="chart-container">
        <h3 style="color:#8b92b0; margin-bottom:15px;">OPEN POSITIONS</h3>
        <table class="positions-table">
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Direction</th>
                    <th>Size</th>
                    <th>Entry</th>
                    <th>Current</th>
                    <th>P&amp;L</th>
                    <th>Strategy</th>
                </tr>
            </thead>
            <tbody id="positions-tbody">
            </tbody>
        </table>
        <div class="no-positions" id="no-positions">No open positions</div>
    </div>

    <div class="chart-container">
        <h3 style="color:#8b92b0; margin-bottom:15px;">STRATEGY PERFORMANCE</h3>
        <div class="strategies-grid" id="strategies-grid">
        </div>
    </div>

    <div class="chart-container">
        <h3 style="color:#8b92b0; margin-bottom:15px;">DATA SOURCES HEALTH</h3>
        <table class="positions-table">
            <thead>
                <tr>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Latency</th>
                    <th>Uptime 24h</th>
                </tr>
            </thead>
            <tbody id="health-tbody">
            </tbody>
        </table>
        <div class="no-positions" id="no-health">No health data yet</div>
    </div>

    <script>
        const ws = new WebSocket('ws://localhost:''' + str(self.port) + '''/ws');
        let equityTimes = [];
        let equityValues = [];
        let chartInitialized = false;

        ws.onopen = function() {
            console.log('Connected to dashboard');
        };

        ws.onmessage = function(event) {
            const raw = JSON.parse(event.data);
            // Suporta tanto formato enhanced como formato original
            if (raw.account) {
                updateFromOriginal(raw);
            } else {
                updateDashboard(raw);
            }
        };

        ws.onclose = function() {
            document.querySelector('.status-dot').style.background = '#f87171';
            document.querySelector('.status span').textContent = 'DISCONNECTED';
        };

        function updateFromOriginal(raw) {
            // Converter formato dashboard_server.py para enhanced
            const data = {
                balance: raw.account.balance || 0,
                equity: raw.account.equity || 0,
                daily_pnl: 0,
                weekly_pnl: 0,
                win_rate: 0,
                sharpe: 0,
                drawdown: 0,
                total_trades: (raw.trades || []).length,
                open_positions: (raw.open_positions || []).map(p => ({
                    symbol: p.symbol,
                    direction: p.type,
                    size: p.lots,
                    entry: p.entry,
                    current: p.entry,
                    pnl: p.profit,
                    strategy: p.comment || '-'
                })),
                equity_history: (raw.equity_curve || []).map(e => ({
                    time: e.t,
                    equity: e.v
                })),
                strategies: {}
            };
            updateDashboard(data);
        }

        function fmt(val) {
            return (val || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        }

        function updateDashboard(data) {
            document.getElementById('balance').textContent = fmt(data.balance);
            document.getElementById('equity').textContent = fmt(data.equity);

            const dailyPnl = data.daily_pnl || 0;
            const dailyEl = document.getElementById('daily-pnl');
            dailyEl.textContent = (dailyPnl >= 0 ? '+' : '') + fmt(dailyPnl);
            dailyEl.className = 'value ' + (dailyPnl >= 0 ? 'positive' : 'negative');

            const weeklyEl = document.getElementById('weekly-pnl');
            const weeklyPnl = data.weekly_pnl || 0;
            weeklyEl.textContent = (weeklyPnl >= 0 ? '+' : '') + fmt(weeklyPnl);
            weeklyEl.className = 'value ' + (weeklyPnl >= 0 ? 'positive' : 'negative');

            if (data.balance > 0 && dailyPnl !== 0) {
                const pct = (dailyPnl / data.balance * 100);
                document.getElementById('daily-pct').textContent =
                    (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
                document.getElementById('daily-pct').className =
                    'change ' + (pct >= 0 ? 'positive' : 'negative');
            }

            document.getElementById('win-rate').textContent =
                (data.win_rate || 0).toFixed(0) + '%';
            document.getElementById('sharpe').textContent =
                (data.sharpe || 0).toFixed(2);
            document.getElementById('drawdown').textContent =
                (data.drawdown || 0).toFixed(1) + '%';
            document.getElementById('total-trades').textContent =
                data.total_trades || 0;

            document.getElementById('timestamp').textContent =
                new Date().toLocaleTimeString();

            updatePositionsTable(data.open_positions || []);
            updateEquityChart(data.equity_history || []);
            updateStrategies(data.strategies || {});
            updateHealthTable(data.data_health || {});
        }

        function updatePositionsTable(positions) {
            const tbody = document.getElementById('positions-tbody');
            const noPos = document.getElementById('no-positions');
            tbody.innerHTML = '';

            if (!positions || positions.length === 0) {
                noPos.style.display = 'block';
                return;
            }
            noPos.style.display = 'none';

            positions.forEach(pos => {
                const row = tbody.insertRow();
                const pnl = pos.pnl || 0;
                const entry = typeof pos.entry === 'number' ? pos.entry.toFixed(5) : pos.entry;
                const current = typeof pos.current === 'number' ? pos.current.toFixed(5) : (pos.current || '-');
                row.innerHTML = `
                    <td>${pos.symbol}</td>
                    <td class="${pos.direction === 'BUY' || pos.direction === 'LONG' ? 'positive' : 'negative'}">
                        ${pos.direction}
                    </td>
                    <td>${pos.size}</td>
                    <td>${entry}</td>
                    <td>${current}</td>
                    <td class="${pnl >= 0 ? 'positive' : 'negative'}">
                        ${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                    </td>
                    <td>${pos.strategy || '-'}</td>
                `;
            });
        }

        function updateEquityChart(history) {
            if (!history || history.length === 0) return;

            const times = history.map(h => h.time);
            const values = history.map(h => h.equity);

            const trace = {
                x: times,
                y: values,
                type: 'scatter',
                mode: 'lines',
                line: { color: '#667eea', width: 2 },
                fill: 'tozeroy',
                fillcolor: 'rgba(102, 126, 234, 0.1)'
            };

            const layout = {
                paper_bgcolor: '#1a1f3a',
                plot_bgcolor: '#1a1f3a',
                font: { color: '#fff' },
                margin: { t: 10, r: 30, b: 40, l: 70 },
                xaxis: {
                    gridcolor: '#2d3348',
                    showgrid: true
                },
                yaxis: {
                    gridcolor: '#2d3348',
                    showgrid: true,
                    title: 'Equity'
                }
            };

            if (!chartInitialized) {
                Plotly.newPlot('equity-chart', [trace], layout, {responsive: true});
                chartInitialized = true;
            } else {
                Plotly.react('equity-chart', [trace], layout);
            }
        }

        function updateHealthTable(health) {
            const tbody = document.getElementById('health-tbody');
            const noHealth = document.getElementById('no-health');
            tbody.innerHTML = '';

            const sources = health.sources || {};
            if (Object.keys(sources).length === 0) {
                noHealth.style.display = 'block';
                return;
            }
            noHealth.style.display = 'none';

            for (const [name, info] of Object.entries(sources)) {
                const row = tbody.insertRow();
                const statusColor = info.status === 'healthy' ? '#4ade80' :
                                    info.status === 'degraded' ? '#fbbf24' : '#f87171';
                row.innerHTML = `
                    <td>${name}</td>
                    <td style="color:${statusColor}; font-weight:bold;">${(info.status || 'unknown').toUpperCase()}</td>
                    <td>${(info.latency_ms || 0).toFixed(0)} ms</td>
                    <td>${(info.uptime_24h || 0).toFixed(1)}%</td>
                `;
            }
        }

        function updateStrategies(strategies) {
            const grid = document.getElementById('strategies-grid');
            if (!strategies || Object.keys(strategies).length === 0) {
                grid.innerHTML = '<div class="no-positions">No strategy data yet</div>';
                return;
            }

            grid.innerHTML = '';
            for (const [name, stats] of Object.entries(strategies)) {
                const pnl = stats.pnl || 0;
                const card = document.createElement('div');
                card.className = 'strategy-card';
                card.innerHTML = `
                    <h4>${name}</h4>
                    <div class="stat">Trades: ${stats.trades || 0}</div>
                    <div class="stat">Win Rate: ${(stats.win_rate || 0).toFixed(0)}%</div>
                    <div class="stat ${pnl >= 0 ? 'positive' : 'negative'}">
                        P&L: ${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                    </div>
                `;
                grid.appendChild(card);
            }
        }
    </script>
</body>
</html>
        '''
