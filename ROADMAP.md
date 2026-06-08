# ROADMAP — AlphaSystem V9

**Ultima actualizacao:** 2026-06-08
**Versao:** V9.0 — Macro-Driven Engine
**Conta demo:** MT5 #6238864 (ActivTrades, EUR)
**Entrada:** `python -m src.main` (NUNCA `python src/main.py`)

> Ficheiro vivo. Actualizar SEMPRE que: nova feature implementada, decisao tecnica tomada,
> milestone atingido, divida identificada, nova integracao discutida.
> Ver tambem: AGENTS.md (memoria tecnica) e .ai/skills/context-router/SKILL.md (routing de skills).

---

## ONDE ESTAMOS AGORA

```
Fase 1  [COMPLETA]   Motor Principal         — orchestrator, BotApp, MT5Bridge
Fase 2  [COMPLETA]   Macro Engine            — 7 daemons: VIX, DXY, Yield, Commodity, News, Calendar, Benchmark
Fase 3  [COMPLETA]   Analise                 — fair_price, volatility_channels, yield_curve, correlation, scenario_evaluator
Fase 4  [COMPLETA]   Tecnicos                — MACD, BB, Hi-Lo, ATR Stop, SAR, VWAP, MA, WeisWave, Pivot, MTF
Fase 5  [COMPLETA]   Score Engine            — TotalScore 7 componentes: MCS+BCS+HCS+VES+ES+CS+RS
Fase 6  [COMPLETA]   Execucao e Risco        — order_manager, professional_risk, VaR, execution_validator
Fase 7  [COMPLETA]   Sessao e Validacao      — market_sessions, prep_workflow, checks/, scripts/
Fase 7b [COMPLETA]   Opportunity-Permission  — scanner.py: OpportunityScore + PermissionScore, 2 fases independentes
Fase 7c [COMPLETA]   RSI + Calibracao        — RSI(14) gate + RSICalibrationPolicy + checks/rsi_report.py
Fase 7d [COMPLETA]   Idiosyncratic Move      — TECNICO_PURO: macro neutro + técnicos fortes -> entrada conservadora
Fase 8  [EM CURSO]   Validacao 7 Dias        — Day 6 de 7 (iniciada 2026-06-03, fim previsto 2026-06-10)
Fase 9  [PENDENTE]   Dashboard V9            — server/ FastAPI + dashboard/ React integrados com dados V9
Fase 9b [PENDENTE]   Testes Unitarios        — Hi-Lo + ATR Stop + TotalScore (divida tecnica alta)
Fase 10 [PENDENTE]   Scalping + Pyramiding   — activar apos Day 7 OK
Fase 11 [PENDENTE]   VPS Windows 24/7        — operacao continua
Fase 12 [PENDENTE]   Paper Trading           — 2 semanas de validacao real
Fase 13 [PENDENTE]   Capital Real            — transicao gradual para conta real
```

---

## FASE 1 — Motor Principal [COMPLETA]

| Ficheiro | Funcao |
|---|---|
| `src/main.py` | BotApp V9: setup, loop principal, cleanup, PID, SIGINT/SIGTERM |
| `src/engine/orchestrator.py` | Coordena todas as camadas, inicia daemons, executa ciclos |
| `src/mt5_bridge.py` | MT5Bridge: connect, shutdown, account_info, TIMEFRAME_MAP |

**Verificado:** bot arranca, escreve bot.pid, ciclos a subir, MT5 conectado.

---

## FASE 2 — Macro Engine [COMPLETA]

7 daemons em threads independentes. Arrancam todos sem erros em cada boot.

