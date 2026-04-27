"""
scripts/discover_new_endpoint.py — Descoberta Automatizada do Novo Endpoint
============================================================================
Tenta múltiplas estratégias para descobrir como a Shopee carrega produtos hoje.

Estratégias:
1. Testa endpoints conhecidos de scrapers externos
2. Captura todas as requests do navegador
3. Analisa o JavaScript para encontrar chamadas de API
4. Testa variações de endpoints antigos
"""

import asyncio
import json
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path para importar módulos
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright


# Endpoints conhecidos de referências externas
KNOWN_ENDPOINTS = [
    "/api/v4/shop/search_items",
    "/api/v4/shop/get_shop_tab",
    "/api/v4/search/search_items",
    "/api/v4/item/get_list",
    "/api/v4/shop/get_shop_detail",
    "/api/v4/shop/get_shop_items",
    "/api/v4/shop/get_shop_base_v2",
    "/api/v4/shop/get_categories",
    "/api/v4/shop/rcmd_items",  # Antigo, mas vamos testar
    "/api/v4/shop/shop_page",   # Antigo, mas vamos testar
]


async def capture_all_requests(username: str):
    """Captura TODAS as requests feitas ao carregar a loja."""
    print(f"\n{'='*70}")
    print(f"ESTRATÉGIA 1: Capturar todas as requests")
    print(f"{'='*70}\n")
    
    captured_requests = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Visível para debug
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9"}
        )
        page = await context.new_page()
        
        async def handle_request(request):
            """Captura todas as requests."""
            if request.method != "OPTIONS":
                captured_requests.append({
                    "url": request.url,
                    "method": request.method,
                    "headers": dict(request.headers),
                    "post_data": request.post_data if request.method == "POST" else None,
                })
        
        async def handle_response(response):
            """Captura responses de APIs."""
            if response.request.method == "OPTIONS":
                return
            
            url = response.url
            
            # Filtra apenas APIs da Shopee
            if "/api/" in url and "shopee.com" in url:
                try:
                    data = await response.json()
                    
                    # Verifica se contém produtos
                    has_items = False
                    items_path = None
                    
                    # Tenta diferentes caminhos comuns
                    possible_paths = [
                        ("items", data.get("items")),
                        ("data.items", data.get("data", {}).get("items")),
                        ("data.item", data.get("data", {}).get("item")),
                        ("data.sections", data.get("data", {}).get("sections")),
                        ("data.products", data.get("data", {}).get("products")),
                    ]
                    
                    for path, value in possible_paths:
                        if value and isinstance(value, list) and len(value) > 0:
                            has_items = True
                            items_path = path
                            break
                    
                    if has_items:
                        print(f"\n🎯 ENDPOINT COM PRODUTOS ENCONTRADO!")
                        print(f"URL: {url}")
                        print(f"Método: {response.request.method}")
                        print(f"Path dos items: {items_path}")
                        print(f"Quantidade: {len(value)}")
                        
                        # Mostra estrutura do primeiro item
                        if value:
                            first_item = value[0]
                            print(f"\nEstrutura do primeiro item:")
                            print(json.dumps(first_item, indent=2, ensure_ascii=False)[:500])
                        
                        # Salva resposta completa
                        output_file = Path(__file__).parent / "discovered_endpoint_response.json"
                        with open(output_file, "w", encoding="utf-8") as f:
                            json.dump({
                                "url": url,
                                "method": response.request.method,
                                "items_path": items_path,
                                "items_count": len(value),
                                "full_response": data,
                            }, f, indent=2, ensure_ascii=False)
                        print(f"\n✅ Resposta completa salva em: {output_file}")
                    
                except Exception as e:
                    pass  # Ignora erros de parsing
        
        page.on("request", handle_request)
        page.on("response", handle_response)
        
        print(f"Navegando para: https://shopee.com.br/{username}")
        await page.goto(
            f"https://shopee.com.br/{username}",
            wait_until="networkidle",
            timeout=60000
        )
        
        print("Aguardando 10 segundos para garantir que tudo carregou...")
        await asyncio.sleep(10)
        
        # Rola a página para forçar lazy loading
        print("Rolando a página...")
        for _ in range(3):
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(1)
        
        await asyncio.sleep(5)
        
        await browser.close()
    
    # Salva todas as requests capturadas
    output_file = Path(__file__).parent / "all_requests_captured.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(captured_requests, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ {len(captured_requests)} requests capturadas e salvas em: {output_file}")
    
    # Filtra requests de API
    api_requests = [r for r in captured_requests if "/api/" in r["url"]]
    print(f"📊 {len(api_requests)} requests de API encontradas")
    
    return captured_requests


