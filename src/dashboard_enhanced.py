"""
Enhanced Dashboard v2 - Institutional grade monitoring.
Inclui Capital Scaling, Projeções e Métricas de Estratégia.
"""

import json
import threading
from datetime import datetime
from typing import Optional, List, Dict
from src.analytics.performance_tracker import PerformanceTracker


class EnhancedDashboard:
    def __init__(self, port=8765):
        self.port = port
        self._lock = threading.Lock()
        self._broadcast_callback = None
        self.tracker = PerformanceTracker()
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
            'strategies': [],
            'equity_history': [],
            'capital_scaling': {},
            'projections': {},
            'realtime': {},
            'data_health': {},
        }

    def set_broadcast_callback(self, callback):
        self._broadcast_callback = callback

    def update_metrics(self, data: dict):
        with self._lock:
            # Atualizar tracker se houver dados novos
            if 'balance' in data or 'equity' in data:
                self.tracker.update_data(
                    data.get('balance', self.metrics['balance']),
                    data.get('equity', self.metrics['equity']),
                    data.get('trades', [])
                )
                
            self.metrics.update(data)
            
            # Recalcular métricas avançadas
            self.metrics['capital_scaling'] = self.tracker.get_capital_scaling_progress()
            self.metrics['projections'] = self.tracker.get_projections()
            self.metrics['strategies'] = self.tracker.get_strategy_performance()
            self.metrics['realtime'] = self.tracker.get_realtime_tracking(self.metrics['open_positions'])

        if self._broadcast_callback:
            self._broadcast_callback(json.dumps(self.metrics))

    def get_html(self) -> str:
        return '''
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <title>Quantum Arbitrage | Institutional Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root {
            --bg-dark: #0a0e17;
            --bg-card: #141b2d;
            --primary: #4e73df;
            --secondary: #1cc88a;
            --accent: #f6c23e;
            --danger: #e74a3b;
            --text-main: #e2e8f0;
            --text-muted: #858796;
            --border: #2d3748;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg-dark);
            color: var(--text-main);
            padding: 20px;
            line-height: 1.5;
        }

        .container { max-width: 1400px; margin: 0 auto; }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding: 20px;
            background: linear-gradient(135deg, #1e3a8a 0%, #1e1b4b 100%);
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.1);
            color: #10b981;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            background: #10b981;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        .main-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 25px;
        }

        .card {
            background: var(--bg-card);
            padding: 20px;
            border-radius: 12px;
            border: 1px solid var(--border);
            transition: transform 0.2s;
        }

        .card:hover { transform: translateY(-2px); }

        .card-label {
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .card-value {
            font-size: 28px;
            font-weight: 800;
            color: #fff;
        }

        .card-sub {
            font-size: 13px;
            margin-top: 6px;
        }

        .positive { color: #10b981; }
        .negative { color: #ef4444; }

        /* Capital Scaling Panel */
        .scaling-panel {
            grid-column: span 2;
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        }

        .progress-container {
            margin-top: 15px;
        }

        .progress-bar-bg {
            height: 12px;
            background: #334155;
            border-radius: 6px;
            overflow: hidden;
            margin-bottom: 10px;
        }

        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #3b82f6 0%, #8b5cf6 100%);
            width: 0%;
            transition: width 1s ease-out;
        }

        .milestone-info {
            display: flex;
            justify-content: space-between;
            font-size: 13px;
            color: var(--text-muted);
        }

        /* Chart Sections */
        .charts-row {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            margin-bottom: 25px;
        }

        .chart-box {
            background: var(--bg-card);
            padding: 20px;
            border-radius: 12px;
            border: 1px solid var(--border);
        }

        .chart-title {
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
        }

        /* Tables */
        .table-container {
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }

        th {
            text-align: left;
            padding: 12px;
            border-bottom: 2px solid var(--border);
            color: var(--text-muted);
            font-weight: 600;
        }

        td {
            padding: 12px;
            border-bottom: 1px solid var(--border);
        }

        .strategy-tag {
            background: rgba(59, 130, 246, 0.1);
            color: #60a5fa;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }

        /* Widgets */
        .widget-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }

        .realtime-item {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }

        .projection-card {
            padding: 15px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            margin-bottom: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <div>
                <h1 style="font-size: 24px; font-weight: 800; letter-spacing: -0.025em;">
                    <i class="fas fa-microchip" style="margin-right: 10px; color: #60a5fa;"></i>
                    QUANTUM ARBITRAGE <span style="font-weight: 300; opacity: 0.7;">v6.2</span>
                </h1>
            </div>
            <div style="display: flex; gap: 20px; align-items: center;">
                <div id="live-clock" style="font-family: monospace; color: var(--text-muted);">00:00:00</div>
                <div class="status-badge">
                    <div class="status-dot"></div>
                    <span>SISTEMA ATIVO</span>
                </div>
            </div>
        </header>

        <!-- Main Stats -->
        <div class="main-grid">
            <div class="card">
                <div class="card-label"><i class="fas fa-wallet"></i> Saldo Total</div>
                <div class="card-value" id="balance">€0.00</div>
                <div class="card-sub positive" id="balance-change">+0.00% (24h)</div>
            </div>
            <div class="card">
                <div class="card-label"><i class="fas fa-chart-line"></i> Equity</div>
                <div class="card-value" id="equity">€0.00</div>
                <div class="card-sub" id="margin-usage" style="color: var(--text-muted);">Margin: €0.00</div>
            </div>
            <div class="card scaling-panel">
                <div class="card-label">
                    <i class="fas fa-trophy" style="color: var(--accent);"></i> 
                    Progresso Capital Scaling: <span id="current-milestone" style="color: #fff; margin-left: 5px;">Micro</span>
                </div>
                <div class="progress-container">
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" id="progress-fill" style="width: 0%"></div>
                    </div>
                    <div class="milestone-info">
                        <span id="milestone-start">€0</span>
                        <span id="progress-pct" style="font-weight: 800; color: #fff;">0%</span>
                        <span id="milestone-end">€500</span>
                    </div>
                    <div style="margin-top: 8px; font-size: 12px; text-align: center;">
                        <i class="fas fa-hourglass-half"></i> Estimativa: <span id="days-to-milestone" style="color: var(--accent);">--</span> dias para <span id="next-milestone-name">Iniciante</span>
                    </div>
                </div>
            </div>
        </div>

        <div class="main-grid">
            <div class="card">
                <div class="card-label">Daily P&L</div>
                <div class="card-value" id="daily-pnl">€0.00</div>
                <div class="card-sub" id="daily-pct">+0.00%</div>
            </div>
            <div class="card">
                <div class="card-label">Win Rate</div>
                <div class="card-value" id="win-rate">0%</div>
                <div class="card-sub" id="total-trades">0 trades realizados</div>
            </div>
            <div class="card">
                <div class="card-label">Sharpe Ratio</div>
                <div class="card-value" id="sharpe">0.00</div>
                <div class="card-sub" style="color: #10b981;">Estabilidade: Alta</div>
            </div>
            <div class="card">
                <div class="card-label">Max Drawdown</div>
                <div class="card-value negative" id="drawdown">-0.0%</div>
                <div class="card-sub" style="color: var(--text-muted);">Limit: -15.0%</div>
            </div>
        </div>

        <!-- Charts Row -->
        <div class="charts-row">
            <div class="chart-box">
                <div class="chart-title">
                    <span>CURVA DE EQUIDADE</span>
                    <div style="font-size: 12px;">
                        <span style="color: var(--primary);"><i class="fas fa-circle"></i> Live Equity</span>
                    </div>
                </div>
                <div id="equity-chart" style="height: 350px;"></div>
            </div>
            <div class="chart-box">
                <div class="chart-title">PROJEÇÃO 12 MESES</div>
                <div id="projection-content">
                    <div class="projection-card" style="border-left: 4px solid #3b82f6;">
                        <div style="font-size: 12px; color: var(--text-muted);">Conservador (15%/mês)</div>
                        <div style="font-size: 20px; font-weight: 700;" id="proj-cons-12">€0.00</div>
                        <div style="font-size: 11px;" id="proj-cons-pct" class="positive">+0%</div>
                    </div>
                    <div class="projection-card" style="border-left: 4px solid #8b5cf6;">
                        <div style="font-size: 12px; color: var(--text-muted);">Agressivo (25%/mês)</div>
                        <div style="font-size: 20px; font-weight: 700;" id="proj-aggr-12">€0.00</div>
                        <div style="font-size: 11px;" id="proj-aggr-pct" class="positive">+0%</div>
                    </div>
                    <div id="projection-chart" style="height: 150px; margin-top: 15px;"></div>
                </div>
            </div>
        </div>

        <!-- Second Row -->
        <div class="widget-grid">
            <!-- Strategy Win Rate -->
            <div class="chart-box">
                <div class="chart-title">WIN RATE POR ESTRATÉGIA</div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>Estratégia</th>
                                <th>Trades</th>
                                <th>Win %</th>
                                <th>Avg P/L</th>
                                <th>Sharpe</th>
                            </tr>
                        </thead>
                        <tbody id="strategy-tbody">
                            <!-- Injected by JS -->
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Real-time tracking -->
            <div class="chart-box">
                <div class="chart-title">TRACKING EM TEMPO REAL</div>
                <div id="realtime-content">
                    <div class="realtime-item">
                        <span><i class="fas fa-layer-group"></i> Posições Ativas</span>
                        <span id="active-count" style="font-weight: 700;">0</span>
                    </div>
                    <div class="realtime-item">
                        <span><i class="fas fa-pyramid"></i> Pyramiding Status</span>
                        <span id="pyramid-status" class="positive">Inativo</span>
                    </div>
                    <div class="realtime-item">
                        <span><i class="fas fa-shield-alt"></i> Trailing Stops</span>
                        <span id="trailing-count">0 ativos</span>
                    </div>
                    <div class="realtime-item" style="border-bottom: none;">
                        <span><i class="fas fa-signal"></i> Último Sinal</span>
                        <span id="last-signal" style="font-size: 11px; color: var(--text-muted);">Nenhum sinal hoje</span>
                    </div>
                    
                    <div style="margin-top: 20px; padding: 15px; background: rgba(255,193,7,0.05); border-radius: 8px; border: 1px solid rgba(255,193,7,0.2);">
                        <div style="font-size: 12px; color: var(--accent); font-weight: 700; margin-bottom: 5px;">LIVE SIGNALS (últimos 10min)</div>
                        <div id="live-signals-list" style="font-size: 12px; font-family: monospace;">
                            Nenhum sinal detectado...
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Open Positions -->
        <div class="chart-box" style="margin-top: 25px;">
            <div class="chart-title">POSIÇÕES ATIVAS</div>
            <div class="table-container">
                <table class="positions-table">
                    <thead>
                        <tr>
                            <th>Ativo</th>
                            <th>Direção</th>
                            <th>Lote</th>
                            <th>Entrada</th>
                            <th>Atual</th>
                            <th>P&L</th>
                            <th>Estratégia</th>
                        </tr>
                    </thead>
                    <tbody id="positions-tbody">
                    </tbody>
                </table>
                <div id="no-positions" style="text-align: center; padding: 30px; color: var(--text-muted); display: none;">
                    Nenhuma posição aberta no momento
                </div>
            </div>
        </div>
    </div>

    <script>
        const ws = new WebSocket('ws://' + window.location.host + '/ws');
        let chartInitialized = false;

        function updateClock() {
            document.getElementById('live-clock').textContent = new Date().toLocaleTimeString();
        }
        setInterval(updateClock, 1000);

        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            updateDashboard(data);
        };

        function fmt(val, digits = 2) {
            return (val || 0).toLocaleString('pt-BR', {minimumFractionDigits: digits, maximumFractionDigits: digits});
        }

        function updateDashboard(data) {
            // Stats Básicas
            document.getElementById('balance').textContent = '€' + fmt(data.balance);
            document.getElementById('equity').textContent = '€' + fmt(data.equity);
            
            const daily = data.daily_pnl || 0;
            const dailyEl = document.getElementById('daily-pnl');
            dailyEl.textContent = (daily >= 0 ? '+€' : '€') + fmt(daily);
            dailyEl.className = 'card-value ' + (daily >= 0 ? 'positive' : 'negative');
            
            if (data.balance > 0) {
                const pct = (daily / data.balance) * 100;
                document.getElementById('daily-pct').textContent = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
                document.getElementById('daily-pct').className = 'card-sub ' + (pct >= 0 ? 'positive' : 'negative');
            }

            document.getElementById('win-rate').textContent = (data.win_rate || 0).toFixed(1) + '%';
            document.getElementById('total-trades').textContent = (data.total_trades || 0) + ' trades realizados';
            document.getElementById('sharpe').textContent = (data.sharpe || 0).toFixed(2);
            document.getElementById('drawdown').textContent = (data.drawdown || 0).toFixed(1) + '%';

            // Capital Scaling
            if (data.capital_scaling) {
                const cs = data.capital_scaling;
                document.getElementById('current-milestone').textContent = cs.current_milestone;
                document.getElementById('progress-fill').style.width = cs.progress_to_next + '%';
                document.getElementById('progress-pct').textContent = cs.progress_to_next.toFixed(1) + '%';
                document.getElementById('milestone-end').textContent = '€' + cs.target;
                document.getElementById('days-to-milestone').textContent = cs.days_to_milestone;
                document.getElementById('next-milestone-name').textContent = cs.next_milestone;
            }

            // Projeções
            if (data.projections) {
                const p = data.projections;
                const cons12 = p.conservative[3]; // 12 meses
                const aggr12 = p.aggressive[3];
                
                document.getElementById('proj-cons-12').textContent = '€' + fmt(cons12.value);
                document.getElementById('proj-cons-pct').textContent = '+' + fmt(cons12.pct, 0) + '%';
                
                document.getElementById('proj-aggr-12').textContent = '€' + fmt(aggr12.value);
                document.getElementById('proj-aggr-pct').textContent = '+' + fmt(aggr12.pct, 0) + '%';
            }

            // Tabelas
            updateStrategyTable(data.strategies || []);
            updatePositionsTable(data.open_positions || []);
            updateRealtime(data.realtime || {});
            
            // Gráfico de Equidade
            updateEquityChart(data.equity_history || []);
        }

        function updateStrategyTable(strategies) {
            const tbody = document.getElementById('strategy-tbody');
            tbody.innerHTML = '';
            strategies.forEach(s => {
                const row = tbody.insertRow();
                row.innerHTML = `
                    <td><span class="strategy-tag">${s.name}</span></td>
                    <td>${s.trades}</td>
                    <td class="${s.win_rate >= 50 ? 'positive' : 'negative'}">${s.win_rate.toFixed(1)}%</td>
                    <td class="${s.avg_pnl >= 0 ? 'positive' : 'negative'}">€${s.avg_pnl.toFixed(2)}</td>
                    <td>${s.sharpe.toFixed(2)}</td>
                `;
            });
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

            positions.forEach(p => {
                const row = tbody.insertRow();
                const pnl = p.pnl || 0;
                row.innerHTML = `
                    <td style="font-weight:700;">${p.symbol}</td>
                    <td class="${p.direction === 'BUY' ? 'positive' : 'negative'}">${p.direction}</td>
                    <td>${p.size}</td>
                    <td>${p.entry.toFixed(5)}</td>
                    <td>${(p.current || p.entry).toFixed(5)}</td>
                    <td class="${pnl >= 0 ? 'positive' : 'negative'}" style="font-weight:700;">
                        ${pnl >= 0 ? '+' : ''}€${pnl.toFixed(2)}
                    </td>
                    <td><span class="strategy-tag">${p.strategy || '-'}</span></td>
                `;
            });
        }

        function updateRealtime(rt) {
            document.getElementById('active-count').textContent = rt.active_positions_count || 0;
            document.getElementById('pyramid-status').textContent = rt.pyramiding || 'Inativo';
            document.getElementById('trailing-count').textContent = rt.trailing_stops || '0 ativos';
        }

        function updateEquityChart(history) {
            if (!history || history.length === 0) return;
            const times = history.map(h => h.time || h.timestamp);
            const values = history.map(h => h.equity);

            const trace = {
                x: times,
                y: values,
                type: 'scatter',
                mode: 'lines',
                line: { color: '#3b82f6', width: 3, shape: 'spline' },
                fill: 'tozeroy',
                fillcolor: 'rgba(59, 130, 246, 0.1)'
            };

            const layout = {
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#858796', family: 'Inter' },
                margin: { t: 0, r: 0, b: 30, l: 40 },
                xaxis: { showgrid: false, zeroline: false },
                yaxis: { gridcolor: '#2d3748', zeroline: false }
            };

            if (!chartInitialized) {
                Plotly.newPlot('equity-chart', [trace], layout, {displayModeBar: false});
                chartInitialized = true;
            } else {
                Plotly.react('equity-chart', [trace], layout);
            }
        }
    </script>
</body>
</html>
'''
