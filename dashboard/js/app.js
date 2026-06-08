/* AlphaSystem V9 Dashboard */

var V9 = {
    token: localStorage.getItem('v9_token') || '',
    ws: null,
    pollTimer: null,
    data: {}
};

/* ── INIT ── */
document.addEventListener('DOMContentLoaded', function () {
    startClock();
    if (V9.token) {
        showDashboard();
        fetchAndRender();
        startPolling();
        connectWS();
    } else {
        showLogin();
    }

    document.getElementById('login-btn').addEventListener('click', doLogin);
    document.getElementById('login-pass').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') doLogin();
    });
});

/* ── CLOCK ── */
function startClock() {
    function tick() {
        var d = new Date();
        var h = String(d.getUTCHours()).padStart(2,'0');
        var m = String(d.getUTCMinutes()).padStart(2,'0');
        var s = String(d.getUTCSeconds()).padStart(2,'0');
        document.getElementById('clock').textContent = h + ':' + m + ':' + s + ' UTC';
    }
    tick();
    setInterval(tick, 1000);
}

/* ── AUTH ── */
function showLogin() {
    document.getElementById('login-overlay').classList.remove('hidden');
    document.getElementById('main-grid').style.visibility = 'hidden';
}
function showDashboard() {
    document.getElementById('login-overlay').classList.add('hidden');
    document.getElementById('main-grid').style.visibility = 'visible';
}

function doLogin() {
    var user = document.getElementById('login-user').value.trim();
    var pass = document.getElementById('login-pass').value;
    var err  = document.getElementById('login-error');
    err.classList.add('hidden');

    fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: user, password: pass })
    })
    .then(function (r) { return r.json(); })
    .then(function (d) {
        if (d.access_token) {
            V9.token = d.access_token;
            localStorage.setItem('v9_token', V9.token);
            showDashboard();
            fetchAndRender();
            startPolling();
            connectWS();
        } else {
            err.classList.remove('hidden');
        }
    })
    .catch(function () { err.classList.remove('hidden'); });
}

/* ── FETCH ── */
function apiFetch(path) {
    return fetch(path, {
        headers: { 'Authorization': 'Bearer ' + V9.token }
    }).then(function (r) {
        if (r.status === 401) { V9.token = ''; localStorage.removeItem('v9_token'); showLogin(); }
        return r.json();
    });
}

function fetchAndRender() {
    apiFetch('/api/v9/state').then(function (d) {
        if (d && d.ts) { V9.data = d; render(d); }
    }).catch(function () {});
}

function startPolling() {
    if (V9.pollTimer) clearInterval(V9.pollTimer);
    V9.pollTimer = setInterval(fetchAndRender, 5000);
}

/* ── WEBSOCKET ── */
function connectWS() {
    if (V9.ws) { try { V9.ws.close(); } catch(e) {} }
    var proto = location.protocol === 'https:' ? 'wss' : 'ws';
    var url   = proto + '://' + location.host + '/ws?token=' + V9.token;
    V9.ws = new WebSocket(url);

    V9.ws.onopen = function () {
        setEl('ws-dot', 'WS [OK]');
        document.getElementById('ws-dot').classList.add('connected');
        document.getElementById('ws-dot').classList.remove('error');
    };
    V9.ws.onmessage = function (e) {
        try {
            var d = JSON.parse(e.data);
            if (d && d.ts) { V9.data = d; render(d); }
        } catch(ex) {}
    };
    V9.ws.onclose = function () {
        setEl('ws-dot', 'WS');
        document.getElementById('ws-dot').classList.remove('connected');
        setTimeout(connectWS, 5000);
    };
    V9.ws.onerror = function () {
        document.getElementById('ws-dot').classList.add('error');
    };
}

/* ── RENDER ── */
function render(d) {
    renderTopbar(d);
    renderRegime(d);
    renderBenchmark(d);
    renderRisk(d);
    renderSession(d);
    renderSignals(d);
    renderScore(d);
    renderScanner(d);
    renderPrep(d);
}

