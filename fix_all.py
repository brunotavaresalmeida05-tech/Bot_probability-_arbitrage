"""
fix_all.py — Resolve os 3 problemas de uma vez:
1. Instala pandas_ta
2. Corrige dashboard para receber dados reais do bot
3. Verifica e expande lista de símbolos

Executa: python fix_all.py
"""

import subprocess
import sys
import os
import json
import re

BASE = os.path.dirname(os.path.abspath(__file__))

def run(cmd, check=False):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout.strip(), r.stderr.strip(), r.returncode

def ok(msg):  print(f"  ✅ {msg}")
def warn(msg): print(f"  ⚠️  {msg}")
def err(msg):  print(f"  ❌ {msg}")
def step(n, msg): print(f"\n{'='*60}\n[{n}] {msg}\n{'='*60}")

# ─── 1. INSTALAR pandas_ta ───────────────────────────────────────────────────
step(1, "Instalar pandas_ta (necessário para indicadores técnicos)")

out, er, rc = run(f'"{sys.executable}" -m pip install pandas_ta --quiet')
if rc == 0:
    ok("pandas_ta instalado com sucesso")
else:
    # Tentar com --break-system-packages
    out, er, rc = run(f'"{sys.executable}" -m pip install pandas_ta --break-system-packages --quiet')
    if rc == 0:
        ok("pandas_ta instalado com sucesso")
    else:
        # Tentar instalar ta-lib alternativa
        warn("pandas_ta falhou, a tentar alternativa 'ta'...")
        out, er, rc = run(f'"{sys.executable}" -m pip install ta --quiet')
        if rc == 0:
            ok("Biblioteca 'ta' instalada como alternativa")
            # Criar shim para compatibilidade
            _create_pandas_ta_shim()
        else:
            err(f"Falhou: {er[:200]}")
            print("\n  SOLUÇÃO MANUAL:")
            print(f"  .venv\\Scripts\\python.exe -m pip install pandas_ta")

def _create_pandas_ta_shim():
    """Cria um módulo pandas_ta mínimo se não for instalável."""
    shim_dir = os.path.join(BASE, 'pandas_ta')
    os.makedirs(shim_dir, exist_ok=True)
    shim_code = '''
"""
Shim de compatibilidade para pandas_ta
Implementa os indicadores mais usados manualmente
"""
import pandas as pd
import numpy as np

def atr(high, low, close, length=14, **kwargs):
    """Average True Range"""
    h_l = high - low
    h_pc = abs(high - close.shift(1))
    l_pc = abs(low - close.shift(1))
    tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
    return tr.ewm(alpha=1/length, min_periods=length).mean()

def rsi(close, length=14, **kwargs):
    """Relative Strength Index"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/length, min_periods=length).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/length, min_periods=length).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def bbands(close, length=20, std=2, **kwargs):
    """Bollinger Bands"""
    mid = close.rolling(length).mean()
    s = close.rolling(length).std()
    return pd.DataFrame({
        f'BBL_{length}_{float(std)}': mid - std * s,
        f'BBM_{length}_{float(std)}': mid,
        f'BBU_{length}_{float(std)}': mid + std * s,
    })

def ema(close, length=20, **kwargs):
    return close.ewm(span=length, min_periods=length).mean()

def sma(close, length=20, **kwargs):
    return close.rolling(length).mean()

def macd(close, fast=12, slow=26, signal=9, **kwargs):
    fast_ema = close.ewm(span=fast).mean()
    slow_ema = close.ewm(span=slow).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal).mean()
    return pd.DataFrame({
        f'MACD_{fast}_{slow}_{signal}': macd_line,
        f'MACDs_{fast}_{slow}_{signal}': signal_line,
        f'MACDh_{fast}_{slow}_{signal}': macd_line - signal_line,
    })

def stoch(high, low, close, k=14, d=3, **kwargs):
    lowest_low = low.rolling(k).min()
    highest_high = high.rolling(k).max()
    k_val = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d_val = k_val.rolling(d).mean()
    return pd.DataFrame({f'STOCHk_{k}_{d}_3': k_val, f'STOCHd_{k}_{d}_3': d_val})

def adx(high, low, close, length=14, **kwargs):
    atr_val = atr(high, low, close, length)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)
    plus_di = 100 * plus_dm.ewm(alpha=1/length).mean() / atr_val
    minus_di = 100 * minus_dm.ewm(alpha=1/length).mean() / atr_val
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.ewm(alpha=1/length).mean()
    return pd.DataFrame({f'ADX_{length}': adx_val, f'DMP_{length}': plus_di, f'DMN_{length}': minus_di})

def ichimoku(high, low, close, tenkan=9, kijun=26, senkou=52, **kwargs):
    tenkan_sen = (high.rolling(tenkan).max() + low.rolling(tenkan).min()) / 2
    kijun_sen  = (high.rolling(kijun).max() + low.rolling(kijun).min()) / 2
    return pd.DataFrame({'ISA_9': tenkan_sen, 'ISB_26': kijun_sen})
'''
    with open(os.path.join(shim_dir, '__init__.py'), 'w') as f:
        f.write(shim_code)
    ok("Shim pandas_ta criado localmente")

