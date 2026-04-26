"""
Teste direto do novo loader baseado em DOM
"""

import sys
import subprocess
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

username = "totalmenteseu"
shopid = "1744033972"

script = f"""
import asyncio, json, sys, re
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Visível para debug
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={{"width": 1280, "height": 800}},
            extra_http_headers={{"Accept-Language": "pt-BR,pt;q=0.9"}}
        )
        page = await context.new_page()
        products = []
        
        try:
            print("[LOADER] Navegando para loja...", file=sys.stderr)
            await page.goto(
                "https://shopee.com.br/{username}",
                wait_until="domcontentloaded",
                timeout=50000
            )
            
            print("[LOADER] Aguardando produtos aparecerem no DOM...", file=sys.stderr)
            
            # Espera por links de produtos (seletor comum da Shopee)
            selectors = [
                'a[href*="/product/"]',  # Links de produtos
                '[data-sqe="link"]',  # Atributo data comum
                '.shopee-search-item-result__item a',  # Grid de produtos
                '.shop-search-result-view__item a',  # Outro formato
            ]
            
            product_elements = None
            for selector in selectors:
                try:
                    print(f"[LOADER] Tentando selector: {{selector}}", file=sys.stderr)
                    await page.wait_for_selector(selector, timeout=15000, state="visible")
                    product_elements = await page.query_selector_all(selector)
                    if product_elements:
                        print(f"[LOADER] Encontrados {{len(product_elements)}} elementos com selector: {{selector}}", file=sys.stderr)
                        break
                except Exception as e:
                    print(f"[LOADER] Selector {{selector}} falhou: {{e}}", file=sys.stderr)
                    continue
            
            if not product_elements:
                print("[LOADER] Nenhum produto encontrado no DOM", file=sys.stderr)
                print("[LOADER] Aguardando 10s para inspeção manual...", file=sys.stderr)
                await asyncio.sleep(10)
                await browser.close()
                print(json.dumps([]))
                return
            
            print(f"[LOADER] Processando {{len(product_elements)}} elementos...", file=sys.stderr)
            
            # Extrai dados dos elementos
            seen_ids = set()
            for i, elem in enumerate(product_elements[:30]):
                try:
                    # Extrai href
                    href = await elem.get_attribute('href')
                    print(f"[LOADER] Elemento {{i}}: href={{href}}", file=sys.stderr)
                    
                    if not href or '/product/' not in href:
                        continue
                    
                    # Extrai itemid e shopid do href
                    match = re.search(r'[.-]i\\.?(\\d+)\\.(\\d+)', href)
                    if not match:
                        match = re.search(r'/product/(\\d+)/(\\d+)', href)
                    
                    if not match:
                        print(f"[LOADER] Não conseguiu extrair IDs do href: {{href}}", file=sys.stderr)
                        continue
                    
                    itemid = int(match.group(1))
                    product_shopid = int(match.group(2))
                    
                    if itemid in seen_ids:
                        continue
                    seen_ids.add(itemid)
                    
                    # Extrai nome
                    name = await elem.get_attribute('title')
                    if not name:
                        name = await elem.inner_text()
                    name = (name or "").strip()
                    
                    print(f"[LOADER] Produto: itemid={{itemid}}, name={{name[:30]}}", file=sys.stderr)
                    
                    products.append({{
                        "itemid": itemid,
                        "shopid": product_shopid,
                        "name": name or f"Produto {{itemid}}",
                        "price": 0,
                        "sold": 0,
                        "image": "",
                    }})
                    
                except Exception as e:
                    print(f"[LOADER] Erro ao processar elemento {{i}}: {{e}}", file=sys.stderr)
                    continue
            
            print(f"[LOADER] Total de produtos extraídos: {{len(products)}}", file=sys.stderr)
            
        except Exception as e:
            print(f"[LOADER] Erro geral: {{e}}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
        
        print("[LOADER] Aguardando 5s antes de fechar...", file=sys.stderr)
        await asyncio.sleep(5)
        await browser.close()
        print(json.dumps(products[:30]))

asyncio.run(run())
"""

print("Executando teste direto do loader baseado em DOM...")
print("=" * 70)

result = subprocess.run(
    [sys.executable, "-c", script],
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=120
)

print("\n[STDERR]:")
print(result.stderr)

print("\n[STDOUT]:")
print(result.stdout)

print("\n[RETURN CODE]:", result.returncode)