/* TOPBAR */
function renderTopbar(d) {
    var dry = d.dry_run !== false;
    var modeEl = document.getElementById('tag-mode');
    modeEl.textContent = dry ? 'DRY RUN' : 'LIVE';
    modeEl.className   = 'tag ' + (dry ? 'tag-dry' : 'tag-live');

    var sess = (d.session || '--').toUpperCase();
    setEl('tag-session', sess);
    setEl('cycle-count', d.cycle_count || '--');

    var acc = d.account || {};
    setEl('kpi-balance',   acc.balance   != null ? fmt2(acc.balance)   + ' ' + (acc.currency || '') : '--');
    setEl('kpi-equity',    acc.equity    != null ? fmt2(acc.equity)    + ' ' + (acc.currency || '') : '--');
    setEl('kpi-pnl',       acc.profit    != null ? fmt2(acc.profit)    + ' ' + (acc.currency || '') : '--');
    setEl('kpi-positions', (d.risk || {}).open_positions || 0);
}

/* REGIME */
function renderRegime(d) {
    var m = d.macro || {};
    var sc = (d.scenario || 'indefinido').toLowerCase().replace('tendencia_', '');

    var badge = document.getElementById('scenario-badge');
    badge.textContent = (d.scenario || '--').toUpperCase().replace('TENDENCIA_', '');
    badge.className   = 'scenario-badge ' + sc;

    setRegimeItem('r-vix',    m.vix,       '', m.vix_regime);
    setRegimeItem('r-dxy',    m.dxy,       '', m.dxy_regime);
    setRegimeItem('r-curve',  m.spread_10y_2y != null ? m.spread_10y_2y.toFixed(2) + '%' : '--', '', m.curve_regime);
    setRegimeItem('r-news',   m.news_score || '--', '', m.news_score);
    setRegimeItem('r-global', m.global_regime || '--', '', m.global_regime);

    var lm = m.lot_multiplier;
    var lmTag = lm >= 1.0 ? 'ok' : (lm >= 0.75 ? 'warn' : 'danger');
    setRegimeItem('r-lotmult', lm != null ? 'x' + lm : '--', '', lmTag);

    function setRegimeItem(id, val, unit, tag) {
        setEl(id, val != null ? val + (unit || '') : '--');
        var tagEl = document.getElementById(id + '-tag');
        if (tagEl) {
            tagEl.textContent  = tag || '';
            tagEl.className    = 'ri-tag ' + sentimentClass(tag);
        }
    }
}

function sentimentClass(v) {
    if (!v) return '';
    var s = String(v).toLowerCase();
    if (s === 'bullish' || s === 'normal' || s === 'risk_on' || s === 'steep' || s === 'ok') return 'ok';
    if (s === 'bearish' || s === 'kill'   || s === 'risk_off' || s === 'panic' || s === 'danger') return 'danger';
    return 'warn';
}

/* BENCHMARK */
function renderBenchmark(d) {
    var b = d.benchmark || {};

    var ros = b.risk_on_score;
    var rosEl = document.getElementById('b-riskon');
    if (rosEl) {
        rosEl.textContent = ros != null ? ros.toFixed(2) : '--';
        rosEl.className   = 'bench-value ' + (ros > 0 ? 'positive' : ros < 0 ? 'negative' : 'neutral');
    }

    var td = b.treasury_demand;
    var tdEl = document.getElementById('b-treasury');
    if (tdEl) {
        tdEl.textContent = td != null ? td.toFixed(2) : '--';
        tdEl.className   = 'bench-value ' + (td > 0 ? 'positive' : td < 0 ? 'negative' : 'neutral');
    }

    setEl('b-gold-signal', b.gold_signal || '--');
    setEl('b-carry', b.carry_trade_active ? '[ACTIVO]' : '[INACTIVO]');

    var levels = b.key_levels || {};
    var html = '';
    Object.keys(levels).slice(0, 6).forEach(function (sym) {
        var lv = levels[sym];
        var chg = lv.change_pct;
        var cls = chg > 0 ? 'positive' : chg < 0 ? 'negative' : '';
        var sign = chg > 0 ? '+' : '';
        html += '<div class="bench-level-row">' +
            '<span>' + sym + '</span>' +
            '<span class="' + cls + '">' + fmt2(lv.last) + ' (' + sign + chg.toFixed(2) + '%)</span>' +
        '</div>';
    });
    setHtml('bench-levels', html);
}

/* RISK */
function renderRisk(d) {
    var r = d.risk || {};

    setEl('rk-tier', r.tier || '--');

    var bEl = document.getElementById('rk-blocked');
    if (bEl) {
        bEl.textContent = r.blocked ? '[ACTIVO]' : '[OK]';
        bEl.className   = 'rk-value ' + (r.blocked ? 'danger' : 'ok');
    }

    setEl('rk-positions', r.open_positions || 0);
    setEl('rk-trades',    r.daily_trades   || 0);

    var pnlEl = document.getElementById('rk-pnl');
    if (pnlEl) {
        var pnl = r.daily_pnl || 0;
        pnlEl.textContent = fmt2(pnl);
        pnlEl.className   = 'rk-value ' + (pnl > 0 ? 'ok' : pnl < 0 ? 'danger' : '');
    }

    var lm = r.lot_multiplier;
    setEl('rk-lotmult', lm != null ? 'x' + lm : '--');
}