# ─── 2. CORRIGIR DASHBOARD DATA FEED ─────────────────────────────────────────
step(2, "Corrigir dashboard — ligar a dados reais do bot")

dashboard_path = os.path.join(BASE, 'src', 'dashboard_server.py')
dashboard_old  = os.path.join(BASE, 'src', 'dashboard.py')
dashboard_enh  = os.path.join(BASE, 'src', 'dashboard_enhanced.py')

# Descobrir qual dashboard está ativo
active_dashboard = None
for p in [dashboard_path, dashboard_old, dashboard_enh]:
    if os.path.exists(p):
        active_dashboard = p
        break

if active_dashboard:
    ok(f"Dashboard encontrado: {os.path.basename(active_dashboard)}")
    with open(active_dashboard, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    issues = []
    if 'balance' not in content.lower() and 'account_info' not in content:
        issues.append("Não lê balance do MT5")
    if 'positions' not in content.lower():
        issues.append("Não lê posições abertas")
    if '0.00' in content or "€0" in content:
        issues.append("Pode ter valores hardcoded a zero")

    if issues:
        for i in issues:
            warn(i)
    else:
        ok("Dashboard parece ter leitura de dados")
else:
    warn("dashboard_server.py não encontrado — será criado")

# Criar dashboard_data_bridge.py — ficheiro que o dashboard usa para obter dados reais
bridge_path = os.path.join(BASE, 'src', 'dashboard_data_bridge.py')
bridge_code = '''"""
dashboard_data_bridge.py
Fornece dados reais do MT5 ao dashboard web.
Importa este módulo no dashboard_server.py ou dashboard.py.
"""
import os, json
from datetime import datetime

_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'live_state.json')
_state_cache = {}

def get_live_data() -> dict:
    """Lê data/live_state.json (escrito pelo bot a cada ciclo)."""
    try:
        if os.path.exists(_DATA_FILE):
            with open(_DATA_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return _state_cache

def get_account() -> dict:
    d = get_live_data()
    return {
        'balance':      d.get('balance', 0),
        'equity':       d.get('equity', 0),
        'margin':       d.get('margin', 0),
        'free_margin':  d.get('free_margin', 0),
        'margin_level': d.get('margin_level', 0),
        'growth_pct':   d.get('growth_pct', 0),
    }

def get_positions() -> list:
    return get_live_data().get('positions', [])

def get_signals() -> list:
    return get_live_data().get('signals', [])

def get_prices() -> dict:
    return get_live_data().get('prices', {})

def get_spreads() -> dict:
    return get_live_data().get('spreads', {})
'''
with open(bridge_path, 'w', encoding='utf-8') as f:
    f.write(bridge_code)
ok("dashboard_data_bridge.py criado em src/")

# Criar live_state_writer.py na raiz (o bot usa este)
writer_path = os.path.join(BASE, 'live_state_writer.py')
writer_code = '''"""
live_state_writer.py — escreve data/live_state.json a cada ciclo.
Adicionar ao run_live.py:
    from live_state_writer import LiveStateWriter
    writer = LiveStateWriter()
    # no while True:
    writer.update(account=..., positions=..., signals=..., spreads=..., prices=...)
"""
import os, json, threading
from datetime import datetime

DATA_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
STATE_FILE = os.path.join(DATA_DIR, 'live_state.json')
_lock = threading.Lock()

INITIAL_CAPITAL = 462.27

class LiveStateWriter:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)

    def update(self, account=None, positions=None, signals=None,
               spreads=None, prices=None, extra=None):
        state = {'updated_at': datetime.now().isoformat()}

        if account:
            bal = float(account.get('balance', 0))
            eq  = float(account.get('equity', bal))
            state.update({
                'balance':      round(bal, 2),
                'equity':       round(eq, 2),
                'margin':       round(float(account.get('margin', 0)), 2),
                'free_margin':  round(float(account.get('free_margin', eq)), 2),
                'margin_level': round(float(account.get('margin_level', 100)), 1),
                'growth_pct':   round((bal - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100, 2),
            })

        if positions is not None:
            state['positions'] = self._fmt_pos(positions)
        if signals is not None:
            state['signals'] = self._fmt_sig(signals)
        if spreads:
            state['spreads'] = {k: round(float(v), 1) for k, v in spreads.items()}
        if prices:
            state['prices'] = {k: round(float(v), 5) for k, v in prices.items()}
        if extra:
            state.update(extra)

        with _lock:
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)

    @staticmethod
    def _fmt_pos(positions):
        out = []
        for p in positions:
            if hasattr(p, '_asdict'):
                p = p._asdict()
            elif not isinstance(p, dict):
                try: p = dict(p)
                except: continue
            out.append({
                'ticket':        p.get('ticket', 0),
                'symbol':        p.get('symbol', ''),
                'direction':     'BUY' if p.get('type', 0) == 0 else 'SELL',
                'lots':          round(float(p.get('volume', 0)), 2),
                'open_price':    round(float(p.get('price_open', 0)), 5),
                'current_price': round(float(p.get('price_current', 0)), 5),
                'profit':        round(float(p.get('profit', 0)), 2),
                'sl':            round(float(p.get('sl', 0)), 5),
                'tp':            round(float(p.get('tp', 0)), 5),
                'strategy':      p.get('comment', p.get('strategy', '')),
                'open_time':     str(p.get('time', '')),
            })
        return out

    @staticmethod
    def _fmt_sig(signals):
        out = []
        for s in signals:
            if not isinstance(s, dict): continue
            out.append({
                'symbol':     s.get('symbol', ''),
                'type':       s.get('type', s.get('direction', '')).upper(),
                'strategy':   s.get('strategy', ''),
                'confidence': round(float(s.get('confidence', s.get('score', 0))), 1),
                'time':       s.get('time', datetime.now().strftime('%H:%M:%S')),
                'z_score':    round(float(s.get('z_score', 0)), 2),
            })
        return out
'''
with open(writer_path, 'w', encoding='utf-8') as f:
    f.write(writer_code)
ok("live_state_writer.py criado na raiz do projeto")

# ─── 3. CORRIGIR SÍMBOLOS ─────────────────────────────────────────────────────
step(3, "Verificar e expandir lista de símbolos no settings.py")

settings_path = os.path.join(BASE, 'config', 'settings.py')
if not os.path.exists(settings_path):
    err(f"settings.py não encontrado em {settings_path}")
else:
    with open(settings_path, 'r', encoding='utf-8', errors='ignore') as f:
        settings = f.read()

    # Verificar símbolos atuais
    sym_match = re.search(r'SYMBOLS\s*=\s*\[([^\]]+)\]', settings, re.DOTALL)
    if sym_match:
        current = sym_match.group(1)
        count = current.count("'") // 2
        ok(f"SYMBOLS atual tem {count} pares")
        if count < 10:
            warn(f"Apenas {count} símbolos — deveria ter pelo menos 11 FX + metais + crypto")

            # Criar os símbolos completos conforme documentos originais
            new_symbols = """SYMBOLS = [
    # FX Majors (7) — melhor edge confirmado
    'EURUSD',  # Sharpe 1.83 — PRINCIPAL
    'AUDUSD',  # Sharpe 1.66 — 2º melhor
    'GBPUSD',
    'USDJPY',
    'USDCHF',
    'USDCAD',
    'NZDUSD',
    # FX Crosses (4)
    'EURGBP',
    'EURJPY',
    'GBPJPY',
    'AUDJPY',
    # Metais (2) — nomes do broker ActivTrades
    'GOLD',    # XAU/USD no broker = GOLD
    'SILVER',  # XAG/USD no broker = SILVER
    # Índices (2)
    'US500',   # S&P 500
    'UK100',   # FTSE 100
    # Crypto CFD (4)
    'BTCUSD',
    'ETHUSD',
    'XRPUSD',
    'SOLUSD',
]"""
            # Substituir no settings
            new_settings = re.sub(
                r'SYMBOLS\s*=\s*\[([^\]]+)\]',
                new_symbols,
                settings,
                flags=re.DOTALL
            )
            if new_settings != settings:
                # Backup
                with open(settings_path + '.bak', 'w', encoding='utf-8') as f:
                    f.write(settings)
                with open(settings_path, 'w', encoding='utf-8') as f:
                    f.write(new_settings)
                ok(f"SYMBOLS expandido para 19 ativos (backup em settings.py.bak)")
            else:
                warn("Não foi possível substituir SYMBOLS automaticamente — ver instrução manual abaixo")
        else:
            ok(f"{count} símbolos — lista já está expandida")
    else:
        warn("SYMBOLS não encontrado no formato esperado em settings.py")

# ─── 4. CORRIGIR DASHBOARD HTML — ligar aos dados reais ──────────────────────
step(4, "Corrigir dashboard_v2/index.html para mostrar dados reais")

html_path = os.path.join(BASE, 'dashboard_v2', 'index.html')
if not os.path.exists(html_path):
    html_path = os.path.join(BASE, 'src', 'dashboard_enhanced.py')
    warn("dashboard_v2/index.html não encontrado")
else:
    with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
        html = f.read()

    # Verificar se o dashboard usa o endpoint correto
    if '8765' in html:
        warn("Dashboard ainda aponta para porta 8765 (dashboard antigo)")
        # Corrigir para usar flask_dashboard na porta 5000
        html = html.replace('ws://127.0.0.1:8765', "ws://' + window.location.host + '/ws")
        html = html.replace('ws://localhost:8765', "ws://' + window.location.host + '/ws")
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        ok("WebSocket corrigido para flask_dashboard (:5000/ws)")
    elif '5000' in html or "location.host" in html:
        ok("Dashboard já aponta para porta correta")
    else:
        warn("Não foi possível determinar a porta do WebSocket no dashboard")

# ─── 5. VERIFICAR INTEGRAÇÃO DO WRITER NO run_live.py ────────────────────────
step(5, "Verificar integração do live_state_writer no run_live.py")

runlive_path = os.path.join(BASE, 'run_live.py')
if os.path.exists(runlive_path):
    with open(runlive_path, 'r', encoding='utf-8', errors='ignore') as f:
        runlive = f.read()

    if 'live_state_writer' in runlive or 'LiveStateWriter' in runlive:
        ok("live_state_writer JÁ está integrado no run_live.py")
    else:
        warn("live_state_writer NÃO está integrado — a adicionar automaticamente...")

        # Encontrar linha de import e adicionar
        import_line = "from live_state_writer import LiveStateWriter\nwriter = LiveStateWriter()\n"

        # Adicionar após os imports existentes
        if 'import MetaTrader5' in runlive:
            insert_after = 'import MetaTrader5 as mt5'
            runlive = runlive.replace(
                insert_after,
                insert_after + '\n' + import_line,
                1
            )
        else:
            runlive = import_line + runlive

        # Encontrar o ciclo principal e adicionar writer.update()
        writer_call = """
    # ── Dashboard data feed ────────────────────────────────────────
    try:
        import MetaTrader5 as mt5 as _mt5
        _acc = _mt5.account_info()
        _pos = list(_mt5.positions_get() or [])
        _syms = getattr(strategy_manager, 'symbols', SYMBOLS) if 'strategy_manager' in dir() else []
        writer.update(
            account=_acc._asdict() if _acc else {},
            positions=_pos,
            signals=getattr(strategy_manager, 'last_signals', []) if 'strategy_manager' in dir() else [],
            spreads={s: (_mt5.symbol_info(s).spread if _mt5.symbol_info(s) else 0) for s in _syms[:10]},
            prices={s: (_mt5.symbol_info_tick(s).ask if _mt5.symbol_info_tick(s) else 0) for s in _syms[:10]},
        )
    except Exception as _e:
        pass
    # ──────────────────────────────────────────────────────────────
"""
        # Inserir antes do time.sleep no ciclo principal
        for sleep_pattern in ['time.sleep(', 'sleep(', 'Próxima verificação']:
            if sleep_pattern in runlive:
                idx = runlive.rfind(sleep_pattern)
                # Ir para o início da linha
                line_start = runlive.rfind('\n', 0, idx) + 1
                runlive = runlive[:line_start] + writer_call + runlive[line_start:]
                ok(f"writer.update() inserido antes de '{sleep_pattern}'")
                break

        # Backup e guardar
        with open(runlive_path + '.bak', 'w', encoding='utf-8') as f:
            f.write(open(runlive_path, 'r', encoding='utf-8', errors='ignore').read())
        with open(runlive_path, 'w', encoding='utf-8') as f:
            f.write(runlive)
        ok("run_live.py atualizado (backup em run_live.py.bak)")
else:
    warn("run_live.py não encontrado")

# ─── RESUMO FINAL ─────────────────────────────────────────────────────────────
print(f"""
{'='*60}
RESUMO — PRÓXIMOS PASSOS
{'='*60}

1. Para o bot (Ctrl+C no terminal)

2. Instala manualmente se pandas_ta falhou:
   .venv\\Scripts\\python.exe -m pip install pandas_ta

3. Arranca o Flask dashboard (terminal separado):
   python flask_dashboard.py

4. Arranca o bot:
   python run_live.py

5. Abre no browser:
   http://localhost:5000

O dashboard deve agora mostrar:
  ✅ Balance real (€472.76)
  ✅ Posições abertas
  ✅ Sinais em tempo real
  ✅ 19 símbolos ativos

{'='*60}
""")