| Ficheiro | Daemon | Funcao | Intervalo |
|---|---|---|---|
| `src/macro/vix_monitor.py` | VixMonitor | VIX → normal/caution/alert/kill/panic | 60s |
| `src/macro/dxy_basket.py` | DXYBasket | DXY sintetico (pesos ICE) → risk_off/neutral/risk_on | 60s |
| `src/macro/yield_monitor.py` | YieldMonitor | Curva FRED US10Y/2Y/3M → steep/flat/inverted | 30min |
| `src/macro/commodity_monitor.py` | CommodityMonitor | Gold, WTI, Brent (precos + variacao%) | 60s |
| `src/macro/news_interpreter.py` | NewsInterpreter | Noticias → bullish/neutral/bearish | 5min |
| `src/macro/economic_calendar.py` | EconomicCalendar | 120 eventos, blackout 30min | 1h |
| `src/macro/news_gate.py` | — | Filtro noticias macro | — |
| `src/benchmark/portfolio_monitor.py` | BenchmarkMonitor | 28 activos via yfinance, risk_on_score | 5min |

**Verificado:** `All daemons started: VIX, DXY, Yield, Commodity, News, Calendar, Benchmark` no log.

---

## FASE 3 — Analise [COMPLETA]

| Ficheiro | Funcao | API principal |
|---|---|---|
| `src/analysis/fair_price.py` | Preco Justo = fecho_anterior × (1+var_DXY%) + 8 canais Fibonacci | `calculate()` → FairPriceResult |
| `src/analysis/volatility_channels.py` | Sandwich de volatilidade: BB10 session × 10 niveis Fibonacci | `compute()` → VolatilityChannel |
| `src/analysis/yield_curve.py` | Curva completa US Treasury + carry trade + ADR flow + futuros | `fetch_yield_snapshot()` → YieldCurveSnapshot |
| `src/analysis/correlation.py` | Matriz rolante 20 periodos + correlacoes estruturais + penalidade 65% | `CorrelationMatrix.compute_state()` |
| `src/analysis/scenario_evaluator.py` | 5 vetos sequenciais → TENDENCIA_ALTA/BAIXA/INDEFINIDO/LATERAL/BLOQUEADO | `evaluate()` → ScenarioResult |
| `src/analysis/asset_profiler.py` | DNA do instrumento: classe, DXY beta, drivers macro, benchmark | `get_profile()` |
| `src/analysis/macro_calculator.py` | Surpresa economica (actual-consensus)/σ, regime score, yield z-score | `compute_regime_score()` |

**Verificado:** todos importam sem erros. Scenario `INDEFINIDO` em neutral+bearish = comportamento correcto.

### Logica do Scenario Evaluator

```
Veto 1 — Blackout de evento (<30min) → BLOQUEADO
Veto 2 — Spread muito largo         → BLOQUEADO
Veto 3 — Alinhamento macro          → sem alinhamento: penalty 65% no lot
Veto 4 — Volume insuficiente        → SKIP (sem entrada)
Veto 5 — Todos alinhados            → CONFIRMAR → TENDENCIA_ALTA ou BAIXA
Nenhum veto ativo mas sinais mistos → INDEFINIDO (sem trade)
```

---

## FASE 4 — Tecnicos [COMPLETA]

### Hierarquia de 4 camadas (formalizada 2026-06-04)

```
Camada 1 — Principal (base da decisao tecnica → MCS, BCS, HCS no TotalScore)
  MACD           — direcao, momentum, cumprimento de movimento
  Bollinger BB10 — compressao, expansao, extremos de volatilidade
  Hi-Lo Activator— range da sessao, pontos por cumprir            [adicionado 2026-06-04]
  ATR Stop       — stop dinamico, trailing, leitura de volatilidade [adicionado 2026-06-04]

Camada 2 — Confirmacao intradiaria (filtros binarios gate 4/8)
  VWAP   — preco justo intradiario e equilibrio de fluxo
  EMA 8  — timing e pullback curto
  SMA 50 / SMA 100 — estrutura e tendencia de preco
  Parabolic SAR — mudanca curta de direcao, apoio a stop tecnico

Camada 3 — Participacao (reforco CS / filtros binarios)
  Weis Wave / Volume — confirmacao de forca real do movimento
  Pivot Points       — zonas do dia e projecoes de reacao
  Fair Price (macro) — referencia de trabalho do ativo na sessao

Camada 4 — Contexto superior (→ CS e RS no TotalScore)
  Macro     — CPI, PIB, payroll, PMI, juros, DXY, VIX, ouro, petroleo
  Benchmark — 28 activos (S&P, DXY, VIX, yields, ouro, petroleo por simbolo)
  Risco     — size, stop, drawdown, exposicao, blackout de eventos
```

