"""
Trading Bot v6 - Live Runner
Simplified launcher with all protections disabled for immediate trading
"""

import sys
import os

# Force live mode
os.environ['TRADING_MODE'] = 'live'

# Import main
from src.main import main

# ── Dashboard real-time data feed ──────────────────────────
try:
    from live_state_writer import LiveStateWriter as _LSW
    _writer = _LSW()
    _DASHBOARD_FEED = True
except Exception:
    _DASHBOARD_FEED = False
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("="*60)
    print("🚀 TRADING BOT V6 - MODO LIVE SIMPLIFICADO")
    print("="*60)
    print("✅ News Filter: DESATIVADO")
    print("✅ Regime Filter: DESATIVADO")
    print("✅ API Consensus: DESATIVADO")
    print("✅ Entrada: Z-score = 1.8 (permissivo)")
    print("✅ Max Posições: 5")
    print("="*60)
    print()
    
    main()


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
