#!/usr/bin/env python3
"""
Script de debug para identificar onde estão os dados de avaliações no ML.
"""

import asyncio
from playwright.async_api import async_playwright

async def debug_ml_reviews(keyword: str):
    """Captura e analisa dados de avaliações do ML."""
    kw_encoded = keyword.replace(" ", "-").lower()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        page = await context.new_page()
        
        search_url = f"https://lista.mercadolivre.com.br/{kw_encoded}"
        print(f"\n🔍 Acessando: {search_url}\n")
        
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        
        products = await page.query_selector_all('.poly-card__content')
        print(f"✅ {len(products)} produtos encontrados\n")
        
        # Analisa os primeiros 3 produtos
        for idx in range(min(3, len(products))):
            product = products[idx]
            
            print("="*60)
            print(f"PRODUTO {idx+1}")
            print("="*60)
            
            # Nome
            name_elem = await product.query_selector('.poly-component__title')
            if name_elem:
                name = await name_elem.inner_text()
                print(f"📦 Nome: {name[:50]}")
            
            # Preço
            price_elem = await product.query_selector('.andes-money-amount__fraction')
            if price_elem:
                price = await price_elem.inner_text()
                print(f"💰 Preço: R$ {price}")
            
            # Busca TODOS os elementos que podem conter avaliações
            print(f"\n🔍 Buscando elementos de avaliações:")
            
            # Tenta diferentes seletores
            selectors = [
                '[class*="review"]',
                '[class*="rating"]',
                '.andes-visually-hidden',
                '.poly-reviews',
                '.poly-component__reviews',
                'span[class*="poly"]',
            ]
            
            for selector in selectors:
                elements = await product.query_selector_all(selector)
                if elements:
                    print(f"\n  ✅ {selector}: {len(elements)} elemento(s)")
                    for i, elem in enumerate(elements[:3]):
                        text = await elem.inner_text()
                        if text.strip():
                            print(f"     [{i}] Texto: '{text.strip()}'")
            
            # Captura TODO o texto do card
            all_text = await product.inner_text()
            print(f"\n📄 Texto completo do card:")
            print("-"*60)
            print(all_text[:500])
            print("-"*60)
            
            # Busca padrões de números que podem ser avaliações
            import re
            numbers = re.findall(r'\d+', all_text)
            if numbers:
                print(f"\n🔢 Números encontrados no texto: {numbers[:10]}")
            
            print()
        
        print("\n" + "="*60)
        print("Pressione Enter para fechar...")
        input()
        
        await browser.close()

if __name__ == "__main__":
    keyword = "mochila escolar"
    print(f"\n🧪 DEBUG: Dados de Avaliações do Mercado Livre")
    print(f"📝 Keyword: {keyword}\n")
    asyncio.run(debug_ml_reviews(keyword))