| Ficheiro | Funcao |
|---|---|
| `src/technical/indicators.py` | `compute_bundle()`: todos os indicadores das Camadas 1-3 |
| `src/technical/macd_analyzer.py` | Dentes MACD (peaks/valleys), divergencia, teeth→price levels |
| `src/technical/bollinger_analyzer.py` | Squeeze (percentil), expansao assimetrica, walking the band, unfulfilled points |
| `src/technical/multi_timeframe.py` | TF adaptativo por BB width, veto H1, confluencia 0-1.0 |
| `src/technical/signal_generator.py` | 8 confirmacoes (gate min 4/8), lot_multiplier em 3 camadas |

**Verificado:** `HiLoResult`, `ATRStopResult` no IndicatorBundle; `compute_bundle()` calcula Hi-Lo e ATR Stop.

---

## FASE 5 — Score Engine [COMPLETA — 2026-06-04]

### Formula TotalScore (7 componentes)

```
TotalScore = wm*MCS_n + wb*BCS_n + wh*HCS_n + wv*VES_n - we*ES_n + wc*CS_n - wr*RS_n

MCS  MACD Completion Score     — momentum por completar
BCS  Bollinger Completion Score — expansao/band por completar
HCS  Hi-Lo Completion Score    — range da sessao por cumprir     [novo 2026-06-04]
VES  Volatility Expansion Score — MCS + BCS + ATR expansion + volume surge
ES   Exhaustion Score          — fim de movimento (subtrai)
CS   Context Score             — macro + evento + benchmark + correlacao
RS   Risk Score                — VIX + ATR Stop proximity + evento + DD (subtrai)
                                 ATR Stop proximity integrado no RS [novo 2026-06-04]
```

### Pesos por classe de activo [MCS, BCS, HCS, VES, ES, CS, RS]

| Classe | MCS | BCS | HCS | VES | ES | CS | RS |
|---|---|---|---|---|---|---|---|
| forex | 0.24 | 0.20 | 0.14 | 0.16 | 0.12 | 0.09 | 0.05 |
| indices | 0.26 | 0.18 | 0.14 | 0.18 | 0.12 | 0.08 | 0.04 |
| gold | 0.22 | 0.22 | 0.14 | 0.16 | 0.14 | 0.08 | 0.04 |
| oil | 0.20 | 0.22 | 0.14 | 0.18 | 0.14 | 0.08 | 0.04 |
| treasuries | 0.18 | 0.20 | 0.14 | 0.16 | 0.18 | 0.09 | 0.05 |
| crypto | 0.28 | 0.18 | 0.12 | 0.20 | 0.10 | 0.06 | 0.06 |

### Thresholds de decisao

```
>= 0.75   → execute  (lot × 1.0)
0.55-0.75 → moderate (lot × 0.7)
0.40-0.55 → wait
< 0.40    → block
ES > 0.70 → block (mesmo com TotalScore alto)
```

**Verificado:** imports OK, `TotalScoreResult` tem `hcs_raw`, `hcs_n`. `describe_score()` inclui HCS.

---

## FASE 6 — Execucao e Risco [COMPLETA]

