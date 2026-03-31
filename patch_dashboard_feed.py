"""
patch_dashboard_feed.py
Adiciona o live_state_writer ao run_live.py de forma segura.
Executa: python patch_dashboard_feed.py
"""
import os, re, shutil
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
RUN  = os.path.join(BASE, 'run_live.py')

def ok(m):   print(f"  ✅ {m}")
def warn(m): print(f"  ⚠️  {m}")
def err(m):  print(f"  ❌ {m}")

print("\n" + "="*60)
print("  PATCH: Dashboard Data Feed")
print("="*60 + "\n")

if not os.path.exists(RUN):
    err("run_live.py não encontrado na raiz do projeto")
    exit(1)

# Backup
bak = RUN + f'.bak_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
shutil.copy2(RUN, bak)
ok(f"Backup criado: {os.path.basename(bak)}")

with open(RUN, 'r', encoding='utf-8', errors='ignore') as f:
    code = f.read()

# Verificar se já está integrado
if 'live_state_writer' in code or 'LiveStateWriter' in code:
    ok("live_state_writer já está integrado no run_live.py")
    print("\n  Nada a fazer — dashboard já recebe dados reais.")
    exit(0)

# ── PASSO 1: Adicionar import no topo ────────────────────────────────────────
IMPORT_BLOCK = (
    "\n# ── Dashboard real-time data feed ──────────────────────────\n"
    "try:\n"
    "    from live_state_writer import LiveStateWriter as _LSW\n"
    "    _writer = _LSW()\n"
    "    _DASHBOARD_FEED = True\n"
    "except Exception:\n"
    "    _DASHBOARD_FEED = False\n"
    "# ─────────────────────────────────────────────────────────────\n"
)

# Inserir após o último import do topo
last_import = 0
for m in re.finditer(r'^(import |from )\S', code, re.MULTILINE):
    last_import = m.end()

insert_pos = code.find('\n', last_import) + 1
code = code[:insert_pos] + IMPORT_BLOCK + code[insert_pos:]
ok("Import adicionado no topo do ficheiro")

# ── PASSO 2: Adicionar writer.update() no ciclo principal ────────────────────
WRITER_CALL = '''
    # ── Dashboard feed (não bloqueia o bot) ──────────────────────
    if _DASHBOARD_FEED:
        try:
            import MetaTrader5 as _mt5
            _acc = _mt5.account_info()
            _pos = list(_mt5.positions_get() or [])
            _syms = SYMBOLS[:10] if 'SYMBOLS' in dir() else []
            _writer.update(
                account  = _acc._asdict() if _acc else {},
                positions= _pos,
                signals  = (getattr(strategy_manager,'last_signals',[])
                            if 'strategy_manager' in dir() else []),
                spreads  = {s: (_mt5.symbol_info(s).spread
                                if _mt5.symbol_info(s) else 0)
                            for s in _syms},
                prices   = {s: (_mt5.symbol_info_tick(s).ask
                                if _mt5.symbol_info_tick(s) else 0)
                            for s in _syms},
            )
        except Exception:
            pass
    # ─────────────────────────────────────────────────────────────
'''

# Encontrar o sleep/próxima verificação no ciclo
inserted = False
for pattern in [
    r'([ \t]*)(time\.sleep\(\s*\d+\s*\))',
    r'([ \t]*)(sleep\(\s*\d+\s*\))',
    r'([ \t]*)(await asyncio\.sleep)',
    r'([ \t]*)(Próxima verificação)',
]:
    matches = list(re.finditer(pattern, code))
    if matches:
        # Usar a última ocorrência (no ciclo principal, não no setup)
        m = matches[-1]
        insert_at = m.start()
        code = code[:insert_at] + WRITER_CALL + code[insert_at:]
        ok(f"writer.update() inserido antes de: {m.group(2)[:40]}")
        inserted = True
        break

if not inserted:
    # Fallback: inserir no final do ficheiro
    code += "\n" + WRITER_CALL
    warn("Não encontrado sleep/ciclo — writer adicionado no final")

# Guardar
with open(RUN, 'w', encoding='utf-8') as f:
    f.write(code)
ok("run_live.py guardado com sucesso")

print(f"""
{'='*60}
  PATCH APLICADO COM SUCESSO!
{'='*60}

  Agora executa em sequência:

  Terminal 1:  python flask_dashboard.py
  Terminal 2:  python run_live.py

  Browser:     http://localhost:5000

  O dashboard vai mostrar dados reais em 10–20 segundos.
{'='*60}
""")
