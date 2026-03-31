"""
Script para ajustar Stop Loss dos trades em drawdown
Protege lucros e limita perdas dinamicamente (Sem dependências externas para ATR)
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

def calculate_atr(symbol, period=14):
    """Calcula ATR atual manualmente para evitar problemas de versão do Python"""
    # Pegar candles suficientes para o cálculo
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, period + 1)
    if rates is None or len(rates) < period + 1:
        return None
    
    df = pd.DataFrame(rates)
    
    # Cálculo do True Range (TR)
    df['prev_close'] = df['close'].shift(1)
    df['tr1'] = df['high'] - df['low']
    df['tr2'] = abs(df['high'] - df['prev_close'])
    df['tr3'] = abs(df['low'] - df['prev_close'])
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    # ATR (Média Móvel Simples do TR para os últimos n períodos)
    atr = df['tr'].tail(period).mean()
    return atr

def adjust_stops_to_breakeven():
    """
    Move SL para breakeven em trades com lucro
    Aperta SL em trades com perda > €2
    """
    if not mt5.initialize():
        print("❌ Falha ao inicializar MT5")
        return
    
    positions = mt5.positions_get()
    if not positions:
        print("ℹ️ Sem posições abertas")
        mt5.shutdown()
        return
    
    print(f"\n🔍 Analisando {len(positions)} posições...\n")
    
    adjusted_count = 0
    
    for pos in positions:
        symbol = pos.symbol
        ticket = pos.ticket
        entry_price = pos.price_open
        current_price = pos.price_current
        sl = pos.sl
        tp = pos.tp
        pos_type = pos.type  # 0=BUY, 1=SELL
        profit = pos.profit
        
        # Calcular ATR manual
        atr = calculate_atr(symbol)
        if atr is None:
            print(f"⚠️ {symbol} - Dados insuficientes para ATR, pulando...")
            continue
        
        # Obter info do símbolo
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            continue
        
        point = symbol_info.point
        
        print(f"📊 {symbol} {'BUY' if pos_type == 0 else 'SELL'} | "
              f"P&L: €{profit:.2f} | Entry: {entry_price:.5f} | ATR: {atr:.5f}")
        
        # ESTRATÉGIA 1: Move para breakeven se lucro > €0.50
        if profit > 0.50:
            if pos_type == 0:  # BUY
                new_sl = entry_price + (5 * point)
                if sl == 0 or new_sl > sl:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": symbol,
                        "position": ticket,
                        "sl": new_sl,
                        "tp": tp
                    }
                    result = mt5.order_send(request)
                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"  ✅ SL → BREAKEVEN: {new_sl:.5f}")
                        adjusted_count += 1
            else:  # SELL
                new_sl = entry_price - (5 * point)
                if sl == 0 or new_sl < sl:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": symbol,
                        "position": ticket,
                        "sl": new_sl,
                        "tp": tp
                    }
                    result = mt5.order_send(request)
                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"  ✅ SL → BREAKEVEN: {new_sl:.5f}")
                        adjusted_count += 1
        
        # ESTRATÉGIA 2: Apertar SL em trades negativos (> €2 loss)
        elif profit < -2.0:
            if pos_type == 0:  # BUY
                new_sl = current_price - (1.5 * atr)
                if sl == 0 or new_sl > sl:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": symbol,
                        "position": ticket,
                        "sl": new_sl,
                        "tp": tp
                    }
                    result = mt5.order_send(request)
                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"  ⚠️ SL APERTADO: {new_sl:.5f}")
                        adjusted_count += 1
            else:  # SELL
                new_sl = current_price + (1.5 * atr)
                if sl == 0 or new_sl < sl:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": symbol,
                        "position": ticket,
                        "sl": new_sl,
                        "tp": tp
                    }
                    result = mt5.order_send(request)
                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"  ⚠️ SL APERTADO: {new_sl:.5f}")
                        adjusted_count += 1
    
    print(f"\n✅ Concluído! {adjusted_count} stop(s) ajustado(s).\n")
    mt5.shutdown()

def close_worst_trade():
    """Fecha o trade com maior perda"""
    if not mt5.initialize(): return
    positions = mt5.positions_get()
    if not positions:
        mt5.shutdown()
        return
    
    worst = min(positions, key=lambda p: p.profit)
    if worst.profit >= 0:
        print("✅ Nenhum trade em perda!")
        mt5.shutdown()
        return
    
    print(f"\n🎯 Pior Trade: {worst.symbol} | P&L: €{worst.profit:.2f}")
    confirm = input("❓ Confirmar fechamento? (s/n): ")
    if confirm.lower() == 's':
        close_type = mt5.ORDER_TYPE_SELL if worst.type == 0 else mt5.ORDER_TYPE_BUY
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": worst.symbol,
            "volume": worst.volume,
            "type": close_type,
            "position": worst.ticket,
            "magic": 123456,
            "comment": "Manual close",
            "type_filling": mt5.ORDER_FILLING_IOC
        }
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"✅ Fechado! Loss: €{worst.profit:.2f}")
    mt5.shutdown()

def show_positions():
    """Mostra todas as posições atuais"""
    if not mt5.initialize(): return
    positions = mt5.positions_get()
    if not positions:
        print("\nℹ️ Sem posições abertas.\n")
        mt5.shutdown()
        return
    
    print(f"\n📊 POSIÇÕES ABERTAS ({len(positions)}):\n")
    print(f"{'Símbolo':<10} {'Tipo':<6} {'P&L (€)':<10} {'Entry':<12}")
    print("-" * 45)
    total = 0
    for p in positions:
        tipo = 'BUY' if p.type == 0 else 'SELL'
        print(f"{p.symbol:<10} {tipo:<6} {p.profit:>9.2f} {p.price_open:>11.5f}")
        total += p.profit
    print("-" * 45)
    print(f"TOTAL: {total:>9.2f} €\n")
    mt5.shutdown()

if __name__ == "__main__":
    print("╔════════════════════════════════════════╗")
    print("║  🛡️ AJUSTE DE STOP LOSS - V6 (V3.14) ║")
    print("╚════════════════════════════════════════╝")
    print("\n1. 🔒 Proteger lucros\n2. ⚠️ Apertar perdas\n3. 🎯 AMBOS\n4. ❌ Fechar PIOR trade\n5. 📊 Ver posições\n6. 🚪 SAIR")
    
    choice = input("\n👉 Opção: ")
    if choice in ["1", "2", "3"]:
        adjust_stops_to_breakeven()
    elif choice == "4":
        close_worst_trade()
    elif choice == "5":
        show_positions()
    else:
        print("Saindo...")
