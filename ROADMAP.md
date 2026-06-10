# ROADMAP — AlphaSystem V9

**Ultima actualizacao:** 2026-06-10
**Versao:** V9.0 — Macro-Driven Engine
**Conta demo:** MT5 #6238864 (ActivTrades, EUR)
**Entrada:** `python -m src.main` (NUNCA `python src/main.py`)

> Ficheiro vivo. Actualizar SEMPRE que: nova feature implementada, decisao tecnica tomada,
> milestone atingido, divida identificada, nova integracao discutida.
> Ver tambem: AGENTS.md (memoria tecnica) e .ai/skills/context-router/SKILL.md (routing de skills).

---

## SKILLS DE TRABALHO (context-router)

| Tipo de tarefa | Skills a carregar |
|---|---|
| Briefing / especificacao | `spec-viva` |
| Arquitectura / design | `architecture-first` |
| Plano de implementacao | `implementation-plan` |
| Escrever codigo | `implementation-assistant` + `tdd-workflow` |
| Escrever testes | `tdd-workflow` + `qa-testing` |
| Debug / erro | `debugging-loop` |
| Refactoring | `refactor-guardrail` |
| Code review | `code-review` |
| Seguranca | `security-review` |
| Deploy / CI/CD | `ci-cd-release` + `devops-secops` |
| Documentacao | `documentation-builder` + `technical-writer` |

