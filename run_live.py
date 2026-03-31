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