| Ficheiro | Funcao |
|---|---|
| `src/execution/order_manager.py` | Ordens MT5 (magic=20260902): market, limit, SL/TP, close |
| `src/risk/professional_risk.py` | Sizing: math.floor + volume_step MT5 + lot_penalty + tiers MICRO/STANDARD/GROWTH |
| `src/risk/var_calculator.py` | VaR parametrico e historico + DrawdownTracker + PortfolioRiskManager |
| `src/risk/execution_validator.py` | R:R liquido (apos execution cost) + spread/ATR + MFE/MAE tracker |

**Verificado:** todos importam sem erros.

---

## FASE 7 — Sessao e Validacao [COMPLETA]

| Ficheiro | Funcao |
|---|---|
| `src/session/market_sessions.py` | Deteccao sessoes: Asia/Londres/NY/Overlap + sleep adaptativo (90s/300s) |
| `src/session/prep_workflow.py` | 6 etapas de preparacao por sessao (news→indices→agenda→fair_price→scenario→levels) |
| `checks/daily_check.py` | 5 checks noturnos: health/liquidity/alerts/logs/backups |
| `checks/signal_report.py` | Qualidade de sinais por simbolo (formato OLD + NEW) |
| `checks/stress_test.py` | 6 testes de safety (T1-T6) |
| `checks/week_validator.py` | Day 7: Monte Carlo + AVANCAR/MANTER/PAUSAR |
| `checks/preflight.py` | preflight_check() chamado no boot |
| `scripts/day0_reset.py` | Reset estado para nova janela de validacao |
| `scripts/watchdog.py` | Process monitor com auto-restart (max 5 restarts/hora) |

**Verificado:** `daily_check.py` corre e reporta. `state_history.jsonl` a ser escrito a cada ciclo.

---

## FASE 7b — Opportunity-Permission Engine [COMPLETA — 2026-06-04]

**Spec:** `.ai/specs/opportunity-permission-engine.md`
**Ficheiro:** `src/engine/scanner.py`

### Arquitectura das 2 fases

```
Fase 1 — OpportunityScore (tecnico puro, sem contexto)
  OpportunityScore = a1*MCS + a2*BCS + a3*HCS + a4*VES - a5*ES
  Labels: weak | watchlist | strong

Fase 2 — PermissionScore (contexto + risco, sem tecnico)
  PermissionScore = b1*CS - b2*RS - b3*ES + b4*ATRFit
  Labels: BLOCK | REDUCE | CONFIRM | EXECUTE
```

**Logica:** Oportunidade fraca nao chega ao PermissionScore. Contexto proibitivo bloqueia mesmo que tecnicos sejam fortes. As 2 fases sao independentes e composable.

**Verificado:** `scan()`, `compute_opportunity_score()`, `compute_permission_score()` implementados.

---

## FASE 8 — Validacao 7 Dias [EM CURSO — Day 3]

**Inicio:** 2026-06-03 | **Fim previsto:** 2026-06-10
**Bot:** dry_run=true | ciclos activos | sleep=90s (London/NY) / 300s (off-session)

### Estado actual (2026-06-08 — Day 6)

```
Sessao:   London/NY (activa)
Regime:   a verificar com daily_check.py + signal_report.py
Sinais:   a verificar com signal_report.py --hours 24
MT5:      a verificar conectividade
Log:      logs/bot_stderr_current.log
```

### Historico de dias

| Dia | Data | Accao | Estado |
|---|---|---|---|
| Day 1 | 2026-06-03 | Arranque V9, day0_reset.py | [x] done |
| Day 2 | 2026-06-04 | signal_report, Hi-Lo + ATR Stop + HCS + O/P Engine | [x] done |
| Day 3 | 2026-06-05 | signal_report, ROADMAP formalizado, TotalScore 7 comp. | [x] done |
| Day 4 | 2026-06-06 | stress_test.py T1-T6 | [ ] verificar |
| Day 5 | 2026-06-07 | daily_check.py | [ ] verificar |
| Day 6 | 2026-06-08 | stress_test.py T1-T6 (HOJE) | [ ] pendente |
| Day 7 | 2026-06-09/10 | week_validator.py → AVANCAR/MANTER/PAUSAR | [ ] pendente |

