"""
Fix Timestamp Issue
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Configurações do MT5 do arquivo .env ou padrão
login = int(os.getenv("MT5_LOGIN", 6220103))
password = os.getenv("MT5_PASSWORD", "HQPjjy1*")
server = os.getenv("MT5_SERVER", "ActivTradesCorp-Server")

# Conectar MT5
if not mt5.initialize(login=login, password=password, server=server):
    print("❌ MT5 não iniciou")
    print(f"Erro: {mt5.last_error()}")
    exit()

# Testar obter dados
symbol = "EURUSD"
# Tenta encontrar o símbolo correto (pode ter sufixo na ActivTrades)
symbols = mt5.symbols_get(group="*EURUSD*")
if symbols:
    symbol = symbols[0].name
    print(f"✅ Símbolo encontrado: {symbol}")

timeframe = mt5.TIMEFRAME_M5
bars = 100

print(f"📊 Testando {symbol}...")

# Obter dados
rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)

if rates is None:
    print(f"❌ Sem dados para {symbol}")
    print(f"Erro MT5: {mt5.last_error()}")
else:
    # Converter para DataFrame
    df = pd.DataFrame(rates)
    
    print(f"✅ Obtidos {len(df)} barras")
    print(f"\nColunas: {list(df.columns)}")
    print(f"\nPrimeiras linhas:")
    print(df.head())
    
    # Verificar se tem 'time'
    if 'time' in df.columns:
        print(f"\n✅ Coluna 'time' existe")
        print(f"Tipo: {df['time'].dtype}")
        print(f"Exemplo: {df['time'].iloc[0]}")
        
        # Converter timestamp
        df['timestamp'] = pd.to_datetime(df['time'], unit='s')
        print(f"\n✅ Timestamp criado:")
        print(df[['time', 'timestamp']].head())
    else:
        print(f"\n❌ Coluna 'time' NÃO existe!")

mt5.shutdown()
