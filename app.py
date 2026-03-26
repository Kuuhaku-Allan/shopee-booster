import streamlit as st
import pandas as pd
import asyncio
import sys
import nest_asyncio
import json
import subprocess
from google import genai
# rembg é importado sob demanda para não travar a inicialização
from PIL import Image
import io
import requests
import re
import time
import random
from functools import lru_cache

import os
from dotenv import load_dotenv

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

nest_asyncio.apply()

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    st.warning("⚠️ Chave da API do Google Gemini não encontrada.")
    API_KEY = st.text_input("Insira sua GOOGLE_API_KEY para continuar usando o app:", type="password")
    if not API_KEY:
        st.info("Você precisa inserir uma chave de API válida para usar os recursos de IA do Shopee Booster.")
        st.stop()

client = genai.Client(api_key=API_KEY)

# Modelos para tarefas COM imagem (multimodal) — cota limitada, usar com parcimônia
MODELOS_VISION = ["gemini-2.5-flash"]

# Modelos para tarefas só de TEXTO — priorizando os de maior cota diária
MODELOS_TEXTO = [
    "gemini-3.1-flash-lite-preview",  # 500 RPD — principal
    "gemini-2.5-flash-lite",          # 20 RPD — fallback
    "gemini-2.5-flash",               # 20 RPD — último recurso
]


def playwright_intercept(script: str) -> dict | list | None:
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=150
        )
        if result.stderr.strip():
            st.caption(f"🔍 Debug stderr: {result.stderr.strip()[:2000]}")
        if result.returncode != 0:
            st.caption(f"🔍 Debug returncode: {result.returncode}")
            st.caption(f"🔍 Debug stdout: {result.stdout.strip()[:500]}")
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
        return None
    except subprocess.TimeoutExpired:
        st.warning("⏱️ Timeout — Playwright demorou mais de 150s")
        return None
    except Exception as e:
        st.caption(f"🔍 Debug exception: {e}")
        return None


def fetch_shop_info(username: str) -> dict:
    script = f"""
import asyncio, json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={{"width": 1280, "height": 800}},
            extra_http_headers={{"Accept-Language": "pt-BR,pt;q=0.9"}}
        )
        page = await context.new_page()
        captured = {{}}

        async def handle_response(response):
            if response.request.method == "OPTIONS": return
            if "get_shop_base" in response.url:
                try:
                    captured["data"] = await response.json()
                except Exception:
                    pass

        page.on("response", handle_response)
        await page.goto("https://shopee.com.br/{username}", wait_until="networkidle", timeout=45000)
        await asyncio.sleep(5)
        await browser.close()
        print(json.dumps(captured.get("data", {{}})))

asyncio.run(run())
"""
    result = playwright_intercept(script)
    return result if result else {}


def fetch_shop_products_intercept(username: str, shopid) -> list: 
    script = f""" 
import asyncio, json, sys 
from playwright.async_api import async_playwright 
 
async def run(): 
    async with async_playwright() as p: 
        browser = await p.chromium.launch( 
            headless=True, 
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
        seen_ids = set() 
 
        async def handle_response(response): 
            if response.request.method == "OPTIONS": 
                return 
            url = response.url 
            if "rcmd_items" not in url and "shop_page" not in url: 
                return 
            try: 
                d = await response.json() 
                cic = d.get("data", {{}}).get("centralize_item_card", {{}}) 
                item_cards = cic.get("item_cards", []) 
                print(f"item_cards: {{len(item_cards)}}", file=sys.stderr) 
 
                for card in item_cards[:30]: 
                    iid = card.get("itemid") or card.get("item_id") 
                    if not iid or iid in seen_ids: 
                        continue 
                    seen_ids.add(iid) 
 
                    sid = card.get("shopid") or card.get("shop_id") or "{shopid}" 
 
                    # Preço 
                    price_raw = 0 
                    for price_key in ["item_card_display_price", "price_obj", "price_info"]: 
                        po = card.get(price_key, {{}}) 
                        if isinstance(po, dict): 
                            price_raw = po.get("price", po.get("current_price", po.get("min_price", 0))) 
                            if price_raw: break 
                    if not price_raw: 
                        price_raw = card.get("price", card.get("price_min", 0)) 
 
                    # Vendas 
                    sold = 0 
                    for sold_key in ["item_card_display_sold_count", "sold_obj"]: 
                        so = card.get(sold_key, {{}}) 
                        if isinstance(so, dict): 
                            sold = so.get("historical_sold_count", so.get("sold", 0)) 
                            if sold: break 
                    if not sold: 
                        sold = card.get("historical_sold", card.get("sold", 0)) 
 
                    # Nome e imagem estão em item_card_displayed_asset 
                    asset = card.get("item_card_displayed_asset") or {{}} 
                    name = asset.get("name") or "" 
                    
                    img = "" 
                    # Imagem pode estar em vários subcampos do asset 
                    for img_key in ["image", "cover", "thumbnail"]: 
                        val = asset.get(img_key) 
                        if val and isinstance(val, str): 
                            img = val 
                            break 
                    # Fallback: lista de imagens no asset 
                    if not img: 
                        imgs_list = asset.get("images") or asset.get("image_list") or [] 
                        if imgs_list: 
                            img = imgs_list[0] 
 
                    print(f"  → iid={{iid}} name={{repr(name[:30])}} img={{repr(img[:40])}}", file=sys.stderr) 
                    products.append({{ 
                         "itemid": iid, 
                         "shopid": sid, 
                         "name":   name or f"Produto {{iid}}", 
                         "price":  price_raw / 100000 if price_raw > 1000 else price_raw, 
                         "sold":   sold, 
                         "image":  img, 
                    }}) 
 
            except Exception as e: 
                print(f"parse err: {{e}}", file=sys.stderr) 
 
        page.on("response", handle_response) 
        try: 
            await page.goto( 
                "https://shopee.com.br/{username}", 
                wait_until="networkidle", timeout=50000 
            ) 
        except Exception as e: 
            print(f"goto err: {{e}}", file=sys.stderr) 
 
        await asyncio.sleep(3) 
        for _ in range(6): 
            await page.mouse.wheel(0, 400) 
            await asyncio.sleep(1.0) 
 
        await asyncio.sleep(2) 
        await browser.close() 
        print(json.dumps(products[:30])) 
 
asyncio.run(run()) 
""" 
    result = playwright_intercept(script) 
    return result if isinstance(result, list) else [] 


def fetch_competitors_intercept(keyword: str) -> list:
    kw_encoded = keyword.replace(" ", "+")
    script = f"""
import asyncio, json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={{"width": 1280, "height": 800}},
            extra_http_headers={{"Accept-Language": "pt-BR,pt;q=0.9"}}
        )
        page = await context.new_page()
        competitors = []

        async def handle_response(response): 
            if response.request.method == "OPTIONS": return 
            url = response.url 
            if ("search_items" in url or "v4/search" in url) and not competitors: 
                try: 
                    data = await response.json() 
                    items = ( 
                        data.get("items") or 
                        data.get("data", {{}}).get("items") or 
                        [] 
                    ) 
                    for item in items[:10]: 
                        b = item.get("item_basic", item) 
                        if b.get("itemid"): 
                            competitors.append({{ 
                                "item_id":    b.get("itemid"), 
                                "shop_id":    b.get("shopid"), 
                                "nome":       b.get("name", "")[:65], 
                                "preco":      b.get("price_min", b.get("price", 0)) / 100000, 
                                "avaliações": b.get("cmt_count", 0), 
                                "curtidas":   b.get("liked_count", 0), 
                                "estrelas":   round(b.get("item_rating", {{}}).get("rating_star", 0), 1), 
                            }}) 
                except Exception: 
                    pass 

        page.on("response", handle_response)
        await page.goto(
            "https://shopee.com.br/search?keyword={kw_encoded}&sortBy=sales",
            wait_until="networkidle", timeout=45000
        )
        await asyncio.sleep(6)
        if not competitors:
            for _ in range(5):
                await page.mouse.wheel(0, 900)
                await asyncio.sleep(2)
            await asyncio.sleep(4)
        await browser.close()
        print(json.dumps(competitors))

asyncio.run(run())
"""
    result = playwright_intercept(script)
    return result if isinstance(result, list) else []