async def test_known_endpoints(username: str, shopid: str):
    """Testa endpoints conhecidos de referências externas."""
    print(f"\n{'='*70}")
    print(f"ESTRATÉGIA 2: Testar endpoints conhecidos")
    print(f"{'='*70}\n")
    
    try:
        from curl_cffi import requests as stealth_requests
        session = stealth_requests.Session(impersonate="chrome124")
        print("✅ Usando curl_cffi (stealth)")
    except ImportError:
        import requests
        session = requests.Session()
        print("⚠️ Usando requests padrão (pode ser bloqueado)")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": f"https://shopee.com.br/{username}",
        "Accept": "application/json",
        "Accept-Language": "pt-BR,pt;q=0.9",
    }
    
    results = []
    
    for endpoint in KNOWN_ENDPOINTS:
        url = f"https://shopee.com.br{endpoint}"
        
        # Tenta diferentes combinações de parâmetros
        param_combinations = [
            {"shopid": shopid, "limit": 30, "offset": 0},
            {"shop_id": shopid, "limit": 30, "offset": 0},
            {"match_id": shopid, "limit": 30, "by": "sales"},
            {"username": username, "limit": 30},
        ]
        
        for params in param_combinations:
            try:
                print(f"Testando: {endpoint} com params={params}")
                response = session.get(url, params=params, headers=headers, timeout=10)
                
                result = {
                    "endpoint": endpoint,
                    "params": params,
                    "status": response.status_code,
                    "has_json": False,
                    "has_items": False,
                    "items_count": 0,
                }
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        result["has_json"] = True
                        
                        # Verifica se tem items
                        items = (
                            data.get("items") or
                            data.get("data", {}).get("items") or
                            data.get("data", {}).get("item") or
                            []
                        )
                        
                        if items and isinstance(items, list):
                            result["has_items"] = True
                            result["items_count"] = len(items)
                            
                            print(f"  ✅ SUCESSO! {len(items)} items encontrados")
                            print(f"  Estrutura: {list(data.keys())}")
                            
                            # Salva resposta
                            output_file = Path(__file__).parent / f"endpoint_success_{endpoint.replace('/', '_')}.json"
                            with open(output_file, "w", encoding="utf-8") as f:
                                json.dump({
                                    "endpoint": endpoint,
                                    "params": params,
                                    "response": data,
                                }, f, indent=2, ensure_ascii=False)
                            print(f"  💾 Salvo em: {output_file}")
                        else:
                            print(f"  ⚠️ JSON válido mas sem items")
                    except:
                        print(f"  ⚠️ Resposta não é JSON")
                else:
                    print(f"  ❌ HTTP {response.status_code}")
                
                results.append(result)
                
            except Exception as e:
                print(f"  ❌ Erro: {e}")
                results.append({
                    "endpoint": endpoint,
                    "params": params,
                    "error": str(e),
                })
    
    # Salva resultados
    output_file = Path(__file__).parent / "endpoint_tests_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Resultados salvos em: {output_file}")
    
    # Resumo
    successful = [r for r in results if r.get("has_items")]
    print(f"\n📊 RESUMO:")
    print(f"  Total testado: {len(results)}")
    print(f"  Com sucesso: {len(successful)}")
    
    return results


async def analyze_javascript(username: str):
    """Analisa o JavaScript da página para encontrar chamadas de API."""
    print(f"\n{'='*70}")
    print(f"ESTRATÉGIA 3: Analisar JavaScript")
    print(f"{'='*70}\n")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto(f"https://shopee.com.br/{username}", wait_until="networkidle")
        
        # Extrai todos os scripts
        scripts = await page.evaluate("""
            () => {
                const scripts = Array.from(document.querySelectorAll('script'));
                return scripts.map(s => s.src || s.textContent).filter(Boolean);
            }
        """)
        
        print(f"📜 {len(scripts)} scripts encontrados")
        
        # Procura por padrões de API
        api_patterns = []
        for script in scripts:
            if isinstance(script, str):
                # Procura por URLs de API
                import re
                matches = re.findall(r'/api/v\d+/[a-z_/]+', script)
                api_patterns.extend(matches)
        
        unique_patterns = list(set(api_patterns))
        print(f"🔍 {len(unique_patterns)} padrões de API únicos encontrados:")
        for pattern in unique_patterns[:20]:  # Mostra os primeiros 20
            print(f"  - {pattern}")
        
        # Salva
        output_file = Path(__file__).parent / "api_patterns_from_js.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(unique_patterns, f, indent=2)
        
        print(f"\n✅ Padrões salvos em: {output_file}")
        
        await browser.close()
    
    return unique_patterns


async def main():
    """Executa todas as estratégias."""
    username = "totalmenteseu"
    shopid = "1744033972"
    
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  DESCOBERTA AUTOMATIZADA DO NOVO ENDPOINT DA SHOPEE             ║
║  Loja: {username:<54} ║
║  Shop ID: {shopid:<51} ║
╚══════════════════════════════════════════════════════════════════╝
""")
    
    try:
        # Estratégia 1: Captura todas as requests
        await capture_all_requests(username)
        
        # Estratégia 2: Testa endpoints conhecidos
        await test_known_endpoints(username, shopid)
        
        # Estratégia 3: Analisa JavaScript
        await analyze_javascript(username)
        
        print(f"\n{'='*70}")
        print("✅ INVESTIGAÇÃO COMPLETA!")
        print(f"{'='*70}")
        print("\nArquivos gerados:")
        print("  - all_requests_captured.json")
        print("  - endpoint_tests_results.json")
        print("  - api_patterns_from_js.json")
        print("  - discovered_endpoint_response.json (se encontrou)")
        print("  - endpoint_success_*.json (se encontrou)")
        
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
