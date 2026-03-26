# ============================================================
#  config/settings.py  —  v5  (índices + metais + MTF + portfólio)
# ============================================================

# --- MT5 ---------------------------------------------------
MT5_PATH     = r"C:\Program Files\MetaTrader 5 - ActivTrades\terminal64.exe"
MT5_LOGIN    = 6212361
MT5_PASSWORD = "AZZmmp5?"
MT5_SERVER   = "ActivTradesCorp-Server"

# --- API Keys ----------------------------------------------
FRED_API_KEY      = "583922c6e7d2a106ee1eae29a70b90e0"
POLYGON_KEY       = "2nC3wlQs0AVj8wF3kgT5jcyCNiIaB2iB"
ALPHA_VANTAGE_KEY = "4F1D7CD56E2X2NE1"
TWELVE_DATA_KEY   = "2e602e1a9694451da0218f15a9f47bad"
FIXER_KEY         = "f47da607354dec69586e1af564bb7221"
EODHD_KEY         = "69bdafa2818c60.63828076"
NEWSAPI_KEY       = "3c7be108d2bc47c18e36e5437a76c632"
FINNHUB_KEY       = "d6uquh1r01qig545jabgd6uquh1r01qig545jac0"
MARKETAUX_KEY     = "Bc02zKl6R48yom6AtBEfSgMTBj9WMjM1jrRTGHVY"
CURRENTS_KEY      = "p1ZOufwZzjpunAkPmVDqYU5-Q0Q7XFl_sWRr9rFW5f1bc7Gs"
MEDIASTACK_KEY    = "fccc2bb417afb7ec2b7a79d6d98100de"
CRYPTOPANIC_KEY   = "8e33959127c1a228ef55177e1c8ef5d177edb1a7"
BINANCE_API_KEY   = "q1gbM0TxW5ifubXLEdR7Y6btNEKHeiGd9767WKPtxOz9fSopVwz7lO1M93koRBIV"
COINGECKO_KEY     = "CG-mKgvMyY9dA9CoW4cPEtG6PGd"
ETHERSCAN_KEY     = "RNWS7AIBRZEVBRUYZ9GG2Y6VSNEFSEYWM3"

# --- Fontes de dados ----------------------------------------
USE_POLYGON_DATA  = False   # plano free não tem intraday
USE_FRED_DATA     = True
USE_NEWSAPI       = True
USE_ALPHA_VANTAGE = True
USE_MACRO_ENGINE  = True
USE_FINNHUB       = True
USE_MARKETAUX     = True
USE_CURRENTS      = True
USE_EODHD         = True

# --- Módulos -----------------------------------------------
USE_MULTI_TIMEFRAME  = True    # análise M5+H1+D1
USE_PORTFOLIO_MANAGER = True   # gestão de correlações
USE_TRIANGULAR_ARB   = True    # arbitragem triangular FX
USE_MULTI_STRATEGY   = True    # sistema multi-estratégia (Pairs, Trend, Breakout, etc.)

# --- Símbolos Mean Reversion (FX) --------------------------
SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
]

# --- Índices CFD (descomenta se a tua corretora tiver) ------
# Verifica o nome exacto no MT5: pode ser "SP500", "US500", etc.
INDICES_SYMBOLS = [
    # "US500",    # S&P 500
    # "US100",    # Nasdaq 100
    # "GER40",    # DAX 40
    # "UK100",    # FTSE 100
]

# --- Metais CFD --------------------------------------------
METALS_SYMBOLS = [
    # "XAUUSD",   # Ouro
    # "XAGUSD",   # Prata
]

# Todos os símbolos activos (FX + índices + metais)
ALL_SYMBOLS = SYMBOLS + INDICES_SYMBOLS + METALS_SYMBOLS

# --- Símbolos extra ARB ------------------------------------
ARB_EXTRA_SYMBOLS = [
    "USDCHF", "USDCAD", "NZDUSD", "EURGBP",
    "EURJPY", "GBPJPY", "AUDJPY",
]

# --- Multi-Timeframe ---------------------------------------
MTF_TIMEFRAMES = ["M5", "H1", "D1"]   # do mais rápido ao mais lento
MTF_MIN_AGREEMENT = 2                 # mínimo de TFs que devem concordar

# --- Timeframe principal (entrada) -------------------------
TIMEFRAME = "M5"

# --- Sessão ------------------------------------------------
SESSION_START_HOUR = 0
SESSION_END_HOUR   = 24