# ─────────────────────────────────────────────────────────────────
# FIX REVIEWS: Aprimorando a interceptação de avaliações.
# O debug anterior mostrou que as URLs capturadas com "rating" eram
# arquivos estáticos. A nova estratégia precisa ser mais robusta
# para identificar o JSON de avaliações, mesmo que a URL não contenha
# a palavra "rating".
#
# Nova estratégia:
# 1. Interceptar todas as respostas JSON.
# 2. Iterar sobre o JSON e suas chaves aninhadas para encontrar uma lista
#    que pareça ser de avaliações (i.e., uma lista de dicionários
#    onde cada dicionário tem uma chave 'comment').
# ─────────────────────────────────────────────────────────────────
def fetch_reviews_intercept(item_id: str, shop_id: str, product_url: str = "", product_name_override: str = "") -> tuple[list, list]:
    logs = []

    # Passo 1: obter nome do produto
    product_name = ""

    # NOVO: usar nome direto se fornecido 
    if product_name_override: 
        product_name = product_name_override 
        logs.append(f"📌 Nome direto: **{product_name}**") 
    elif product_url: 
        slug_match = re.search(r"shopee\.com\.br/([^?#/]+)-i\.", product_url)
        if slug_match:
            from urllib.parse import unquote
            slug = unquote(slug_match.group(1)).replace("-", " ")
            product_name = " ".join(slug.split()[:5])
            logs.append(f"📌 Nome do slug: **{product_name}**")

    if not product_name:
        try:
            api = f"https://shopee.com.br/api/v4/pdp/get_pc?item_id={item_id}&shop_id={shop_id}&tz_offset_in_minutes=-180&detail_level=0"
            r = requests.get(api, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                product_name = " ".join(((r.json().get("data") or {}).get("name") or "").split()[:5])
                logs.append(f"📌 Nome via API: **{product_name}**")
        except Exception as e:
            logs.append(f"⚠️ API erro: {e}")

    if not product_name:
        logs.append("❌ Nome não obtido.")
        return [], logs

    import unicodedata
    kw = "".join(
        c for c in unicodedata.normalize("NFD", product_name)
        if unicodedata.category(c) != "Mn"
    )
    # Simplificar: só primeiras 3 palavras genéricas para busca
    kw_short = " ".join(kw.split()[:3])
    logs.append(f"🔍 Buscando no ML: **{kw_short}**")

    # Passo 2: Playwright no ML
    script = f"""
import asyncio, json, sys
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="pt-BR",
            viewport={{"width": 1280, "height": 900}},
            extra_http_headers={{
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }}
        )
        page = await context.new_page()

        kw_url = f"{kw_short.replace(' ', '-').lower()}"
        search_url = f"https://lista.mercadolivre.com.br/{{kw_url}}"
        print("Buscando: " + search_url, file=sys.stderr)
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print("Goto search erro: " + str(e), file=sys.stderr)
        await asyncio.sleep(3)
        print("URL atual: " + page.url, file=sys.stderr)
        print("Título: " + await page.title(), file=sys.stderr)

        # Debug: mostrar quantos links /MLB existem na página
        all_mlb = await page.query_selector_all("a[href*='/MLB']")
        print(f"Links MLB encontrados: {{len(all_mlb)}}", file=sys.stderr)
        if all_mlb:
            first_href = await all_mlb[0].get_attribute("href")
            print(f"Primeiro link: {{first_href[:100]}}", file=sys.stderr)

        # Pegar links reais de produto (não tracking URLs)
        product_link = None
        try:
            hrefs = await page.evaluate('''
                () => Array.from(document.querySelectorAll('a'))
                    .map(a => a.href)
                    .filter(h =>
                        h.includes('mercadolivre.com.br/') &&
                        h.includes('/MLB') &&
                        !h.includes('click1.') &&
                        !h.includes('/mclics/') &&
                        !h.includes('mercadopago')
                    )
                    .slice(0, 5)
            ''')
            print(f"Links diretos encontrados: {{hrefs}}", file=sys.stderr)
            if hrefs:
                product_link = hrefs[0]
        except Exception as e:
            print(f"evaluate hrefs erro: {{e}}", file=sys.stderr)

        # Fallback: pegar o href do atributo data-* ou link dentro do card
        if not product_link:
            try:
                hrefs = await page.evaluate('''
                    () => {{
                        const cards = document.querySelectorAll(
                            '.ui-search-item__image-link, .poly-card__portada, [data-item-id]'
                        );
                        return Array.from(cards)
                            .map(el => el.closest('a') ? el.closest('a').href : el.href)
                            .filter(h => h && h.includes('mercadolivre.com.br/') && h.includes('/MLB'))
                            .slice(0, 3);
                    }}
                ''')
                print(f"Links via cards: {{hrefs}}", file=sys.stderr)
                if hrefs:
                    product_link = hrefs[0]
            except Exception as e:
                print(f"cards hrefs erro: {{e}}", file=sys.stderr)

        if not product_link:
            print("Sem produto encontrado. HTML snippet:", file=sys.stderr)
            try:
                body = await page.inner_text("body")
                print(body[:500], file=sys.stderr)
            except Exception:
                pass
            await browser.close()
            print(json.dumps([]))
            return

        # Navegar para página do produto
        clean_url = product_link.split("?")[0]
        print(f"Abrindo produto: {{clean_url}}", file=sys.stderr)
        try:
            await page.goto(clean_url + "#reviews", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print("Goto product erro: " + str(e), file=sys.stderr)
        await asyncio.sleep(3)

        # Scroll até avaliações
        for _ in range(10):
            await page.mouse.wheel(0, 600)
            await asyncio.sleep(0.5)
        await asyncio.sleep(2)

        # Extrair avaliações
        reviews = []
        review_selectors = [
            ".ui-review-capability-comments__comment p",
            "[class*='review-comment'] p",
            "[class*='review__content']",
            "[data-testid='review-content']",
            ".review p",
            "[class*='comment__content']",
        ]
        for sel in review_selectors:
            try:
                els = await page.query_selector_all(sel)
                if els:
                    print(f"Review seletor '{{sel}}': {{len(els)}} elementos", file=sys.stderr)
                    for el in els[:15]:
                        txt = (await el.inner_text()).strip()
                        # Filtrar labels de estrelas e textos muito curtos
                        if len(txt) > 15 and txt not in reviews and not txt.startswith("Avalia"):
                            reviews.append(txt)
                    if reviews:
                        break
            except Exception:
                continue

        if not reviews:
            # Fallback evaluate: buscar parágrafos próximos a elementos de estrela
            try:
                reviews = await page.evaluate('''
                    () => {{
                        const res = [];
                        document.querySelectorAll('[class*="review"], [class*="Review"]').forEach(el => {{
                            const p = el.querySelector('p');
                            if (p && p.innerText.trim().length > 10) {{
                                res.push(p.innerText.trim().slice(0, 300));
                            }}
                        }});
                        return res.slice(0, 10);
                    }}
                ''')
                print(f"Fallback evaluate: {{len(reviews)}} reviews", file=sys.stderr)
            except Exception as e:
                print(f"Fallback evaluate erro: {{e}}", file=sys.stderr)

        print(f"Total reviews: {{len(reviews)}}", file=sys.stderr)
        await browser.close()
        print(json.dumps(reviews[:10]))

asyncio.run(run())
"""
    result = playwright_intercept(script)
    if result is None:
        result = []

    logs.append(f"✅ {len(result)} avaliações encontradas via ML")
    return result, logs








def resolve_shopee_url(url):
    match = re.search(r"i\.([0-9]+)\.([0-9]+)", url)
    if match:
        return {"type": "product", "shopid": match.group(1), "itemid": match.group(2), "full_url": url}
    if "shopee.com.br/" in url:
        username = url.split("shopee.com.br/")[1].split("?")[0]
        return {"type": "shop", "username": username}
    return None


def generate_full_optimization(product: dict, competitors_df, reviews: list, segmento: str) -> str: 
    nome = product.get("name", "") 
    preco = product.get("price", 0) 
 
    comp_text = "Sem dados de concorrentes." 
    if competitors_df is not None and not competitors_df.empty: 
        linhas = [] 
        for _, r in competitors_df.iterrows(): 
            linhas.append( 
                f"• {r['nome']} | R${r['preco']:.2f} | " 
                f"{r.get('avaliações', 0)} avaliações | " 
                f"⭐{r.get('estrelas', 0)}" 
            ) 
        comp_text = "\n".join(linhas) 
        preco_medio = competitors_df["preco"].mean() 
        comp_text += f"\n\nPreço médio do mercado: R${preco_medio:.2f}" 
 
    reviews_text = "Sem avaliações coletadas." 
    if reviews: 
        reviews_text = "\n".join(f"• {r}" for r in reviews[:8]) 
 
    prompt = f"""Você é um especialista em e-commerce Shopee brasileiro com foco em maximizar CTR e conversão orgânica. 
 
 PRODUTO ATUAL DA LOJA: 
 - Nome: {nome} 
 - Preço atual: R$ {preco:.2f} 
 - Segmento: {segmento} 
 
 TOP CONCORRENTES NA SHOPEE (ordenados por engajamento): 
 {comp_text} 
 
 AVALIAÇÕES DO MERCADO (reclamações reais de compradores de produtos similares): 
 {reviews_text} 
 
 Com base nessa análise completa, gere uma otimização de listing para Shopee 2026. 
 Seja específico, use as fraquezas dos concorrentes como diferenciais. 
 
 Responda EXATAMENTE neste formato: 
 
 ## 🏷️ TÍTULO OTIMIZADO 
 [Título de 60-70 caracteres com keyword principal no início] 
 
 ## 💰 ESTRATÉGIA DE PREÇO 
 [Recomendação de preço com justificativa baseada nos concorrentes e no mercado] 
 
 ## 📝 DESCRIÇÃO OTIMIZADA 
 [Descrição de 400-600 caracteres focada em conversão. Destaque os 3 principais diferenciais vs as reclamações coletadas. Use emojis estratégicos.] 
 
 ## 🏷️ 20 TAGS LSI 
 [20 tags separadas por vírgula, do maior para menor volume de busca estimado] 
 
 ## 🚀 3 ARGUMENTOS DE VENDA ÚNICOS 
 [3 bullets curtos baseados diretamente nas fraquezas/reclamações dos concorrentes] 
 """ 
    ultimo_erro = "" 
    for m in MODELOS_TEXTO: 
        try: 
            config = {"thinking_config": {"thinking_budget": 0}} if "3.1" in m or "2.5" in m else {} 
            response = client.models.generate_content( 
                model=m, 
                contents=[prompt], 
                config=config if config else None 
            ) 
            return response.text 
        except Exception as e: 
            ultimo_erro = f"{m}: {e}" 
            time.sleep(2) 
            continue 
    return f"⏳ Todos os modelos falharam. Último erro: {ultimo_erro}" 


def build_catalog_context(produtos: list, shop_name: str) -> str: 
    linhas = [f"Você é o assistente virtual da loja '{shop_name}' na Shopee Brasil."] 
    linhas.append("Seu papel é ajudar clientes a encontrar o produto ideal, responder dúvidas e dar confiança para a compra.") 
    linhas.append("Seja simpático, use emojis com moderação e responda SEMPRE em português brasileiro.") 
    linhas.append("Nunca invente informações que não estão no catálogo abaixo.") 
    linhas.append("Se não souber algo, diga que vai verificar com a loja.\n") 
    linhas.append(f"=== CATÁLOGO COMPLETO DA LOJA ({len(produtos)} produtos) ===\n") 
    for i, p in enumerate(produtos, 1): 
        linhas.append(f"{i}. {p['name']}") 
        linhas.append(f"   Preço: R$ {p['price']:.2f}") 
        linhas.append(f"   ID: {p['itemid']}\n") 
    linhas.append("=== FIM DO CATÁLOGO ===") 
    linhas.append("\nQuando recomendar produtos, sempre mencione o nome completo e o preço.") 
    return "\n".join(linhas) 
 
 
def chat_with_gemini(user_message: str, history: list, catalog_context: str) -> str: 
    # Montar histórico no formato que o Gemini espera 
    contents = [catalog_context + "\n\n---\nInício da conversa com o cliente:\n"] 
    for turn in history: 
        contents.append(f"Cliente: {turn['user']}") 
        contents.append(f"Assistente: {turn['assistant']}") 
    contents.append(f"Cliente: {user_message}\nAssistente:") 
     
    prompt = "\n".join(contents) 
     
    ultimo_erro = "" 
    for m in MODELOS_TEXTO: 
        try: 
            config = {"thinking_config": {"thinking_budget": 0}} if "3.1" in m or "2.5" in m else {} 
            response = client.models.generate_content( 
                model=m, 
                contents=[prompt], 
                config=config if config else None 
            ) 
            return response.text.strip() 
        except Exception as e: 
            ultimo_erro = f"{m}: {e}" 
            time.sleep(2) 
            continue 
    return f"⏳ Erro ao conectar com a IA. Tente novamente. ({ultimo_erro})" 


from PIL import ImageEnhance, ImageFilter 
 
def generate_ai_scenario(prompt_text: str, segmento: str = "") -> Image.Image | None: 
    """Gera cenário via Hugging Face (FLUX.1-dev), Together AI ou Pollinations com fallback gradiente.""" 
    
    # 1. TENTATIVA: Hugging Face (FLUX.1-dev) - QUALIDADE SUPERIOR
    hf_token = os.getenv("HF_TOKEN", "")
    if hf_token:
        try:
            from huggingface_hub import InferenceClient
            client_hf = InferenceClient(api_key=hf_token)

            # Prompts técnicos por nicho — Packshot minimalista de alta conversão
            prompts_nicho = {
                "Escolar / Juvenil": (
                    "Professional e-commerce packshot background. A clean, minimalist white geometric podium "
                    "centered in the frame. Soft neutral studio lighting with high-key lighting. "
                    "Seamless light grey and soft lavender gradient background. Professional product photography, "
                    "sharp focus on the podium surface, realistic ambient occlusion shadows, 8k, shot on Phase One IQ4."
                ),
                "Viagem": (
                    "Professional outdoor studio background. A clean concrete or stone platform. "
                    "Soft, out-of-focus mountain landscape at golden hour in the far distance. "
                    "Premium travel photography style, soft natural shadows, 8k, sharp focus on the base."
                ),
                "Profissional / Tech": (
                    "Minimalist modern office studio background. A sleek white desk surface. "
                    "Soft LED studio lighting, clean grey gradient wall, professional advertising quality. "
                    "Subtle contact shadows, 8k resolution, ultra-sharp focus."
                ),
                "Moda": (
                    "High-end fashion editorial studio background. A white marble floor surface. "
                    "Soft diffused lighting with rim light. Minimalist aesthetic with a neutral pastel wall "
                    "in harmony with product colors, empty surface, 8k, professional packshot style."
                ),
            }
            prompt_hf = prompts_nicho.get(segmento, prompts_nicho["Escolar / Juvenil"])

            try:
                img = client_hf.text_to_image(
                    prompt=prompt_hf,
                    model="black-forest-labs/FLUX.1-dev",  # dev > schnell em qualidade
                )
                return img.convert("RGBA")
            except Exception:
                # Fallback para schnell se dev não disponível
                img = client_hf.text_to_image(
                    prompt=prompt_hf,
                    model="black-forest-labs/FLUX.1-schnell"
                )
                return img.convert("RGBA")
        except Exception as e:
            st.caption(f"🔍 Hugging Face falhou: {e}")

    # 2. TENTATIVA: Together AI (FLUX.1-schnell-Free)
    prompt_completo = ( 
        f"Professional e-commerce packshot background. A clean, minimalist white geometric podium "
        f"centered in the frame. Soft neutral studio lighting with high-key lighting. "
        f"Seamless light grey and soft lavender gradient background. Professional product photography, "
        f"sharp focus on the podium surface, realistic ambient occlusion shadows, 8k, shot on Phase One IQ4."
    ) 
    together_key = os.getenv("TOGETHER_API_KEY", "")
    if together_key:
        try:
            res = requests.post(
                "https://api.together.xyz/v1/images/generations",
                headers={"Authorization": f"Bearer {together_key}"},
                json={
                    "model": "black-forest-labs/FLUX.1-schnell-Free",
                    "prompt": prompt_completo,
                    "width": 1024,
                    "height": 1024,
                    "steps": 4,
                    "n": 1
                },
                timeout=45
            )
            if res.status_code == 200:
                data = res.json()
                img_url = data.get("data", [{}])[0].get("url")
                if img_url:
                    img_res = requests.get(img_url, timeout=30)
                    return Image.open(io.BytesIO(img_res.content)).convert("RGBA")
            elif res.status_code == 402:
                st.caption("🔍 Together AI: Limite de créditos atingido (Free tier).")
        except Exception as e:
            st.caption(f"🔍 Together AI erro: {e}")
    
    # 3. TENTATIVA: Pollinations (Fallback gratuito comum)
    pollinations_key = os.getenv("POLLINATIONS_SK_KEY", "") 
    from urllib.parse import quote 
    prompt_encoded = quote(prompt_text) 
    url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width=1024&height=1024&model=turbo&seed={random.randint(1,9999)}" 
    if pollinations_key: 
        url += f"&key={pollinations_key}" 
    try: 
        time.sleep(2) 
        res = requests.get(url, timeout=60, headers={ 
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" 
        }) 
        if res.status_code == 200 and "image" in res.headers.get("Content-Type", ""): 
            return Image.open(io.BytesIO(res.content)).convert("RGBA") 
    except Exception: 
        pass 
    
    return None  # Ativa o fallback gradiente local 
 
 
@lru_cache(maxsize=4)
def generate_gradient_background(segmento: str) -> Image.Image: 
    """Fundo gradiente profissional estilo packshot — harmonia com o produto.""" 
    import numpy as np 
    size = 1024 
    img_array = np.zeros((size, size, 3), dtype=np.uint8) 
 
    paletas = { 
        "Escolar / Juvenil": ((255, 240, 248), (220, 210, 245)),  # branco rosado → lilás suave 
        "Profissional / Tech": ((240, 245, 255), (210, 220, 240)),  # branco azulado → cinza azul 
        "Viagem": ((255, 248, 235), (235, 220, 200)),              # branco quente → bege 
        "Moda": ((255, 252, 255), (240, 230, 245)),                # branco → lilás muito suave 
    } 
    cor_top, cor_bot = paletas.get(segmento, ((250, 250, 255), (230, 225, 245))) 
 
    cx, cy = size // 2, size // 2 
    max_dist = (size * 0.75) 
 
    for y in range(size): 
        for x in range(size): 
            dist = ((x - cx)**2 + (y - cy)**2) ** 0.5 
            t = min(dist / max_dist, 1.0) 
            r = int(cor_top[0] * (1 - t) + cor_bot[0] * t) 
            g = int(cor_top[1] * (1 - t) + cor_bot[1] * t) 
            b = int(cor_top[2] * (1 - t) + cor_bot[2] * t) 
            img_array[y, x] = [r, g, b] 
 
    return Image.fromarray(img_array, "RGB").convert("RGBA") 
 
 
def apply_contact_shadow(bg: Image.Image, fg: Image.Image, offset: tuple) -> Image.Image: 
    """Adiciona sombra de contato para ancorar o produto no cenário.""" 
    import numpy as np 
    if fg.mode != "RGBA": 
        fg = fg.convert("RGBA") 
    alpha = fg.split()[-1] 
    shadow = Image.new("L", fg.size, 0) 
    shadow.paste(alpha, (0, 0)) 
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=18)) 
    shadow_img = Image.new("RGBA", bg.size, (0, 0, 0, 0)) 
    # Sombra levemente deslocada para baixo e para a direita 
    shadow_offset = (offset[0] + 12, offset[1] + 20) 
    shadow_layer = Image.new("RGBA", bg.size, (0, 0, 0, 0)) 
    shadow_layer.paste(Image.new("RGBA", fg.size, (0, 0, 0, 100)), shadow_offset, mask=shadow) 
    result = Image.alpha_composite(bg, shadow_layer) 
    return result 


