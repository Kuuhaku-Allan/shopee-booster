#!/usr/bin/env python3
"""
Script de debug para capturar a estrutura HTML do Mercado Livre
e identificar os seletores CSS corretos.
"""

import asyncio
from playwright.async_api import async_playwright

async def debug_ml_structure(keyword: str):
    """Captura e analisa a estrutura HTML do ML."""
    kw_encoded = keyword.replace(" ", "-").lower()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Mostra o navegador
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
        await asyncio.sleep(5)  # Espera carregar completamente
        
        # Tenta diferentes seletores para cards de produtos
        selectors_to_try = [
            '.ui-search-result__content',
            '.poly-card__content',
            '.ui-search-result',
            '.poly-card',
            'li.ui-search-layout__item',
            'ol.ui-search-layout li',
        ]
        
        print("="*60)
        print("TESTANDO SELETORES DE CARDS")
        print("="*60)
        
        products = None
        working_selector = None
        
        for selector in selectors_to_try:
            elements = await page.query_selector_all(selector)
            print(f"\n{selector}: {len(elements)} elementos")
            if len(elements) > 0 and not products:
                products = elements
                working_selector = selector
        
        if not products:
            print("\n❌ ERRO: Nenhum card de produto encontrado!")
            await browser.close()
            return
        
        print(f"\n✅ Usando seletor: {working_selector}")
        print(f"✅ {len(products)} produtos encontrados")
        
        # Analisa o primeiro produto em detalhes
        print("\n" + "="*60)
        print("ANALISANDO PRIMEIRO PRODUTO")
        print("="*60)
        
        first_product = products[0]
        
        # Captura HTML do primeiro produto
        html = await first_product.inner_html()
        print(f"\n📄 HTML do primeiro produto (primeiros 1000 chars):")
        print("-"*60)
        print(html[:1000])
        print("-"*60)
        
        # Testa seletores de nome
        print("\n🏷️ TESTANDO SELETORES DE NOME:")
        name_selectors = [
            'h2',
            '.ui-search-item__title',
            '.poly-component__title',
            'a.poly-component__title',
            '.ui-search-item__group__element',
            'a[title]',
        ]
        
        for selector in name_selectors:
            elem = await first_product.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                print(f"  ✅ {selector}: {text[:50]}")
            else:
                print(f"  ❌ {selector}: não encontrado")
        
        # Testa seletores de preço
        print("\n💰 TESTANDO SELETORES DE PREÇO:")
        price_selectors = [
            '.andes-money-amount__fraction',
            '.price-tag-fraction',
            '.andes-money-amount-combo__part--symbol-fraction',
            '.andes-money-amount',
            '.price-tag',
        ]
        
        for selector in price_selectors:
            elem = await first_product.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                print(f"  ✅ {selector}: {text}")
            else:
                print(f"  ❌ {selector}: não encontrado")
        
        # Testa seletores de avaliações
        print("\n⭐ TESTANDO SELETORES DE AVALIAÇÕES:")
        review_selectors = [
            '.ui-search-reviews__amount',
            '.ui-search-reviews__rating-number',
            '.andes-visually-hidden',
            '[class*="review"]',
        ]
        
        for selector in review_selectors:
            elem = await first_product.query_selector(selector)
            if elem:
                text = await elem.inner_text()
                print(f"  ✅ {selector}: {text[:50]}")
            else:
                print(f"  ❌ {selector}: não encontrado")
        
        # Testa seletores de link
        print("\n🔗 TESTANDO SELETORES DE LINK:")
        link_selectors = [
            'a[href*="/MLB"]',
            'a[href*="mercadolivre.com.br"]',
            'a',
        ]
        
        for selector in link_selectors:
            elem = await first_product.query_selector(selector)
            if elem:
                href = await elem.get_attribute('href')
                print(f"  ✅ {selector}: {href[:80]}")
            else:
                print(f"  ❌ {selector}: não encontrado")
        
        print("\n" + "="*60)
        print("✅ DEBUG COMPLETO")
        print("="*60)
        print("\nPressione Enter para fechar o navegador...")
        input()
        
        await browser.close()

if __name__ == "__main__":
    keyword = "mochila escolar"
    print(f"\n🧪 DEBUG: Estrutura HTML do Mercado Livre")
    print(f"📝 Keyword: {keyword}\n")
    asyncio.run(debug_ml_structure(keyword))