**Regra:** sempre ler AGENTS.md primeiro → context-router decide skills → max 3 skills em simultaneo.

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
Fase 7d [COMPLETA]   Idiosyncratic Move      — TECNICO_PURO: macro neutro + tecnicos fortes -> entrada conservadora
Fase 8  [EM CURSO]   Validacao 7 Dias        — Day 8, week_validator.py pendente (2026-06-10)
Fase 9A [PENDENTE]   Refactor Engine V9.1    — simplificar vetos, regime router, reduzir dependencia macro absoluta
Fase 9B [PENDENTE]   SMC Layer               — Order Blocks, FVG, BOS/ChoCh, Liquidity Sweeps
Fase 9C [PENDENTE]   Capital Manager V2      — 3 camadas capital + Kelly/4 sizing + Margin Semaphore
Fase 9D [PENDENTE]   Dashboard V9            — server/ FastAPI + dashboard/ React (apos engine V9.1 estavel)
Fase 9E [PENDENTE]   Testes Unitarios        — cobertura dos novos modulos (divida tecnica alta)
Fase 10 [PENDENTE]   ML Filter + WFO         — RandomForest quality filter + Walk-Forward Optimization
Fase 11 [PENDENTE]   Scalping                — activar apos V9.1 validado (Day 7+ OK)
Fase 12 [PENDENTE]   VPS Windows 24/7        — operacao continua
Fase 13 [PENDENTE]   Paper Trading 2 Semanas — validacao real do V9.1
Fase 14 [PENDENTE]   Capital Real            — transicao gradual
```

---

## NOVA DIRECAO — V9.1 (Pos-Veredicto Day 8)

**Decisao (2026-06-10):** O motor V9 correu 199 ciclos com `signals=0` e `scenario=indefinido`. O problema central e estrutural: a dependencia de consenso macro absoluto como veto cria um sistema demasiado defensivo que nao executa mesmo quando os tecnicos estao corretos.

**Filosofia nova:** Regime-based strategy switching. O mercado decide a estrategia; o macro e um contexto, nao uma barreira.

### Gap Analysis — V9 → V9.1

| Componente | V9 Actual | V9.1 Alvo | Accao |
|---|---|---|---|
| Regime Detection | `scenario_evaluator.py` (5 vetos, macro obrigatorio) | `RegimeDetector` simples: TRENDING/RANGING/VOLATILE | Refactor: relaxar veto macro, manter base ADX/EMA |
| Signal Engine | TotalScore 7 comp + gate 4/8 (bloqueia muito) | Confluence 3/5: EMA+MACD/RSI+PriceAction+ML+Session | Simplificar: remover dependencia de TS>=0.75 absoluto |
| Price Action | Nao existe (SMC nao implementado) | Order Blocks + FVG + BOS/ChoCh + Liquidity Sweeps | NOVO: `src/analysis/smc.py` |
| Capital Manager | Sem divisao em camadas (1 pool) | 3 camadas: 70% ativo / 20% margem / 10% emergencia | NOVO: `src/risk/capital_manager.py` |
| Position Sizing | `professional_risk.py` (0.5% base, multiplicadores) | Kelly/4 dinamico (regime × DD × winrate recente) | Upgrade: integrar Kelly no `professional_risk.py` |
| Margin Manager | Nao existe | Semaforo 5 niveis (>500% verde, <150% critico) | NOVO: `src/risk/margin_manager.py` |
| TP System | TP1/TP2 basico | Scaled TP: 40% TP1 + BE → 35% TP2 + Trailing → 25% runner | Upgrade: `src/execution/order_manager.py` |
| ML Filter | Nao existe | RandomForest quality filter (walk-forward) | NOVO (Fase 10): `src/analysis/ml_filter.py` |
| Walk-Forward | Nao implementado | WFO anti-overfitting | NOVO (Fase 10): `scripts/walk_forward.py` |
| Circuit Breaker | Kill switch (nivel unico) | 4 niveis: ALERTA/REDUCAO/PAUSA/PARAGEM TOTAL | Upgrade: `src/engine/circuit_breaker.py` |

### O que MANTER do V9

```
[MANTER] src/mt5_bridge.py                — conexao MT5 estavel
[MANTER] src/macro/vix_monitor.py         — VIX como contexto (nao veto absoluto)
[MANTER] src/macro/economic_calendar.py   — blackout de eventos (regra de ouro)
[MANTER] src/analysis/correlation.py      — penalidade de correlacao
[MANTER] src/session/market_sessions.py   — janelas London/NY (timing institucional)
[MANTER] src/risk/professional_risk.py    — base de sizing (upgrade com Kelly)
[MANTER] src/risk/var_calculator.py       — VaR e DrawdownTracker
[MANTER] src/technical/indicators.py      — todos os indicadores (MACD, BB, Hi-Lo, ATR Stop)
[MANTER] checks/ + scripts/               — validacao e operacao
[MANTER] server/ + dashboard/             — infraestrutura de monitorização
```

### O que SIMPLIFICAR/REMOVER como barreira

```
[SIMPLIFICAR] scenario_evaluator.py       — manter como contexto, nao como veto absoluto
[SIMPLIFICAR] TotalScore como hard gate   — usar como score informativo, nao bloqueador unico
[SIMPLIFICAR] PermissionScore gate        — manter logica, mas threshold mais permissivo
[SIMPLIFICAR] Requisito 4/8 confirmacoes  — reduzir para 3/5 em regime TRENDING claro
[REMOVER COMO VETO] macro=neutral bloqueador total — neutral nao e sinal de nao entrar
```

### Estrategia de Implementacao (post-veredicto)

```
AVANCAR → implementar V9.1 incrementalmente (sem quebrar o que funciona)
MANTER  → correr mais 7 dias E planear V9.1 em paralelo
PAUSAR  → refactor agressivo para V9.1 antes de voltar a correr
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

## FASE 8 — Validacao 7 Dias [EM CURSO — Day 7]

**Inicio:** 2026-06-03 | **Fim previsto:** 2026-06-10
**Bot:** dry_run=true | ciclos activos | sleep=90s (London/NY) / 300s (off-session)

### Estado actual (2026-06-10 — POS-DAY 7)

```
Sessao:   Bot parado — ultimo ciclo: cycle=199 (2026-06-09T19:19Z)
Regime:   indefinido / macro=neutral (persistente durante toda a semana)
Sinais:   signals=0 em todos os ciclos (sem sinal executavel)
Scanner:  watchlist=[LCrude 0.41, Brent 0.40, Usa500 0.46, UsaTec 0.44, GOLD 0.43]
MT5:      activo durante NY session (8/9 symbols activos)
Veredicto: week_validator.py PENDENTE — correr HOJE para fechar Fase 8
Log:      logs/bot_stderr_current.log (ultimo: 2026-06-09T19:19Z)
```

### Historico de dias