def improve_image_quality(img_pil: Image.Image) -> Image.Image: 
    """Melhora nitidez e contraste para fotos de e-commerce.""" 
    img = ImageEnhance.Sharpness(img_pil).enhance(2.0) 
    img = ImageEnhance.Contrast(img).enhance(1.2) 
    img = img.filter(ImageFilter.SMOOTH_MORE) 
    return img 


def upscale_image(img_pil: Image.Image, scale: int = 2) -> Image.Image: 
    """Aumenta resolução usando LANCZOS — melhor qualidade sem dependências extras.""" 
    novo_w = img_pil.width * scale 
    novo_h = img_pil.height * scale 
    return img_pil.resize((novo_w, novo_h), Image.LANCZOS) 


def analyze_reviews_with_gemini(reviews, segmento):
    if not reviews:
        return "Sem avaliações para analisar"
    reviews_text = "\n".join(reviews)
    prompt = f"""
    Você é um especialista em conversão para e-commerce.

    Analise estas reclamações dos concorrentes e me dê 3 argumentos de venda
    para minha mochila ({segmento}) que RESOLVEM esses problemas:

    RECLAMAÇÕES DOS CONCORRENTES:
    {reviews_text}

    Formato de resposta:
    1. [Problema] -> [Meu Argumento de Venda]
    2. [Problema] -> [Meu Argumento de Venda]
    3. [Problema] -> [Meu Argumento de Venda]
    """
    ultimo_erro = ""
    for m in MODELOS_TEXTO:
        try:
            config = {"thinking_config": {"thinking_budget": 0}} if "3.1" in m or "2.5" in m else {}
            response = client.models.generate_content(
                model=m,
                contents=[prompt],
                config=config if config else None
            )
            return response.text
        except Exception as e:
            ultimo_erro = f"{m}: {e}"
            time.sleep(2)  # pausa antes de tentar próximo modelo
            continue
    return f"⏳ Todos os modelos falharam. Último erro: {ultimo_erro}"


