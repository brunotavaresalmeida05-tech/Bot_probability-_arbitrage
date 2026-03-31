"""
CRITICAL FIXES - Aplicar todas as correções
"""

import re

print("🔧 APLICANDO CORREÇÕES CRÍTICAS...")
print("=" * 60)

# ============================================================
# FIX 1: Adicionar modify_position_sl_tp ao mt5_connector.py
# ============================================================

print("\n1️⃣ Adicionando modify_position_sl_tp...")

mt5_connector_addition = '''

def modify_position_sl_tp(position_ticket: int, symbol: str, new_sl: float = None, new_tp: float = None):
    """
    Modifica SL/TP de uma posição existente
    
    Args:
        position_ticket: Ticket da posição
        symbol: Símbolo
        new_sl: Novo stop loss (None = manter atual)
        new_tp: Novo take profit (None = manter atual)
    
    Returns:
        dict com success=True/False
    """
    # Buscar posição atual
    positions = mt5.positions_get(ticket=position_ticket)
    if not positions or len(positions) == 0:
        return {"success": False, "error": "Position not found"}
    
    position = positions[0]
    
    # Usar valores atuais se não especificado
    if new_sl is None:
        new_sl = position.sl
    if new_tp is None:
        new_tp = position.tp
    
    # Validar SL
    direction = "BUY" if position.type == 0 else "SELL"
    new_sl = validate_sl(symbol, direction, position.price_open, new_sl)
    
    if new_sl == 0.0:
        return {"success": False, "error": "Invalid SL after validation"}
    
    # Preparar request
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": position_ticket,
        "sl": new_sl,
        "tp": new_tp,
    }
    
    result = mt5.order_send(request)
    
    if result is None:
        return {"success": False, "error": "order_send returned None"}
    
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return {
            "success": True,
            "ticket": position_ticket,
            "new_sl": new_sl,
            "new_tp": new_tp
        }
    
    return {
        "success": False,
        "retcode": result.retcode,
        "error": result.comment
    }
'''

# Adicionar ao mt5_connector.py
with open('src/mt5_connector.py', 'r', encoding='utf-8') as f:
    mt5_content = f.read()

if 'modify_position_sl_tp' not in mt5_content:
    with open('src/mt5_connector.py', 'a', encoding='utf-8') as f:
        f.write(mt5_connector_addition)
    print("   ✅ modify_position_sl_tp adicionado")
else:
    print("   ℹ️ modify_position_sl_tp já existe")

# ============================================================
# FIX 2: Adicionar get_position_adds ao PositionManager
# ============================================================

print("\n2️⃣ Adicionando get_position_adds ao PositionManager...")

position_manager_addition = '''
    
    def get_position_adds(self, symbol: str) -> int:
        """
        Retorna número de adds (pyramiding) já feitos numa posição
        
        Args:
            symbol: Símbolo da posição
            
        Returns:
            int: Número de adds (0 se nenhum)
        """
        if symbol not in self.pyramiding_tracker:
            return 0
        
        return self.pyramiding_tracker[symbol].get('adds', 0)
    
    def track_pyramiding_add(self, symbol: str):
        """Registra um add de pyramiding"""
        if symbol not in self.pyramiding_tracker:
            self.pyramiding_tracker[symbol] = {'adds': 0}
        
        self.pyramiding_tracker[symbol]['adds'] += 1
    
    def reset_pyramiding(self, symbol: str):
        """Reset tracking quando posição fecha"""
        if symbol in self.pyramiding_tracker:
            del self.pyramiding_tracker[symbol]
'''