### Protocolo diario

| Dia | Accao | Criterio de pass |
|---|---|---|
| 1-7 manha | `python checks/daily_check.py` | ALL CLEAR |
| Dia 2 | `python checks/signal_report.py --hours 24` | sinais presentes quando regime != indefinido |
| Dia 4, 6 | `python checks/stress_test.py` | T1-T6 todos PASS |
| Dia 7 | `python checks/week_validator.py` | AVANCAR (PF>=1.3, WR>=48%, DD<=6%) |

### Proximas accoes (Day 6 — HOJE 2026-06-08)

- [ ] `daily_check.py` — verificar saude geral
- [ ] `stress_test.py` — T1-T6 devem passar todos (obrigatorio Day 6)
- [ ] `signal_report.py --hours 24` — qualidade de sinais das ultimas 24h
- [ ] Dia 7 (2026-06-09/10): `week_validator.py` → veredicto AVANCAR/MANTER/PAUSAR

### Criterios para AVANCAR (Day 7)

```
PF      >= 1.3
WR      >= 48%
DD      <= 6%
Uptime  >= 95%
T1-T6   todos PASS
```

---

## FASE 9 — Dashboard V9 [PENDENTE]

**Pre-requisito:** Fase 8 completa com sinal estavel.

### 9.1 Backend FastAPI

| Ficheiro | Estado | Tarefa |
|---|---|---|
| `server/main.py` | [x] done | FastAPI + CORS + JWT + WebSocket hub |
| `server/auth.py` | [x] done | JWT create/verify |
| `server/state_reader.py` | [x] done | le state.json |
| `server/control_writer.py` | [x] done | comandos de controlo ao bot |
| `server/bot_manager.py` | [x] done | start/stop do processo bot |
| `server/ws/hub.py` | [x] done | WebSocket broadcast (polling 1s) |
| `/api/indicators` | [ ] pendente | expor MCS/BCS/HCS/VES/ES/CS/RS por simbolo |
| `/api/score` | [ ] pendente | TotalScoreResult em tempo real |
| `/api/regime` | [ ] pendente | scenario + global_regime + news_score |
| `/api/opportunity` | [ ] pendente | OpportunityScore + PermissionScore por simbolo |

### 9.2 React Dashboard

| Componente | Estado | Tarefa |
|---|---|---|
| `dashboard/index.html` + `js/app.js` + `css/main.css` | [x] base | SPA montada |
| ScorePanel | [ ] pendente | barras MCS/BCS/HCS/VES/ES/CS/RS por simbolo |
| RegimeIndicator | [ ] pendente | badge scenario + macro (INDEFINIDO/ALTA/BAIXA/BLOQUEADO) |
| SignalFeed | [ ] pendente | sinais em tempo real com rationale do TotalScore |
| SessionClock | [ ] pendente | sessao activa + countdown + sleep_until |
| OpportunityMatrix | [ ] pendente | grid simbolos × OpportunityScore × PermissionScore |

### 9.3 Integracao state.json V9

- [ ] Incluir `total_score_result` por simbolo no state.json
- [ ] Incluir `opportunity_score` + `permission_score` por simbolo no state.json
- [ ] WebSocket broadcast dos novos campos (HCS, scenario, regime, scores)

### Plano de implementacao Fase 9

```
Task 9.1 — state.json V9 schema               [S] — prerequisito de tudo
Task 9.2 — /api/indicators + /api/score        [M] — ler TotalScoreResult do state
Task 9.3 — /api/regime + /api/opportunity      [S] — ler scenario e scanner do state
Task 9.4 — ScorePanel React                    [M] — barras animadas por simbolo
Task 9.5 — RegimeIndicator + SignalFeed        [M] — badges + feed live
Task 9.6 — OpportunityMatrix                   [L] — grid com cores por score
Task 9.7 — Teste e2e dashboard → bot           [M] — ws conecta, dados chegam ao browser
```

