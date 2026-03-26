"""
Test All APIs
Verifica quais APIs estão funcionando
"""

import os
from dotenv import load_dotenv
import requests
import time

load_dotenv()

def test_api(name, test_func):
    """Testa uma API e mostra resultado."""
    print(f"\n{'='*60}")
    print(f"🧪 Testando: {name}")
    print(f"{'='*60}")
    
    start = time.time()
    try:
        result = test_func()
        elapsed = (time.time() - start) * 1000
        
        if result:
            print(f"✅ {name}: OK ({elapsed:.0f}ms)")
            print(f"   Resultado: {result}")
            return True
        else:
            print(f"❌ {name}: FAILED (sem dados)")
            return False
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print(f"❌ {name}: ERROR ({elapsed:.0f}ms)")
        print(f"   Erro: {str(e)[:100]}")
        return False

# ============================================================
#  TESTES
# ============================================================

def test_binance():
    url = "https://api.binance.com/api/v3/ticker/price"
    r = requests.get(url, params={'symbol': 'BTCUSDT'}, timeout=5)
    return f"BTC: ${float(r.json()['price']):.2f}"

def test_coingecko():
    url = "https://api.coingecko.com/api/v3/simple/price"
    r = requests.get(url, params={'ids': 'bitcoin', 'vs_currencies': 'usd'}, timeout=5)
    return f"BTC: ${r.json()['bitcoin']['usd']}"

def test_alpha_vantage():
    key = os.getenv('ALPHA_VANTAGE_KEY')
    if not key:
        return None
    url = "https://www.alphavantage.co/query"
    params = {
        'function': 'CURRENCY_EXCHANGE_RATE',
        'from_currency': 'EUR',
        'to_currency': 'USD',
        'apikey': key
    }
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    if 'Realtime Currency Exchange Rate' in data:
        rate = data['Realtime Currency Exchange Rate']['5. Exchange Rate']
        return f"EURUSD: {rate}"
    return None

def test_twelve_data():
    key = os.getenv('TWELVE_DATA_KEY')
    if not key:
        return None
    url = "https://api.twelvedata.com/price"
    params = {'symbol': 'EUR/USD', 'apikey': key}
    r = requests.get(url, params=params, timeout=5)
    data = r.json()
    if 'price' in data:
        return f"EURUSD: {data['price']}"
    return None

def test_fixer():
    key = os.getenv('FIXER_KEY')
    if not key:
        return None
    url = "http://data.fixer.io/api/latest"
    params = {'access_key': key, 'base': 'EUR', 'symbols': 'USD'}
    r = requests.get(url, params=params, timeout=5)
    data = r.json()
    if data.get('success'):
        return f"EURUSD: {data['rates']['USD']}"
    return f"Error: {data.get('error', {}).get('info')}"

def test_polygon():
    key = os.getenv('POLYGON_KEY')
    if not key:
        return None
    url = "https://api.polygon.io/v2/aggs/ticker/AAPL/prev"
    params = {'apiKey': key}
    r = requests.get(url, params=params, timeout=5)
    data = r.json()
    if 'results' in data:
        return f"AAPL: ${data['results'][0]['c']}"
    return None

def test_newsapi():
    key = os.getenv('NEWSAPI_KEY')
    if not key:
        return None
    url = "https://newsapi.org/v2/everything"
    params = {
        'q': 'bitcoin',
        'apiKey': key,
        'pageSize': 1
    }
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    if data.get('status') == 'ok':
        return f"{data['totalResults']} articles found"
    return f"Error: {data.get('message')}"

def test_finnhub():
    key = os.getenv('FINNHUB_KEY')
    if not key:
        return None
    url = "https://finnhub.io/api/v1/quote"
    params = {'symbol': 'AAPL', 'token': key}
    r = requests.get(url, params=params, timeout=5)
    data = r.json()
    if 'c' in data:
        return f"AAPL: ${data['c']}"
    return None

def test_marketaux():
    key = os.getenv('MARKETAUX_KEY')
    if not key:
        return None
    url = "https://api.marketaux.com/v1/news/all"
    params = {'api_token': key, 'limit': 1}
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    if 'data' in data:
        return f"{len(data['data'])} news found"
    return None