/* SESSION */
function renderSession(d) {
    setEl('se-session',  (d.session || '--').toUpperCase());

    var trEl = document.getElementById('se-tradeable');
    if (trEl) {
        trEl.textContent = d.tradeable ? '[SIM]' : '[NAO]';
        trEl.className   = 'se-value ' + (d.tradeable ? 'ok' : 'warn');
    }

    var macro = d.macro || {};
    var bkEl = document.getElementById('se-blackout');
    if (bkEl) {
        var bk = macro.high_impact_next_30m;
        bkEl.textContent = bk ? '[SIM - BLACKOUT]' : '[NAO]';
        bkEl.className   = 'se-value ' + (bk ? 'danger' : 'ok');
    }

    setEl('se-cycle', d.cycle_count || '--');
    setEl('se-ts',    d.ts ? d.ts.slice(0,19).replace('T', ' ') + ' UTC' : '--');
}

/* SIGNALS */
function renderSignals(d) {
    var sigs = d.signals || [];
    var countEl = document.getElementById('signal-count');
    if (countEl) countEl.textContent = '[' + sigs.length + ']';

    var feed = document.getElementById('signals-feed');
    if (!feed) return;

    if (!sigs.length) {
        var hint = (d.scenario || 'indefinido').toUpperCase();
        feed.innerHTML = '<p class="empty-state">Sem sinais. Scenario: ' + hint + '</p>';
        return;
    }

    var html = '';
    sigs.forEach(function (sig) {
        var dir = (sig.signal || sig.direction || 'HOLD').toLowerCase();
        var sym = sig.symbol || '';
        var score = sig.score != null ? sig.score.toFixed(3) : '';
        var decision = sig.decision || '';
        var rationale = sig.rationale || [];
        var session = sig.session || '';

        html += '<div class="signal-card ' + dir + '">';
        html += '<div class="signal-header">';
        html += '<span class="signal-symbol">' + sym + '</span>';
        html += '<span class="signal-dir ' + dir + '">[' + dir.toUpperCase() + ']</span>';
        if (score) html += '<span class="signal-score">score ' + score + '</span>';
        if (decision) html += '<span class="signal-session">' + decision.toUpperCase() + '</span>';
        if (session) html += '<span class="signal-session">' + session + '</span>';
        html += '</div>';

        if (rationale.length) {
            html += '<div class="signal-rationale">';
            rationale.forEach(function (r) {
                var cls = r.startsWith('[+]') ? 'ok' : r.startsWith('[-]') ? 'fail' : '';
                html += '<span class="rat-item ' + cls + '">' + r + '</span>';
            });
            html += '</div>';
        }
        html += '</div>';
    });
    feed.innerHTML = html;
}

/* SCORE */
function renderScore(d) {
    var sigs = d.signals || [];
    var panel = document.getElementById('score-panel');
    if (!panel) return;

    var scoreSigs = sigs.filter(function (s) { return s.total_score != null; });
    if (!scoreSigs.length) {
        panel.innerHTML = '<p class="empty-state">Score por simbolo disponivel quando houver sinais activos com TotalScore calculado.</p>';
        return;
    }

    var html = '';
    scoreSigs.forEach(function (sig) {
        var sym  = sig.symbol || '';
        var ts   = sig.total_score || 0;
        var dec  = sig.decision || 'block';
        var mcs  = sig.mcs_n  || 0;
        var bcs  = sig.bcs_n  || 0;
        var hcs  = sig.hcs_n  || 0;
        var ves  = sig.ves    || 0;
        var es   = sig.es     || 0;
        var cs   = sig.cs     || 0;
        var rs   = sig.rs     || 0;

        html += '<div class="score-symbol-block">';
        html += '<div class="score-sym-header">';
        html += '<span class="score-sym-name">' + sym + '</span>';
        html += '<span class="score-total ' + dec + '">' + ts.toFixed(3) + ' [' + dec.toUpperCase() + ']</span>';
        html += '</div>';
        html += '<div class="score-bars">';
        html += scoreBar('MCS', mcs, 'mcs');
        html += scoreBar('BCS', bcs, 'bcs');
        html += scoreBar('HCS', hcs, 'hcs');
        html += scoreBar('VES', ves, 'ves');
        html += scoreBar('ES',  es,  'es');
        html += scoreBar('CS',  cs,  'cs');
        html += scoreBar('RS',  rs,  'rs');
        html += '</div></div>';
    });
    panel.innerHTML = html;
}