---

## FASE 9b — Testes Unitarios [PENDENTE — DIVIDA ALTA]

**Pre-requisito:** pode comecar durante Fase 8 (paralelo).

### Plano de implementacao

```
Task T1 — tests/test_hi_lo_activator.py        [M] — HiLoResult, edge cases sessao/range
Task T2 — tests/test_atr_stop.py               [M] — ATRStopResult, trailing, proximity_pct
Task T3 — tests/test_total_score.py            [L] — TotalScore 7 componentes, pesos, thresholds
Task T4 — tests/test_opportunity_permission.py [M] — scanner.py: 2 fases, labels
Task T5 — tests/test_scenario_evaluator.py     [S] — 5 vetos, resultados esperados
Task T6 — CI hook: pytest pre-commit           [S] — bloquear commit se testes falham
```

---

## FASE 10 — Scalping + Pyramiding [PENDENTE]

**Pre-requisito:** Day 7 com veredicto AVANCAR.

### Plano de implementacao

```
Task 10.1 — scalping.yaml enabled: true             [XS] — flip de flag
Task 10.2 — Testar M5: EURUSD/GBPUSD/USDJPY         [M]  — 0.25%/trade, max 2 posicoes
Task 10.3 — src/risk/pyramiding.py                  [L]  — max 2 adds, cada add = 50% lote
Task 10.4 — Gate pyramiding: TotalScore >= 0.75 H1  [M]  — integracao com score engine
Task 10.5 — Escalar 0.50% → 0.75% risco/trade       [S]  — apos Day 14 estavel
```

---

## FASE 11 — VPS Windows 24/7 [PENDENTE]

**Pre-requisito:** Fase 10 estavel.

```
Task 11.1 — Provisionar VPS Windows Server          [M]  — Contabo/OVH/AWS (~20-50 EUR/mes)
Task 11.2 — Instalar MT5 + ActivTrades no VPS       [M]  — configurar conta demo primeiro
Task 11.3 — Task Scheduler: Bot + Server + Watchdog [M]  — auto-restart, logs persistentes
Task 11.4 — Nginx reverse proxy HTTPS               [M]  — Let's Encrypt, porta 443
Task 11.5 — Testar acesso dashboard de telemovel    [S]  — HTTPS + auth JWT
```

---

## FASE 12 — Paper Trading 2 Semanas [PENDENTE]

**Pre-requisito:** Fase 11 estavel.

| Metrica | Minimo | Ideal |
|---|---|---|
| Win rate | >= 52% | >= 55% |
| Profit factor | >= 1.3 | >= 1.5 |
| Max drawdown diario | < 6% | < 4% |
| Trades analisados | >= 50 | >= 100 |
| Uptime | >= 14 dias | 14 dias sem crash |

---

## FASE 13 — Capital Real [PENDENTE]

**Pre-requisito:** Fase 12 com todos os criterios cumpridos.

```
1. Conta real ActivTrades — lotes minimos (0.01)
2. Perfil live_safe: dry_run=false, lotes 50% do calculado
3. Perfil live completo apos 30 dias de live_safe lucrativo
4. Escalar capital gradualmente — nunca mais de 2× por mes
```

---

## DIVIDA TECNICA

| Item | Prioridade | Fase alvo | Estado |
|---|---|---|---|
| Testes unitarios Hi-Lo Activator | ALTA | 9b | [ ] pendente |
| Testes unitarios ATR Stop | ALTA | 9b | [ ] pendente |
| Testes integracao TotalScore 7 componentes | ALTA | 9b | [ ] pendente |
| Testes Opportunity-Permission Engine | ALTA | 9b | [ ] pendente |
| `/api/indicators` + `/api/score` no server | MEDIA | 9 | [ ] pendente |
| ScorePanel + RegimeIndicator no dashboard | MEDIA | 9 | [ ] pendente |
| state.json incluir TotalScoreResult | MEDIA | 9 | [ ] pendente |
| OpportunityMatrix no dashboard | MEDIA | 9 | [ ] pendente |
| Scalping validado em M5 | BAIXA | 10 | [ ] pendente |
| Pyramiding implementado | BAIXA | 10 | [ ] pendente |
| CI hook pytest pre-commit | BAIXA | 9b | [ ] pendente |