def test_currents():
    key = os.getenv('CURRENTS_KEY')
    if not key:
        return None
    url = "https://api.currentsapi.services/v1/latest-news"
    params = {'apiKey': key, 'language': 'en'}
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    if data.get('status') == 'ok':
        return f"{len(data['news'])} articles"
    return None

def test_mediastack():
    key = os.getenv('MEDIASTACK_KEY')
    if not key:
        return None
    url = "http://api.mediastack.com/v1/news"
    params = {'access_key': key, 'limit': 1}
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    if 'data' in data:
        return f"{len(data['data'])} articles"
    return f"Error: {data.get('error', {}).get('info')}"

def test_cryptopanic():
    key = os.getenv('CRYPTOPANIC_KEY')
    url = "https://cryptopanic.com/api/v1/posts/"
    params = {'auth_token': key if key else 'free', 'filter': 'hot'}
    r = requests.get(url, params=params, timeout=5)
    data = r.json()
    if 'results' in data:
        return f"{len(data['results'])} posts"
    return None

def test_etherscan():
    key = os.getenv('ETHERSCAN_KEY')
    if not key:
        return None
    url = "https://api.etherscan.io/api"
    params = {
        'module': 'stats',
        'action': 'ethprice',
        'apikey': key
    }
    r = requests.get(url, params=params, timeout=5)
    data = r.json()
    if data.get('status') == '1':
        return f"ETH: ${data['result']['ethusd']}"
    return None

def test_eodhd():
    key = os.getenv('EODHD_KEY')
    if not key:
        return None
    url = "https://eodhd.com/api/real-time/AAPL.US"
    params = {'api_token': key, 'fmt': 'json'}
    r = requests.get(url, params=params, timeout=5)
    data = r.json()
    if 'close' in data:
        return f"AAPL: ${data['close']}"
    return None

def test_fred():
    key = os.getenv('FRED_API_KEY')
    if not key:
        return None
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        'series_id': 'DFF',
        'api_key': key,
        'file_type': 'json',
        'limit': 1,
        'sort_order': 'desc'
    }
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    if 'observations' in data:
        return f"Fed Funds Rate: {data['observations'][0]['value']}%"
    return None

# ============================================================
#  EXECUTAR TESTES
# ============================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 TESTE DE TODAS AS APIs")
    print("="*60)
    
    results = {}
    
    # Crypto (sem key)
    results['Binance'] = test_api('Binance (Crypto)', test_binance)
    results['CoinGecko'] = test_api('CoinGecko (Crypto)', test_coingecko)
    
    # Forex
    results['Alpha Vantage'] = test_api('Alpha Vantage (Forex)', test_alpha_vantage)
    results['Twelve Data'] = test_api('Twelve Data (Forex)', test_twelve_data)
    results['Fixer'] = test_api('Fixer.io (Forex)', test_fixer)
    
    # Stocks
    results['Polygon'] = test_api('Polygon.io (Stocks)', test_polygon)
    results['EODHD'] = test_api('EODHD (Stocks)', test_eodhd)
    
    # News
    results['NewsAPI'] = test_api('NewsAPI', test_newsapi)
    results['Finnhub'] = test_api('Finnhub', test_finnhub)
    results['MarketAux'] = test_api('MarketAux', test_marketaux)
    results['Currents'] = test_api('Currents API', test_currents)
    results['MediaStack'] = test_api('MediaStack', test_mediastack)
    results['CryptoPanic'] = test_api('CryptoPanic', test_cryptopanic)
    
    # On-chain
    results['Etherscan'] = test_api('Etherscan (ETH)', test_etherscan)
    
    # Macro
    results['FRED'] = test_api('FRED (Federal Reserve)', test_fred)
    
    # Resumo
    print("\n" + "="*60)
    print("📊 RESUMO DOS TESTES")
    print("="*60)
    
    working = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\n✅ Funcionando: {working}/{total} ({working/total*100:.0f}%)")
    print(f"❌ Com problemas: {total - working}/{total}")
    
    print("\n📋 DETALHES:")
    for name, status in results.items():
        icon = "✅" if status else "❌"
        print(f"  {icon} {name}")
    
    if working < total:
        print("\n⚠️  ATENÇÃO: Algumas APIs não estão funcionando!")
        print("Possíveis causas:")
        print("  - Rate limits esgotados")
        print("  - Keys inválidas")
        print("  - Serviço temporariamente indisponível")