| Dia | Data | Accao | Estado |
|---|---|---|---|
| Day 1 | 2026-06-03 | Arranque V9, day0_reset.py | [x] done |
| Day 2 | 2026-06-04 | signal_report, Hi-Lo + ATR Stop + HCS + O/P Engine | [x] done |
| Day 3 | 2026-06-05 | signal_report, ROADMAP formalizado, TotalScore 7 comp. | [x] done |
| Day 4 | 2026-06-06 | stress_test.py T1-T6 | [ ] confirmar |
| Day 5 | 2026-06-07 | daily_check.py | [ ] confirmar |
| Day 6 | 2026-06-08 | stress_test.py T1-T6 + RSI + TECNICO_PURO | [ ] confirmar |
| Day 7 | 2026-06-09 | Bot: cycle=199, scenario=indefinido, signals=0 ao longo de toda NY | [x] ciclos ok |
| Day 8 | 2026-06-10 | week_validator.py → AVANCAR/MANTER/PAUSAR (CORRER HOJE) | [ ] pendente |

### Protocolo diario

| Dia | Accao | Criterio de pass |
|---|---|---|
| 1-7 manha | `python checks/daily_check.py` | ALL CLEAR |
| Dia 2 | `python checks/signal_report.py --hours 24` | sinais presentes quando regime != indefinido |
| Dia 4, 6 | `python checks/stress_test.py` | T1-T6 todos PASS |
| Dia 7 | `python checks/week_validator.py` | AVANCAR (PF>=1.3, WR>=48%, DD<=6%) |

### Proximas accoes (Day 8 — HOJE 2026-06-10)

- [ ] `python checks/daily_check.py` — saude geral
- [ ] `python checks/stress_test.py` — confirmar T1-T6 PASS
- [ ] `python checks/signal_report.py --hours 48` — qualidade de sinais (48h para cobrir todo o periodo)
- [ ] `python checks/week_validator.py` — **veredicto final** AVANCAR/MANTER/PAUSAR
- Nota: scenario=indefinido/macro=neutral persistente → sinais=0 esperado; validar via PF, WR e DD dos ciclos dry_run

### Criterios para AVANCAR (Day 7)

```
PF      >= 1.3
WR      >= 48%
DD      <= 6%
Uptime  >= 95%
T1-T6   todos PASS
```

### Pos-veredicto

```
AVANCAR  → iniciar Fase 9 (Dashboard) + Fase 9b (testes) em paralelo
            apos 14 dias estaveis: Fase 10 (Scalping)
MANTER   → continuar validacao mais 7 dias, sem alterar parametros
PAUSAR   → diagnosticar problemas, corrigir, novo day0_reset.py
```

---

## FASE 9A — Refactor Engine V9.1 [PENDENTE — pos-veredicto]

**Pre-requisito:** veredicto Day 8 + decisao de estrategia.
**Objectivo:** Eliminar o `signals=0` estrutural. Manter disciplina de risco. Operar mais.

### ADR-001: Remover macro como veto absoluto
```
Contexto:  Bot correu 199 ciclos em 8 dias com signals=0. Causa: scenario=indefinido
           bloqueia todas as entradas mesmo quando ADX>25 e tecnicos alinham.
Decisao:   Macro passa a ser CONTEXTO (ajusta sizing/confianca), nao VETO.
           Excepção: blackout de eventos (<30min de NFP/FOMC/CPI) mantém-se como veto.
Alternativa rejeitada: manter V9 e esperar regime macro mudar.
Consequencias: mais operacoes, risco gerido por Capital Manager V2 e Circuit Breaker.
```

### ADR-002: Regime Router simplificado
```
Contexto:  scenario_evaluator.py tem 5 vetos sequenciais que raramente passam todos.
Decisao:   Implementar RegimeDetector com 3 estados: TRENDING / RANGING / VOLATILE
           TRENDING  → trend following activo (ADX>25 + estrutura HH/LL)
           RANGING   → mean reversion activo (ADX<20 + BB comprimido)
           VOLATILE  → reduz exposicao (ATR_ratio > 2.0 ou VIX > alerta)
Ficheiro:  src/engine/regime_router.py
```

### ADR-003: Sistema de confluencia 3/5
```
Contexto:  Gate 4/8 com dependencia de macro cria bloqueio sistematico.
Decisao:   Confluencia minima 3/5 pontos:
           +1 EMA Cross alinhado com regime (H1 context)
           +1 RSI/MACD confirmam direcao
           +1 Price Action (OB/FVG/BOS ou Hi-Lo + ATR Stop)
           +1 ML Filter = HIGH (opcional, fase 10)
           +1 Sessao de mercado favoravel (London/NY overlap priority)
Threshold: 3/5 → entrada | 2/5 → watchlist | <2 → ignorar
```

