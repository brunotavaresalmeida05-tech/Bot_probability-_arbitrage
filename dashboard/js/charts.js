var DASHBOARD = (function () {
  'use strict';

  var equityHistory = [];
  var MAX_POINTS = 100;

  function drawEquityChart(data) {
    var canvas = document.getElementById('equity-chart');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    var w = rect.width, h = rect.height;

    if (data && data.account && data.account.equity !== undefined) {
      equityHistory.push(data.account.equity);
      if (equityHistory.length > MAX_POINTS) equityHistory.shift();
    }

    var points = equityHistory;
    if (points.length < 2) {
      ctx.fillStyle = '#5c6370';
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Aguardando dados...', w / 2, h / 2);
      return;
    }

    var min = Math.min.apply(null, points);
    var max = Math.max.apply(null, points);
    var range = max - min || 1;
    var pad = 15;
    var pw = w - pad * 2, ph = h - pad * 2;

    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = 'rgba(45, 52, 72, 0.3)';
    ctx.lineWidth = 0.5;
    for (var i = 0; i <= 4; i++) {
      var gy = pad + (i / 4) * ph;
      ctx.beginPath(); ctx.moveTo(pad, gy); ctx.lineTo(w - pad, gy); ctx.stroke();
    }

    ctx.fillStyle = '#5c6370';
    ctx.font = '9px monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (var li = 0; li <= 4; li++) {
      var ly = pad + (li / 4) * ph;
      ctx.fillText('€' + (max - (li / 4) * range).toFixed(0), pad - 4, ly);
    }

    ctx.beginPath();
    ctx.strokeStyle = '#00d4ff';
    ctx.lineWidth = 1.5;
    for (var pi = 0; pi < points.length; pi++) {
      var x = pad + (pi / (points.length - 1)) * pw;
      var y = h - pad - ((points[pi] - min) / range) * ph;
      if (pi === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();

    var grad = ctx.createLinearGradient(0, pad, 0, h - pad);
    grad.addColorStop(0, 'rgba(0, 212, 255, 0.08)');
    grad.addColorStop(1, 'rgba(0, 212, 255, 0.01)');
    ctx.lineTo(w - pad, h - pad); ctx.lineTo(pad, h - pad); ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    var last = points[points.length - 1];
    var lx = w - pad;
    var ly = h - pad - ((last - min) / range) * ph;
    ctx.beginPath(); ctx.arc(lx, ly, 3, 0, Math.PI * 2);
    ctx.fillStyle = '#00d4ff'; ctx.fill();
    ctx.strokeStyle = '#0a0e27'; ctx.lineWidth = 1.5; ctx.stroke();

    ctx.fillStyle = '#00d4ff';
    ctx.font = 'bold 10px monospace';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'bottom';
    ctx.fillText('€' + last.toFixed(2), lx + 5, ly - 1);
  }

  function drawProjectionChart(data) {
    var canvas = document.getElementById('projection-chart');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    var w = rect.width, h = rect.height;

    var proj = (data && data.projections) ? data.projections : [];
    var points = proj.length ? proj : [500, 550, 605, 666, 732, 805, 886, 974, 1072, 1179, 1297, 1427];
    var min = Math.min.apply(null, points);
    var max = Math.max.apply(null, points);
    var range = max - min || 1;
    var pad = 15;
    var pw = w - pad * 2, ph = h - pad * 2;

    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = 'rgba(45, 52, 72, 0.3)';
    ctx.lineWidth = 0.5;
    for (var i = 0; i <= 4; i++) {
      var gy = pad + (i / 4) * ph;
      ctx.beginPath(); ctx.moveTo(pad, gy); ctx.lineTo(w - pad, gy); ctx.stroke();
    }

    ctx.beginPath();
    ctx.strokeStyle = '#7b61ff';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    for (var pi = 0; pi < points.length; pi++) {
      var x = pad + (pi / (points.length - 1)) * pw;
      var y = h - pad - ((points[pi] - min) / range) * ph;
      if (pi === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    var last = points[points.length - 1];
    var lx = w - pad;
    var ly = h - pad - ((last - min) / range) * ph;
    ctx.beginPath(); ctx.arc(lx, ly, 3, 0, Math.PI * 2);
    ctx.fillStyle = '#7b61ff'; ctx.fill();

    ctx.fillStyle = '#7b61ff';
    ctx.font = 'bold 10px monospace';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'bottom';
    ctx.fillText('€' + last.toFixed(0), lx + 5, ly - 1);
  }

  function drawSentimentGauge(data) {
    var canvas = document.getElementById('sentiment-gauge');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    var w = rect.width, h = rect.height;
    var cx = w / 2, cy = h * 0.65, r = Math.min(w, h) * 0.35;

    ctx.clearRect(0, 0, w, h);

    var pct = 0.55;
    var startAngle = Math.PI * 0.75;
    var endAngle = Math.PI * 2.25;
    var total = endAngle - startAngle;
    var val = startAngle + total * pct;

    ctx.beginPath(); ctx.arc(cx, cy, r, startAngle, endAngle);
    ctx.strokeStyle = '#2d3748'; ctx.lineWidth = 12; ctx.stroke();

    ctx.beginPath(); ctx.arc(cx, cy, r, startAngle, val);
    var g = ctx.createLinearGradient(0, 0, w, 0);
    g.addColorStop(0, '#ff5252'); g.addColorStop(0.5, '#ffc107'); g.addColorStop(1, '#00e676');
    ctx.strokeStyle = g; ctx.lineWidth = 12; ctx.stroke();

    ctx.fillStyle = '#e0e6ed';
    ctx.font = 'bold 16px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText((pct * 100).toFixed(0) + '%', cx, cy * 0.5);
    ctx.fillStyle = '#8b92a7';
    ctx.font = '10px sans-serif';
    ctx.fillText('Bearish', cx - r * 0.7, cy + r * 0.5);
    ctx.fillText('Bullish', cx + r * 0.7, cy + r * 0.5);
    ctx.fillText('Neutral', cx, cy + r * 0.75);
  }

  function updateCharts(data) {
    drawEquityChart(data);
    drawProjectionChart(data);
  }

  function init() {
    var ec = document.getElementById('equity-chart');
    if (ec) {
      var ro = new ResizeObserver(function () { drawEquityChart({ account: { equity: equityHistory[equityHistory.length - 1] || 0 } }); });
      ro.observe(ec.parentElement);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { updateCharts: updateCharts, drawSentimentGauge: drawSentimentGauge };
})();
