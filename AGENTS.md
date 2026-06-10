# AGENTS.md — Memória Viva do Projecto AlphaSystem V8

> Lido automaticamente por qualquer agente ao iniciar.
> Actualiza sempre que tomas uma decisão técnica, resolves um bug recorrente ou defines um padrão.
> Ver `.ai/skills/context-router/SKILL.md` para decidir que skills carregar por tipo de tarefa.

---

## 1. IDENTIDADE DO PROJECTO

```yaml
name:    "AlphaSystem V9 — Macro-Driven Engine"
version: "0.9.0"
type:    "trading-bot"
status:  "development"       # V9 em construção — substituiu V8 em 2026-06-03
owner:   "bruno"
broker:  "ActivTrades demo #6238864"
```

---

## 2. OBJECTIVO

Sistema de trading macro-driven multi-activo. Opera como "bom negociador profissional": o contexto macroeconómico é condição necessária para qualquer entrada — indicadores técnicos são confirmação, nunca gatilho.

**Filosofia:** Mercado é calculado. Regime detectado (VIX + DXY + Yield Curve + Noticias) → Preço Justo calculado → Canais de volatilidade projectados → Indicadores técnicos confirmam → Risco dimensionado profissionalmente → Execução disciplinada.

**Motor:** VIX + DXY + Curva de Juros + Commodities + Agenda Económica + MACD/BB/Hi-Lo/ATRStop/SAR/EMA8/VWAP/MA50/MA100/Pivot/WeisWave. Multi-timeframe: 3/5/10/15/30min e 1H. Portfolio benchmark de 30+ activos observados em permanência.

**Objectivo:** Multiplicar capital de forma consistente, robusta e credível. Sistema capaz de gerir capital institucional.

---

## 3. STACK REAL

```yaml
trading_engine:
  language:  "Python 3.14"
  broker_api: "MetaTrader5 (MT5Bridge)"
  broker:    "ActivTrades demo #6238864"
  entry:     "python -m src.main"   # NUNCA python src/main.py (ver secção 10)

backend:
  framework: "FastAPI"
  server:    "server/ (FastAPI + WebSockets)"

frontend:
  framework: "React + TypeScript"
  styling:   "Tailwind CSS"
  state:     "Zustand"
  location:  "dashboard/"

ai_tools:
  cli:   "Claude Code (claude-sonnet-4-6)"
  model: "claude-sonnet-4-6"
```

---

## 4. VARIÁVEIS DE AMBIENTE

> NUNCA commitar `.env`. As chaves reais estão no `.env` local (não versionado).

```env
MT5_LOGIN=           # login ActivTrades
MT5_PASSWORD=
MT5_SERVER=          # ActivTradesCorp-Server
MT5_PATH=            # path ao terminal64.exe

FRED_API_KEY=        # macro regime (taxas, yields)
POLYGON_API_KEY=     # market data externo
FINNHUB_API_KEY=     # VIX monitor + news
NEWSAPI_API_KEY=     # news gate
MARKETAUX_KEY=       # news gate alternativo
CURRENTS_KEY=
MEDIASTACK_KEY=
EODHD_KEY=
ALPHA_VANTAGE_KEY=
TWELVE_DATA_KEY=
FIXER_KEY=
CRYPTOPANIC_KEY=     # crypto sentiment
BINANCE_API_KEY=
COINGECKO_KEY=
ETHERSCAN_KEY=

JWT_SECRET=          # dashboard auth
DASHBOARD_USER=
DASHBOARD_PASSWORD=
```

---

## 5. ESTRUTURA DE DIRECTÓRIOS (V9 — ACTUAL)