function scoreBar(label, val, cls) {
    var pct = Math.round(Math.min(1, Math.max(0, val)) * 100);
    return '<div class="score-bar-row">' +
        '<span class="score-bar-label">' + label + '</span>' +
        '<div class="score-bar-track"><div class="score-bar-fill ' + cls + '" style="width:' + pct + '%"></div></div>' +
        '<span class="score-bar-num">' + val.toFixed(2) + '</span>' +
    '</div>';
}

/* PREP */
function renderPrep(d) {
    var prep = d.last_prep || {};
    var panel = document.getElementById('prep-panel');
    if (!panel || !Object.keys(prep).length) return;

    var steps = [
        { label: 'Sessao',     val: (prep.session || '--').toUpperCase() },
        { label: 'Noticias',   val: prep.step1_news || '--',  cls: sentimentCls(prep.step1_news) },
        { label: 'Scenario',   val: (prep.step5_scenario || {}).verdict || '--', cls: scenarioCls((prep.step5_scenario || {}).verdict) },
        { label: 'VIX',        val: ((prep.step2_indices || {}).vix || {}).value || '--' },
        { label: 'DXY regime', val: ((prep.step2_indices || {}).dxy || {}).regime || '--' },
        { label: 'Eventos',    val: ((prep.step3_agenda || {}).events_count || 0) + ' hoje' },
    ];

    var html = '';
    steps.forEach(function (s) {
        html += '<div class="prep-step">';
        html += '<span class="prep-step-label">' + s.label + '</span>';
        html += '<span class="prep-step-value ' + (s.cls || '') + '">' + s.val + '</span>';
        html += '</div>';
    });
    panel.innerHTML = html;
}

function sentimentCls(v) {
    if (!v) return '';
    var s = String(v).toLowerCase();
    if (s === 'bullish') return 'ok';
    if (s === 'bearish') return 'bad';
    return 'warn';
}
function scenarioCls(v) {
    if (!v) return '';
    var s = String(v).toLowerCase();
    if (s.includes('alta'))    return 'ok';
    if (s.includes('baixa'))   return 'bad';
    if (s.includes('bloq'))    return 'bad';
    return 'warn';
}