# ─────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Shopee Booster - Estágio Allan", layout="wide")
st.title("🚀 Módulo I: Otimização de Listing & Estúdio IA")
st.markdown("---")

# ── SESSION STATE ────────────────────────────────────────────────
if 'selected_product' not in st.session_state:
    st.session_state.selected_product = None
if 'selected_kw' not in st.session_state:
    st.session_state.selected_kw = None
if 'shop_data' not in st.session_state:
    st.session_state.shop_data = None
if 'shop_produtos' not in st.session_state:
    st.session_state.shop_produtos = None
if 'df_competitors' not in st.session_state:
    st.session_state.df_competitors = None
if 'auto_search_competitors' not in st.session_state:
    st.session_state.auto_search_competitors = False
if 'optimization_reviews' not in st.session_state: 
    st.session_state.optimization_reviews = None 
if 'optimization_result' not in st.session_state: 
    st.session_state.optimization_result = None 
if 'auto_fetch_opt_reviews' not in st.session_state: 
    st.session_state.auto_fetch_opt_reviews = False 
if 'chat_history' not in st.session_state: 
    st.session_state.chat_history = [] 
if 'chatbot_active' not in st.session_state: 
    st.session_state.chatbot_active = False 

with st.sidebar:
    st.header("⚙️ Configurações")
    segmento = st.selectbox("Nicho do Produto", ["Escolar / Juvenil", "Profissional / Tech", "Viagem", "Moda"])

