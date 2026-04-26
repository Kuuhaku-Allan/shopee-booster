"""
Captura o HTML renderizado após JavaScript carregar
"""

import asyncio
from playwright.async_api import async_playwright

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="pt-BR",
            viewport={"width": 1280, "height": 800}
        )
        
        page = await context.new_page()
        
        print("Navegando...")
        await page.goto("https://shopee.com.br/totalmenteseu", wait_until="networkidle", timeout=60000)
        
        print("Aguardando 10s...")
        await asyncio.sleep(10)
        
        print("Capturando HTML...")
        html = await page.content()
        
        with open("rendered_html.html", "w", encoding="utf-8") as f:
            f.write(html)
        
        print(f"HTML salvo: {len(html)} bytes")
        
        # Busca por classes comuns
        print("\nBuscando classes de produto...")
        if "shopee-search-item-result" in html:
            print("✓ Encontrado: shopee-search-item-result")
        if "shop-search-result-view" in html:
            print("✓ Encontrado: shop-search-result-view")
        if 'href="/product/' in html or 'href="/Mochila' in html:
            print("✓ Encontrado: links de produto")
        
        # Lista todos os links
        links = await page.query_selector_all("a")
        print(f"\nTotal de links na página: {len(links)}")
        
        product_links = []
        for link in links:
            href = await link.get_attribute("href")
            if href and ("/product/" in href or "-i." in href):
                product_links.append(href)
        
        print(f"Links de produtos encontrados: {len(product_links)}")
        for i, link in enumerate(product_links[:10], 1):
            print(f"  {i}. {link[:80]}...")
        
        await browser.close()

asyncio.run(capture())
