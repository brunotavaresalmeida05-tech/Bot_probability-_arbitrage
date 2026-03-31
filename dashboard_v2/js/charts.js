/**
 * charts.js - Chart.js equity curve initialisation and update
 */

let equityChart = null;

function initEquityChart() {
    const ctx = document.getElementById('equity-chart');
    if (!ctx) return;

    equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'P&L Acumulado (€)',
                data: [],
                borderColor: '#58a6ff',
                backgroundColor: 'rgba(88,166,255,0.08)',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                fill: true,
                tension: 0.4,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#21262d',
                    borderColor: '#30363d',
                    borderWidth: 1,
                    titleColor: '#8b949e',
                    bodyColor: '#e6edf3',
                    callbacks: {
                        label: ctx => `  €${ctx.parsed.y.toFixed(2)}`,
                    },
                },
            },
            scales: {
                x: {
                    ticks: {
                        color: '#8b949e',
                        maxTicksLimit: 8,
                        maxRotation: 0,
                    },
                    grid: { color: '#21262d' },
                },
                y: {
                    ticks: {
                        color: '#8b949e',
                        callback: v => `€${v.toFixed(2)}`,
                    },
                    grid: { color: '#21262d' },
                },
            },
        },
    });
}

function updateEquityChart(equityCurve) {
    if (!equityChart || !equityCurve || equityCurve.length === 0) return;

    const labels = equityCurve.map(r => {
        const ts = r.close_time || r.timestamp || '';
        if (!ts) return '';
        try {
            const d = new Date(ts);
            return d.toLocaleDateString('pt-PT', { month: 'short', day: 'numeric' });
        } catch { return ts.slice(0, 10); }
    });

    const values = equityCurve.map(r =>
        parseFloat(r.cumulative_profit || r.profit || 0)
    );

    // Colour line green if positive, red if negative
    const lastVal = values[values.length - 1] || 0;
    const colour  = lastVal >= 0 ? '#3fb950' : '#f85149';
    equityChart.data.datasets[0].borderColor = colour;
    equityChart.data.datasets[0].backgroundColor = colour + '12';
    equityChart.data.labels = labels;
    equityChart.data.datasets[0].data = values;
    equityChart.update('none');
}

document.addEventListener('DOMContentLoaded', initEquityChart);
