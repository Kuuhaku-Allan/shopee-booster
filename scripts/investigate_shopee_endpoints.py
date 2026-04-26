"""
scripts/investigate_shopee_endpoints.py — Investigação de Endpoints da Shopee
==============================================================================
Captura TODOS os endpoints de API que a Shopee usa para carregar produtos.
Salva em arquivo JSON para análise.

Uso:
    python scripts/investigate_shopee_endpoints.py
"""

import sys
import os
from pathlib import Path
import json
import asyncio

# Força UTF-8 no Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Adiciona o diretório raiz ao path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))


async def investigate_endpoints():
    """Captura todos os endpoints de API da página da loja"""
    from playwright.async_api import async_playwright
    
    url = "https://shopee.com.br/totalmenteseu"
    captured_endpoints = []
    
    print("=" * 70)
    print("INVESTIGAÇÃO DE ENDPOINTS DA SHOPEE")
    print("=" * 70)
    print(f"\nURL: {url}")
    print("\nCapturando requisições...\n")
    
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
        
        async def handle_response(response):
            """Captura todas as respostas de API"""
            if response.request.method == "OPTIONS":
                return
            
            url = response.url
            
            # Filtra apenas APIs relevantes
            if "api" in url.lower() or "graphql" in url.lower():
                endpoint_info = {
                    "url": url,
                    "status": response.status,
                    "method": response.request.method,
                    "headers": dict(response.headers),
                }
                
                # Tenta capturar o corpo da resposta
                try:
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type:
                        data = await response.json()
                        endpoint_info["response_preview"] = str(data)[:500]  # Primeiros 500 chars
                        
                        # Verifica se contém produtos
                        data_str = json.dumps(data).lower()
                        has_items = any(keyword in data_str for keyword in [
                            "itemid", "item_id", "product", "mochila", "rosa"
                        ])
                        endpoint_info["likely_has_products"] = has_items
                        
                        if has_items:
                            print(f"🎯 POSSÍVEL ENDPOINT DE PRODUTOS: {url}")
                            endpoint_info["full_response"] = data
                except Exception as e:
                    endpoint_info["error"] = str(e)
                
                captured_endpoints.append(endpoint_info)
                
                # Log em tempo real
                if "shop" in url or "item" in url or "search" in url or "product" in url:
                    print(f"📡 {response.request.method} {url[:100]}...")
        
        page.on("response", handle_response)
        
        print("Navegando para a página da loja...")
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        print("\nAguardando carregamento completo...")
        await asyncio.sleep(5)
        
        print("\nRolando a página para carregar mais produtos...")
        for i in range(10):
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(1)
            print(f"  Scroll {i+1}/10")
        
        print("\nAguardando requisições finais...")
        await asyncio.sleep(3)
        
        await browser.close()
    
    # Salva resultados
    output_file = "shopee_endpoints_investigation.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(captured_endpoints, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 70)
    print(f"RESULTADOS SALVOS EM: {output_file}")
    print("=" * 70)
    
    # Análise rápida
    api_endpoints = [e for e in captured_endpoints if "api" in e["url"].lower()]
    product_endpoints = [e for e in captured_endpoints if e.get("likely_has_products")]
    
    print(f"\nTotal de endpoints capturados: {len(captured_endpoints)}")
    print(f"Endpoints de API: {len(api_endpoints)}")
    print(f"Endpoints com possíveis produtos: {len(product_endpoints)}")
    
    if product_endpoints:
        print("\n🎯 ENDPOINTS PROMISSORES:")
        for ep in product_endpoints:
            print(f"\n  URL: {ep['url']}")
            print(f"  Status: {ep['status']}")
            print(f"  Method: {ep['method']}")
    else:
        print("\n⚠️ Nenhum endpoint com produtos foi detectado!")
        print("\nEndpoints de API encontrados:")
        for ep in api_endpoints[:20]:  # Mostra os primeiros 20
            print(f"  - {ep['method']} {ep['url'][:80]}...")


if __name__ == "__main__":
    try:
        asyncio.run(investigate_endpoints())
    except KeyboardInterrupt:
        print("\n\nInvestigação interrompida pelo usuário.")
    except Exception as e:
        print(f"\n❌ ERRO: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
