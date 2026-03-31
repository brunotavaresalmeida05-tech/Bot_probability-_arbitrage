/**
 * app.js - Main dashboard application
 * Handles navigation, data rendering, and WebSocket event processing
 */

// ─── Navigation ──────────────────────────────────────────────

document.querySelectorAll('.menu-item').forEach(item => {
    item.addEventListener('click', e => {
        e.preventDefault();
        const page = item.dataset.page;

        document.querySelectorAll('.menu-item').forEach(m => m.classList.remove('active'));
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));

        item.classList.add('active');
        const pageEl = document.getElementById('page-' + page);
        if (pageEl) pageEl.classList.add('active');

        // Load history/strategy stats on first visit
        if (page === 'history') loadHistoryData();
    });
});

// ─── Formatters ───────────────────────────────────────────────

const fmt = {
    currency: v => `€${parseFloat(v || 0).toFixed(2)}`,
    pct:      v => `${parseFloat(v || 0).toFixed(1)}%`,
    lots:     v => parseFloat(v || 0).toFixed(2),
    price:    v => parseFloat(v || 0).toFixed(5),
    time:     ts => {
        if (!ts) return '—';
        try {
            return new Date(ts).toLocaleString('pt-PT', {
                month: 'short', day: 'numeric',
                hour: '2-digit', minute: '2-digit',
            });
        } catch { return ts; }
    },
};

function pnlClass(v) {
    return parseFloat(v) >= 0 ? 'pnl-pos' : 'pnl-neg';
}

function wrClass(v) {
    v = parseFloat(v);
    if (v >= 55) return 'wr-good';
    if (v >= 45) return 'wr-ok';
    return 'wr-bad';
}

// ─── KPI Updates ─────────────────────────────────────────────

function updateKPIs(state) {
    const acc   = state.account || {};
    const stats = state.stats   || {};

    setText('kpi-balance',  fmt.currency(acc.balance));
    setText('kpi-equity',   fmt.currency(acc.equity));
    setText('kpi-positions', (state.positions || []).length);
    setText('kpi-winrate',  fmt.pct(stats.win_rate));
    setText('kpi-profit',   fmt.currency(stats.total_profit));
    setText('kpi-trades',   stats.total_trades || 0);

    // Colour profit
    const profitEl = document.getElementById('kpi-profit');
    if (profitEl) profitEl.className = 'kpi-value ' + pnlClass(stats.total_profit);
}

// ─── Milestone ───────────────────────────────────────────────

const MILESTONE_TARGET = 500;

function updateMilestone(balance) {
    const initial  = 464.63;
    const target   = MILESTONE_TARGET;
    const progress = Math.min(((balance - initial) / (target - initial)) * 100, 100);
    const growthPct = ((balance - initial) / initial) * 100;

    setText('milestone-current', fmt.currency(balance));
    setText('milestone-target',  fmt.currency(target));
    setText('milestone-pct',     fmt.pct(Math.max(0, progress)));
    setText('milestone-label',   `€${target} (Growth: ${growthPct.toFixed(1)}%)`);

    const bar = document.getElementById('milestone-bar');
    if (bar) bar.style.width = Math.max(0, progress) + '%';
}

// ─── Positions Table ──────────────────────────────────────────

function updatePositions(positions) {
    const tbody  = document.getElementById('positions-body');
    const badge  = document.getElementById('pos-count');
    if (!tbody) return;

    setText('pos-count', positions.length);

    if (positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-row">Sem posições abertas</td></tr>';
        return;
    }

    tbody.innerHTML = positions.map(p => {
        const dirClass = p.type === 'BUY' ? 'tag-buy' : 'tag-sell';
        return `<tr>
            <td><strong>${p.symbol}</strong></td>
            <td><span class="${dirClass}">${p.type}</span></td>
            <td>${fmt.lots(p.volume)}</td>
            <td>${fmt.price(p.price_open)}</td>
            <td>${fmt.price(p.price_current)}</td>
            <td class="${pnlClass(p.profit)}">${fmt.currency(p.profit)}</td>
            <td class="${pnlClass(p.swap)}">${fmt.currency(p.swap)}</td>
        </tr>`;
    }).join('');
}

// ─── Open P&L Summary ────────────────────────────────────────

function updateOpenPnL(state) {
    const acc = state.account || {};
    const positions = state.positions || [];
    const totalPnL = positions.reduce((s, p) => s + (p.profit || 0), 0);

    const pnlEl = document.getElementById('open-pnl');
    if (pnlEl) {
        pnlEl.textContent = fmt.currency(totalPnL);
        pnlEl.className = 'kpi-value ' + pnlClass(totalPnL);
    }
    setText('free-margin',  fmt.currency(acc.free_margin));
    setText('margin-level', fmt.pct(acc.margin_level));
}

// ─── Signals ─────────────────────────────────────────────────