# Adicionar ao position_manager.py
try:
    with open('src/risk/position_manager.py', 'r', encoding='utf-8') as f:
        pm_content = f.read()
    
    if 'get_position_adds' not in pm_content:
        # Procurar fim da classe (antes de fechar)
        # Adicionar antes do último }
        lines = pm_content.split('\n')
        
        # Encontrar última linha não vazia da classe
        insert_pos = len(lines) - 1
        while insert_pos > 0 and not lines[insert_pos].strip():
            insert_pos -= 1
        
        lines.insert(insert_pos + 1, position_manager_addition)
        
        with open('src/risk/position_manager.py', 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        print("   ✅ get_position_adds adicionado")
    else:
        print("   ℹ️ get_position_adds já existe")

except FileNotFoundError:
    print("   ⚠️ position_manager.py não encontrado, continuando...")

# ============================================================
# FIX 3: Adicionar get_max_spread_for_symbol ao settings.py
# ============================================================

print("\n3️⃣ Adicionando get_max_spread_for_symbol...")

settings_addition = '''

# ============================================================
#  SPREAD FILTER
# ============================================================

# Spread máximo por tipo de símbolo (em pontos)
MAX_SPREAD_FOREX = 20       # Pares forex
MAX_SPREAD_CRYPTO = 100     # Crypto
MAX_SPREAD_INDICES = 50     # Índices
MAX_SPREAD_COMMODITIES = 30 # Commodities
MAX_SPREAD_DEFAULT = 30     # Default

def get_max_spread_for_symbol(symbol: str) -> float:
    """
    Retorna spread máximo aceitável para o símbolo
    
    Args:
        symbol: Nome do símbolo (ex: EURUSD, BTCUSD)
        
    Returns:
        float: Spread máximo em pontos
    """
    symbol = symbol.upper()
    
    # Crypto
    if any(x in symbol for x in ['BTC', 'ETH', 'XRP', 'SOL', 'ADA']):
        return MAX_SPREAD_CRYPTO
    
    # Commodities
    if any(x in symbol for x in ['GOLD', 'SILVER', 'OIL', 'GAS']):
        return MAX_SPREAD_COMMODITIES
    
    # Índices
    if any(x in symbol for x in ['SPX', 'NAS', 'DAX', 'FTSE', 'NDX']):
        return MAX_SPREAD_INDICES
    
    # Forex (default)
    if any(x in symbol for x in ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'NZD', 'CAD']):
        return MAX_SPREAD_FOREX
    
    return MAX_SPREAD_DEFAULT
'''

# Adicionar ao settings.py
with open('config/settings.py', 'r', encoding='utf-8') as f:
    settings_content = f.read()

if 'get_max_spread_for_symbol' not in settings_content:
    with open('config/settings.py', 'a', encoding='utf-8') as f:
        f.write(settings_addition)
    print("   ✅ get_max_spread_for_symbol adicionado")
else:
    print("   ℹ️ get_max_spread_for_symbol já existe")

# ============================================================
# FIX 4: Corrigir NaN no dashboard performance_tracker
# ============================================================

print("\n4️⃣ Corrigindo ValueError NaN...")

with open('src/analytics/performance_tracker.py', 'r', encoding='utf-8') as f:
    tracker_content = f.read()

# Substituir cálculo problemático
tracker_content = re.sub(
    r'days = int\(remaining / avg_daily_profit\)',
    '''# Proteger contra divisão por zero e NaN
        if avg_daily_profit > 0 and not np.isnan(avg_daily_profit):
            days = int(remaining / avg_daily_profit)
        else:
            days = 999  # Valor placeholder quando não há dados''',
    tracker_content
)

# Adicionar import numpy se não existe
if 'import numpy as np' not in tracker_content:
    tracker_content = 'import numpy as np\n' + tracker_content

with open('src/analytics/performance_tracker.py', 'w', encoding='utf-8') as f:
    f.write(tracker_content)

print("   ✅ ValueError NaN corrigido")

# ============================================================
# FIX 5: Corrigir erro ORDER_TYPE_ASK no close_position
# ============================================================

print("\n5️⃣ Corrigindo ORDER_TYPE_ASK...")

with open('src/mt5_connector.py', 'r', encoding='utf-8') as f:
    mt5_content = f.read()

# Corrigir linha 199
mt5_content = mt5_content.replace(
    'price      = tick.bid if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_ASK',
    'price      = tick.bid if position.type == mt5.ORDER_TYPE_BUY else tick.ask'
)

with open('src/mt5_connector.py', 'w', encoding='utf-8') as f:
    f.write(mt5_content)

print("   ✅ ORDER_TYPE_ASK corrigido")

# ============================================================
# FIX 6: Adicionar pyramiding_tracker ao __init__
# ============================================================

print("\n6️⃣ Verificando pyramiding_tracker...")

try:
    with open('src/risk/position_manager.py', 'r', encoding='utf-8') as f:
        pm_content = f.read()
    
    if 'self.pyramiding_tracker' not in pm_content:
        # Adicionar no __init__
        pm_content = pm_content.replace(
            'def __init__(self',
            '''def __init__(self,
        # Tracking para pyramiding
        self.pyramiding_tracker = {}'''
        )
        
        with open('src/risk/position_manager.py', 'w', encoding='utf-8') as f:
            f.write(pm_content)
        
        print("   ✅ pyramiding_tracker inicializado")
    else:
        print("   ℹ️ pyramiding_tracker já existe")

except Exception as e:
    print(f"   ⚠️ Erro ao adicionar pyramiding_tracker: {e}")

print("\n" + "=" * 60)
print("✅ TODAS AS CORREÇÕES APLICADAS!")
print("\nAgora executa:")
print("  python run_live.py")
print("=" * 60)
