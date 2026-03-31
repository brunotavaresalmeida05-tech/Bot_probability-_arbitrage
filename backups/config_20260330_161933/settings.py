"""
Configuration Settings - Trading Bot v6
"""

import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# ============================================================
#  MT5 CONNECTION
# ============================================================
MT5_PATH = os.getenv('MT5_PATH', r'C:\Program Files\MetaTrader 5\terminal64.exe')
MT5_LOGIN = int(os.getenv('MT5_LOGIN', '6220103'))
MT5_PASSWORD = os.getenv('MT5_PASSWORD', 'HQPjjy1*')
MT5_SERVER = os.getenv('MT5_SERVER', 'ActivTradesCorp-Server')

# ============================================================
#  TRADING PARAMETERS
# ============================================================
TIMEFRAME = 'M5'
LOOKBACK_BARS = 500
Z_ENTRY = 1.8
Z_ENTER = 1.8
Z_EXIT = 0.3
Z_STOP = 3.5
MA_PERIOD = 50
MA_TYPE = 'SMA'  # ADICIONAR ESTA LINHA (ou 'EMA')
STD_PERIOD = 20
STDDEV_PERIOD = 20
ATR_PERIOD = 50
ATR_BASE_PERIOD = 50
SL_ATR_MULT = 2.0

# Risk Management
MAX_RISK_PER_TRADE = 0.02
MAX_POSITIONS = 5
POSITION_SIZE = 0.01

# Magic Number
MAGIC_NUMBER = 123456
MAX_SLIPPAGE = 3

# ============================================================
#  LOOP & TIMING
# ============================================================
LOOP_INTERVAL_SECONDS = 10
FAST_TICK_INTERVAL_MS = 200

# ============================================================
#  SYMBOLS - APENAS OS QUE FUNCIONAM
# ============================================================
ALL_AVAILABLE_SYMBOLS = [
    # Forex (11)
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF", 
    "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "AUDJPY",
    
    # Metais (2)
    "GOLD", "SILVER",
    
    # Crypto (4)
    "BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD",
]

# ============================================================
#  SYMBOLS ALIAS
# ============================================================
SYMBOLS = ALL_AVAILABLE_SYMBOLS  # Alias para compatibilidade

# ============================================================
#  FEATURES - SIMPLIFICADO
# ============================================================
USE_REGIME_FILTER = False       # DESATIVADO
USE_NEWS_FILTER = False          # DESATIVADO
USE_MULTI_API_CONSENSUS = False  # DESATIVADO
MONITOR_API_HEALTH = False       # DESATIVADO
USE_DATA_QUALITY_SCORER = False  # DESATIVADO

# Multi-strategy
USE_MULTI_STRATEGY = True

# Analytics
USE_PERFORMANCE_ANALYTICS = True
USE_TRADE_LOGGER = True