uploaded_files = st.file_uploader( 
    "Arraste as fotos do produto (pode selecionar várias)", 
    type=["jpg", "png", "jpeg"], 
    accept_multiple_files=True 
) 
 
if uploaded_files: 
    for idx, uploaded_file in enumerate(uploaded_files): 
        st.markdown(f"#### 🖼️ Imagem {idx+1}: `{uploaded_file.name}`") 
        col1, col2 = st.columns(2) 
        img_bytes = uploaded_file.getvalue() 
        img_original = Image.open(io.BytesIO(img_bytes)) 
 
        with col1: 
            st.subheader("Original") 
            st.image(img_original, width="stretch") 
            st.caption(f"Resolução: {img_original.width}×{img_original.height}px") 
 
        with col2: 
            st.subheader("✨ Resultado") 
             
            op_upscale  = st.checkbox("🔍 Aumentar qualidade (2×)", key=f"upscale_{idx}") 
            op_rembg    = st.checkbox("✂️ Remover fundo", key=f"rembg_{idx}", value=True) 
            op_cenario  = st.checkbox("🎨 Gerar cenário IA", key=f"cenario_{idx}") 
 
            if op_cenario and not op_rembg: 
                st.warning("⚠️ Gerar cenário requer remoção de fundo ativada.") 
                op_cenario = False 
 
            if st.button(f"▶️ Processar", key=f"proc_{idx}"): 
                with st.spinner("Processando..."): 
                    img_work = img_original.copy() 
 
                    # 1. Upscale + melhoria de qualidade 
                    if op_upscale: 
                        img_work = upscale_image(img_work, scale=2) 
                        img_work = improve_image_quality(img_work) 
                        st.caption(f"📐 {img_work.width}×{img_work.height}px — qualidade melhorada") 
 
                    # 2. Remoção de fundo 
                    if op_rembg: 
                        st.info("✂️ Removendo fundo... (No 1º uso, o modelo de IA (~176MB) será baixado. Aguarde.)") 
                        buf = io.BytesIO() 
                        img_work.save(buf, format="PNG") 
                        from rembg import remove
                        no_bg_bytes = remove(buf.getvalue()) 
                        img_work = Image.open(io.BytesIO(no_bg_bytes)).convert("RGBA") 
                        st.success("✅ Fundo removido com sucesso!") 
 
                    final_img = img_work 
 
                    # 3. Cenário 
                    if op_cenario: 
                        st.write("🎨 Gerando cenário (pode levar até 90s)...") 
                        prompt_cenario = "product photography studio white background soft lighting" 
                        if segmento == "Escolar / Juvenil": 
                            prompt_cenario = "minimalist white geometric podium soft lavender background" 
                        elif segmento == "Viagem": 
                            prompt_cenario = "stone platform outdoors golden hour soft focus" 
                        elif segmento == "Profissional / Tech": 
                            prompt_cenario = "sleek white desk surface modern office lighting" 
                        elif segmento == "Moda": 
                            prompt_cenario = "white marble floor fashion studio aesthetic" 
 
                        bg_img = generate_ai_scenario(prompt_cenario, segmento) 
                        if not bg_img: 
                            bg_img = generate_gradient_background(segmento) 
                        else:
                            st.success("✅ Cenário IA gerado!") 
 
                        bg_img = bg_img.resize((1024, 1024)) 
                        fg = img_work.copy() 
                        fg.thumbnail((800, 800)) 
                        # Posiciona ligeiramente para baixo do centro para ficar "apoiada" 
                        offset = ( 
                            (bg_img.width - fg.width) // 2, 
                            int((bg_img.height - fg.height) * 0.6) 
                        ) 
                        # Aplica sombra de contato ANTES de colar o produto 
                        bg_img = apply_contact_shadow(bg_img, fg, offset) 
                        bg_img.paste(fg, offset, fg) 
                        final_img = bg_img 
 
                    st.image(final_img, width="stretch") 
 
                    # Download da imagem processada 
                    buf_out = io.BytesIO() 
                    final_img.convert("RGB").save(buf_out, format="JPEG", quality=95) 
                    st.download_button( 
                        "⬇️ Baixar imagem processada", 
                        data=buf_out.getvalue(), 
                        file_name=f"processada_{idx+1}_{uploaded_file.name}", 
                        mime="image/jpeg", 
                        key=f"dl_{idx}" 
                    ) 
 
                    # 4. Análise SEO com Gemini (só na primeira imagem para economizar cota) 
                    if idx == 0: 
                        st.markdown("---") 
                        prompt_seo = f"Analise esta mochila ({segmento}) e gere Título (60-70 chars), 20 Tags LSI e Descrição CR para Shopee 2026." 
                        response = None 
                        for m in MODELOS_VISION: 
                            try: 
                                response = client.models.generate_content(model=m, contents=[prompt_seo, img_original]) 
                                st.success(f"✅ Estratégia SEO gerada ({m})") 
                                break 
                            except Exception: 
                                continue 
                        if response: 
                            st.markdown("### 📈 Diagnóstico de Listing") 
                            st.write(response.text) 
                        else: 
                            st.error("❌ Cota de IA atingida. Tente em 60s.") 
 
        st.markdown("---") 

