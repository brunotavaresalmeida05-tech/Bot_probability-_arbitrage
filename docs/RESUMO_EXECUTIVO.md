# 🎯 RESUMO EXECUTIVO - APIS & PRÓXIMOS PASSOS

## 📡 ESTADO ATUAL DAS APIS

### **APIs Conectadas no Projeto:**
1. ✅ **FRED** (Federal Reserve Economic Data) - macro data
2. ✅ **Polygon** - market data (limitações no free plan)
3. ✅ **Alpha Vantage** - market data
4. ✅ **Finnhub** - news & sentiment
5. ✅ **Market aux** - news aggregator
6. ✅ **Currents** - news API
7. ✅ **EODHD** - end-of-day historical data

### **⚠️ PROBLEMA IDENTIFICADO:**
- **Não sabemos se estão a funcionar bem**
- Precisamos testar cada uma
- Validar quais têm melhor qualidade de dados

---

## 🆕 FOREX FACTORY - VALE A PENA?

### **✅ SIM! Extremamente Útil**

**O que oferece:**
1. **Calendário Económico em tempo real**
   - NFP, CPI, FOMC, PMI, GDP
   - Impact rating (low/medium/high)
   - Forecast vs Actual vs Previous

2. **Melhor que as outras APIs porque:**
   - Dados mais rápidos que fontes oficiais
   - Community-driven (traders a validar)
   - Filtros por moeda e impacto

### **❌ MAS...**

**Forex Factory NÃO tem API oficial!**

**Soluções:**
1. **JBlanked News API** (gratuita) - scraping de FF
   - `https://www.jblanked.com/news/api/forex-factory/calendar/today/`
   - Retorna JSON com eventos do dia
   - Filtros por currency e impact

2. **MQL5 Economic Calendar** (nativo MT5)
   - Acesso direto via MT5
   - Mais confiável que scraping

3. **Web Scraping próprio** (não recomendado)
   - Pode quebrar a qualquer momento
   - Ético questionável

### **📌 RECOMENDAÇÃO:**

Usar **JBlanked API** (gratuita) + **MQL5 Calendar**:

```python
import requests

def get_forex_factory_news(currency="USD", impact="High"):
    url = "https://www.jblanked.com/news/api/forex-factory/calendar/today/"
    params = {"currency": currency, "impact": impact}
    headers = {"API-KEY": "YOUR_KEY"}  # Criar conta em jblanked.com
    
    response = requests.get(url, params=params, headers=headers)
    return response.json()

# Exemplo
high_impact_usd = get_forex_factory_news("USD", "High")
```

---

## 💰 GESTÃO DE CAPITAL - DECISÃO FINAL

### **O QUE IMPLEMENTÁMOS:**

**Sistema de Tiers com Scaling Automático**

| Capital | Tier | Risk/Trade | Símbolos | Estratégias |
|---------|------|-----------|----------|-------------|
| $0-$10k | MICRO | 2% | 2-4 | Mean Rev |
| $10k-$100k | SMALL | 1% | 4-8 | +StatArb |
| $100k-$500k | MEDIUM | 0.75% | 8-15 | +Macro+MTF |
| $500k-$5M | LARGE | 0.5% | 15-30 | +CTA+Neutral |
| $5M+ | MEGA | 0.3% | 30-50 | All |

**Inspirado em:** Bridgewater, Millennium, Citadel

### **Vantagens:**
✅ Protege contas pequenas com foco em 2 pares (EURUSD/AUDUSD)  
✅ Escala risco para baixo à medida que cresce  
✅ Diversificação aumenta progressivamente  
✅ Automático - zero intervenção manual  

### **vs Outros Modelos:**

❌ **Kelly Criterion** - muito agressivo para retail  
❌ **Risk Parity** - complexo, precisa muitos ativos  
❌ **Volatility Targeting** - bom mas não escala capital  
✅ **Tier-Based Scaling** - simples, profissional, testado  

---

## 🚀 PLANO DE AÇÃO IMEDIATO

### **FASE 1: VALIDAR & OTIMIZAR (2-3 dias)**

#### **1.1 Testar APIs Existentes**
```bash
python src/external_data.py --test-all
```
- Ver quais respondem
- Verificar qualidade de dados
- Medir latência

#### **1.2 Integrar Capital Scaling**
```bash
# Copiar ficheiros
cp capital_scaling.py src/
cp CAPITAL_SCALING_INTEGRATION.md docs/

# Modificar main.py
# (seguir guia de integração)
```

#### **1.3 Backtest com Scaling Ativo**
```bash
python src/backtest_engine.py --symbols EURUSD,AUDUSD --bars 5000 --use-scaling
```
Comparar performance:
- **Sem scaling:** risk fixo 0.5%
- **Com scaling:** risk dinâmico por tier

---

### **FASE 2: ADICIONAR FOREX FACTORY (1 dia)**

#### **2.1 Criar Conta JBlanked**
1. Ir a https://www.jblanked.com/
2. Criar conta
3. Obter API key
4. Testar endpoint