### Plano de implementacao Fase 9A

```
Task 9A.1 — src/engine/regime_router.py         [S]  [DONE 2026-06-10] — 3 regimes (TRENDING_UP/DOWN/RANGING/VOLATILE), ADX+MA+indicators, macro=contexto
Task 9A.2 — relaxar scenario_evaluator.py       [M]  [DONE 2026-06-10] — VETO 5 reescrito: trending regime bypassa macro=neutral; sinal gerado com ADX>=25
Task 9A.3 — confluencia 3/5 em signal_generator [M]  [DONE 2026-06-10] — TRENDING: 3/8 confirms + lot_context; TECNICO_PURO: 5/8; Normal: 4/8
Task 9A.4 — circuit_breaker.py 4 niveis         [M]  [DONE 2026-06-10] — GREEN/YELLOW(lot×0.5)/ORANGE(no entry)/RED(halt+close); integrado no orchestrator
Task 9A.5 — testes: signals>0 em trending regime [S]  [DONE 2026-06-10] — 43 testes PASS: test_regime_router.py (17) + test_circuit_breaker.py (26)
Task 9A.6 — day0_reset + nova janela 7 dias      [XS] [PENDENTE] — reiniciar validacao com V9.1
```

---

## FASE 9B — SMC Layer [PENDENTE]

**Pre-requisito:** Fase 9A estavel.
**Objectivo:** Adicionar leitura de Smart Money para melhorar qualidade de entradas.

### Conceitos a implementar

```
Order Blocks (OB)     — ultima vela de direcao oposta antes de movimento forte
                        bullish_ob: ultimo candle bearish antes de impulso bullish
                        bearish_ob: ultimo candle bullish antes de impulso bearish

Fair Value Gaps (FVG) — desequilibrio de 3 velas: corpo da 3a nao cobre range da 1a
                        zona de reentrada de alta probabilidade

Break of Structure (BOS) — preco fecha alem do swing anterior → tendencia confirmada
Change of Character (ChoCh) — primeira violacao de estrutura oposta → alerta de reversao

Liquidity Sweeps      — spike alem de high/low recente com reversao rapida
                        sinal de cacada de stops institucional
```

| Ficheiro | Funcao |
|---|---|
| `src/analysis/smc.py` | detect_order_blocks, detect_fvg, detect_bos, detect_choch, detect_liq_sweep |
| `src/technical/signal_generator.py` | integrar SMC como +1 no sistema de confluencia 3/5 |

### Plano de implementacao Fase 9B

```
Task 9B.1 — src/analysis/smc.py: OB detection         [M]
Task 9B.2 — src/analysis/smc.py: FVG detection        [M]
Task 9B.3 — src/analysis/smc.py: BOS/ChoCh detection  [M]
Task 9B.4 — src/analysis/smc.py: Liquidity Sweeps     [S]
Task 9B.5 — integrar SMC no signal_generator.py       [M]
Task 9B.6 — testes unitarios smc.py                   [M]
```

---

## FASE 9C — Capital Manager V2 [PENDENTE]

**Pre-requisito:** Pode comecar em paralelo com 9A.

### Arquitectura de capital em 3 camadas

```
CAPITAL TOTAL
├── 70% CAPITAL ATIVO      — sujeito a trades e risco diario
├── 20% RESERVA DE MARGEM  — nunca em trades, protege contra margin calls
└── 10% RESERVA EMERGENCIA — activa apenas se DD >= 12% do capital ativo
```

### Modulos a criar

| Ficheiro | Funcao |
|---|---|
| `src/risk/capital_manager.py` | 3 camadas + rebalanceamento mensal + Kelly/4 sizing |
| `src/risk/margin_manager.py` | Semaforo 5 niveis: >500% verde / 300-500% amarelo / 200-300% laranja / <200% vermelho / <150% critico |

### Kelly Criterion (Quarter-Kelly)

```
f* = (W x R - (1-W)) / R   # Kelly completo
sizing = f* / 4             # Quarter Kelly (conservador)
cap_absoluto = 2%           # Nunca mais de 2% por trade
```