# Horário 24/7 para crypto
SYMBOLS_24_7 = ["BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD"]

# --- Parâmetros Mean Reversion ----------------------------
MA_PERIOD       = 100
MA_TYPE         = "SMA"
STDDEV_PERIOD   = 50
USE_STDDEV      = True
ATR_PERIOD      = 50
ATR_MULT_FOR_Z  = 1.0
ATR_BASE_PERIOD = 200

Z_ENTER = 2.0
Z_EXIT  = 0.7
Z_STOP  = 3.5

USE_Z_STOP   = True
USE_ATR_STOP = False
SL_ATR_MULT  = 2.0

# --- Parâmetros ARB ----------------------------------------
ARB_TRADING_ENABLED  = True
ARB_PAPER_MODE       = False
ARB_MIN_CORRELATION  = 0.70
ARB_MAX_PAIRS        = 8
ARB_Z_ENTER          = 2.0
ARB_Z_EXIT           = 0.5
ARB_Z_STOP           = 3.5
ARB_RISK_PCT         = 0.3
ARB_SL_ATR_MULT      = 2.0

# --- Arbitragem Triangular ---------------------------------
TRIANGULAR_ARB_ENABLED  = False
TRIANGULAR_ARB_MIN_PROFIT = 0.0003   # mínimo 0.3 pips de lucro após custos
TRIANGULAR_ARB_PAPER     = True      # True = só detecta, não executa

# --- Macro Engine ------------------------------------------
MACRO_REFRESH_INTERVAL = 300
MACRO_BLOCK_SCORE      = -0.6
MACRO_LOT_MAX_MULT     = 1.5
MACRO_LOT_MIN_MULT     = 0.5

# --- Portfolio Manager -------------------------------------
MAX_TOTAL_RISK_PCT        = 6.0    # risco total máximo em aberto
MAX_CURRENCY_EXPOSURE_PCT = 3.0    # exposição máxima por moeda
MAX_CORR_THRESHOLD        = 0.70   # correlação máxima entre posições

# --- Optimizador -------------------------------------------
OPTIMIZER_ENABLED    = True
OPTIMIZER_INTERVAL_H = 24
OPTIMIZER_MAX_TRIALS = 200
OPTIMIZER_METRIC     = "sharpe"
OPTIMIZER_LOOKBACK   = 252

OPTIMIZER_GRID = {
    "MA_PERIOD":     [50, 80, 100, 150, 200],
    "STDDEV_PERIOD": [20, 30, 50, 70],
    "Z_ENTER":       [1.5, 1.8, 2.0, 2.2, 2.5],
    "Z_EXIT":        [0.3, 0.5, 0.7, 1.0],
    "Z_STOP":        [3.0, 3.5, 4.0],
}

# --- Risk Management ---------------------------------------
RISK_PER_TRADE_PCT     = 0.5
MAX_DAILY_LOSS_PCT     = 4.0
MAX_TRADES_PER_DAY     = 30
MAX_CONSECUTIVE_LOSSES = 5

# --- Filtros -----------------------------------------------
MAX_SPREAD_POINTS  = 20.0

# Spreads por categoria
def get_max_spread_for_symbol(symbol):
    """Spread máximo baseado no tipo de ativo."""
    symbol_upper = symbol.upper()

    # Crypto: spreads MUITO altos
    if any(c in symbol_upper for c in ["BTC", "ETH", "XRP", "SOL"]):
        return 15000.0

    # Índices
    if any(i in symbol_upper for i in ["US500", "US100", "UK100", "GER40", "JP225"]):
        return 500.0

    # Metais
    if any(m in symbol_upper for m in ["XAU", "XAG", "GOLD", "SILVER"]):
        return 100.0

    # Commodities
    if any(c in symbol_upper for c in ["OIL", "NGAS", "BRENT", "WTI"]):
        return 150.0

    # FX Crosses com JPY
    if "JPY" in symbol_upper:
        return 30.0

    # FX Majors
    return 20.0

USE_TIME_FILTER    = True
NO_TRADE_WINDOW_1  = (0, 0)
NO_TRADE_WINDOW_2  = (0, 0)
ATR_MIN_MULT       = 0.5
ATR_MAX_MULT       = 3.0

# --- Logging -----------------------------------------------
LOG_DIR      = "logs"
CSV_LOG_FILE = "logs/trades.csv"
LOG_LEVEL    = "INFO"