# ── AUDITORIA DE LOJA ──────────────────────────────────────────
st.markdown("---")
st.header("🕵️ Auditoria de Loja e Radar de Concorrência")

url_loja = st.text_input("Cole a URL da sua loja")

if url_loja and st.button("Analisar Loja"):
    resolved = resolve_shopee_url(url_loja)
    if not resolved or resolved["type"] != "shop":
        st.error("URL inválida.")
    else:
        username = resolved["username"]
        with st.spinner("Abrindo Shopee e interceptando dados... (30-60s)\n(Se não carregar, tente novamente ou verifique se a URL da loja está correta e a loja possui produtos visíveis.)"):
            shop_raw = fetch_shop_info(username)

        d = shop_raw.get("data", shop_raw)
        if d:
            st.session_state.shop_data = d
            shopid = d.get("shopid") or d.get("shop_id")
            with st.spinner("Carregando galeria..."):
                st.session_state.shop_produtos = fetch_shop_products_intercept(username, shopid)
        else:
            st.error("Não foi possível carregar os dados da loja.")

if st.session_state.shop_data:
    d = st.session_state.shop_data
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏪 Loja",       d.get("name", "—"))
    c2.metric("👥 Seguidores", d.get("follower_count", "N/D"))
    c3.metric("📦 Produtos",   d.get("item_count", "N/D"))
    c4.metric("⭐ Avaliação",  d.get("rating_star", "N/D"))

    rr = d.get("chat_response_rate") or d.get("response_rate")
    if rr:
        st.metric("💬 Taxa de Resposta", f"{rr}%")
        if rr < 95:
            st.warning("⚠️ Taxa de resposta abaixo de 95% prejudica o ranking.")

    st.subheader("📦 Produtos da Loja")
    produtos = st.session_state.shop_produtos or []

    if produtos:
        cols = st.columns(4)
        for i, prod in enumerate(produtos):
            with cols[i % 4]:
                # Suporte a URLs completas ou apenas hashes de imagem
                img_url = prod['image'] if prod['image'].startswith('http') else f"https://down-br.img.susercontent.com/file/{prod['image']}"
                st.image(img_url, caption=f"{prod['name'][:28]}\nR$ {prod['price']:.2f}", width="stretch")
                if st.button("🔍 Otimizar", key=f"opt_{prod['itemid']}"):
                    st.session_state.selected_product = prod 
                    st.session_state.selected_kw = prod['name'][:40] 
                    st.session_state.auto_search_competitors = True 
                    st.session_state.auto_fetch_opt_reviews = True 
                    st.session_state.optimization_result = None 
                    st.session_state.optimization_reviews = None 
                    st.rerun()
    else:
        st.warning("Galeria não carregou. Verifique os logs de debug acima.")

# ── PAINEL DE OTIMIZAÇÃO COMPLETA ──────────────────────────── 
if st.session_state.selected_product: 
    prod = st.session_state.selected_product 
    st.markdown("---") 
    st.header(f"⚡ Otimização Completa: {prod['name'][:50]}") 
 
    col_img, col_info = st.columns([1, 3]) 
    with col_img: 
        img_url = prod['image'] if prod['image'].startswith('http') else f"https://down-br.img.susercontent.com/file/{prod['image']}" 
        st.image(img_url, width="stretch") 
    with col_info: 
        st.markdown(f"**Nome atual:** {prod['name']}") 
        st.markdown(f"**Preço atual:** R$ {prod['price']:.2f}") 
        st.markdown(f"**Item ID:** `{prod['itemid']}`") 
        if st.button("❌ Desselecionar produto"): 
            st.session_state.selected_product = None 
            st.session_state.optimization_result = None 
            st.session_state.optimization_reviews = None 
            st.rerun() 
 
    # Auto-buscar avaliações no ML assim que produto é selecionado 
    if st.session_state.auto_fetch_opt_reviews: 
        st.session_state.auto_fetch_opt_reviews = False 
        with st.spinner(f"🔍 Buscando avaliações do mercado para '{prod['name'][:30]}...' (30-60s)"): 
            reviews_opt, _ = fetch_reviews_intercept( 
                str(prod['itemid']), 
                str(prod['shopid']), 
                product_url="", 
                product_name_override=prod['name'] 
            ) 
            st.session_state.optimization_reviews = reviews_opt 
 
    # Status do que foi coletado 
    df_comp = st.session_state.df_competitors 
    reviews_opt = st.session_state.optimization_reviews 
 
    c1, c2 = st.columns(2) 
    with c1: 
        if df_comp is not None and not df_comp.empty: 
            st.success(f"✅ {len(df_comp)} concorrentes coletados") 
        else: 
            st.warning("⏳ Concorrentes ainda não carregados — aguarde ou clique 'Buscar Concorrentes' na aba abaixo") 
    with c2: 
        if reviews_opt: 
            st.success(f"✅ {len(reviews_opt)} avaliações do mercado coletadas") 
        else: 
            st.warning("⚠️ Sem avaliações coletadas — a IA usará só os dados de concorrentes") 
 
    if st.button("🤖 Gerar Otimização Completa com IA", type="primary"): 
        with st.spinner("IA analisando concorrentes + avaliações e gerando listing otimizado..."): 
            st.session_state.optimization_result = generate_full_optimization( 
                prod, 
                df_comp, 
                reviews_opt or [], 
                segmento 
            ) 
 
    if st.session_state.optimization_result: 
        st.markdown("---") 
        st.markdown("### 📈 Listing Otimizado pela IA") 
        st.markdown(st.session_state.optimization_result) 
        st.download_button( 
            "⬇️ Baixar otimização (.txt)", 
            data=st.session_state.optimization_result, 
            file_name=f"otimizacao_{prod['itemid']}.txt", 
            mime="text/plain" 
        ) 

# ── TABS: CONCORRENTES + AVALIAÇÕES + CHATBOT ──────────────────
tab1, tab2, tab3 = st.tabs(["Radar de Concorrentes", "Mineração de Avaliações", "🤖 Chatbot da Loja"]) 

