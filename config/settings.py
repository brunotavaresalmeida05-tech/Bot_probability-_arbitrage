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
ALPHA_VANTAGE_KEY = "71K9P6F0RGLHYD39"
NEWSAPI_KEY       = ""
FINNHUB_KEY       = "d6uquh1r01qig545jabgd6uquh1r01qig545jac0"
MARKETAUX_KEY     = "Bc02zKl6R48yom6AtBEfSgMTBj9WMjM1jrRTGHVY"
CURRENTS_KEY      = "p1ZOufwZzjpunAkPmVDqYU5-Q0Q7XFl_sWRr9rFW5f1bc7Gs"
MEDIASTACK_KEY    = "fccc2bb417afb7ec2b7a79d6d98100de"
EODHD_KEY         = "69bdafa2818c60.63828076"

# --- Fontes de dados ----------------------------------------
USE_POLYGON_DATA  = False   # plano free não tem intraday
USE_FRED_DATA     = True
USE_NEWSAPI       = False
USE_ALPHA_VANTAGE = False
USE_MACRO_ENGINE  = True
USE_FINNHUB       = True
USE_MARKETAUX     = True
USE_CURRENTS      = True
USE_EODHD         = True

# --- Módulos -----------------------------------------------
USE_MULTI_TIMEFRAME  = True    # análise M5+H1+D1
USE_PORTFOLIO_MANAGER = True   # gestão de correlações
USE_TRIANGULAR_ARB   = True    # arbitragem triangular FX

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
SESSION_START_HOUR = 7
SESSION_END_HOUR   = 22

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
TRIANGULAR_ARB_ENABLED  = True
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
