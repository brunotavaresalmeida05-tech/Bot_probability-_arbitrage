# 🤖 Mean Reversion MT5 Bot

Bot de mean reversion em Python, totalmente controlado pelo VS Code.
Conecta ao MetaTrader 5 via API oficial, executa no terminal com logs ricos.

---

## Estrutura do projeto

```
mt5-meanreversion/
├── .vscode/
│   ├── tasks.json        ← Ctrl+Shift+B para correr o bot
│   ├── settings.json     ← config do VS Code (Python, formatter)
│   └── extensions.json   ← extensões recomendadas
├── config/
│   └── settings.py       ← ⭐ EDITA AQUI: símbolos, parâmetros, risco
├── src/
│   ├── main.py           ← loop principal do bot
│   ├── strategy.py       ← Z-score, sinais, filtros
│   ├── mt5_connector.py  ← toda a comunicação com o MT5
│   ├── logger.py         ← logs no terminal + CSV
│   └── backtest.py       ← backtest com dados históricos do MT5
├── scripts/
│   ├── check_connection.py  ← verifica ligação + símbolos
│   └── close_all.py         ← fecha todas as posições do bot
├── logs/
│   └── trades.csv        ← registo de todos os trades fechados
└── requirements.txt
```

---

## Setup (Windows)

### 1. Pré-requisitos
- Python 3.11+ instalado (https://python.org)
- MetaTrader 5 instalado e aberto, com conta logada

### 2. Criar ambiente virtual e instalar dependências
```bash
# No terminal do VS Code (Ctrl+`)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configurar o bot
Edita `config/settings.py`:
```python
# Caminhos e conta
MT5_PATH  = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MT5_LOGIN = 0   # 0 = usa conta já logada no terminal

# Símbolos
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY"]

# Parâmetros de risco
RISK_PER_TRADE_PCT  = 0.5
MAX_DAILY_LOSS_PCT  = 4.0
```

### 4. Verificar ligação
```bash
python scripts/check_connection.py
# ou via task: Ctrl+Shift+P → "Run Task" → "🔍 Check MT5 Connection"
```

---

## Como correr

### Paper (simulação, sem ordens reais)
```bash
python src/main.py --mode paper
```
ou `Ctrl+Shift+P → Run Task → 🧪 Run Bot (Paper)`

### Live (ordens reais)
```bash
python src/main.py --mode live
```
ou `Ctrl+Shift+B` (task padrão)

### Backtest
```bash
python src/backtest.py
```
ou `Ctrl+Shift+P → Run Task → 📊 Backtest`

### Fechar tudo
```bash
python scripts/close_all.py
```

---

## O que vês no terminal

```
╭─────────────────────────────────────╮
│ 🤖 Mean Reversion Bot               │
│ Conta: 123456  Saldo: 10000.00 USD  │
│ Símbolos: EURUSD, GBPUSD, USDJPY   │
╰─────────────────────────────────────╯

  Símbolo  │  Z-score  │   Close   │    MA     │ Spread │ Sinal │ Posição │   P&L
───────────┼───────────┼───────────┼───────────┼────────┼───────┼─────────┼────────
  EURUSD   │  -2.134   │ 1.08521   │ 1.08734   │  1.2   │ ▲ BUY │  BUY    │ +12.30
  GBPUSD   │  +0.421   │ 1.27443   │ 1.27390   │  1.8   │  –    │   –     │   –
  USDJPY   │  +1.876   │ 149.821   │ 149.654   │  1.1   │  –    │   –     │   –
```

---

## Logs de trades (CSV)
Cada trade fechado é registado em `logs/trades.csv`:
```
timestamp, symbol, direction, entry_price, exit_price, sl,
z_entry, z_exit, atr_entry, profit_pips, profit_currency, reason
```

---

## Parâmetros principais (config/settings.py)

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `Z_ENTER` | 2.0 | Entra quando \|Z\| ≥ este valor |
| `Z_EXIT` | 0.7 | Sai quando \|Z\| ≤ este valor |
| `Z_STOP` | 3.5 | Stop loss em desvios (se USE_Z_STOP=True) |
| `MA_PERIOD` | 100 | Período da média móvel (fair value) |
| `STDDEV_PERIOD` | 50 | Período do desvio padrão |
| `RISK_PER_TRADE_PCT` | 0.5 | % do saldo arriscado por trade |
| `MAX_DAILY_LOSS_PCT` | 4.0 | Stop diário de perdas |
| `MAX_SPREAD_POINTS` | 20 | Máximo spread permitido |

---

## Para parar o bot
`Ctrl+C` no terminal — fecha posições abertas **não é** automático.
Para fechar posições: `python scripts/close_all.py`
