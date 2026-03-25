# 💰 SISTEMA DE CAPITAL SCALING - GUIA DE INTEGRAÇÃO

## 📊 VISÃO GERAL

Este sistema implementa **scaling institucional de capital** baseado em 5 tiers que ajustam automaticamente:
- Risco por trade
- Número de ativos operados  
- Estratégias ativas
- Diversificação

**Inspirado em:** Bridgewater, Citadel, Man AHL, Millennium

---

## 🎯 TIERS E TRANSIÇÕES

| Tier | Capital Range | Risk/Trade | Símbolos | Estratégias |
|------|--------------|-----------|----------|-------------|
| **MICRO** | $0 - $10k | 2.0% | 2-4 | Mean Reversion only |
| **SMALL** | $10k - $100k | 1.0% | 4-8 | +Statistical Arbitrage |
| **MEDIUM** | $100k - $500k | 0.75% | 8-15 | +Macro +MTF |
| **LARGE** | $500k - $5M | 0.5% | 15-30 | +CTA +Market Neutral |
| **MEGA** | $5M+ | 0.3% | 30-50 | All strategies |

---

## 🔧 INTEGRAÇÃO COM O PROJETO V5

### **1. Adicionar ao projeto**

```bash
# Copiar ficheiro
cp capital_scaling.py Bot_probability_arbitrage/src/

# Ou criar diretamente em src/
```

### **2. Modificar `src/main.py`**

```python
# No topo do ficheiro
from src.capital_scaling import CapitalScaling

# Inicializar no __main__
scaler = CapitalScaling()

# No loop principal, ANTES de processar símbolos
balance = mt5c.get_account_info()["balance"]
config = scaler.get_config(balance)

# Usar configuração dinâmica
symbols_to_trade = config["recommended_symbols"]
max_positions = config["max_positions"]

# Ajustar risco por símbolo
for symbol in symbols_to_trade:
    risk_pct = scaler.get_position_size(balance, symbol)
    # ... resto da lógica
```

### **3. Modificar `config/settings.py`**

```python
# ADICIONAR no final do ficheiro

# ============================================================
#  CAPITAL SCALING (substituir valores fixos)
# ============================================================

USE_CAPITAL_SCALING = True  # Ativar scaling automático

# Valores de fallback se scaling desativado
FALLBACK_RISK_PCT = 0.5
FALLBACK_SYMBOLS = ["EURUSD", "AUDUSD"]
```

### **4. Modificar `src/strategy.py`**

```python
# Substituir valor fixo de risco

# ANTES:
# risk_money = balance * cfg.RISK_PER_TRADE_PCT / 100

# DEPOIS:
if cfg.USE_CAPITAL_SCALING:
    from src.capital_scaling import CapitalScaling
    scaler = CapitalScaling()
    risk_pct = scaler.get_position_size(balance, symbol)
    risk_money = balance * risk_pct / 100
else:
    risk_money = balance * cfg.FALLBACK_RISK_PCT / 100
```

---

## 📈 LÓGICA DE SCALING

### **Scale UP (adicionar ativos/estratégias)**

Acontece quando:
1. Balance cresceu **>100%** desde entrada no tier
2. Está a **>80%** do limite superior do tier

```python
should_scale, reason = scaler.should_scale_up(balance, entry_balance)
if should_scale:
    print(f"⬆️  SCALE UP: {reason}")
    # Adicionar mais símbolos
    # Ativar novas estratégias
```

### **Scale DOWN (reduzir exposição)**

Acontece quando:
1. **Drawdown >30%** desde peak
2. Caiu para **tier inferior**

```python
should_scale, reason = scaler.should_scale_down(balance, peak_balance)
if should_scale:
    print(f"⬇️  SCALE DOWN: {reason}")
    # Fechar posições mais arriscadas
    # Reduzir número de símbolos
```

---

## 🎯 EXEMPLO PRÁTICO

### **Começar com $5,000 (Tier MICRO)**

