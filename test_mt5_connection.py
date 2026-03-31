"""
Test MT5 Connection
"""

import MetaTrader5 as mt5
from datetime import datetime

print("="*60)
print("🧪 TESTE DE CONEXÃO MT5")
print("="*60)

# Inicializar
print("\n1. Tentando inicializar MT5...")
if not mt5.initialize():
    print("❌ ERRO: MT5 não inicializou")
    print(f"   Error code: {mt5.last_error()}")

    # Tentar com path explícito
    print("\n2. Tentando com path explícito...")
    mt5_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"

    if not mt5.initialize(path=mt5_path):
        print(f"❌ ERRO: Não conseguiu inicializar mesmo com path")
        print(f"   Error: {mt5.last_error()}")
        exit()

print("✅ MT5 inicializado com sucesso!")

# Verificar versão
version = mt5.version()
print(f"\n✅ MT5 Version: {version}")

# Login
print("\n3. Tentando fazer login...")
login = 6220103
password = "HQPjjy1*"
server = "ActivTradesCorp-Server"

authorized = mt5.login(login, password, server)

if not authorized:
    print(f"❌ ERRO: Login falhou")
    print(f"   Error: {mt5.last_error()}")
    mt5.shutdown()
    exit()

print("✅ Login bem-sucedido!")

# Informação da conta
account_info = mt5.account_info()
if account_info is None:
    print("❌ ERRO: Não conseguiu obter info da conta")
else:
    print("\n" + "="*60)
    print("📊 INFORMAÇÃO DA CONTA")
    print("="*60)
    print(f"Login: {account_info.login}")
    print(f"Balance: €{account_info.balance:.2f}")
    print(f"Equity: €{account_info.equity:.2f}")
    print(f"Margin Free: €{account_info.margin_free:.2f}")
    print(f"Server: {account_info.server}")
    print(f"Leverage: 1:{account_info.leverage}")

# Testar obter dados
print("\n" + "="*60)
print("📈 TESTE DE DADOS")
print("="*60)

symbol = "EURUSD"
print(f"\nTestando símbolo: {symbol}")

# Verificar se símbolo existe
symbol_info = mt5.symbol_info(symbol)
if symbol_info is None:
    print(f"❌ Símbolo {symbol} não encontrado")
else:
    print(f"✅ Símbolo encontrado: {symbol}")
    print(f"   Bid: {symbol_info.bid}")
    print(f"   Ask: {symbol_info.ask}")
    print(f"   Spread: {symbol_info.spread}")

# Tentar obter rates
rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 10)
if rates is None:
    print(f"❌ Não conseguiu obter rates")
    print(f"   Error: {mt5.last_error()}")
else:
    print(f"✅ Obtidos {len(rates)} barras")
    print(f"   Última: {datetime.fromtimestamp(rates[-1][0])}")
    print(f"   Close: {rates[-1][4]}")

# Shutdown
mt5.shutdown()
print("\n" + "="*60)
print("✅ TESTE CONCLUÍDO")
print("="*60)