```
src/
  engine/
    orchestrator.py       ← motor principal V9: coordena todas as camadas
  macro/
    macro_context.py      ← MacroContext dataclass: estado macro consolidado (fonte de verdade)
    vix_monitor.py        ← VIX thread daemon (Finnhub, 60s) → regime: normal/caution/alert/kill/panic
    dxy_basket.py         ← DXY sintético (pesos ICE) via forex rates → regime: risk_off/neutral/risk_on
    yield_monitor.py      ← Curva de juros FRED (US10Y/2Y/3M) → steep/flat/inverted
    news_gate.py          ← filtro de noticias macro
    economic_calendar.py  ← agenda económica (eventos, impacto, timing)
    commodity_monitor.py  ← Gold XAU/USD, WTI, Brent (preços + variação%)
    news_interpreter.py   ← classificação: bullish/neutral/bearish
  analysis/
    fair_price.py         ← Preço Justo = fecho_anterior × (1+var_DXY%) + canais Fibonacci BB10
    volatility_channels.py← Canais de volatilidade por projecção Fibonacci (0.236 a 2.618)
    yield_curve.py        ← curva de juros completa + futuros (ZT,ZN,ES,VX,DX) via yfinance
    correlation.py        ← matriz rolante 20-períodos + correlações estruturais + penalidade 65%
    scenario_evaluator.py ← 5 vetos sequenciais → TENDENCIA_ALTA/BAIXA/INDEFINIDO/BLOQUEADO
    asset_profiler.py     ← DNA de cada instrumento: classe, DXY beta, drivers macro, benchmark
    macro_calculator.py   ← surpresa económica (actual-consensus)/σ, regime score, yield curve, z-score, RS
    total_score.py        ← TotalScore = wm*MCS + wb*BCS + wh*HCS + wv*VES - we*ES + wc*CS - wr*RS
                            7 componentes: MCS(MACD) BCS(BB) HCS(Hi-Lo) VES ES CS RS(+ATRStop)
                            Pesos por classe (forex/indices/gold/oil/treasuries/crypto) × timeframe (M3→H1)
                            Thresholds: ≥0.75 execute | 0.55-0.75 moderate | <0.40 block
  technical/
    indicators.py         ← MACD(linhas), BB10, Hi-Lo Activator, ATR Stop (Chandelier), SAR, EMA8, VWAP, MA50/100, WeisWave, Pivot
                            Hierarquia 4 camadas: Principal | Confirmação | Participação | Contexto
    macd_analyzer.py      ← dentes MACD: peaks/valleys clusterizados, impact_count, divergência, teeth→price levels
    bollinger_analyzer.py ← squeeze(percentil), expansão assimétrica, walking the band, BB unfulfilled points
    multi_timeframe.py    ← coordenador adaptativo: TF selecionado por BB width, veto 1H, confluência 0-1.0
    signal_generator.py   ← pipeline completo: 7 vetos sequenciais + 8 confirmações (gate 4/8) + lot_multiplier
  engine/
    scanner.py            ← Opportunity-Permission Engine: scan(), compute_opportunity_score(), compute_permission_score()
                            OpportunityScore = a1*MCS+a2*BCS+a3*HCS+a4*VES-a5*ES  (técnico puro)
                            PermissionScore  = b1*CS-b2*RS-b3*ES+b4*ATRFit        (contexto+risco)
                            Labels: weak|watchlist|strong / BLOCK|REDUCE|CONFIRM|EXECUTE
  benchmark/
    portfolio_monitor.py  ← 28 activos benchmark via yfinance (observar, não operar)
    # ADR flow, treasury demand, gold signal, carry trade — derivados do benchmark
  session/
    market_sessions.py    ← detecção sessões: Asia/Londres/NY/Overlap
    prep_workflow.py      ← 6 etapas de preparação por sessão
  execution/
    order_manager.py      ← gestão de ordens MT5 (magic=20260902)
    position_tracker.py   ← tracking de posições abertas
  risk/
    professional_risk.py  ← sizing: math.floor + volume_step MT5 + lot_penalty composto + tiers
    var_calculator.py     ← VaR paramétrico e histórico + DrawdownTracker + PortfolioRiskManager
    execution_validator.py← R:R líquido (após execution cost) + spread/ATR + MFE/MAE tracker
  indicators/             ← indicadores técnicos auxiliares (stoch_rsi, ema_stack, vwap, hilo)
  data_sources/           ← forex_factory (calendário), multi_api_aggregator
  notifications/          ← email_reporter (alertas críticos)
  mt5_bridge.py           ← MT5 connection + TIMEFRAME_MAP (mantido)
  session_scheduler.py    ← session scheduler (mantido, usado pelo server/)
  main.py                 ← BotApp V9 entry point
config/
  strategies.yaml         ← registry: trend_following(ON) + breakout_session(ON)
  scalping.yaml           ← scalping module (enabled: false até Day 7 OK)
  config.yaml             ← main config: profile=demo, max_positions=5, daily_loss=0.03
  asset_universe.yaml     ← 9 symbols + spread limits por classe
checks/
  daily_check.py          ← 5 nightly checks (health/liquidity/alerts/logs/backups)
  signal_report.py        ← Day 2: qualidade de sinais por símbolo
  stress_test.py          ← Day 4+6: 6 testes de safety (T1-T6, todos PASS)
  week_validator.py       ← Day 7: Monte Carlo + AVANÇAR/MANTER/PAUSAR
  preflight.py            ← preflight_check() chamado no boot
scripts/
  day0_reset.py           ← reset estado para início de janela de validação
  watchdog.py             ← process monitor com auto-restart
state/
  state.json              ← estado actual do engine (actualizado a cada ciclo)
  state_history.jsonl     ← histórico de ciclos
  preflight_report.json   ← último relatório de preflight
  bot.pid                 ← PID do processo bot
server/                   ← FastAPI backend (arrancar com uvicorn server.main:app)
  main.py                 ← app FastAPI: CORS, JWT auth, WebSocket /ws, serve dashboard/ como static
  auth.py                 ← JWT: check_credentials, create_token, verify_token
  state_reader.py         ← lê state.json para os routers
  control_writer.py       ← escreve comandos de controlo para o bot
  bot_manager.py          ← gestão do processo bot (start/stop)
  ws/
    hub.py                ← WebSocket hub: polling state.json + broadcast para clientes
  routers/
    status.py             ← GET /api/status → read_state()
    trades.py             ← GET /api/trades
    history.py            ← GET /api/history
    control.py            ← POST /api/control (pause/resume/stop)
    dashboard_api.py      ← endpoints adicionais do dashboard
dashboard/                ← React + TypeScript + Tailwind (servido como static pelo server)
  index.html              ← SPA entry point
  js/app.js               ← lógica principal + Zustand state
  css/main.css            ← Tailwind styles
app/                      ← LEGADO: comparador de sessões de backtest (não é o engine live)
  main.py                 ← entry: compare_sessions() + save_historical_rankings()
  compare.py              ← ranking ponderado: sharpe/win_rate/equity/max_dd → score
  data_io.py              ← load/save runs, curves, config
  launcher.py             ← launcher legado
  dashboard.py            ← dashboard legado (substituído por dashboard/)
```

