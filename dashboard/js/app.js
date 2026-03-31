// ============================================
// DASHBOARD APP - MAIN LOGIC
// ============================================

// Global state
const state = {
    currentPage: 'home',
    ws: null,
    data: {
        balance: 0,
        equity: 0,
        positions: [],
        strategies: [],
        symbols: [],
        history: []
    }
};

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initializeNavigation();
    initializeWebSocket();
    updateHeaderStats();
    
    // Update every 1s
    setInterval(updateHeaderStats, 1000);
});

// ============================================
// NAVIGATION
// ============================================

function initializeNavigation() {
    const menuItems = document.querySelectorAll('.menu-item');
    
    menuItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            
            const page = item.dataset.page;
            if (page) {
                navigateToPage(page);
            }
        });
    });
}

function navigateToPage(pageName) {
    // Update active menu item
    document.querySelectorAll('.menu-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`[data-page="${pageName}"]`).classList.add('active');
    
    // Update active page
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });
    document.getElementById(`page-${pageName}`).classList.add('active');
    
    // Update page title
    const titles = {
        'home': 'Dashboard Geral',
        'execution': 'Execução',
        'portfolio': 'Portfolio',
        'strategies': 'Estratégias',
        'symbols': 'Símbolos',
        'history': 'Histórico',
        'correlations': 'Correlações'
    };
    document.getElementById('page-title').textContent = titles[pageName];
    
    // Load page data
    loadPageData(pageName);
    
    state.currentPage = pageName;
}

// ============================================
// DATA LOADING
// ============================================

function loadPageData(pageName) {
    switch(pageName) {
        case 'home':
            loadHomeData();
            break;
        case 'execution':
            loadExecutionData();
            break;
        case 'portfolio':
            loadPortfolioData();
            break;
        case 'strategies':
            loadStrategiesData();
            break;
        case 'symbols':
            loadSymbolsData();
            break;
        case 'history':
            loadHistoryData();
            break;
        case 'correlations':
            loadCorrelationsData();
            break;
    }
}

function loadHomeData() {
    // Update capital scaling
    updateCapitalScaling();
    
    // Load charts
    if (typeof updateEquityChart === 'function') {
        updateEquityChart();
    }
    if (typeof updateProjectionChart === 'function') {
        updateProjectionChart();
    }
    
    // Load strategy performance
    loadStrategyPerformance();
}

function updateCapitalScaling() {
    fetch('/api/capital_scaling')
        .then(r => r.json())
        .then(data => {
            document.getElementById('current-milestone').textContent = data.current_milestone || 'Micro';
            document.getElementById('next-milestone').textContent = `€${data.next_target || 500}`;
            document.getElementById('current-balance').textContent = `€${data.current_balance || 0}`;
            document.getElementById('target-balance').textContent = `€${data.next_target || 500}`;
            document.getElementById('progress-percentage').textContent = `${data.progress_pct || 0}%`;
            document.getElementById('milestone-progress').style.width = `${data.progress_pct || 0}%`;
            document.getElementById('growth-percentage').textContent = `${data.growth_pct || 0}%`;
            document.getElementById('remaining-amount').textContent = `€${data.remaining || 0}`;
            document.getElementById('days-to-milestone').textContent = data.days_estimate || '--';
        })
        .catch(err => console.error('Error loading capital scaling:', err));
}

function loadStrategyPerformance() {
    fetch('/api/strategies')
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('strategy-performance');
            
            if (!data || data.length === 0) {
                container.innerHTML = '<p class="empty-state">Sem dados de estratégias</p>';
                return;
            }
            
            let html = '<table><thead><tr>';
            html += '<th>Estratégia</th><th>Trades</th><th>Win %</th><th>Avg P/L</th><th>Sharpe</th>';
            html += '</tr></thead><tbody>';
            
            data.forEach(strategy => {
                const winClass = strategy.win_rate >= 60 ? 'positive' : strategy.win_rate >= 50 ? '' : 'negative';
                html += `<tr>
                    <td><strong>${strategy.name}</strong></td>
                    <td>${strategy.trades}</td>
                    <td class="${winClass}">${strategy.win_rate}%</td>
                    <td class="${strategy.avg_pnl >= 0 ? 'positive' : 'negative'}">€${strategy.avg_pnl}</td>
                    <td>${strategy.sharpe}</td>
                </tr>`;
            });
            
            html += '</tbody></table>';
            container.innerHTML = html;
        })
        .catch(err => {
            console.error('Error loading strategies:', err);
            document.getElementById('strategy-performance').innerHTML = 
                '<p class="empty-state">Erro ao carregar dados</p>';
        });
}