---

## DECISOES TECNICAS

| Data | Decisao | Rationale |
|---|---|---|
| 2026-06-03 | Migracao V8 → V9 | Arquitectura macro-driven mais robusta e modular |
| 2026-06-04 | Hi-Lo Activator — Camada 1 | Range da sessao como componente primario da decisao tecnica |
| 2026-06-04 | ATR Stop (Chandelier) — Camada 1 | Stop dinamico com proximidade a entrar no RS como penalidade |
| 2026-06-04 | HCS criado no TotalScore | Hi-Lo passa a ter peso directo no score final (wh) |
| 2026-06-04 | RS integra atr_stop_dist_pct | Preco proximo do stop aumenta penalidade de risco |
| 2026-06-04 | 8 confirmacoes, gate 4/8 | Mais filtros → menos falsos positivos em regime incerto |
| 2026-06-04 | Hierarquia 4 camadas formalizada | Funcao fixa por indicador: direcao/volatilidade/range/stop/confirmacao/contexto/risco |
| 2026-06-04 | Opportunity-Permission Engine | TotalScore dividido em 2 fases independentes. Spec: .ai/specs/opportunity-permission-engine.md |
| 2026-06-05 | ROADMAP.md formalizado | Ficheiro vivo de planificacao: actualizar sempre que nova integracao discutida |
| 2026-06-08 | RSI(14) integrado no scanner | rsi=50.0 neutro por defeito. Momentum +0.02, extremo mod -0.03/RS+0.07, extremo forte -0.06/RS+0.15. checks/rsi_report.py |
| 2026-06-08 | RSI Calibration Policy | config/rsi_calibration.yaml + src/engine/rsi_calibration.py. Peso dinamico por classe x TF x vol_regime. Matriz: increase/maintain/reduce/disable. --calibrate e --apply no rsi_report |
| 2026-06-08 | Idiosyncratic Move (TECNICO_PURO) | Novo Scenario.TECNICO_PURO activa quando macro=neutro mas 3/4 indicadores (MACD+HiLo+ATRStop+SAR) concordam e TS>=0.72. Gates elevados: 5/8 confirms, lote×0.50 (sem macro), conf<=7. Activar/desactivar: strategies.yaml idiosyncratic_move.enabled |

---

## COMO CORRER O SISTEMA

```powershell
# Arrancar bot (output para ficheiro)
$root = "C:\Users\bruno\Desktop\Bot_probability _arbitrage"
Start-Process python -ArgumentList "-m src.main" -WorkingDirectory $root `
  -RedirectStandardError "$root\logs\bot_stderr_current.log" `
  -RedirectStandardOutput "$root\logs\bot_stdout_current.log" `
  -WindowStyle Hidden

# Ver log em tempo real
Get-Content logs\bot_stderr_current.log -Tail 20 -Wait

# Verificar sinais
python checks/signal_report.py --hours 4

# Estado geral
python checks/daily_check.py

# Arrancar servidor FastAPI
uvicorn server.main:app --reload --port 8000
```

---

## REGRA DE ACTUALIZACAO

```
Quando discutires uma nova integracao com a IA → actualizar secção relevante + DIVIDA TECNICA
Quando uma fase ficar completa → mudar [EM CURSO] / [PENDENTE] para [COMPLETA] + data
Quando tomares uma decisao tecnica → adicionar linha em DECISOES TECNICAS
Quando a validacao diaria passar → actualizar "Estado actual" na Fase 8
```