---

## 6. FILOSOFIA E REGRAS OPERACIONAIS (INVIOLÁVEIS)

### O Bom Negociador

```
NUNCA entrar no topo de expansão ou fundo de colapso.
SEMPRE esperar pullback para zona de valor + confirmação de inversão.

Comprar barato: pullback em uptrend, StochRSI saindo de sobrevenda.
Vender caro:    pullback em downtrend, StochRSI saindo de sobrecompra.
```

### LÓGICA DE DECISÃO EM 6 CAMADAS

```
CAMADA 1 — REGIME MACRO H1
  ADX_H1 >= 25 + EMA50 > EMA100 → TRENDING_UP
  ADX_H1 >= 25 + EMA50 < EMA100 → TRENDING_DOWN
  ADX_H1 < 20                    → RANGING (sem trades)

CAMADA 2 — FILTROS (pipeline.py)
  spread_ok + volatility_ok + news_ok + correlation_ok

CAMADA 3 — HV VOLATILITY (volatility_service.py)
  LOW_VOL:     size=0.8× sl=0.9×  entry=OK  scalp=OK
  NORMAL_VOL:  size=1.0× sl=1.0×  entry=OK  scalp=OK
  HIGH_VOL:    size=0.5× sl=1.3×  entry=OK  scalp=BLOCK
  EXTREME_VOL: size=0.0× sl=2.0×  entry=BLOCK scalp=BLOCK

CAMADA 4 — SINAL (strategy.generate_signal)
  trend_following: EMA cross + Donchian breakout + pullback (3 setups em cascata)
  breakout_session: Donchian + sessão UTC + volume > 1.2× média

CAMADA 5 — RISCO (risk_engine_v2.py)
  lot = (balance × 0.5%) / (sl_distance × point_value) × vix_mult × vol_mult
  Bloqueia se: streak=3, daily_loss=3%, max_positions=5

CAMADA 6 — KILL SWITCH
  DD>3%, streak, MT5 offline>5min, spread>3× baseline
```

### UNIVERSO DE ACTIVOS (ACTIVO)

