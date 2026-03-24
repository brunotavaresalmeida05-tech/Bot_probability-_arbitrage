# Plano de Implementação — Bot Probability Arbitrage MT5

## Contexto

Projeto Python completo (17 módulos) para trading algorítmico com MT5. Usa mean reversion, stat arb, triangular arb, macro engine, multi-timeframe e portfolio manager. **Zero testes existentes.** Credenciais MT5 e API keys estão expostas em [config/settings.py](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/config/settings.py) (em texto limpo, versionado no Git).

## User Review Required

> [!CAUTION]
> **Credenciais expostas no Git**: [config/settings.py](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/config/settings.py) contém `MT5_PASSWORD`, `FRED_API_KEY`, `POLYGON_KEY`, etc. em texto limpo. Estas estão no historial do Git. Recomendo fazer `git rm --cached config/settings.py` e mover para `.env`.

> [!IMPORTANT]
> **Não há testes**: O bot opera com dinheiro real mas tem 0 ficheiros de teste. A suite proposta usa dados sintéticos/mock — não requer MT5 ligado para correr.

---

## Alterações Propostas

### Componente 1 — Segurança de Credenciais

#### [MODIFY] [settings.py](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/config/settings.py)
- Substituir valores sensíveis por `os.getenv("MT5_PASSWORD", "")` etc.
- Manter valores padrão não-sensíveis no ficheiro

#### [NEW] [.env.example](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/.env.example)
- Template com todas as variáveis de ambiente necessárias

#### [MODIFY] [.gitignore](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/.gitignore)
- Adicionar `.env` se não estiver já

---

### Componente 2 — Suite de Testes (pytest)

#### [NEW] [tests/test_strategy.py](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/tests/test_strategy.py)
Testa [src/strategy.py](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/src/strategy.py) (sem MT5):
- `compute_ma()` — SMA e EMA com dados sintéticos
- `compute_stddev()` — desvio padrão rolante
- `compute_atr()` — ATR com OHLCV sintético
- [trading_allowed()](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/src/dashboard_server.py#250-253) — filtros de spread e horário

#### [NEW] [tests/test_arb_strategy.py](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/tests/test_arb_strategy.py)
Testa [src/arb_strategy.py](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/src/arb_strategy.py) (sem MT5):
- [adf_test()](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/src/arb_strategy.py#43-112) — com série estacionária conhecida vs random walk
- `calc_half_life()` — com spread simulado de reversão conhecida
- `compute_pair_score()` — ranking de qualidade de pares

#### [NEW] [tests/test_risk.py](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/tests/test_risk.py)
Testa lógica de risco puro:
- `DailyState.reset_if_new_day()` — reset diário
- `DailyState.record_trade_result()` — contagem de perdas consecutivas
- Limites de max daily loss

#### [NEW] [tests/conftest.py](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/tests/conftest.py)
- Fixture `sample_ohlcv_df()` — DataFrame OHLCV sintético (200 barras)
- Fixture `stationary_spread()` — série AR(1) estacionária para ADF
- Fixture `random_walk_spread()` — para testar rejeição ADF

---

### Componente 3 — Dashboard: Novos Endpoints

#### [MODIFY] [src/dashboard_server.py](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/src/dashboard_server.py)
- Adicionar `GET /api/arb_pairs` — retorna pares ARB activos com score e z-score
- Adicionar `POST /api/close_all` — fecha todas as posições (chama `mt5c.close_all_positions()`)
- Adicionar `GET /api/macro` — retorna scores macro por símbolo

#### [MODIFY] [dashboard/index.html](file:///c:/Users/bruno/Desktop/Bot_probability%20_arbitrage/dashboard/index.html)
- Adicionar aba **"ARB Pairs"** com tabela de pares e score de qualidade
- Adicionar aba **"Macro"** com cards por símbolo (score, regime, razões)
- Adicionar botão **"⛔ Fechar Tudo"** com confirmação modal
- Melhorar painel de posições abertas: mostrar P&L colorido (verde/vermelho)

---

## Verificação

### Testes Automatizados

1. **Instalar pytest** (já deve estar no ambiente):
   ```bash
   cd "c:\Users\bruno\Desktop\Bot_probability _arbitrage"
   .venv\Scripts\activate
   pip install pytest
   ```

2. **Correr toda a suite de testes** (não requer MT5):
   ```bash
   pytest tests/ -v
   ```

3. **Resultado esperado**: todos os testes passam em <5 segundos, sem necessidade do MT5 ligado.

### Verificação Manual (Dashboard)

1. Correr o bot em paper mode:
   ```bash
   python src/main.py --mode paper
   ```
2. Abrir `http://127.0.0.1:8765` no browser
3. Verificar: aba "ARB Pairs" existe e mostra pares, aba "Macro" mostra scores
4. Verificar: botão "Fechar Tudo" mostra modal de confirmação antes de executar
5. Verificar `GET http://127.0.0.1:8765/api/macro` retorna JSON com scores por símbolo

### Verificação de Segurança

```bash
# Verificar que .env NÃO está versionado
git status .env
# Deve mostrar: untracked (ou não aparecer)

# Verificar que settings.py já não tem passwords hardcoded
grep "MT5_PASSWORD" config/settings.py
# Deve mostrar: MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
```