function updateSignals(signals) {
    const container = document.getElementById('signals-container');
    const badge     = document.getElementById('signals-count');
    if (!container) return;

    setText('signals-count', signals.length);

    if (!signals || signals.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-satellite-dish"></i>
                <p>Sem sinais activos</p>
            </div>`;
        return;
    }

    container.innerHTML = signals.map(s => {
        const dir  = (s.signal || s.direction || '').toUpperCase();
        const cls  = dir === 'BUY' ? 'buy' : 'sell';
        const conf = s.confidence ? `${(s.confidence * 100).toFixed(0)}%` : '';
        return `<div class="signal-card ${cls}">
            <div>
                <div class="signal-sym">${s.symbol || '—'}</div>
                <div class="signal-meta">${s.strategy || 'Z-Score'}</div>
            </div>
            <div style="text-align:right">
                <div class="signal-dir ${cls}">${dir}</div>
                ${conf ? `<div class="signal-conf">Conf: ${conf}</div>` : ''}
            </div>
        </div>`;
    }).join('');
}

// ─── Spreads ─────────────────────────────────────────────────

const MAX_SPREAD = { default: 20, BTC: 500, ETH: 200, XRP: 50, SOL: 50, GOLD: 30, SILVER: 30 };

function getMaxSpread(sym) {
    for (const [k, v] of Object.entries(MAX_SPREAD)) {
        if (sym.includes(k)) return v;
    }
    return MAX_SPREAD.default;
}

function updateSpreads(spreads) {
    const grid = document.getElementById('spreads-grid');
    if (!grid || !spreads) return;

    const entries = Object.entries(spreads);
    if (entries.length === 0) {
        grid.innerHTML = '<p style="color:var(--text-muted);padding:16px">Sem dados de spread</p>';
        return;
    }

    grid.innerHTML = entries.map(([sym, val]) => {
        const max = getMaxSpread(sym);
        const cls = val <= max ? 'ok' : 'high';
        return `<div class="spread-item">
            <div class="spread-sym">${sym}</div>
            <div class="spread-val ${cls}">${parseFloat(val).toFixed(1)}</div>
        </div>`;
    }).join('');
}

// ─── History & Strategy Stats (loaded once) ───────────────────

let historyLoaded = false;

async function loadHistoryData() {
    if (historyLoaded) return;

    // Strategy stats
    try {
        const res  = await fetch('/api/strategy_stats');
        const data = await res.json();
        const tbody = document.getElementById('strategy-body');
        if (tbody) {
            if (data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-row">Sem dados</td></tr>';
            } else {
                tbody.innerHTML = data.map(r => {
                    const wr = r.total > 0 ? (r.wins / r.total * 100).toFixed(1) : '0';
                    return `<tr>
                        <td><strong>${r.strategy || '—'}</strong></td>
                        <td>${r.total}</td>
                        <td>${r.wins}</td>
                        <td class="${wrClass(wr)}">${wr}%</td>
                        <td class="${pnlClass(r.total_profit)}">${fmt.currency(r.total_profit)}</td>
                        <td class="${pnlClass(r.avg_profit)}">${fmt.currency(r.avg_profit)}</td>
                    </tr>`;
                }).join('');
            }
        }
    } catch (e) { console.warn('Strategy stats error:', e); }

    // Trade history
    try {
        const res  = await fetch('/api/history?limit=50');
        const data = await res.json();
        const tbody = document.getElementById('history-body');
        if (tbody) {
            if (data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-row">Sem trades fechados</td></tr>';
            } else {
                tbody.innerHTML = data.map(r => {
                    const dir = (r.direction || '').toUpperCase();
                    const cls = dir === 'BUY' ? 'tag-buy' : 'tag-sell';
                    return `<tr>
                        <td><strong>${r.symbol || '—'}</strong></td>
                        <td><span class="${cls}">${dir || '—'}</span></td>
                        <td>${fmt.lots(r.lots)}</td>
                        <td>${r.strategy || '—'}</td>
                        <td class="${pnlClass(r.profit)}">${fmt.currency(r.profit)}</td>
                        <td>${fmt.time(r.close_time)}</td>
                    </tr>`;
                }).join('');
            }
        }
    } catch (e) { console.warn('History error:', e); }

    historyLoaded = true;
}

// ─── Timestamp ───────────────────────────────────────────────

function updateTimestamp(ts) {
    const ids = ['last-update', 'portfolio-update', 'exec-update'];
    const label = ts ? fmt.time(ts) : '—';
    ids.forEach(id => setText(id, 'Actualizado: ' + label));
}

// ─── Utility ─────────────────────────────────────────────────

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

// ─── Main data handler ────────────────────────────────────────

window.addEventListener('botdata', evt => {
    const state = evt.detail;
    if (!state) return;

    updateTimestamp(state.timestamp);
    updateKPIs(state);
    updateMilestone(state.account?.balance || 0);
    updatePositions(state.positions || []);
    updateOpenPnL(state);
    updateSignals(state.signals || []);
    updateSpreads(state.spreads || {});
    updateEquityChart(state.equity_curve || []);
});

// ─── Initial REST fetch (before WebSocket connects) ───────────

async function initialFetch() {
    try {
        const [balRes, posRes, eqRes, statsRes] = await Promise.all([
            fetch('/api/balance'),
            fetch('/api/positions'),
            fetch('/api/equity'),
            fetch('/api/stats'),
        ]);
        const acc   = await balRes.json();
        const pos   = await posRes.json();
        const eq    = await eqRes.json();
        const stats = await statsRes.json();

        const fakeState = {
            account: acc,
            positions: pos,
            signals: [],
            spreads: {},
            equity_curve: eq,
            stats,
        };
        updateKPIs(fakeState);
        updateMilestone(acc.balance || 0);
        updatePositions(pos);
        updateOpenPnL(fakeState);
        updateEquityChart(eq);
    } catch (e) {
        console.warn('Initial fetch failed (bot may not be running yet):', e.message);
    }
}

document.addEventListener('DOMContentLoaded', initialFetch);