function loadPortfolioData() {
    fetch('/api/positions')
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('open-positions-list');
            
            if (!data || data.length === 0) {
                container.innerHTML = '<p class="empty-state">Sem posições abertas</p>';
                return;
            }
            
            let html = '';
            data.forEach(pos => {
                const pnlClass = pos.profit >= 0 ? 'positive' : 'negative';
                html += `
                <div class="position-card">
                    <div class="position-header">
                        <span class="symbol">${pos.symbol}</span>
                        <span class="type ${pos.type}">${pos.type}</span>
                    </div>
                    <div class="position-body">
                        <div class="row">
                            <span>Entry:</span>
                            <span>${pos.entry}</span>
                        </div>
                        <div class="row">
                            <span>Current:</span>
                            <span>${pos.current}</span>
                        </div>
                        <div class="row">
                            <span>P&L:</span>
                            <span class="${pnlClass}">€${pos.profit}</span>
                        </div>
                    </div>
                </div>`;
            });
            
            container.innerHTML = html;
        })
        .catch(err => console.error('Error loading portfolio:', err));
}

function loadSymbolsData() {
    fetch('/api/symbols')
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('symbols-table');
            
            if (!data || data.length === 0) {
                container.innerHTML = '<p class="empty-state">Sem dados de símbolos</p>';
                return;
            }
            
            let html = '<table><thead><tr>';
            html += '<th>Símbolo</th><th>Z-Score</th><th>Preço</th><th>MA</th><th>Spread</th><th>Sinal</th><th>P&L</th>';
            html += '</tr></thead><tbody>';
            
            data.forEach(sym => {
                const signalClass = sym.signal === 'BUY' ? 'positive' : sym.signal === 'SELL' ? 'negative' : '';
                html += `<tr>
                    <td><strong>${sym.symbol}</strong></td>
                    <td>${sym.z_score}</td>
                    <td>${sym.price}</td>
                    <td>${sym.ma}</td>
                    <td>${sym.spread}</td>
                    <td class="${signalClass}">${sym.signal || '--'}</td>
                    <td class="${sym.pnl >= 0 ? 'positive' : 'negative'}">€${sym.pnl || 0}</td>
                </tr>`;
            });
            
            html += '</tbody></table>';
            container.innerHTML = html;
        })
        .catch(err => console.error('Error loading symbols:', err));
}

function loadHistoryData() {
    fetch('/api/history')
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('history-table');
            
            if (!data || data.length === 0) {
                container.innerHTML = '<p class="empty-state">Sem histórico de trades</p>';
                return;
            }
            
            let html = '<table><thead><tr>';
            html += '<th>Data</th><th>Símbolo</th><th>Tipo</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Motivo</th>';
            html += '</tr></thead><tbody>';
            
            data.forEach(trade => {
                const pnlClass = trade.profit >= 0 ? 'positive' : 'negative';
                html += `<tr>
                    <td>${trade.date}</td>
                    <td><strong>${trade.symbol}</strong></td>
                    <td>${trade.type}</td>
                    <td>${trade.entry}</td>
                    <td>${trade.exit}</td>
                    <td class="${pnlClass}">€${trade.profit}</td>
                    <td class="small">${trade.reason}</td>
                </tr>`;
            });
            
            html += '</tbody></table>';
            container.innerHTML = html;
        })
        .catch(err => console.error('Error loading history:', err));
}

function loadExecutionData() {
    // Placeholder for live signals
    console.log('Loading execution data...');
}

function loadStrategiesData() {
    // Reuse strategy performance logic
    loadStrategyPerformance();
}

function loadCorrelationsData() {
    // Placeholder for correlations
    console.log('Loading correlations...');
}

// ============================================
// HEADER STATS UPDATE
// ============================================

function updateHeaderStats() {
    fetch('/api/account')
        .then(r => r.json())
        .then(data => {
            document.getElementById('balance').textContent = `€${data.balance || 0}`;
            document.getElementById('equity').textContent = `€${data.equity || 0}`;
            
            const pnl = data.equity - data.balance;
            const pnlEl = document.getElementById('pnl');
            pnlEl.textContent = `€${pnl.toFixed(2)}`;
            pnlEl.className = `stat-value ${pnl >= 0 ? 'positive' : 'negative'}`;
            
            document.getElementById('open-positions').textContent = data.positions_count || 0;
            document.getElementById('positions-count').textContent = data.positions_count || 0;
            
            state.data.balance = data.balance;
            state.data.equity = data.equity;
        })
        .catch(err => console.error('Error updating header:', err));
}

// ============================================
// WEBSOCKET (placeholder)
// ============================================

function initializeWebSocket() {
    // Placeholder - implement when backend supports WebSocket
    console.log('WebSocket placeholder initialized');
}