# ============================================================
#  ASSET METRICS (limpo)
# ============================================================
ASSET_METRICS = {
    # Forex
    "EURUSD": {"sharpe": 0.84, "win_rate": 0.55, "avg_return": 0.061, "total_trades": 187},
    "GBPUSD": {"sharpe": 0.81, "win_rate": 0.54, "avg_return": 0.058, "total_trades": 186},
    "USDJPY": {"sharpe": 0.73, "win_rate": 0.52, "avg_return": 0.052, "total_trades": 249},
    "AUDUSD": {"sharpe": 1.77, "win_rate": 0.59, "avg_return": 0.137, "total_trades": 190},
    "USDCHF": {"sharpe": 1.41, "win_rate": 0.58, "avg_return": 0.101, "total_trades": 187},
    "USDCAD": {"sharpe": 2.54, "win_rate": 0.62, "avg_return": 0.146, "total_trades": 152},
    "NZDUSD": {"sharpe": -0.21, "win_rate": 0.48, "avg_return": -0.016, "total_trades": 215},
    "EURGBP": {"sharpe": 6.00, "win_rate": 0.68, "avg_return": 0.314, "total_trades": 128},
    "EURJPY": {"sharpe": -0.23, "win_rate": 0.49, "avg_return": -0.011, "total_trades": 151},
    "GBPJPY": {"sharpe": 2.24, "win_rate": 0.61, "avg_return": 0.126, "total_trades": 162},
    "AUDJPY": {"sharpe": -0.15, "win_rate": 0.49, "avg_return": -0.009, "total_trades": 163},
    
    # Metais
    "GOLD": {"sharpe": -0.98, "win_rate": 0.47, "avg_return": -0.055, "total_trades": 167},
    "SILVER": {"sharpe": -1.15, "win_rate": 0.46, "avg_return": -0.071, "total_trades": 201},
    
    # Crypto
    "BTCUSD": {"sharpe": -0.73, "win_rate": 0.47, "avg_return": -0.035, "total_trades": 111},
    "ETHUSD": {"sharpe": 0.29, "win_rate": 0.50, "avg_return": 0.010, "total_trades": 91},
    "XRPUSD": {"sharpe": 1.07, "win_rate": 0.55, "avg_return": 0.053, "total_trades": 119},
    "SOLUSD": {"sharpe": 0.70, "win_rate": 0.52, "avg_return": 0.030, "total_trades": 120},
}

# ============================================================
#  API KEYS
# ============================================================
FRED_API_KEY = os.getenv('FRED_API_KEY', '583922c6e7d2a106ee1eae29a70b90e0')
ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_KEY', '4F1D7CD56E2X2NE1')
POLYGON_KEY = os.getenv('POLYGON_KEY', '2nC3wlQs0AVj8wF3kgT5jcyCNiIaB2iB')
TWELVE_DATA_KEY = os.getenv('TWELVE_DATA_KEY', '2e602e1a9694451da0218f15a9f47bad')
FIXER_KEY = os.getenv('FIXER_KEY', 'f47da607354dec69586e1af564bb7221')
EODHD_KEY = os.getenv('EODHD_KEY', '69bdafa2818c60.63828076')
NEWSAPI_KEY = os.getenv('NEWSAPI_KEY', '3c7be108d2bc47c18e36e5437a76c632')
FINNHUB_KEY = os.getenv('FINNHUB_KEY', 'd6uquh1r01qig545jabgd6uquh1r01qig545jac0')
MARKETAUX_KEY = os.getenv('MARKETAUX_KEY', 'Bc02zKl6R48yom6AtBEfSgMTBj9WMjM1jrRTGHVY')
CURRENTS_KEY = os.getenv('CURRENTS_KEY', 'p1ZOufwZzjpunAkPmVDqYU5-Q0Q7XFl_sWRr9rFW5f1bc7Gs')
MEDIASTACK_KEY = os.getenv('MEDIASTACK_KEY', 'fccc2bb417afb7ec2b7a79d6d98100de')
CRYPTOPANIC_KEY = os.getenv('CRYPTOPANIC_KEY', '8e33959127c1a228ef55177e1c8ef5d177edb1a7')
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', 'q1gbM0TxW5ifubXLEdR7Y6btNEKHeiGd9767WKPtxOz9fSopVwz7lO1M93koRBIV')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')
COINGECKO_KEY = os.getenv('COINGECKO_KEY', 'CG-mKgvMyY9dA9CoW4cPEtG6PGd')
ETHERSCAN_KEY = os.getenv('ETHERSCAN_KEY', 'RNWS7AIBRZEVBRUYZ9GG2Y6VSNEFSEYWM3')

# ============================================================
#  STRATEGY ALLOCATION
# ============================================================
STRATEGY_ALLOCATION = {
    'pairs': 0.20,
    'trend': 0.25,
    'breakout': 0.20,
    'volatility': 0.15,
    'news': 0.10,
    'mean_reversion': 0.10
}