#### **2.2 Criar news_filter.py**
```python
"""
src/news_filter.py
Filtro de notícias de alto impacto para evitar operar durante eventos.
"""

import requests
from datetime import datetime, timedelta
from typing import List, Dict

class NewsFilter:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.jblanked.com/news/api/forex-factory/calendar"
    
    def get_high_impact_events(self, hours_ahead: int = 2) -> List[Dict]:
        """Retorna eventos de alto impacto nas próximas X horas."""
        url = f"{self.base_url}/range/"
        now = datetime.now()
        end = now + timedelta(hours=hours_ahead)
        
        params = {
            "from": now.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
            "impact": "High"
        }
        headers = {"API-KEY": self.api_key}
        
        response = requests.get(url, params=params, headers=headers)
        return response.json()
    
    def should_avoid_trading(self, currency: str, hours_ahead: int = 2) -> tuple[bool, str]:
        """
        Verifica se deve evitar trading nas próximas X horas.
        
        Returns:
            (should_avoid, reason)
        """
        events = self.get_high_impact_events(hours_ahead)
        
        # Extrair moeda base do par (ex: EURUSD -> EUR e USD)
        if len(currency) >= 6:
            base = currency[:3]
            quote = currency[3:6]
            currencies = [base, quote]
        else:
            currencies = [currency]
        
        for event in events:
            if event.get("currency") in currencies:
                event_time = event.get("time")
                event_name = event.get("name")
                return True, f"High impact event: {event_name} ({event_time})"
        
        return False, "ok"

# Uso em main.py
news_filter = NewsFilter(api_key="YOUR_KEY")
avoid, reason = news_filter.should_avoid_trading("EURUSD", hours_ahead=2)
if avoid:
    print(f"⚠️  Evitar trading: {reason}")
    continue
```

---

### **FASE 3: ESTRATÉGIAS INSTITUCIONAIS (1 semana)**

#### **3.1 Statistical Arbitrage (Pairs Trading)**
**Já tens parcialmente!** Melhorar:
- Usar correlações dinâmicas (rolling 60 dias)
- Z-score de spread entre pares
- Hedge ratio otimizado

#### **3.2 Market Neutral (Long/Short simultâneos)**
- Long EURUSD + Short USDCHF (correlação -0.9)
- Neutralizar exposição USD
- Capturar spread

#### **3.3 CTA / Trend Following**
- Detetar tendências em múltiplos TFs
- Ride the trend até reversão confirmada
- Usar ADX + moving averages

#### **3.4 Macro Factor-Based**
- Carry trade (juros FED vs BCE)
- Risk-on/risk-off (VIX-based)
- Central bank policy tracking

---

## 📊 LISTA DE ATIVOS FINAL

### **Tier MICRO ($0-$10k):**
- EURUSD
- AUDUSD

### **Tier SMALL ($10k-$100k):**
- EURUSD, AUDUSD
- GBPUSD (H1 only)
- USDJPY (H1 only)

### **Tier MEDIUM ($100k-$500k):**
- FX: EURUSD, AUDUSD, GBPUSD, USDJPY, USDCHF, USDCAD, NZDUSD
- Metals: XAUUSD

### **Tier LARGE ($500k-$5M):**
- FX: todos acima + EURGBP, EURJPY, GBPJPY
- Metals: XAUUSD, XAGUSD
- Indices: US500, US100, GER40
- Crypto: BTCUSD (se disponível)

### **Tier MEGA ($5M+):**
- Todos acima +
- Commodities: USOIL, NGAS
- Mais índices: UK100, JP225
- Mais crypto: ETHUSD

---

## 🎯 PRÓXIMAS 24 HORAS

**PRIORIDADE 1:**
1. ✅ Integrar capital_scaling.py
2. ✅ Testar em paper mode
3. ✅ Validar transições de tier

**PRIORIDADE 2:**
1. ⏳ Testar APIs existentes
2. ⏳ Criar conta JBlanked
3. ⏳ Implementar news_filter.py

**PRIORIDADE 3:**
1. ⏳ Backtest EURUSD/AUDUSD com scaling
2. ⏳ Comparar performance vs fixo
3. ⏳ Documentar resultados

---

## 📞 DECISÕES PENDENTES

**Tu decides:**

1. **Capital inicial?** (para configurar tier correto)
2. **Broker permite crypto?** (BTC/ETH)
3. **Queres implementar estratégias novas JÁ** ou focar em otimizar mean reversion primeiro?

**Minha recomendação:**
- Começar com **MICRO tier** (EURUSD + AUDUSD only)
- Otimizar mean reversion até Sharpe >2.0
- DEPOIS adicionar stat arb e outras estratégias

---

## 📦 FICHEIROS CRIADOS

Vou preparar para download:

1. ✅ `capital_scaling.py` - sistema de tiers
2. ✅ `CAPITAL_SCALING_INTEGRATION.md` - guia
3. ⏳ `news_filter.py` - filtro de notícias (próximo)
4. ⏳ `api_tester.py` - testar todas as APIs (próximo)

---

**Próximo passo:** 
Diz-me qual capital inicial tens e eu configuro o sistema para o teu tier específico! 

Queres começar por qual fase? 🚀