# --- Magic numbers -----------------------------------------
MAGIC_NUMBER = 20240101  # mean reversion
# ARB usa MAGIC_NUMBER+1, triangular usa MAGIC_NUMBER+2

# --- Loop --------------------------------------------------
LOOP_INTERVAL_SECONDS = 10

# ============================================================
#  MULTI-STRATEGY SYSTEM
# ============================================================

# Estratégias habilitadas
ENABLED_STRATEGIES = [
    'pairs',         # Pairs Trading
    'trend',         # Trend Following
    'breakout',      # Breakout
    'volatility',    # Volatility Arbitrage
    'news'           # News Trading
]

# Alocação de capital por estratégia (%)
STRATEGY_ALLOCATION = {
    'mean_reversion': 10,  # Estratégia existente
    'pairs': 20,
    'trend': 25,
    'breakout': 20,
    'volatility': 15,
    'news': 10
}

# ============================================================
#  PORTFOLIO ALLOCATION - SISTEMA SEM LIMITES
# ============================================================

USE_DYNAMIC_ALLOCATION = True  # ⭐ Ativar sistema novo

# Risk total máximo (% do capital)
MAX_TOTAL_RISK_PCT = 10.0  # 10% do capital em risco total

# Sharpe mínimo para alocar capital
MIN_SHARPE_THRESHOLD = -2.0  # Permite TODOS operarem (até negativos)

# Método de alocação
ALLOCATION_METHOD = "sharpe_weighted"  # Ativos melhores = mais capital

# Rebalanceamento automático
REBALANCE_INTERVAL_HOURS = 24  # Rebalancea a cada 24h

# ============================================================
#  TODOS OS ATIVOS DISPONÍVEIS (SEM LIMITES!)
# ============================================================

ALL_AVAILABLE_SYMBOLS = [
    # ========================================
    # A. FX MAJORS (7 pares - Alta Liquidez)
    # ========================================
    "EURUSD",   # Sharpe 0.84
    "GBPUSD",   # Sharpe 0.81
    "USDJPY",   # Sharpe 0.73
    "AUDUSD",   # Sharpe 1.77 (TOP 4)
    "USDCHF",   # Sharpe 1.41 (TOP 5)
    "USDCAD",   # Sharpe 2.54 (TOP 2)
    "NZDUSD",   # Sharpe -0.21 (fraco mas diversifica)

    # ========================================
    # B. FX CROSSES (4 pares)
    # ========================================
    "EURGBP",   # Sharpe 6.00 (CAMPEÃO!)
    "EURJPY",   # Sharpe -0.23 (fraco)
    "GBPJPY",   # Sharpe 2.24 (TOP 3)
    "AUDJPY",   # Sharpe -0.15 (fraco)

    # ========================================
    # C. METAIS (2 - Safe Haven)
    # ========================================
    "GOLD",     # Sharpe -0.98 (M5), testar H1
    "SILVER",   # Sharpe -1.15 (M5), testar H1

    # ========================================
    # D. ÍNDICES (5 - Momentum + Mean Rev)
    # ========================================
    "US500",    # S&P 500 (se disponível)
    "US100",    # Nasdaq (se disponível)
    "GER40",    # DAX (se disponível)
    "UK100",    # Sharpe -0.56 (fraco)
    "JP225",    # Nikkei (se disponível)

    # ========================================
    # E. COMMODITIES (3 - Macro Driven)
    # ========================================
    "USOIL",    # WTI Crude (se disponível)
    "UKOIL",    # Brent (se disponível)
    "NGAS",     # Natural Gas (se disponível)

    # ========================================
    # F. CRYPTO CFD (4 - Alta Volatilidade)
    # ========================================
    "BTCUSD",   # Sharpe -0.73 (fraco mas volátil)
    "ETHUSD",   # Sharpe 0.29 (fraco)
    "XRPUSD",   # Sharpe 1.07 (BOM!)
    "SOLUSD",   # Sharpe 0.70 (OK)
]

# ============================================================
#  MÉTRICAS DE PERFORMANCE (Atualizar com backtests reais!)
# ============================================================