# ============================================================
#  NOTIFICATIONS (DESATIVADO)
# ============================================================
TELEGRAM_ENABLED = False
EMAIL_ENABLED = False

# ============================================================
#  LOGGING
# ============================================================
LOG_DIR = 'logs'
CSV_LOG_FILE = 'logs/trades.csv'

# ============================================================
#  PATHS
# ============================================================
DATA_DIR = 'data'
MODELS_DIR = 'models'

# ============================================================
#  DASHBOARD
# ============================================================
DASHBOARD_PORT = 8765
DASHBOARD_HOST = '127.0.0.1'

# ============================================================
#  OPTIMIZER
# ============================================================
USE_OPTIMIZER = True
OPTIMIZER_ENABLED = True  # Alias
OPTIMIZER_COMBINATIONS = 200
OPTIMIZER_WALK_FORWARD = True
OPTIMIZER_MAX_TRIALS = 50
OPTIMIZER_LOOKBACK = 1000
OPTIMIZER_INTERVAL_H = 24
OPTIMIZER_GRID = {
    "MA_PERIOD": [20, 50, 100],
    "STDDEV_PERIOD": [10, 20, 30],
    "Z_ENTER": [1.5, 2.0, 2.5],
    "Z_EXIT": [0.2, 0.5, 0.8],
    "Z_STOP": [3.0, 3.5, 4.0]
}

# ============================================================
#  TIMEFRAMES
# ============================================================
TIMEFRAME_M5 = 'M5'
TIMEFRAME_H1 = 'H1'
TIMEFRAME_D1 = 'D1'

# ============================================================
#  CORRELATION
# ============================================================
CORRELATION_THRESHOLD = 0.7
MAX_CORRELATED_POSITIONS = 3

# ============================================================
#  PORTFOLIO
# ============================================================
TOTAL_CAPITAL = 500.0
RISK_PER_ASSET = 0.10

# ============================================================
#  NEWS SOURCES (quando reativar)
# ============================================================
NEWS_SOURCES = {
    'newsapi': False,
    'finnhub': True,
    'marketaux': True,
    'currents': False,
    'mediastack': True,
    'cryptopanic': False
}

# ============================================================
#  DATA SOURCES WEIGHTS (quando reativar)
# ============================================================
DATA_SOURCE_WEIGHTS = {
    'crypto': {
        'binance': 0.60,
        'coingecko': 0.40,
    },
    'forex': {
        'twelve_data': 0.60,
        'fixer': 0.40,
    },
    'stocks': {
        'polygon': 0.50,
        'eodhd': 0.50,
    }
}

# ============================================================
#  CONSENSUS
# ============================================================
CONSENSUS_MIN_SOURCES = 2
CONSENSUS_MIN_CONFIDENCE = 0.80

# ============================================================
#  FILTERS & PROTECTIONS
# ============================================================

# Time Filter (horários de trading)
USE_TIME_FILTER = False  # ADICIONAR

# Macro Score Blocking
MACRO_BLOCK_SCORE = -50  # ADICIONAR (score mínimo para permitir trades)

# ============================================================
#  ARBITRAGE / STAT-ARB PARAMETERS
# ============================================================
ARB_Z_ENTER = 2.0           # Z-score para entrar no par
ARB_Z_EXIT = 0.5            # Z-score para fechar posição
ARB_Z_STOP = 4.0            # Z-score stop-loss
ARB_MIN_CORRELATION = 0.7   # Correlação mínima entre pares

# ============================================================
#  ARBITRAGE
# ============================================================
ARB_EXTRA_SYMBOLS = []  # Símbolos extras para arbitragem (vazio por agora)
USE_ARBITRAGE = False   # Desativado por agora
TRIANGULAR_ARB_ENABLED = False

# ============================================================
#  MULTI-TIMEFRAME
# ============================================================
USE_MULTI_TIMEFRAME = True
MTF_TIMEFRAMES = ['M5', 'H1', 'D1']

