"""
scripts/check_html_products.py — Verifica se produtos estão no HTML
====================================================================
Verifica se a Shopee está usando Server-Side Rendering para produtos.

Uso:
    python scripts/check_html_products.py
"""

import sys
import os
from pathlib import Path
import asyncio
import re

# Força UTF-8 no Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Adiciona o diretório raiz ao path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))


async def check_html_products():
    """Verifica se produtos estão no HTML da página"""
    from playwright.async_api import async_playwright
    
    url = "https://shopee.com.br/totalmenteseu"
    
    print("=" * 70)
    print("VERIFICAÇÃO DE PRODUTOS NO HTML")
    print("=" * 70)
    print(f"\nURL: {url}\n")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="pt-BR",
            viewport={"width": 1280, "height": 800}
        )
        
        page = await context.new_page()
        
        print("Carregando página...")
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        print("Aguardando renderização...")
        await asyncio.sleep(5)
        
        # Pega o HTML completo
        html = await page.content()
        
        # Pega o texto visível
        body_text = await page.inner_text("body")
        
        await browser.close()
    
    print("\n" + "=" * 70)
    print("ANÁLISE DO HTML")
    print("=" * 70)
    
    # Busca por palavras-chave dos produtos conhecidos
    keywords = [
        "mochila",
        "rosa",
        "feminina",
        "infantil",
        "minions",
        "princesa"
    ]
    
    print("\n1. Busca por palavras-chave dos produtos:")
    for keyword in keywords:
        count_html = html.lower().count(keyword)
        count_text = body_text.lower().count(keyword)
        print(f"   '{keyword}': {count_html} no HTML, {count_text} visível")
    
    # Busca por estruturas de dados JSON no HTML
    print("\n2. Busca por dados JSON embutidos:")
    
    # Padrão comum: <script>window.__INITIAL_STATE__ = {...}</script>
    json_patterns = [
        r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
        r'window\.__APP_STATE__\s*=\s*({.+?});',
        r'window\.__PRELOADED_STATE__\s*=\s*({.+?});',
        r'<script[^>]*type="application/json"[^>]*>(.+?)</script>',
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>',
    ]
    
    found_json = False
    for pattern in json_patterns:
        matches = re.findall(pattern, html, re.DOTALL)
        if matches:
            print(f"   ✓ Encontrado: {pattern[:50]}...")
            print(f"     Total de matches: {len(matches)}")
            
            # Verifica se contém produtos
            for i, match in enumerate(matches[:3]):  # Analisa os primeiros 3
                if any(kw in match.lower() for kw in keywords):
                    print(f"     Match {i+1} contém palavras-chave de produtos!")
                    found_json = True
                    
                    # Salva o JSON para análise
                    with open(f"product_json_{i+1}.json", "w", encoding="utf-8") as f:
                        f.write(match)
                    print(f"     Salvo em: product_json_{i+1}.json")
    
    if not found_json:
        print("   ✗ Nenhum JSON com produtos encontrado")
    
    # Busca por itemid no HTML
    print("\n3. Busca por IDs de produtos:")
    itemid_pattern = r'"itemid":\s*(\d+)'
    itemids = re.findall(itemid_pattern, html)
    if itemids:
        print(f"   ✓ Encontrados {len(set(itemids))} itemids únicos")
        print(f"     Exemplos: {list(set(itemids))[:5]}")
    else:
        print("   ✗ Nenhum itemid encontrado")
    
    # Busca por elementos DOM de produtos
    print("\n4. Estrutura DOM:")
    print(f"   Tamanho do HTML: {len(html):,} bytes")
    print(f"   Tamanho do texto visível: {len(body_text):,} caracteres")
    
    # Salva HTML para análise manual
    with open("shop_page.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n   HTML completo salvo em: shop_page.html")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(check_html_products())
    except Exception as e:
        print(f"\n❌ ERRO: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