ASSET_METRICS = {
    # ========================================
    # FX MAJORS (CONFIRMADO via backtest)
    # ========================================
    "EURUSD": {
        "sharpe": 0.84,
        "win_rate": 0.55,
        "avg_return_pct": 6.1,
        "volatility": 0.8,
        "n_trades": 187
    },
    "GBPUSD": {
        "sharpe": 0.81,
        "win_rate": 0.54,
        "avg_return_pct": 5.8,
        "volatility": 1.0,
        "n_trades": 186
    },
    "USDJPY": {
        "sharpe": 0.73,
        "win_rate": 0.52,
        "avg_return_pct": 5.2,
        "volatility": 1.1,
        "n_trades": 249
    },
    "AUDUSD": {
        "sharpe": 1.77,
        "win_rate": 0.59,
        "avg_return_pct": 13.7,
        "volatility": 0.9,
        "n_trades": 190
    },
    "USDCHF": {
        "sharpe": 1.41,
        "win_rate": 0.58,
        "avg_return_pct": 10.1,
        "volatility": 0.9,
        "n_trades": 187
    },
    "USDCAD": {
        "sharpe": 2.54,
        "win_rate": 0.62,
        "avg_return_pct": 14.6,
        "volatility": 0.8,
        "n_trades": 152
    },
    "NZDUSD": {
        "sharpe": -0.21,
        "win_rate": 0.48,
        "avg_return_pct": -1.6,
        "volatility": 1.2,
        "n_trades": 215
    },

    # ========================================
    # FX CROSSES (CONFIRMADO via backtest)
    # ========================================
    "EURGBP": {
        "sharpe": 6.00,
        "win_rate": 0.68,
        "avg_return_pct": 31.4,
        "volatility": 0.7,
        "n_trades": 128
    },
    "EURJPY": {
        "sharpe": -0.23,
        "win_rate": 0.49,
        "avg_return_pct": -1.1,
        "volatility": 1.3,
        "n_trades": 151
    },
    "GBPJPY": {
        "sharpe": 2.24,
        "win_rate": 0.61,
        "avg_return_pct": 12.6,
        "volatility": 1.2,
        "n_trades": 162
    },
    "AUDJPY": {
        "sharpe": -0.15,
        "win_rate": 0.49,
        "avg_return_pct": -0.9,
        "volatility": 1.4,
        "n_trades": 163
    },

    # ========================================
    # METAIS (CONFIRMADO via backtest - M5)
    # ========================================
    "GOLD": {
        "sharpe": -0.98,
        "win_rate": 0.47,
        "avg_return_pct": -5.5,
        "volatility": 1.5,
        "n_trades": 167
    },
    "SILVER": {
        "sharpe": -1.15,
        "win_rate": 0.46,
        "avg_return_pct": -7.1,
        "volatility": 2.0,
        "n_trades": 201
    },

    # ========================================
    # ÍNDICES (Estimativas - FAZER BACKTEST!)
    # ========================================
    "US500": {
        "sharpe": 1.00,
        "win_rate": 0.54,
        "avg_return_pct": 5.5,
        "volatility": 1.8,
        "n_trades": 72
    },
    "US100": {
        "sharpe": 1.05,
        "win_rate": 0.55,
        "avg_return_pct": 6.0,
        "volatility": 2.2,
        "n_trades": 68
    },
    "GER40": {
        "sharpe": 0.95,
        "win_rate": 0.53,
        "avg_return_pct": 5.0,
        "volatility": 2.0,
        "n_trades": 65
    },
    "UK100": {
        "sharpe": -0.56,
        "win_rate": 0.48,
        "avg_return_pct": -3.0,
        "volatility": 2.5,
        "n_trades": 146
    },
    "JP225": {
        "sharpe": 0.85,
        "win_rate": 0.52,
        "avg_return_pct": 4.5,
        "volatility": 2.3,
        "n_trades": 58
    },

    # ========================================
    # COMMODITIES (Estimativas - FAZER BACKTEST!)
    # ========================================
    "USOIL": {
        "sharpe": 0.75,
        "win_rate": 0.52,
        "avg_return_pct": 4.0,
        "volatility": 3.5,
        "n_trades": 56
    },
    "UKOIL": {
        "sharpe": 0.70,
        "win_rate": 0.51,
        "avg_return_pct": 3.5,
        "volatility": 3.5,
        "n_trades": 52
    },
    "NGAS": {
        "sharpe": 0.60,
        "win_rate": 0.50,
        "avg_return_pct": 3.0,
        "volatility": 4.5,
        "n_trades": 48
    },

    # ========================================
    # CRYPTO (CONFIRMADO via backtest)
    # ========================================
    "BTCUSD": {
        "sharpe": -0.73,
        "win_rate": 0.47,
        "avg_return_pct": -3.5,
        "volatility": 3.0,
        "n_trades": 111
    },
    "ETHUSD": {
        "sharpe": 0.29,
        "win_rate": 0.50,
        "avg_return_pct": 1.0,
        "volatility": 3.5,
        "n_trades": 91
    },
    "XRPUSD": {
        "sharpe": 1.07,
        "win_rate": 0.55,
        "avg_return_pct": 5.3,
        "volatility": 4.0,
        "n_trades": 119
    },
    "SOLUSD": {
        "sharpe": 0.70,
        "win_rate": 0.52,
        "avg_return_pct": 3.0,
        "volatility": 4.2,
        "n_trades": 120
    },
}

