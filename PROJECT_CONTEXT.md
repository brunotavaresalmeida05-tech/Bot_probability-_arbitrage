# PROJECT CONTEXT (Updated 2026-05-04)
## O que é este projeto
AlphaSystem — bot de trading automatizado para MetaTrader 5.
**Nova arquitetura (Fase 1 concluída):** Estratégia única EMA Stoch ATR + Regime Filter + Context Layer.

---
## Estado atual (2026-05-04)
- **Fase 1 CONCLUÍDA** — Reestruturação da Base.
- Nova arquitetura limpa: `strategy/` (Estratégia única) + `core/` (validado) + `connectors/` (validado).
- Conta live: ActivTrades #6229822, 466.12 EUR (validada).

---
## Nova Estrutura de Pastas (Fase 1 Concluída)
```
AlphaSystem/
├── strategy/                      # NOVA PASTA — Estratégia única
│   ├── __init__.py
│   ├── ema_stoch_atr.py        # Estratégia principal (EMA 20/50/100/200 + Stoch RSI + ATR)
│   ├── regime_filter.py        # Filtro de regime (simplificado)
│   └── context_layer.py       # Contexto (usando connectors/)
│
├── core/                          # Mantém (já validado)
│   ├── event_bus.py
│   ├── snapshot_builder.py
│   ├── layered_scheduler.py
│   ├── risk_gate.py        # Com kill switch, cooldown, latency check
│   ├── mt5_guard.py
│   └── mt5_trade_runner.py
│
├── connectors/                    # Mantém (já validado)
│   ├── fred.py
│   ├── polygon.py
│   ├── finnhub.py
│   └── newsapi.py
│
├── dashboard/                     # Mantém
│   └── app.py
│
├── tests/                        # Atualizar para nova estratégia
│   └── test_ema_stoch_atr.py  # 8/8 tests passing
│
├── archive/                      # Arquivo
│   └── old_strategies/        # 18 estratégias antigas arquivadas
│
├── main.py                       # ATUALIZADO — usa nova estratégia
├── requirements.txt
├── .env                           # API keys (Polygon inválida, Finnhub OK)
├── PROGRESS.md                    # Estado do projeto
└── FASE1_REESTRUTURAÇÃO.md   # Documentação da Fase 1
```

---
## Nova Estratégia Principal (EMA Stoch ATR)
**Ficheiro:** `strategy/ema_stoch_atr.py`

**Regras:**
- **LONG:** Price > EMA200 (uptrend) AND Price > EMA20 (momentum) AND Stoch RSI < 20 (oversold)
- **SHORT:** Price < EMA200 (downtrend) AND Price < EMA20 (momentum) AND Stoch RSI > 80 (overbought)

**Stop Loss:** Baseado em ATR (2x ATR)  
**Take Profit:** Baseado em ATR (3x ATR)

---
## Regime Filter (Simplificado + ADX)
**Ficheiro:** `core/regime.py`

**Tipos:** trend_up, trend_down, sideways, unknown  
**Lógica:** ADX < 20 → sideways; ADX >= 20 + EMA20 > EMA50 → trend_up; caso contrário → trend_down.

---
## Context Layer
**Ficheiro:** `strategy/context_layer.py`  
**Fornece:** Macro data (FRED), News sentiment (NewsAPI), Market breadth.  
**Usa:** `connectors/` já validados.

---
## Componentes Principais (Core — Validados)
| Componente | Ficheiro | Estado | Testes |
|-----------|----------|--------|--------|
| EventBus | `core/event_bus.py` | ✅ | 7/7 |
| SnapshotBuilder | `core/snapshot_builder.py` | ✅ | 4/4 |
| LayeredScheduler | `core/layered_scheduler.py` | ✅ | 5/5 |
| RiskGate | `core/risk_gate.py` | ✅ | 1/1 |
| MT5Guard | `core/mt5_guard.py` | ✅ | — |
| MT5TradeRunner | `core/mt5_trade_runner.py` | ✅ | — |

**RiskGate tem:** Kill switch (15% equity loss), Cooldown (5 min), Max latency (5s), Max trades/session (10).

---
## Fluxo de Dados (Atualizado)
```
Connectors (Finnhub) → EventBus → Strategy (EMA Stoch ATR) → Signal
                                                      ↓
Regime Filter → RiskGate → MT5Guard → order_check() → order_send()
                                                      ↓
                                              MT5 Account #6229822
```

---
## O que foi removido (Fase 1)
✅ 18 estratégias antigas (`src/strategies/`)  
✅ `src/engine/` (redundante com `strategy/`)  
✅ `src/data/` (redundante com `connectors/`)  
✅ `src/regime/` (substituído por `strategy/regime_filter.py`)  
✅ `src/execution/` (substituído por `core/mt5_trade_runner.py`)  

---
## Próximo Passo (Fase 2 — Integração e Validação)
1. ✅ **Fase 1 CONCLUÍDA** — Reestruturação completa
2. 📋 **Limpar testes antigos** (`tests/test_v8_*.py`)
3. 📋 **Fazer teste ao vivo de 10 minutos** com nova arquitetura limpa
4. 📋 **Validar ciclo completo:** poll_market() → evaluate_signals() → RiskGate → MT5Guard → order_check() → order_send()
5. 📋 **Commit das alterações**

---
## Variáveis de ambiente (.env)
```
MT5_LOGIN=6229822
MT5_PASSWORD=SCDvxg8-
MT5_SERVER=ActivTradesCorp-Server
MT5_PATH=C:\Program Files\MetaTrader 5 - ActivTrades\terminal64.exe
FRED_API_KEY=583922c6e7d2a106ee1eae29a70b90e0
POLYGON_API_KEY=2nC3wlQs0AVj8wF3kgT5jcyCNiA2iB  # INVÁLIDA (401)
FINNHUB_API_KEY=d6uquh1r01qig545jabgd6uquh1r01qig545jac0  # OK
NEWS_API_KEY=3c7be108d2bc47c18e36e5437a76c632
# ... outras chaves
```

---
## Regras de desenvolvimento
- Um componente de cada vez; teste imediato; só avança se passar
- Fase 1 concluída: estratégia única implementada e testada (8/8)
- Variáveis sensíveis sempre em `.env` (nunca em código)
- `bot_lock.txt` só apagar após validação manual do risco
- Testes: `python -m pytest tests/ -v`
- Total: 8 novos testes passing (Fase 1) ✅