/* SCANNER */
function renderScanner(d) {
    var sm = d.scanner_metrics;
    if (!sm || !sm.totals) return;

    var t = sm.totals;
    var cycles = sm.cycles_observed || 0;
    var window_sz = sm.window_size || 50;

    setEl('scanner-window', '[ ' + cycles + '/' + window_sz + ' ciclos ]');

    // Alertas badge
    var alerts = sm.alerts || [];
    var badge = document.getElementById('scanner-alerts-badge');
    if (badge) {
        var hasRed = alerts.some(function(a) { return a.level === 'red'; });
        var hasYellow = alerts.some(function(a) { return a.level === 'yellow'; });
        if (hasRed) {
            badge.textContent = '[ALERTA]'; badge.className = 'scanner-alerts-badge red';
        } else if (hasYellow) {
            badge.textContent = '[ATENCAO]'; badge.className = 'scanner-alerts-badge yellow';
        } else {
            badge.textContent = ''; badge.className = 'scanner-alerts-badge';
        }
    }

    // KPIs totais
    var exRate = t.execute_rate || 0;
    var wlRate = t.watchlist_rate || 0;
    var exRateCls = exRate > 0.2 ? 'ok' : exRate > 0.05 ? 'warn' : 'danger';

    setHtml('scanner-totals',
        skpi('Scanned',  t.total_scanned, '') +
        skpi('Watchlist', t.watchlist, '') +
        skpi('Strong',   t.strong, '') +
        skpi('Execute',  t.execute, 'ok') +
        skpi('Block',    t.block, t.block > t.execute * 3 ? 'warn' : '') +
        skpi('WL Rate',  (wlRate*100).toFixed(0) + '%', '') +
        skpi('Exec Rate', (exRate*100).toFixed(0) + '%', exRateCls) +
        skpi('Avg Opp',  t.avg_opp_score || '--', '') +
        skpi('Avg RS',   t.avg_rs || '--', t.avg_rs > 0.5 ? 'danger' : '') +
        skpi('Avg ES',   t.avg_es || '--', t.avg_es > 0.5 ? 'danger' : '')
    );

    // Tabela por classe
    var byClass = sm.by_class || {};
    var classRows = '';
    Object.keys(byClass).sort().forEach(function(cls) {
        var g = byClass[cls];
        var conv = g.execute_rate || 0;
        var convCls = conv > 0.2 ? 'ok' : conv > 0 ? 'low' : 'zero';
        classRows += '<tr>' +
            '<td>' + cls + '</td>' +
            '<td>' + g.total + '</td>' +
            '<td>' + g.watchlist + '</td>' +
            '<td>' + g.execute + '</td>' +
            '<td>' + g.block + '</td>' +
            '<td class="conv-rate ' + convCls + '">' + (conv*100).toFixed(0) + '%</td>' +
            '<td>' + (g.avg_opp_score || '--') + '</td>' +
            '<td>' + (g.avg_rs || '--') + '</td>' +
        '</tr>';
    });
    var classTbody = document.querySelector('#scanner-by-class tbody');
    if (classTbody) classTbody.innerHTML = classRows || '<tr><td colspan="8">Sem dados</td></tr>';

    // Tabela por TF
    var byTF = sm.by_timeframe || {};
    var tfRows = '';
    ['M3','M5','M10','M15','M30','H1'].forEach(function(tf) {
        var g = byTF[tf];
        if (!g) return;
        var conv = g.execute_rate || 0;
        var convCls = conv > 0.2 ? 'ok' : conv > 0 ? 'low' : 'zero';
        tfRows += '<tr>' +
            '<td>' + tf + '</td>' +
            '<td>' + g.total + '</td>' +
            '<td>' + g.watchlist + '</td>' +
            '<td>' + g.execute + '</td>' +
            '<td>' + g.block + '</td>' +
            '<td class="conv-rate ' + convCls + '">' + (conv*100).toFixed(0) + '%</td>' +
        '</tr>';
    });
    var tfTbody = document.querySelector('#scanner-by-tf tbody');
    if (tfTbody) tfTbody.innerHTML = tfRows || '<tr><td colspan="6">Sem dados</td></tr>';

    // Top oportunidades
    var topOpps = sm.top_opportunities || [];
    var oppsHtml = topOpps.length ? topOpps.map(function(o) {
        return '<div class="scanner-opp-item">' +
            '<div class="soi-header"><span class="soi-sym">' + o.symbol + '</span>' +
            '<span class="soi-score">' + (o.score||0).toFixed(3) + ' / ' + (o.thr||0).toFixed(3) + '</span></div>' +
            '<div class="soi-meta">' + (o.class||'') + ' ' + (o.tf||'') + ' [' + (o.label||'').toUpperCase() + ']</div>' +
        '</div>';
    }).join('') : '<p class="empty-state">Sem oportunidades activas</p>';
    setHtml('scanner-top-opps', oppsHtml);

    // Top rejeições
    var topRej = sm.top_rejections || [];
    var rejHtml = topRej.length ? topRej.map(function(r) {
        return '<div class="scanner-reject-item">' +
            '<div class="soi-header"><span class="soi-sym">' + r.symbol + '</span>' +
            '<span style="color:var(--red)">' + (r.reason||r.decision||'BLOCK') + '</span></div>' +
            '<div class="soi-meta">opp=' + (r.opp||0).toFixed(2) + ' rs=' + (r.rs||0).toFixed(2) + ' es=' + (r.es||0).toFixed(2) + '</div>' +
        '</div>';
    }).join('') : '<p class="empty-state">Sem rejeicoes recentes</p>';
    setHtml('scanner-top-rejects', rejHtml);

    // Alertas
    var alertsHtml = alerts.length ? alerts.map(function(a) {
        return '<div class="scanner-alert-item ' + (a.level||'yellow') + '">' + a.msg + '</div>';
    }).join('') : '<p class="empty-state" style="color:var(--green)">[OK] Sem alertas</p>';
    setHtml('scanner-alerts', alertsHtml);
}

function skpi(label, val, cls) {
    return '<div class="scanner-kpi">' +
        '<span class="scanner-kpi-label">' + label + '</span>' +
        '<span class="scanner-kpi-value ' + (cls||'') + '">' + val + '</span>' +
    '</div>';
}

/* ── UTILS ── */
function setEl(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = val;
}
function setHtml(id, html) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = html;
}
function fmt2(n) {
    if (n == null) return '--';
    return Number(n).toFixed(2);
}
