# AGENTS.md — Spec Viva do Projeto

> Este ficheiro é lido AUTOMATICAMENTE por qualquer agente de IA ao iniciar.
> É a fonte de verdade do projeto. Actualiza-o a cada iteração relevante.

---

## 1. IDENTIDADE DO PROJETO

```yaml
name: "Bot Probability Arbitrage"
version: "0.1.0"
type: "monorepo"
status: "in-dev"
owner: "bruno"
```

---

## 2. OBJECTIVO

> Descreve em 2-3 frases O QUE este projecto faz e PARA QUÉM.

Bot de arbitragem de probabilidades que identifica oportunidades de trading entre múltiplos mercados financeiros. Recolhe dados de exchanges de crypto, mercados de ações e mercados forex em tempo real. Executa operações automatizadas para explorar discrepâncias de preço e gerar retornos através de arbitragem estatística.

---

## 3. STACK TECNOLÓGICO

```yaml
frontend:
  framework: "React"          # React | Next.js | Vue | Svelte | None
  styling: "Tailwind"         # Tailwind | CSS Modules | Styled Components
  state: "Zustand"            # Zustand | Redux | Jotai | Context API
  language: "TypeScript"      # TypeScript | JavaScript

backend:
  framework: "FastAPI"        # FastAPI | Express | Rails | Django | None
  language: "Python"          # Python | Node.js | Ruby | Go | Rust
  orm: "SQLAlchemy"           # Prisma | SQLAlchemy | ActiveRecord | None
  auth: "JWT"                 # JWT | OAuth2 | Clerk | Auth0 | NextAuth

database:
  primary: "PostgreSQL"       # PostgreSQL | MySQL | SQLite | MongoDB
  cache: "Redis"              # Redis | Memcached | None
  search: "None"              # Elasticsearch | Algolia | None

infra:
  hosting: "AWS"              # Vercel | Railway | Fly.io | VPS | AWS
  ci_cd: "GitHub Actions"     # GitHub Actions | GitLab CI | None
  containers: "Docker"        # Docker | None
  monitoring: "Datadog"       # Sentry | Datadog | None

ai_tools:
  agents: "OpenCode"          # Claude Code | OpenCode | Cursor | Copilot
  models: "claude-haiku-4.5"  # claude-sonnet | gpt-4o | gemini | deepseek
```

---

## 4. VARIÁVEIS DE AMBIENTE

> NUNCA commites o `.env`. Usa este ficheiro apenas para DOCUMENTAR as chaves (sem valores reais).

```env
# Base
NODE_ENV=development|production
PORT=3000
PYTHON_PORT=8000

# Database
DATABASE_URL=postgresql://user:password@localhost/bot_arbitrage
REDIS_URL=redis://localhost:6379

# Auth
JWT_SECRET=
OAUTH_CLIENT_ID=
OAUTH_CLIENT_SECRET=

# Crypto & Trading APIs
BINANCE_API_KEY=
BINANCE_API_SECRET=
KRAKEN_API_KEY=
KRAKEN_API_SECRET=

# Financial Data APIs
FRED_API_KEY=
POLYGON_KEY=
FINNHUB_KEY=
MARKETAUX_KEY=
CURRENTS_KEY=
MEDIASTACK_KEY=
EODHD_KEY=
ALPHAVANTAGE_KEY=
TWELVEDATA_KEY=
FIXER_KEY=
NEWSAPI_KEY=
CRYPTOPANIC_KEY=
ETHERSCAN_API_KEY=
COINGECKO_API_KEY=

# Trading Config
MIN_ARBITRAGE_SPREAD=0.1
MAX_POSITION_SIZE=1000
TRADING_ENABLED=false
```

---

## 5. ESTRUTURA DE DIRECTÓRIOS

```
projeto/
├── .ai/                    ← pasta de contexto IA (este sistema)
├── apps/
│   ├── web/                ← frontend
│   └── api/                ← backend
├── packages/               ← shared libs (monorepo)
├── docs/                   ← documentação técnica
├── tests/                  ← testes globais / e2e
├── scripts/                ← automação e CI/CD
├── infra/                  ← IaC / Docker / configs
├── .env.example            ← template de variáveis (sem valores)
├── .gitignore
└── README.md
```

---

## 6. ARQUITECTURA

> Descreve o desenho do sistema. Actualiza ao evoluir.

- **Padrão arquitectural:** [MVC | Clean Architecture | Hexagonal | Monolith | Microservices]
- **Comunicação:** [REST | GraphQL | gRPC | WebSockets]
- **Autenticação:** [JWT stateless | Sessions | OAuth2 flow]
- **Deploy:** [descrição do pipeline]

---

## 7. REGRAS DO PROJECTO (INVIOLÁVEIS)

```
NEVER  commitar .env ou ficheiros com segredos reais
NEVER  commitar num repositório público sem intenção explícita de open-source
ALWAYS adicionar .gitignore com .env antes do primeiro commit
ALWAYS escrever testes antes do código (TDD)
ALWAYS todo o código passa em testes antes de ser aceite
ALWAYS rever código antes de deploy (security + quality gate)
ALWAYS usar HTTPS em produção
NEVER  guardar passwords ou chaves em código fonte
ALWAYS separar configuração do código (12-factor app)
```

---

## 8. DESIGN PATTERNS DO PROJECTO

> Lista os padrões adoptados para manter consistência.

- [ ] Repository Pattern (acesso a dados)
- [ ] Service Layer (lógica de negócio)
- [ ] DTO / Schema validation (entrada/saída)
- [ ] Error boundary (tratamento de erros)
- [ ] Feature flags (activar funcionalidades gradualmente)

---

## 9. HISTÓRIAS / FUNCIONALIDADES

> Lista as funcionalidades planeadas com estado.

| # | Funcionalidade | Estado | Notas |
|---|---------------|--------|-------|
| 1 | [descreve] | [ ] planned / [x] done | |
| 2 | | | |

---

## 10. COMMON PROBLEMS & SOLUÇÕES

> Documenta aqui os problemas recorrentes e como foram resolvidos.

| Problema | Causa | Solução |
|---------|-------|---------|
| | | |

---

## 11. MCPS DISPONÍVEIS

> Lista os MCPs activos para este projecto.

```yaml
mcps:
  - name: ""
    url: ""
    purpose: ""
```

---

## 12. CHECKLIST PÓS-IMPLEMENTAÇÃO

```
[ ] Testes unitários passam
[ ] Testes de integração passam
[ ] Code review feito
[ ] Security review feito
[ ] .env.example actualizado
[ ] README actualizado
[ ] AGENTS.md actualizado
[ ] Deploy pipeline validado
[ ] Monitorização configurada
```

---

## 13. CONTEXTO PARA A IA

> Instruções específicas para agentes de IA neste projecto.

- Lê sempre este ficheiro antes de qualquer tarefa
- Lê `.ai/skills/context-router/SKILL.md` para decidir que skills carregar
- Nunca assumas stack — verifica sempre neste ficheiro
- Segue os design patterns definidos na secção 8
- Aplica TDD: testes primeiro, código depois
- Antes de qualquer commit, verifica a secção 7 (regras invioláveis)
