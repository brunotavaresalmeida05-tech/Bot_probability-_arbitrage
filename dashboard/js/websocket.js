var WS = (function () {
  'use strict';

  var _ws = null;
  var _reconnectTimer = null;
  var _listeners = [];

  function connect() {
    if (_ws && (_ws.readyState === WebSocket.OPEN || _ws.readyState === WebSocket.CONNECTING)) return;
    var proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var url = proto + '//' + window.location.host + '/ws';
    _ws = new WebSocket(url);
    _ws.onopen = function () {
      console.log('[WS] Connected');
      document.getElementById('ws-status').textContent = 'Live';
      document.getElementById('ws-status').className = 'ws-dot online';
    };
    _ws.onmessage = function (evt) {
      try {
        var data = JSON.parse(evt.data);
        _listeners.forEach(function (fn) { fn(data); });
      } catch (e) { console.warn('[WS] Parse error', e); }
    };
    _ws.onclose = function () {
      console.log('[WS] Disconnected');
      document.getElementById('ws-status').textContent = 'Offline';
      document.getElementById('ws-status').className = 'ws-dot offline';
      _ws = null;
      if (!_reconnectTimer) {
        _reconnectTimer = setTimeout(function () {
          _reconnectTimer = null;
          connect();
        }, 3000);
      }
    };
    _ws.onerror = function () { _ws.close(); };
  }

  function onData(fn) {
    _listeners.push(fn);
  }

  function disconnect() {
    if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
    if (_ws) { _ws.onclose = null; _ws.close(); _ws = null; }
    _listeners = [];
  }

  connect();

  return { connect: connect, onData: onData, disconnect: disconnect };
})();

document.addEventListener('DOMContentLoaded', function () {
  WS.onData(function (data) {
    var acc = data.account || {};
    var el = function (id) { return document.getElementById(id); };

    if (acc.balance !== undefined) {
      el('balance').textContent = '€' + Number(acc.balance).toFixed(2);
      el('current-balance').textContent = '€' + Number(acc.balance).toFixed(2);
    }
    if (acc.equity !== undefined) {
      el('equity').textContent = '€' + Number(acc.equity).toFixed(2);
      var pnl = (acc.equity || 0) - (acc.balance || 0);
      var pnlEl = el('pnl');
      pnlEl.textContent = (pnl >= 0 ? '+' : '') + '€' + pnl.toFixed(2);
      pnlEl.className = 'stat-value ' + (pnl >= 0 ? 'positive' : 'negative');
    }
    var positions = data.open_positions || [];
    el('open-positions').textContent = positions.length;
    var pcEl = el('positions-count');
    if (pcEl) pcEl.textContent = positions.length;

    if (data.scaling) {
      var s = data.scaling;
      el('current-milestone').textContent = s.current_milestone || 'Micro';
      el('next-milestone').textContent = '€' + (s.next_milestone || 500);
      el('target-balance').textContent = '€' + (s.next_milestone || 500);
      el('progress-percentage').textContent = (s.progress_pct || 0) + '%';
      el('milestone-progress').style.width = (s.progress_pct || 0) + '%';
      el('days-to-milestone').textContent = s.days_estimate || '--';
    }

    if (window.DASHBOARD && window.DASHBOARD.updateCharts) {
      window.DASHBOARD.updateCharts(data);
    }
  });
});
