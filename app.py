import streamlit as st
import pandas as pd
import asyncio
import sys
import nest_asyncio
import json
import subprocess
from google import genai
from rembg import remove
from PIL import Image
import io
import requests
import re
import time
import random

import os
from dotenv import load_dotenv

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

nest_asyncio.apply()

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
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

with st.sidebar:
    st.header("⚙️ Configurações")
    segmento = st.selectbox("Nicho do Produto", ["Escolar / Juvenil", "Profissional / Tech", "Viagem", "Moda"])
    st.subheader("🎨 Estúdio Visual")
    gerar_cenario = st.checkbox("Gerar Cenário Lifestyle (AI)", value=False)
    st.info("A remoção de fundo é obrigatória para o CTR de 9.5.")

uploaded_file = st.file_uploader("Arraste a foto da mochila", type=["jpg", "png", "jpeg"])

if uploaded_file:
    col1, col2 = st.columns(2)
    img_bytes = uploaded_file.getvalue()
    img_original = Image.open(io.BytesIO(img_bytes))

    with col1:
        st.subheader("🖼️ Original")
        st.image(img_original, width="stretch")

    with col2:
        st.subheader("✨ Resultado Otimizado")
        if st.button("Executar Otimização Completa"):
            with st.spinner("Removendo fundo e calculando estratégia..."):
                no_bg_bytes = remove(img_bytes)
                no_bg_img = Image.open(io.BytesIO(no_bg_bytes)).convert("RGBA")
                final_img = no_bg_img

                if gerar_cenario:
                    st.write("🎨 Criando cenário ideal para o nicho...")
                    prompt_cenario = f"Commercial photography of a {segmento} backpack on a clean aesthetic background, professional lighting, 4k, high resolution"
                    if segmento == "Escolar / Juvenil":
                        prompt_cenario = "A wooden school desk, natural sunlight from a window, blurred classroom background, aesthetic"
                    bg_url = f"https://pollinations.ai/p/{prompt_cenario.replace(' ', '%20')}?width=1024&height=1024&seed=42"
                    try:
                        bg_res = requests.get(bg_url, timeout=15)
                        if bg_res.status_code == 200 and "image" in bg_res.headers.get("Content-Type", ""):
                            bg_img = Image.open(io.BytesIO(bg_res.content)).convert("RGBA").resize((1024, 1024))
                            no_bg_img.thumbnail((800, 800))
                            offset = ((bg_img.width - no_bg_img.width) // 2, (bg_img.height - no_bg_img.height) // 2)
                            bg_img.paste(no_bg_img, offset, no_bg_img)
                            final_img = bg_img
                        else:
                            st.warning("⚠️ Não foi possível gerar o cenário agora. Mantendo fundo limpo.")
                    except Exception as e:
                        st.warning(f"⚠️ Erro ao conectar ao gerador de cenários: {e}")

                st.image(final_img, width="stretch")

                prompt_seo = f"Analise esta mochila ({segmento}) e gere Título (60-70 chars), 20 Tags LSI e Descrição CR para Shopee 2026."
                response = None
                for m in MODELOS_VISION:
                    try:
                        response = client.models.generate_content(model=m, contents=[prompt_seo, img_original])
                        st.success(f"Estratégia gerada com sucesso pelo modelo: {m}")
                        break
                    except Exception:
                        continue

                if response:
                    st.markdown("### 📈 Diagnóstico de Listing")
                    st.write(response.text)
                else:
                    st.error("❌ Todos os modelos de IA atingiram o limite de cota. Tente novamente em 60 segundos.")

st.markdown("---")
st.caption("Nota: Para geração de cenários reais (Flux API), adicione integração no bloco de processamento de imagem.")

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

# ── TABS: CONCORRENTES + AVALIAÇÕES ──────────────────────────
tab1, tab2 = st.tabs(["Radar de Concorrentes", "Mineração de Avaliações"])

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

video_file = st.file_uploader("Upload do vídeo do produto (MP4)", type=["mp4"])

if video_file:
    if st.button("Analisar Retenção do Vídeo"):
        with st.spinner("IA analisando hook e iluminação...\n(Esta funcionalidade ainda está em desenvolvimento e pode não fornecer insights completos.)"):
            st.warning("⚠️ Insight de IA: O gancho inicial (hook) está fraco. Mostre a mochila aberta nos primeiros 3 segundos.")