```yaml
estratégias_activas:
  trend_following:    [EURUSD, USDJPY, Usa500, UsaTec, Ger40, GOLD, Brent, LCrude]
  breakout_session:   [Usa500, UsaTec, Ger40, EURUSD, USDJPY, GOLD]
  scalping:           [EURUSD, GBPUSD, USDJPY, Usa500, UsaTec, Ger40, GOLD]  # disabled

risco:
  core:    0.50% por trade | 3% daily cap | streak: 3 perdas | max: 5 posições
  scalping: 0.25% por trade | 1% daily cap | max: 2 posições simultâneas
```

### INDICADORES (parâmetros fixos)

```yaml
adx:      period=14  strong>=25  weak<20  H1 como contexto primário
ema:      periods=[20, 50]  uptrend=EMA20>EMA50  M15 execução
donchian: period=20  H1 ADX>25 obrigatório para breakout
atr:      period=14  uso=[SL placement, lot sizing, vol filter]
hv:       window=20  log-returns  thresholds adaptivos por percentil (p30/p70/p90)
sessions: london=08-17UTC  new_york=13-22UTC  asia=DESLIGADA (spread)
```

---

## 7. REGRAS DO PROJECTO (INVIOLÁVEIS)

```
NEVER  commitar .env ou segredos reais
ALWAYS usar python -m src.main (NUNCA python src/main.py — ver secção 10)
ALWAYS verificar secção 10 antes de debugar (problemas conhecidos)
ALWAYS actualizar este AGENTS.md ao tomar uma decisão técnica
NEVER  mexer em thresholds de gates durante janela de validação (7 dias)
ALWAYS estratégias desligadas: scalping (enabled: false em scalping.yaml)
ALWAYS kill_switch global tem prioridade sobre todas as estratégias
```

---

## 8. DESIGN PATTERNS DO PROJECTO

- [x] **State-Driven Architecture** — state.json como fonte de verdade por ciclo
- [x] **Strategy Registry** — strategies.yaml + `_STRATEGY_REGISTRY` em alpha_engine.py
- [x] **Layered Filter Pipeline** — 6 camadas independentes e composable
- [x] **Background Daemon Threads** — VIX monitor, MacroGate, YieldMonitor (60s/1h/30m)
- [x] **Adaptive Percentile Thresholds** — HV regimes por percentil (não thresholds fixos)
- [x] **Bootstrap Guard** — serviços retornam NORMAL/safe até terem dados suficientes
- [x] **Service Facade** — VolatilityService, ScalpFilters, ScalpExecutor como facades
- [x] **JSONL Audit Trail** — state_history.jsonl + scalp_metrics.jsonl para auditoria

---

## 9. FUNCIONALIDADES / ESTADO