# ============================================================
#  EXTERNAL DATA SOURCES - TODAS AS APIS
# ============================================================

# Binance, CoinGecko, CryptoCompare, Yahoo Finance - SEM KEY NECESSARIA
USE_BINANCE_DATA = True

# Data Aggregator (simples - data_aggregator.py)
USE_DATA_AGGREGATOR = False

# Multi-API Consensus (avancado - multi_api_aggregator.py)
USE_MULTI_API_CONSENSUS = True
CONSENSUS_MIN_SOURCES = 2
CONSENSUS_MIN_CONFIDENCE = 0.80  # 80% confianca minima

# Order book filter (crypto)
USE_ORDER_BOOK_FILTER = False

# Data source weights (ponderacao por tipo de ativo)
DATA_SOURCE_WEIGHTS = {
    'crypto': {
        'binance': 0.45,
        'coingecko': 0.35,
        'cryptocompare': 0.20
    },
    'forex': {
        'alpha_vantage': 0.35,
        'twelve_data': 0.35,
        'fixer': 0.20,
        'eodhd': 0.10
    },
    'stocks': {
        'yahoo': 0.40,
        'polygon': 0.35,
        'eodhd': 0.25
    }
}

# News sentiment sources
NEWS_SOURCES = {
    'newsapi': True,
    'finnhub': True,
    'marketaux': True,
    'currents': True,
    'mediastack': True,
    'cryptopanic': True  # Crypto only
}

# API Health Monitoring
MONITOR_API_HEALTH = True
API_HEALTH_CHECK_INTERVAL = 300  # 5 minutos

# ============================================================
#  TELEGRAM NOTIFICATIONS
# ============================================================

TELEGRAM_ENABLED = False  # Ativar quando tiveres bot token
TELEGRAM_BOT_TOKEN = ""   # Obter de @BotFather
TELEGRAM_CHAT_ID = ""     # Teu chat ID

# Que alertas enviar
TELEGRAM_ALERTS = {
    'trade_opened': True,
    'trade_closed': True,
    'drawdown_warning': True,
    'daily_summary': True,
    'weekly_summary': True,
}

# ============================================================
#  EMAIL REPORTS
# ============================================================

EMAIL_ENABLED = False
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587
EMAIL_ADDRESS = ""
EMAIL_PASSWORD = ""       # App password (não a password normal)
EMAIL_TO = ""             # Email de destino dos reports

# ============================================================
#  FOREX FACTORY / ECONOMIC CALENDAR
# ============================================================

TRADING_ECONOMICS_KEY = ""  # Obter em tradingeconomics.com
USE_FOREX_FACTORY_SCRAPING = True
FF_BLOCK_MINUTES_BEFORE = 30  # Bloquear X min antes de evento HIGH
FF_BLOCK_MINUTES_AFTER = 15   # Bloquear X min depois de evento HIGH

# ============================================================
#  NOTAS IMPORTANTES
# ============================================================
# 1. Ativos com dados insuficientes no broker:
#    - US500, US100, GER40 (verificar disponibilidade)
#    - USOIL, UKOIL, NGAS (verificar disponibilidade)
#    - JP225 (verificar disponibilidade)
#
# 2. Sistema auto-remove ativos sem dados no MT5
#
# 3. Alocação proporcional ao Sharpe:
#    - Sharpe 6.0 (EURGBP) → ~20% do risk total
#    - Sharpe -0.7 (BTCUSD) → ~1% do risk total
#
# 4. Ativos fracos OPERAM mas com capital mínimo
#
# 5. FAZER BACKTESTS dos ativos estimados:
#    - Índices: US500, US100, GER40, JP225
#    - Commodities: USOIL, UKOIL, NGAS
#    - Metais em H1: GOLD, SILVER

