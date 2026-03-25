import MetaTrader5 as mt5

mt5.initialize()

all_symbols = [s.name for s in mt5.symbols_get()]
gold = [s for s in all_symbols if any(x in s.upper() for x in ["GOLD", "XAU"])]
silver = [s for s in all_symbols if any(x in s.upper() for x in ["SILVER", "XAG"])]
oil = [s for s in all_symbols if "OIL" in s.upper()]

print("\n🪙 OURO:", gold)
print("🥈 PRATA:", silver) 
print("🛢️  PETRÓLEO:", oil)

mt5.shutdown()