### TP Escalonado (upgrade ao order_manager)

```
TP1 (40%) → fecha 40%, move SL para Break Even
TP2 (35%) → fecha 35%, activa trailing stop adaptativo (ATR x 1.0)
TP3 (25%) → runner, trailing stop adaptativo (ATR x 1.2), fecha por sinal oposto
```

### Plano de implementacao Fase 9C

```
Task 9C.1 — src/risk/capital_manager.py (3 camadas + Kelly)   [M]
Task 9C.2 — src/risk/margin_manager.py (semaforo 5 niveis)    [M]
Task 9C.3 — upgrade order_manager.py (TP escalonado 40/35/25) [M]
Task 9C.4 — upgrade professional_risk.py (integrar Kelly)     [S]
Task 9C.5 — testes: sizing com diferentes DD/regime/winrate   [M]
```

---

## FASE 9D — Dashboard V9 [PENDENTE]

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

## FASE 9E — Testes Unitarios [PENDENTE — DIVIDA ALTA]

**Pre-requisito:** cobrir modulos V9.1 novos primeiro.

### Plano de implementacao

```
Task T1 — tests/test_regime_router.py          [M] — 3 regimes, transicoes, edge cases
Task T2 — tests/test_smc.py                    [M] — OB, FVG, BOS/ChoCh, sweeps
Task T3 — tests/test_capital_manager.py        [M] — 3 camadas, Kelly, rebalanceamento
Task T4 — tests/test_margin_manager.py         [M] — 5 niveis, accoes automaticas
Task T5 — tests/test_hi_lo_activator.py        [M] — HiLoResult, edge cases
Task T6 — tests/test_atr_stop.py               [M] — ATRStopResult, trailing
Task T7 — tests/test_total_score.py            [L] — TotalScore 7 componentes
Task T8 — tests/test_opportunity_permission.py [M] — scanner.py: 2 fases, labels
Task T9 — CI hook: pytest pre-commit           [S] — bloquear commit se testes falham
```

---

## FASE 10 — ML Filter + Walk-Forward [PENDENTE]

**Pre-requisito:** Fases 9A/9B/9C estaveis com dados suficientes (min. 200 trades).

### ML Filter (RandomForest Quality Classifier)

```
Funcao: NAO gera sinais — FILTRA sinais das camadas 1 e 2.
Classifica: HIGH (>0.65) / MEDIUM (0.50-0.65) / LOW (<0.50)
Features:   RSI(14), ADX, ATR_ratio, volume_ratio, session, day_of_week, spread_ratio
Treino:     walk-forward (nao single backtest — evita overfitting)
```

### Walk-Forward Optimization (WFO)

```
Metodo: janela deslizante 3 meses
  TREINO (70%) | VALIDACAO | TEST (OOS min. 6 meses)
Regras anti-overfitting:
  max 5 parametros optimizaveis por estrategia
  degradation check: OOS < 60% IS → rejeita
  Monte Carlo simulation sobre resultados
```

### Plano de implementacao Fase 10

```
Task 10.1 — src/analysis/ml_filter.py (RandomForest)      [L]
Task 10.2 — scripts/walk_forward.py (WFO pipeline)        [L]
Task 10.3 — integrar ML Filter no signal_generator.py     [M]
Task 10.4 — scripts/train_ml_filter.py (treino periodico) [M]
Task 10.5 — validacao: ML Filter melhora WR >= 5%?        [S]
```

---

## FASE 11 — Scalping + Pyramiding [PENDENTE]

**Pre-requisito:** V9.1 (Fases 9A-9C) validado com veredicto AVANCAR.

### Plano de implementacao

```
Task 11.1 — scalping.yaml enabled: true             [XS] — flip de flag
Task 11.2 — Testar M5: EURUSD/GBPUSD/USDJPY         [M]  — 0.25%/trade, max 2 posicoes
Task 11.3 — src/risk/pyramiding.py                  [L]  — max 2 adds, cada add = 50% lote
Task 11.4 — Gate pyramiding: regime=TRENDING + 3/5  [M]  — integracao com regime router
Task 11.5 — Escalar risco apos Day 14 estavel        [S]  — via Capital Manager V2
```