| # | Funcionalidade | Estado | Notas |
|---|---------------|--------|-------|
| 1 | AlphaEngine + TrendFollowing | [x] done | M15/H1, 3 setups em cascata |
| 2 | BreakoutSession | [x] done | Sessão UTC fix aplicado (era bypass silencioso) |
| 3 | FilterPipeline (5 filtros) | [x] done | regime+spread+vol+news+correlation |
| 4 | RiskEngineV2 + KillSwitch | [x] done | 6 camadas de risco |
| 5 | 7-day validation scripts | [x] done | daily_check + signal_report + stress_test + week_validator |
| 6 | Stress test (T1-T6) | [x] pass | Todos os safety mechanisms verificados |
| 7 | Scalping module | [x] built | DESLIGADO — activar após Day 7 OK |
| 8 | HV volatility layer | [x] done | Integrado no AlphaEngine (3 pontos) |
| 9 | Day 0 reset + launcher | [x] done | day0_reset.py + run_bot.ps1 |
| 10 | Bot correndo em demo | [x] running | PID 14420, Day 2, regime indefinido (neutral+bearish), n_results=0 correcto |
| 11 | ScalpMetrics (JSONL) | [x] done | separado do PaperValidator |
| 12 | VIX regime fix | [x] done | `regime()` era guardado como method object |
| 13 | Hi-Lo Activator + ATR Stop | [x] done | Camada 1: HiLoResult + ATRStopResult em IndicatorBundle |
| 14 | HCS no TotalScore | [x] done | 7 componentes; ATR Stop proximity integrado em RS |
| 15 | Hierarquia 4 camadas | [x] done | Principal/Confirmação/Participação/Contexto — documentada em indicators.py |
| 16 | 8 confirmações gate | [x] done | signal_generator: Hi-Lo=3, ATR Stop=4, min 4/8 |
| 17 | Escalar para 0.75% | [ ] planned | Após Day 7: PF>=1.3, WR>=48%, DD<=6% |
| 18 | Activar scalping | [ ] planned | Após Day 7 validado |
| 19 | Pyramiding controlado | [ ] planned | Fase posterior |
| 20 | Testes unitários Hi-Lo/ATR Stop/HCS | [ ] pendente | Dívida técnica alta |
| 21 | Opportunity-Permission Engine | [x] done | src/engine/scanner.py — 2 fases separadas; spec em .ai/specs/opportunity-permission-engine.md |
| 22 | RSI(14) no scanner | [x] done | rsi=50.0 neutro (sem efeito). Momentum +0.02, extremo mod -0.03/RS+0.07, extremo forte -0.06/RS+0.15. checks/rsi_report.py |
| 23 | RSI Calibration Policy | [x] done | Peso dinâmico por classe×TF×vol_regime. config/rsi_calibration.yaml. Avaliação automática em checks/rsi_report.py --calibrate |
| 24 | Idiosyncratic Move (TECNICO_PURO) | [x] done | Novo cenário: macro neutro + técnicos fortes (3/4 indicadores + TS>=0.72). Gates elevados: 5/8 confirms, lote×0.50, conf≤7. Activar/desactivar via config/strategies.yaml |
| 25 | Regime Router V9.1 | [x] done | src/engine/regime_router.py — TRENDING_UP/DOWN/RANGING/VOLATILE; ADX+MA+indicators; macro=contexto(lot_context); integrado em signal_generator VETO 5 |
| 26 | Confluência 3/5 (TRENDING mode) | [x] done | signal_generator: TRENDING→3/8 confirms+lot_context; TECNICO_PURO→5/8; Normal→4/8 |
| 33 | Circuit Breaker 4 níveis | [x] done | src/engine/circuit_breaker.py — GREEN/YELLOW(lot×0.5)/ORANGE/RED; DD e streak triggers; integrado orchestrator |
| 34 | ADX(14) no IndicatorBundle | [x] done | indicators.py: adx_indicator() Wilder EWM; default=20.0; usado pelo regime_router |
| 27 | SMC Layer | [ ] planned | src/analysis/smc.py — Order Blocks, FVG, BOS/ChoCh, Liquidity Sweeps |
| 28 | Capital Manager V2 | [ ] planned | src/risk/capital_manager.py — 3 camadas (70/20/10) + Kelly/4 sizing + rebalanceamento mensal |
| 29 | Margin Manager | [ ] planned | src/risk/margin_manager.py — semáforo 5 níveis (>500% verde → <150% crítico) |
| 30 | TP Escalonado 40/35/25% | [ ] planned | Upgrade order_manager.py — TP1 40%+BE, TP2 35%+trailing ATR×1.0, TP3 25% runner |
| 31 | Circuit Breaker 4 Níveis | [ ] planned | src/engine/circuit_breaker.py — ALERTA/REDUÇÃO/PAUSA/PARAGEM TOTAL |
| 32 | ML Filter | [ ] planned | src/analysis/ml_filter.py — RandomForest quality classifier. Fase 10 (após 200+ trades V9.1) |

---

## 10. PROBLEMAS RECORRENTES E SOLUÇÕES