# ============================================================
#  PORTFOLIO MANAGER
# ============================================================
USE_PORTFOLIO_MANAGER = True

# ============================================================
#  MACRO ENGINE
# ============================================================
USE_MACRO_ENGINE = True
MACRO_LAYERS = 7

# ============================================================
#  PROFESSIONAL CAPITAL SCALING
# ============================================================

# Compounding Strategy
USE_COMPOUNDING = True
TARGET_MONTHLY_RETURN = 0.15  # 15% conservador (ou 0.25 agressivo)
INITIAL_CAPITAL = 464.63  # Capital inicial atual

# Kelly Criterion
USE_KELLY_SIZING = True
KELLY_MIN_TRADES = 30  # Mínimo de trades para calcular Kelly

# Anti-Martingale (scale winners)
USE_ANTI_MARTINGALE = True
ANTI_MARTINGALE_MAX_MULTIPLIER = 4.0

# Pyramiding (adicionar em vencedores)
PYRAMIDING_ENABLED = True
PYRAMIDING_MAX_ADDS = 3
PYRAMIDING_MIN_PROFIT_PCT = 0.02  # 2%
PYRAMIDING_SIZE_MULTIPLIER = 0.5  # Cada add = 50% do inicial

# Volatility Scaling
USE_VOLATILITY_SCALING = True
VOLATILITY_SCALING_MIN = 0.5
VOLATILITY_SCALING_MAX = 2.0

# ============================================================
#  PRICE ACTION STRATEGIES
# ============================================================

# Supply/Demand Zones
USE_SUPPLY_DEMAND = True
SUPPLY_DEMAND_ZONE_STRENGTH = 2  # Mínimo touches
SUPPLY_DEMAND_ZONE_AGE = 50  # Máximo bars idade
SUPPLY_DEMAND_MIN_MOVE = 0.015  # 1.5% movimento mínimo

# Pin Bar Reversals
USE_PIN_BAR = True
PIN_BAR_SHADOW_RATIO = 2.0  # Shadow > 2x body
PIN_BAR_SHADOW_PCT = 0.60  # Shadow > 60% total
PIN_BAR_Z_THRESHOLD = 2.0  # Só em extremos Z > 2.0

# ============================================================
#  ADVANCED PRICE ACTION STRATEGIES
# ============================================================

# Inside Bar Breakout
USE_INSIDE_BAR = True
INSIDE_BAR_MIN_MOTHER = 0.003  # 30 pips mínimo
INSIDE_BAR_MAX_RATIO = 0.70    # Inside <= 70% mother
INSIDE_BAR_BUFFER = 0.0001     # Buffer breakout

# Engulfing Patterns
USE_ENGULFING = True
ENGULFING_MIN_BODY = 0.60      # Corpo >= 60% da vela
ENGULFING_MARGIN = 1.05        # Engolfar 105%
ENGULFING_Z_THRESHOLD = 1.5    # Só em extremos

# Fibonacci Retracements
USE_FIBONACCI = True
FIB_LOOKBACK_SWING = 50        # Bars para swing
FIB_TOLERANCE = 0.0005         # 5 pips tolerância
FIB_KEY_LEVELS = [0.382, 0.500, 0.618]  # Níveis principais

# ============================================================
#  AUTOMATION & NOTIFICATIONS
# ============================================================

# Telegram
USE_TELEGRAM = True
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"

# Email (opcional)
USE_EMAIL = False
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587
EMAIL_FROM = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"
EMAIL_TO = "your_email@gmail.com"

# Auto-restart
AUTO_RESTART_ENABLED = True
MAX_RESTARTS = 5
RESTART_COOLDOWN_MIN = 5

# Daily reports
DAILY_REPORT_ENABLED = True
REPORT_TIME_HOUR = 23  # 23:00

# Config backup
AUTO_BACKUP_ENABLED = True
BACKUP_INTERVAL_HOURS = 24