---

## FASE 12 — VPS Windows 24/7 [PENDENTE]

**Pre-requisito:** Fase 11 estavel.

```
Task 11.1 — Provisionar VPS Windows Server          [M]  — Contabo/OVH/AWS (~20-50 EUR/mes)
Task 11.2 — Instalar MT5 + ActivTrades no VPS       [M]  — configurar conta demo primeiro
Task 11.3 — Task Scheduler: Bot + Server + Watchdog [M]  — auto-restart, logs persistentes
Task 11.4 — Nginx reverse proxy HTTPS               [M]  — Let's Encrypt, porta 443
Task 11.5 — Testar acesso dashboard de telemovel    [S]  — HTTPS + auth JWT
```

---

## FASE 13 — Paper Trading 2 Semanas [PENDENTE]

**Pre-requisito:** Fase 12 estavel.

| Metrica | Minimo | Ideal |
|---|---|---|
| Win rate | >= 52% | >= 55% |
| Profit factor | >= 1.3 | >= 1.5 |
| Max drawdown diario | < 6% | < 4% |
| Trades analisados | >= 50 | >= 100 |
| Uptime | >= 14 dias | 14 dias sem crash |

---

## FASE 14 — Capital Real [PENDENTE]

**Pre-requisito:** Fase 13 com todos os criterios cumpridos.

```
1. Conta real ActivTrades — lotes minimos (0.01)
2. Perfil live_safe: dry_run=false, lotes 50% do calculado
3. Capital em 3 camadas (Capital Manager V2): 70/20/10
4. Perfil live completo apos 30 dias de live_safe lucrativo
5. Escalar capital gradualmente via Kelly/4 — nunca mais de 2x por mes
```

---

## DIVIDA TECNICA

| Item | Prioridade | Fase alvo | Estado |
|---|---|---|---|
| RegimeRouter (simplificar scenario_evaluator) | CRITICA | 9A | [ ] pendente |
| Confluencia 3/5 (substituir gate 4/8 em trending) | CRITICA | 9A | [ ] pendente |
| Circuit breaker 4 niveis | ALTA | 9A | [ ] pendente |
| SMC: Order Blocks + FVG + BOS/ChoCh | ALTA | 9B | [ ] pendente |
| Capital Manager V2 (3 camadas + Kelly/4) | ALTA | 9C | [ ] pendente |
| Margin Manager (semaforo 5 niveis) | ALTA | 9C | [ ] pendente |
| TP escalonado 40/35/25% + trailing | ALTA | 9C | [ ] pendente |
| Testes unitarios regime_router + SMC | ALTA | 9E | [ ] pendente |
| Testes unitarios Hi-Lo + ATR Stop | ALTA | 9E | [ ] pendente |
| Testes integracao TotalScore 7 componentes | MEDIA | 9E | [ ] pendente |
| Testes Opportunity-Permission Engine | MEDIA | 9E | [ ] pendente |
| Dashboard: novos endpoints V9.1 | MEDIA | 9D | [ ] pendente |
| ML Filter RandomForest | BAIXA | 10 | [ ] pendente |
| Walk-Forward Optimization | BAIXA | 10 | [ ] pendente |
| Scalping validado em M5 | BAIXA | 11 | [ ] pendente |
| Pyramiding implementado | BAIXA | 11 | [ ] pendente |
| CI hook pytest pre-commit | BAIXA | 9E | [ ] pendente |

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
| 2026-06-10 | Nova Direccao V9.1 | 199 ciclos com signals=0 confirmam que macro-as-veto e demasiado defensivo. Adoptar: regime-based routing (TRENDING/RANGING/VOLATILE) + confluencia 3/5 + SMC layer + Capital Manager V2 (3 camadas, Kelly/4) + Margin Semaphore. Macro passa a contexto (ajusta sizing), nao veto. Blackout de eventos mantem-se como unico veto hard. |
| 2026-06-10 | Capital Manager V2 — 3 camadas | 70% capital ativo / 20% reserva margem (nunca em trades) / 10% emergencia (activa se DD>=12%). Sizing: Quarter Kelly = f*/4, cap absoluto 2% por trade. Multipliers: regime × drawdown_atual × winrate_recente. |
| 2026-06-10 | TP Escalonado 40/35/25% | TP1: fecha 40%, move SL para break-even. TP2: fecha 35%, activa trailing ATR×1.0. TP3 (runner): 25% restante, trailing ATR×1.2, fecha por sinal oposto ou trailing atingido. Melhora sobrevivencia em movimentos parcialmente corretos. |
| 2026-06-10 | SMC Layer planeada (Fase 9B) | Order Blocks, Fair Value Gaps, Break of Structure, Liquidity Sweeps. Funcao: fonte de price action institucional para o ponto +1 no sistema de confluencia 3/5. Ficheiro: src/analysis/smc.py |
| 2026-06-10 | ML Filter planeado (Fase 10) | RandomForest quality classifier (HIGH/MEDIUM/LOW). NAO gera sinais — filtra sinais existentes. Treino walk-forward (70% treino, OOS >6 meses, max 5 parametros). Implementar so apos 200+ trades com V9.1. |

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

