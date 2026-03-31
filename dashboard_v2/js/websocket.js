/**
 * websocket.js - WebSocket client for live data updates
 * Connects to ws://localhost:5000/ws and dispatches events every 2s
 */

const WS_URL = `ws://${location.host}/ws`;
let ws = null;
let reconnectTimer = null;
let reconnectDelay = 2000;

function setWsStatus(status) {
    const el = document.getElementById('ws-status');
    if (!el) return;
    el.className = 'ws-badge ws-' + status;
    const labels = {
        connecting: '<i class="fas fa-circle"></i> Connecting...',
        connected:  '<i class="fas fa-circle"></i> Live',
        error:      '<i class="fas fa-circle"></i> Disconnected',
    };
    el.innerHTML = labels[status] || labels.connecting;
}

function connectWS() {
    setWsStatus('connecting');
    try {
        ws = new WebSocket(WS_URL);
    } catch (e) {
        scheduleReconnect();
        return;
    }

    ws.onopen = () => {
        setWsStatus('connected');
        reconnectDelay = 2000;
        clearTimeout(reconnectTimer);
    };

    ws.onmessage = (evt) => {
        try {
            const data = JSON.parse(evt.data);
            window.dispatchEvent(new CustomEvent('botdata', { detail: data }));
        } catch (e) {
            console.warn('[WS] Parse error:', e);
        }
    };

    ws.onerror = () => {
        setWsStatus('error');
    };

    ws.onclose = () => {
        setWsStatus('error');
        scheduleReconnect();
    };
}

function scheduleReconnect() {
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
        reconnectDelay = Math.min(reconnectDelay * 1.5, 30000);
        connectWS();
    }, reconnectDelay);
}

// Start connection when DOM is ready
document.addEventListener('DOMContentLoaded', connectWS);
