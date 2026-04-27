#!/usr/bin/env python3
"""
Debug dos seletores CSS do Mercado Livre
Salva o HTML da página para análise manual
"""

import asyncio
import sys
from playwright.async_api import async_playwright

async def debug_ml_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Abre o navegador visível
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
        
        search_url = "https://lista.mercadolivre.com.br/mochila-escolar"
        print(f"[DEBUG] Abrindo: {search_url}")
        
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)  # Aguarda carregamento completo
        
        # Salva HTML completo
        html = await page.content()
        with open("ml_page_debug.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("[DEBUG] HTML salvo em: ml_page_debug.html")
        
        # Testa vários seletores
        selectors_to_test = [
            '.poly-card__content',
            '.ui-search-result__content',
            '.ui-search-item',
            '[class*="search-result"]',
            '[class*="item"]',
            'article',
            '.poly-component__title',
            '.ui-search-item__title',
            'h2',
            '.andes-money-amount__fraction',
            '.price-tag-fraction',
            '[class*="price"]',
            '[class*="review"]',
            '[class*="rating"]',
        ]
        
        print("\n[DEBUG] Testando seletores:")
        for selector in selectors_to_test:
            try:
                elements = await page.query_selector_all(selector)
                print(f"  {selector:40s} → {len(elements):3d} elementos")
                
                # Mostra exemplo do primeiro elemento
                if elements and len(elements) > 0:
                    first = elements[0]
                    text = await first.inner_text()
                    text_preview = text.strip()[:80].replace("\n", " ")
                    print(f"    Exemplo: {text_preview}")
            except Exception as e:
                print(f"  {selector:40s} → ERRO: {e}")
        
        # Extrai estrutura de um card de produto
        print("\n[DEBUG] Estrutura do primeiro card:")
        try:
            first_card = await page.query_selector('.ui-search-result__content, .poly-card__content, article')
            if first_card:
                html_card = await first_card.inner_html()
                with open("ml_card_debug.html", "w", encoding="utf-8") as f:
                    f.write(html_card)
                print("  HTML do card salvo em: ml_card_debug.html")
        except Exception as e:
            print(f"  Erro ao extrair card: {e}")
        
        print("\n[DEBUG] Pressione Enter para fechar o navegador...")
        input()
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_ml_page())