## SEQUENCIA DE FASES (VISAO MACRO)

```
[COMPLETA]  Fase 1   Motor Principal          Orchestrator + BotApp + MT5Bridge
[COMPLETA]  Fase 2   Macro Engine             7 daemons: VIX, DXY, Yield, Commodity, News, Calendar, Benchmark
[COMPLETA]  Fase 3   Analise                  FairPrice, VolChannels, YieldCurve, Correlation, ScenarioEval
[COMPLETA]  Fase 4   Tecnicos                 MACD, BB, Hi-Lo, ATR Stop, SAR, VWAP, MA, WeisWave, Pivot, MTF
[COMPLETA]  Fase 5   Score Engine             TotalScore 7 componentes (MCS+BCS+HCS+VES+ES+CS+RS)
[COMPLETA]  Fase 6   Execucao e Risco         OrderManager, ProfessionalRisk, VaR, ExecutionValidator
[COMPLETA]  Fase 7   Sessao e Validacao       Sessions, PrepWorkflow, checks/, scripts/
[COMPLETA]  Fase 7b  Opportunity-Permission   scanner.py: OpportunityScore + PermissionScore
[COMPLETA]  Fase 7c  RSI + Calibracao         RSI(14) gate + RSICalibrationPolicy + rsi_report.py
[COMPLETA]  Fase 7d  Idiosyncratic Move       TECNICO_PURO: macro neutro + tecnicos fortes
[COMPLETA]  Fase 8   Validacao 7 Dias         Day 8 — 199 ciclos, signals=0 estrutural confirmado; veredicto: AVANCAR→V9.1
[EM CURSO]  Fase 9A  Refactor Engine V9.1     RegimeRouter+CircuitBreaker DONE (Tasks 9A.1-9A.5); pendente: 9A.6 day0_reset
[PENDENTE]  Fase 9B  SMC Layer                Order Blocks + FVG + BOS/ChoCh + Liquidity Sweeps
[PENDENTE]  Fase 9C  Capital Manager V2       3 camadas capital + Kelly/4 + Margin Semaphore + TP escalonado
[PENDENTE]  Fase 9D  Dashboard V9             FastAPI + React integrados com dados V9.1
[PENDENTE]  Fase 9E  Testes Unitarios         Cobertura V9.1: regime, SMC, capital, margem + legado
[PENDENTE]  Fase 10  ML Filter + WFO          RandomForest quality filter + Walk-Forward Optimization
[PENDENTE]  Fase 11  Scalping                 apos V9.1 validado
[PENDENTE]  Fase 12  VPS Windows 24/7         operacao continua
[PENDENTE]  Fase 13  Paper Trading            2 semanas de validacao real V9.1
[PENDENTE]  Fase 14  Capital Real             transicao gradual com Capital Manager V2
```

---

## REGRA DE ACTUALIZACAO

```
Quando discutires uma nova integracao com a IA → actualizar seccao relevante + DIVIDA TECNICA
Quando uma fase ficar completa → mudar [EM CURSO] / [PENDENTE] para [COMPLETA] + data
Quando tomares uma decisao tecnica → adicionar linha em DECISOES TECNICAS
Quando a validacao diaria passar → actualizar "Estado actual" na Fase 8
Quando o veredicto Day 7 sair → actualizar Fase 8 para COMPLETA + Fase 9 para EM CURSO
```
