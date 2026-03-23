"""
scripts/check_apis.py  —  Testa todas as APIs do sistema
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import requests
from rich.console import Console
from rich.table import Table
from rich import box
import config.settings as cfg

console = Console()
console.print("\n[bold blue]🔌 Diagnóstico completo de APIs[/]\n")

results = []

def test(name, fn, role):
    try:
        estado, detalhe = fn()
        results.append((name, estado, detalhe, role))
    except Exception as e:
        results.append((name, "❌ ERRO", str(e)[:60], role))

def _mt5():
    import MetaTrader5 as mt5
    if mt5.initialize(path=cfg.MT5_PATH):
        i = mt5.account_info(); mt5.shutdown()
        return "✅ OK", f"Conta {i.login}, Saldo {i.balance:.2f} {i.currency}"
    return "❌ FALHOU", "Não conectou"
test("MetaTrader 5", _mt5, "Ordens, preços, posições")

def _fred():
    r = requests.get("https://api.stlouisfed.org/fred/series/observations",
        params={"series_id":"FEDFUNDS","api_key":cfg.FRED_API_KEY,
                "file_type":"json","limit":1}, timeout=8)
    d = r.json()
    if "observations" in d:
        return "✅ OK", f"Fed Funds Rate: {d['observations'][-1]['value']}%"
    return "⚠️ ERRO", str(d)[:60]
test("FRED (Fed Reserve)", _fred, "Taxas, VIX, yields, ouro")

def _polygon():
    r = requests.get(
        f"https://api.polygon.io/v2/aggs/ticker/C:EURUSD/range/5/minute/2024-01-02/2024-01-02"
        f"?limit=1&apiKey={cfg.POLYGON_KEY}", timeout=8)
    d = r.json()
    if d.get("resultsCount", 0) > 0:
        return "✅ OK", f"{d['resultsCount']} barras recebidas"
    if "exceeded" in str(d).lower():
        return "⚠️ RATE LIMIT", "Aguarda 1 min e volta a testar"
    return "⚠️ KEY", str(d.get("error", d.get("message","?")))[:60]
test("Polygon.io", _polygon, "Preços FX precisos, índices")

def _finnhub():
    r = requests.get("https://finnhub.io/api/v1/news",
        params={"category":"forex","token":cfg.FINNHUB_KEY}, timeout=8)
    d = r.json()
    if isinstance(d, list) and len(d) > 0:
        return "✅ OK", f"{len(d)} artigos forex recebidos"
    if isinstance(d, dict) and "error" in d:
        return "❌ KEY", d["error"][:60]
    return "⚠️ VAZIO", "Sem artigos (normal fora de horário)"
test("Finnhub.io", _finnhub, "Notícias + sentimento + calendário")

def _marketaux():
    r = requests.get("https://api.marketaux.com/v1/news/all",
        params={"symbols":"EUR/USD","api_token":cfg.MARKETAUX_KEY,"limit":1}, timeout=8)
    d = r.json()
    if "data" in d and len(d["data"]) > 0:
        return "✅ OK", f"{d['meta']['found']} artigos disponíveis"
    if "error" in d:
        return "❌ KEY", str(d["error"])[:60]
    return "⚠️ VAZIO", "Sem dados"
test("MarketAux", _marketaux, "Notícias financeiras + sentimento")

def _currents():
    r = requests.get("https://api.currentsapi.services/v1/latest-news",
        params={"apiKey":cfg.CURRENTS_KEY,"language":"en",
                "keywords":"forex EUR USD","page_size":1}, timeout=8)
    d = r.json()
    if d.get("status") == "ok":
        return "✅ OK", f"{len(d.get('news',[]))} artigos recebidos"
    return "⚠️ KEY", str(d.get("message","?"))[:60]
test("Currents API", _currents, "Notícias gerais + macro")

def _mediastack():
    r = requests.get("http://api.mediastack.com/v1/news",
        params={"access_key":cfg.MEDIASTACK_KEY,"keywords":"forex",
                "languages":"en","limit":1}, timeout=8)
    d = r.json()
    if "data" in d:
        return "✅ OK", f"{d.get('pagination',{}).get('total',0)} artigos"
    if "error" in d:
        return "❌ KEY", str(d["error"].get("message","?"))[:60]
    return "⚠️ VAZIO", str(d)[:60]
test("Mediastack", _mediastack, "Notícias globais")

def _eodhd():
    r = requests.get("https://eodhd.com/api/news",
        params={"api_token":cfg.EODHD_KEY,"s":"EURUSD.FOREX",
                "limit":1,"fmt":"json"}, timeout=8)
    d = r.json()
    if isinstance(d, list) and len(d) > 0:
        return "✅ OK", f"{len(d)} notícias EURUSD"
    if isinstance(d, dict) and "message" in d:
        return "❌ KEY", d["message"][:60]
    return "⚠️ VAZIO", "Sem dados"
test("EODHD", _eodhd, "Notícias + fundamentais + calendário")

def _av():
    r = requests.get("https://www.alphavantage.co/query",
        params={"function":"CURRENCY_EXCHANGE_RATE","from_currency":"EUR",
                "to_currency":"USD","apikey":cfg.ALPHA_VANTAGE_KEY}, timeout=10)
    d = r.json()
    if "Realtime Currency Exchange Rate" in d:
        rate = d["Realtime Currency Exchange Rate"]["5. Exchange Rate"]
        return "✅ OK", f"EUR/USD = {rate}"
    if "Note" in d:
        return "⚠️ RATE LIMIT", "25 req/dia atingido"
    return "⚠️ KEY", str(d.get("Information","?"))[:60]
test("Alpha Vantage", _av, "Câmbios tempo real (backup)")

# Tabela
table = Table(box=box.SIMPLE_HEAVY, header_style="bold magenta", show_lines=True)
table.add_column("API", style="cyan", width=20)
table.add_column("Estado", width=16)
table.add_column("Detalhe", width=44)
table.add_column("Papel", width=30)

for api, estado, detalhe, papel in results:
    c = "green" if "OK" in estado else "yellow" if "⚠" in estado else "red"
    table.add_row(api, f"[{c}]{estado}[/]", detalhe, f"[dim]{papel}[/]")

console.print(table)
ok   = sum(1 for _,e,_,_ in results if "OK" in e)
warn = sum(1 for _,e,_,_ in results if "⚠"  in e)
fail = sum(1 for _,e,_,_ in results if "❌" in e)
console.print(f"\n[bold]Resumo:[/] [green]{ok} OK[/]  [yellow]{warn} aviso[/]  [red]{fail} falhou[/]")