```python
scaler = CapitalScaling()
config = scaler.get_config(5000)

print(config)
# {
#   'tier': 'micro',
#   'risk_per_trade_pct': 2.0,
#   'max_symbols': 4,
#   'max_positions': 2,
#   'recommended_symbols': ['EURUSD', 'AUDUSD']
# }

# Position sizing
risk_eurusd = scaler.get_position_size(5000, "EURUSD")  # 2.0%
risk_btc = scaler.get_position_size(5000, "BTCUSD")     # 1.0% (não recomendado)
```

### **Crescer para $50,000 (Tier SMALL)**

```python
config = scaler.get_config(50000)

# Agora permite:
# - 4 posições simultâneas
# - 8 símbolos
# - Statistical Arbitrage ativo
# - Risk 1.0% por trade

symbols = config["recommended_symbols"]
# ['EURUSD', 'AUDUSD', 'GBPUSD', 'USDJPY']
```

### **Atingir $500,000 (Tier LARGE)**

```python
config = scaler.get_config(500000)

# Permite:
# - 15 posições
# - 30 símbolos (FX + Índices + Metais + Crypto)
# - 5 estratégias ativas
# - Risk 0.5% por trade (mais conservador)
```

---

## 🔥 BENEFÍCIOS DO SISTEMA

### **1. Proteção em Contas Pequenas**
- Risco inicial 2% permite recuperar de losses
- Foca em 2 ativos com edge comprovado (EURUSD/AUDUSD)

### **2. Crescimento Sustentável**
- Risco reduz à medida que capital cresce
- Diversificação aumenta progressivamente

### **3. Profissionalismo Institucional**
- Modelo usado por fundos multi-bilionários
- Evita over-trading em contas pequenas
- Evita under-diversification em contas grandes

### **4. Automático**
- Sem intervenção manual
- Ajusta em tempo real

---

## ⚙️ CONFIGURAÇÃO AVANÇADA

### **Personalizar Tiers**

```python
# Em capital_scaling.py, modificar TIERS dict

TIERS = {
    "micro": {
        "min": 0,
        "max": 5_000,  # Ajustar limite
        "risk_per_trade_pct": 1.5,  # Ajustar risco
        # ...
    }
}
```

### **Adicionar Novos Símbolos por Tier**

```python
TIER_SYMBOLS = {
    "medium": [
        "EURUSD", "AUDUSD", 
        "AAPL",  # Adicionar ações se broker permitir
        # ...
    ]
}
```

---

## 📊 MONITORIZAÇÃO

### **Dashboard Addition**

Adicionar ao dashboard existente:

```python
# Em dashboard_server.py

tier_info = scaler.get_config(balance)

dashboard_data = {
    "tier": tier_info["tier"],
    "tier_risk_pct": tier_info["risk_per_trade_pct"],
    "tier_max_positions": tier_info["max_positions"],
    "tier_description": tier_info["description"],
    # ... resto
}
```

### **Logs de Transição**

```python
# Quando tier muda, registar

if scaler.tier_history:
    last_change = scaler.tier_history[-1]
    print(f"""
    🔔 TIER CHANGE ALERT
    ─────────────────────
    From: {last_change['old_tier']}
    To:   {last_change['new_tier']}
    Balance: ${last_change['balance']:,.2f}
    Time: {last_change['timestamp']}
    """)
```

---

## 🚨 AVISOS IMPORTANTES

1. **Não desativar scaling em live** sem testar primeiro
2. **Tier MICRO é agressivo** (2% risco) - ideal para contas <$10k
3. **Tier changes** devem ser monitorizados - podem indicar problemas
4. **Símbolos recomendados** são baseados em backtests - validar sempre

---

## 📞 PRÓXIMOS PASSOS

1. ✅ Integrar no `main.py`
2. ✅ Testar em paper mode com diferentes balances
3. ✅ Validar transições de tier
4. ✅ Adicionar ao dashboard
5. ✅ Backtest com scaling ativo vs fixo

---

## 🎓 REFERÊNCIAS

- "Size, Age, and Performance Life Cycle of Hedge Funds" (Gao et al., 2018)
- Bridgewater Associates - Risk Parity Model
- Millennium Management - Pod Structure
- Man AHL - Systematic Scaling

---

**Criado por:** Claude + Bruno
**Data:** 24 Março 2026
**Versão:** 1.0