with tab1:
    kw = st.text_input("Palavra-chave", value=st.session_state.get("selected_kw") or "mochila escolar")

    buscar_agora = st.button("🔍 Buscar Concorrentes")

    if st.session_state.auto_search_competitors:
        st.session_state.auto_search_competitors = False
        buscar_agora = True

    if buscar_agora:
        with st.spinner("Navegando na Shopee e interceptando resultados... (30-60s)"):
            rows = fetch_competitors_intercept(kw)

        if rows:
            df = pd.DataFrame(rows)
            df["avaliações"] = pd.to_numeric(df["avaliações"], errors="coerce").fillna(0).astype(int)
            df["curtidas"]   = pd.to_numeric(df["curtidas"],   errors="coerce").fillna(0).astype(int)
            df["preco"]      = pd.to_numeric(df["preco"],      errors="coerce").fillna(0)
            st.session_state.df_competitors = df
        else:
            st.session_state.df_competitors = None
            st.error("Nenhum resultado. Verifique os logs de debug acima.")

    df = st.session_state.df_competitors
    if df is not None and not df.empty:
        st.dataframe(df, width="stretch", hide_index=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("Preço Médio", f"R$ {df['preco'].mean():.2f}")
        c2.metric("Mínimo",      f"R$ {df['preco'].min():.2f}")
        c3.metric("Máximo",      f"R$ {df['preco'].max():.2f}")
        st.warning(f"💡 Preço de lançamento sugerido: R$ {df['preco'].mean()*0.95:.2f}")

        if df["avaliações"].max() > 0:
            top = df.loc[df["avaliações"].idxmax()]
            st.info(f"🏆 Líder por engajamento: **{top['nome']}** — {int(top['avaliações'])} avaliações · {int(top['curtidas'])} curtidas")
        else:
            st.info("Produtos novos — sem avaliações ainda. Use curtidas como referência de demanda.")

        if st.button("🤖 Analisar padrões com IA"):
            titulos = "\n".join(df["nome"].tolist())
            insight = analyze_reviews_with_gemini(
                [f"Títulos dos top sellers:\n{titulos}\n\nIdentifique padrões, keywords mais usadas e sugira um título otimizado."],
                segmento
            )
            st.write(insight)

with tab2:
    url_comp = "" # Inicializar url_comp para garantir que sempre esteja definida
    iid = ""
    sid = ""

    url_comp_input = st.text_input("URL do produto concorrente")
    if url_comp_input:
        res = resolve_shopee_url(url_comp_input)
        if res and res["type"] == "product":
            st.info(f"Item: `{res['itemid']}` | Shop: `{res['shopid']}`")
            iid = res["itemid"]
            sid = res["shopid"]
            url_comp = url_comp_input
        else:
            iid = st.text_input("Item ID", "")
            sid = st.text_input("Shop ID", "")
    else:
        iid = st.text_input("Item ID", "")
        sid = st.text_input("Shop ID", "")

    if st.button("📚 Extrair Avaliações") and iid and sid:
        with st.spinner("Buscando avaliações no Mercado Livre..."):
            reviews, debug_logs = fetch_reviews_intercept(iid, sid, product_url=url_comp if url_comp else "")

        # Sempre mostrar o log de debug
        with st.expander("🔍 Log de execução", expanded=not reviews):
            for line in debug_logs:
                st.markdown(line)

        if reviews:
            st.success(f"✅ {len(reviews)} avaliações encontradas")
            for i, r in enumerate(reviews, 1):
                st.write(f"{i}. {r}")
            insight = analyze_reviews_with_gemini(reviews, segmento)
            st.success("🚀 Argumentos de Venda:")
            st.write(insight)
        else:
            st.warning(
                "⚠️ Sem avaliações encontradas. Veja o log acima para detalhes. "
                "**Dica:** Use o Radar de Concorrentes → 'Analisar padrões com IA' para insights equivalentes."
            )

with tab3: 
    if not st.session_state.shop_data or not st.session_state.shop_produtos: 
        st.info("👈 Carregue uma loja primeiro na seção 'Auditoria de Loja' acima.") 
    else: 
        shop_name = st.session_state.shop_data.get("name", "Loja") 
        produtos = st.session_state.shop_produtos 
 
        if not st.session_state.chatbot_active: 
            st.markdown(f"### 🤖 Chatbot da loja **{shop_name}**") 
            st.markdown(f"O chatbot vai conhecer todos os **{len(produtos)} produtos** da loja e responder clientes em tempo real.") 
            col_a, col_b = st.columns(2) 
            with col_a: 
                st.success(f"✅ {len(produtos)} produtos carregados") 
            with col_b: 
                st.info("💬 Multi-turn · Recomendações · Dúvidas") 
 
            if st.button("🚀 Ativar Chatbot", type="primary"): 
                st.session_state.chatbot_active = True 
                st.session_state.chat_history = [] 
                st.rerun() 

            if st.button("📋 Gerar FAQ para Seller Centre", type="secondary"): 
                with st.spinner("Gerando configuração do Assistente de IA..."): 
                    faq_prompt = f"""Você é especialista em e-commerce Shopee Brasil. 
 
 Com base neste catálogo da loja '{shop_name}': 
 {chr(10).join(f"- {p['name']} | R$ {p['price']:.2f}" for p in produtos)} 
 
 Gere EXATAMENTE 9 perguntas divididas em 3 categorias, com 3 perguntas cada. 
 Categorias: "📦 Produtos e Modelos", "🚚 Entrega e Frete", "🔄 Trocas e Pagamento" 
 Regras OBRIGATÓRIAS: 
 - Cada pergunta: máximo 80 caracteres 
 - Cada resposta: máximo 500 caracteres 
 - Respostas curtas, simpáticas, em português brasileiro 
 - As perguntas devem ser GENÉRICAS, sem citar nomes específicos de produtos 
 - Fale sobre a loja no geral, não sobre um produto específico 
 - Ex correto: "Vocês têm mochilas coloridas?" 
 - Ex errado: "A Mochila Infantil Princesa Rosa tem bolsos?" 
 
 Formato EXATO: 
 
 CATEGORIA 1: 📦 Produtos e Modelos 
 PERGUNTA 1: [pergunta] 
 RESPOSTA 1: [resposta] 
 PERGUNTA 2: [pergunta] 
 RESPOSTA 2: [resposta] 
 PERGUNTA 3: [pergunta] 
 RESPOSTA 3: [resposta] 
 
 CATEGORIA 2: 🚚 Entrega e Frete 
 PERGUNTA 4: [pergunta] 
 RESPOSTA 4: [resposta] 
 PERGUNTA 5: [pergunta] 
 RESPOSTA 5: [resposta] 
 PERGUNTA 6: [pergunta] 
 RESPOSTA 6: [resposta] 
 
 CATEGORIA 3: 🔄 Trocas e Pagamento 
 PERGUNTA 7: [pergunta] 
 RESPOSTA 7: [resposta] 
 PERGUNTA 8: [pergunta] 
 RESPOSTA 8: [resposta] 
 PERGUNTA 9: [pergunta] 
 RESPOSTA 9: [resposta]""" 
 
                    faq_result = "" 
                    for m in MODELOS_TEXTO: 
                        try: 
                            config = {"thinking_config": {"thinking_budget": 0}} if "3.1" in m or "2.5" in m else {} 
                            response = client.models.generate_content( 
                                model=m, 
                                contents=[faq_prompt], 
                                config=config if config else None 
                            ) 
                            faq_result = response.text.strip() 
                            break 
                        except Exception as e: 
                            time.sleep(2) 
                            continue 
 
                    if faq_result: 
                        # Validar e avisar sobre limites de caracteres 
                        avisos = [] 
                        for linha in faq_result.split("\n"): 
                            if linha.startswith("PERGUNTA") and ":" in linha: 
                                texto = linha.split(":", 1)[1].strip() 
                                if len(texto) > 80: 
                                    avisos.append(f"⚠️ Pergunta muito longa ({len(texto)} chars): '{texto[:50]}...'") 
                            elif linha.startswith("RESPOSTA") and ":" in linha: 
                                texto = linha.split(":", 1)[1].strip() 
                                if len(texto) > 500: 
                                    avisos.append(f"⚠️ Resposta muito longa ({len(texto)} chars): '{texto[:50]}...'") 
 
                        st.markdown("---") 
                        st.markdown("### 📋 FAQ para o Assistente de IA do Seller Centre") 
 
                        if avisos: 
                            with st.expander("⚠️ Avisos de limite de caracteres"): 
                                for a in avisos: 
                                    st.warning(a) 
 
                        st.info("""📌 **Como usar no Seller Centre:** 
 1. Acesse seller.shopee.com.br → Atendimento ao Cliente → Assistente de IA 
 2. Clique em "Adicionar Categoria" e crie as 3 categorias acima 
 3. Dentro de cada categoria, adicione as 3 perguntas correspondentes 
 4. Cole a pergunta e a resposta nos campos indicados 
 5. Salve e ative o Assistente""") 

                        st.success("💡 **Dica:** O Chat AI Assistant nativo da Shopee aprende automaticamente com as descrições dos seus produtos. Use a função 'Otimização Completa' para melhorar essas descrições e o robô da Shopee ficará mais inteligente automaticamente.")

                        # Exibir com botão de copiar por bloco 
                        categorias = faq_result.split("\n\n") 
                        for bloco in categorias: 
                            if bloco.strip(): 
                                st.code(bloco.strip(), language=None) 
 
                        faq_result = faq_result.replace("**", "")
                        st.download_button( 
                            "⬇️ Baixar FAQ completo (.txt)", 
                            data=faq_result, 
                            file_name=f"faq_{shop_name}.txt", 
                            mime="text/plain" 
                        ) 
                    else: 
                        st.error("❌ Não foi possível gerar o FAQ. Tente novamente.") 
        else: 
            shop_name = st.session_state.shop_data.get("name", "Loja") 
            catalog_context = build_catalog_context(produtos, shop_name) 
 
            col_titulo, col_reset = st.columns([4, 1]) 
            with col_titulo: 
                st.markdown(f"### 💬 Chatbot — {shop_name}") 
            with col_reset: 
                if st.button("🔄 Reiniciar"): 
                    st.session_state.chat_history = [] 
                    st.rerun() 

            with st.expander("📋 Construtor de FAQ Personalizado"): 
                st.markdown("Use o chat para montar seu FAQ. Quando terminar, exporte abaixo.") 
                
                if 'faq_personalizado' not in st.session_state: 
                    st.session_state.faq_personalizado = [] 
 
                # Mostrar FAQ construído até agora 
                if st.session_state.faq_personalizado: 
                    st.markdown("**FAQ atual:**") 
                    for i, item in enumerate(st.session_state.faq_personalizado): 
                        col_faq, col_del = st.columns([10, 1]) 
                        with col_faq: 
                            st.markdown(f"**P{i+1}:** {item['pergunta']}") 
                            st.markdown(f"**R{i+1}:** {item['resposta']}") 
                            st.divider() 
                        with col_del: 
                            if st.button("🗑️", key=f"del_faq_{i}"): 
                                st.session_state.faq_personalizado.pop(i) 
                                st.rerun() 
 
                # Adicionar novo par manualmente 
                st.markdown("**Adicionar pergunta:**") 
                col_p, col_r = st.columns(2) 
                with col_p: 
                    nova_pergunta = st.text_input( 
                        "Pergunta", 
                        placeholder="Ex: Vocês têm mochila azul?", 
                        key="nova_pergunta", 
                        max_chars=80 
                    ) 
                with col_r: 
                    nova_resposta = st.text_area( 
                        "Resposta", 
                        placeholder="Ex: Sim! Temos modelos em azul disponíveis.", 
                        key="nova_resposta", 
                        max_chars=500, 
                        height=80 
                    ) 
 
                col_btn1, col_btn2 = st.columns(2) 
                with col_btn1: 
                    if st.button("➕ Adicionar par") and nova_pergunta and nova_resposta: 
                        st.session_state.faq_personalizado.append({ 
                            "pergunta": nova_pergunta, 
                            "resposta": nova_resposta 
                        }) 
                        st.rerun() 
                with col_btn2: 
                    if st.button("🤖 Gerar sugestão com IA") and nova_pergunta: 
                        with st.spinner("Gerando resposta sugerida..."): 
                            sugestao = chat_with_gemini( 
                                f"Gere uma resposta curta e simpática (máx 500 chars) para esta pergunta de cliente: '{nova_pergunta}'. Baseie-se no catálogo da loja.", 
                                [], 
                                catalog_context 
                            ) 
                        st.session_state.faq_personalizado.append({ 
                            "pergunta": nova_pergunta, 
                            "resposta": sugestao[:500] 
                        }) 
                        st.rerun() 
 
                # Exportar 
                if st.session_state.faq_personalizado: 
                    n = len(st.session_state.faq_personalizado) 
                    faq_txt = "\n\n".join([ 
                        f"PERGUNTA {i+1}: {item['pergunta']}\nRESPOSTA {i+1}: {item['resposta']}" 
                        for i, item in enumerate(st.session_state.faq_personalizado) 
                    ]) 
                    faq_txt = faq_txt.replace("**", "")
                    st.download_button( 
                        f"⬇️ Exportar FAQ personalizado ({n} pares)", 
                        data=faq_txt, 
                        file_name=f"faq_personalizado_{shop_name}.txt", 
                        mime="text/plain" 
                    ) 
                    if st.button("🗑️ Limpar FAQ personalizado"): 
                        st.session_state.faq_personalizado = [] 
                        st.rerun() 
 
            # Exibir histórico 
            for turn in st.session_state.chat_history: 
                with st.chat_message("user"): 
                    st.write(turn["user"]) 
                with st.chat_message("assistant"): 
                    st.write(turn["assistant"]) 
 
            # Sugestões de perguntas iniciais 
            if not st.session_state.chat_history: 
                st.markdown("**💡 Sugestões para começar:**") 
                sugestoes = [ 
                    "Quais mochilas vocês têm disponíveis?", 
                    "Tem mochila rosa ou lilás?", 
                    "Qual mochila é ideal para escola?", 
                    "Qual o produto mais barato?", 
                ] 
                cols_s = st.columns(2) 
                for idx, sug in enumerate(sugestoes): 
                    with cols_s[idx % 2]: 
                        if st.button(sug, key=f"sug_{idx}"): 
                            with st.spinner("Respondendo..."): 
                                resposta = chat_with_gemini(sug, st.session_state.chat_history, catalog_context) 
                            st.session_state.chat_history.append({"user": sug, "assistant": resposta}) 
                            st.rerun() 
 
            # Input do usuário 
            user_input = st.chat_input("Digite sua pergunta sobre os produtos...") 
            if user_input: 
                with st.spinner("Respondendo..."): 
                    resposta = chat_with_gemini(user_input, st.session_state.chat_history, catalog_context) 
                st.session_state.chat_history.append({"user": user_input, "assistant": resposta}) 
                st.rerun() 

video_file = st.file_uploader("Upload do vídeo do produto (MP4)", type=["mp4"])

if video_file:
    if st.button("Analisar Retenção do Vídeo"):
        with st.spinner("IA analisando hook e iluminação...\n(Esta funcionalidade ainda está em desenvolvimento e pode não fornecer insights completos.)"):
            st.warning("⚠️ Insight de IA: O gancho inicial (hook) está fraco. Mostre a mochila aberta nos primeiros 3 segundos.")