| Problema | Causa | Solução |
|----------|-------|---------|
| `ModuleNotFoundError: No module named 'src'` (sintoma superficial) | `python src/main.py` adiciona `src/` ao início do sys.path → `src/signal/` shadowa o stdlib `signal` antes de qualquer import. Consequência silenciosa: `import signal` no BotApp passa a importar o módulo interno, não o stdlib — os handlers SIGINT/SIGTERM nunca são registados, o watchdog.py perde a capacidade de terminar o processo limpo, e o `state/bot.pid` pode ficar órfão. `python -m src.main` executa o interpretador em modo módulo, preservando o sys.path do ecossistema e a integridade dos sinais do SO. | **Sempre** usar `python -m src.main` — é protecção de escopo, não apenas conveniência |
| Session gate bypass em breakout_session | `FilterResult` não tem `active_sessions` → `getattr(...)` retornava None → `if active is not None` nunca entrava | Substituído por `_current_sessions()` com `datetime.now(timezone.utc).hour` |
| VIX regime gravado como method object | `vix_monitor.regime` (sem `()`) guardava o bound method | Corrigido para `vix_monitor.regime()` e `vix_monitor.lot_multiplier()` |
| `config.yaml max_positions: 3` vs `strategies.yaml max_positions_total: 5` | Dois ficheiros com o mesmo conceito e valores diferentes | `config.yaml` actualizado para 5 (alinhado) |
| `checks.allowed_bar_age_s: 7200` | Preflight aceitava barras com 2h de atraso | Actualizado para 600s (10 min) |
| Preflight falha no cold start | Barras não populadas à primeira chamada (antes de `_mt5_refresh()` correr) | Comportamento esperado para `demo` profile — não bloqueia; resolver após 2-3 ciclos |
| PowerShell `Start-Job` não persiste entre comandos | Cada tool call Claude Code = nova sessão PowerShell | Usar `Start-Process -NoNewWindow -RedirectStandardOutput` para processos independentes |
| `state_history.jsonl` só tem `n_results: 0` | Bot no loop Sydney/Asia (sem barras forex) — `n_results` conta resultados do engine, não sinais | Normal fora de London/NY — verificar ts e cycle count para confirmar actividade |
| `logging.basicConfig` vai para stderr, não stdout | Python logging usa stderr por defeito | Usar `-RedirectStandardError` em Start-Process; monitorizar `bot_stderr_current.log` |
| signal_report.py retorna "No data" com --hours 1 | Ciclos são gerados a cada 90s; cutoff de 1h pode cair exatamente entre entradas | Usar --hours 2 ou ler state_history.jsonl directamente para diagnóstico |
| Hierarquia de indicadores: Hi-Lo e ATR Stop | Adicionados como Camada 1 em 2026-06-04 | HiLoResult + ATRStopResult em IndicatorBundle; HCS como 3º componente do TotalScore; ATR Stop proximity no RS |

---

## 11. MCPS DISPONÍVEIS

```yaml
mcps:
  - name: "Figma"
    purpose: "design → código (dashboard)"
  - name: "Google Drive"
    purpose: "backups e partilha de relatórios"
  - name: "Miro"
    purpose: "diagramas de arquitectura"
```

---

## 12. CHECKLIST PÓS-IMPLEMENTAÇÃO

```
[ ] Testes / stress_test.py passam
[ ] python -m src.main arranca sem erro
[ ] state.json actualiza (mtime recente, cycle a subir)
[ ] signals corretos para o regime actual (HOLD em RANGING = correcto)
[ ] AGENTS.md actualizado com decisão/padrão/bug
[ ] config/strategies.yaml e config/scalping.yaml coerentes
[ ] daily_check.py retorna ALL CLEAR
```

---

## 13. CONTEXTO PARA A IA

```
SEMPRE ler este ficheiro antes de qualquer tarefa.
SEMPRE ler .ai/skills/context-router/SKILL.md para seleccionar skills.
NEVER assumir stack — verificar secção 3.
ALWAYS verificar secção 10 antes de debugar.
ALWAYS usar python -m src.main (NUNCA python src/main.py).
NEVER mexer em estratégias desligadas sem instruções explícitas.
ALWAYS declarar qual skill está a usar e porquê.

Estado operacional actual (2026-06-10):
  Bot: PARADO — ultimo ciclo: cycle=199 (2026-06-09T19:19Z, NY session)
  Fase 8: COMPLETA — veredicto: AVANCAR para V9.1 (signals=0 estrutural confirmado)
  Fase 9A: EM CURSO — Tasks 9A.1-9A.5 concluidas; pendente: 9A.6 (day0_reset nova janela)
  Implementados: regime_router.py + circuit_breaker.py + ADX no IndicatorBundle
  signal_generator.py: VETO 5 reescrito — TRENDING (ADX>=25) bypassa macro=neutral
  state.json: inclui agora "regime" + "circuit_breaker" + "scenario" por sinal
  Testes: 43 PASS (test_regime_router.py + test_circuit_breaker.py)
  Bug corrigido: CircuitBreaker._date="" causava daily_start_equity override na 1a update()
  Proximo passo: day0_reset.py + arrancar bot V9.1 + validar signals>0 em regime TRENDING
  Divida critica restante: SMC Layer (9B), Capital Manager V2 (9C), Dashboard V9 (9D)
  server/: FastAPI + WebSockets (uvicorn server.main:app) — serve dashboard/ como static
  app/: modulo legado de comparacao de backtest (nao e o engine live)
  ROADMAP.md: ficheiro vivo de planificacao — actualizar sempre que nova integracao discutida
```
