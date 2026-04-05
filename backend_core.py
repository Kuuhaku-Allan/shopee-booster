"""
backend_core.py — Núcleo do Shopee Booster
==========================================
⚠️  ARQUIVO DE BACKEND — NÃO EDITE PARA ALTERAÇÕES DE DESIGN/UI ⚠️

Contém TODA a lógica de:
  - Playwright / interceptação de APIs da Shopee e Mercado Livre
  - Integração com Google Gemini (geração de texto e visão)
  - Integração com Hugging Face / Together AI / Pollinations (geração de imagem)
  - Processamento de imagens com rembg e Pillow
  - Funções utilitárias de scraping

Para alterar o visual da aplicação, edite:
  - ui_theme.py  (CSS, paleta de cores, dark/light mode)
  - app.py       (layout, partições, componentes Streamlit)
"""

import streamlit as st
import pandas as pd
import subprocess
import json
import sys
import os
import re
import time
import random
import requests
import io
import unicodedata
from functools import lru_cache
from urllib.parse import quote, unquote
from PIL import Image, ImageEnhance, ImageFilter
from google import genai
from dotenv import load_dotenv

# ── Configuração de ambiente ──────────────────────────────────────
# 🔥 MEDIDA DE SEGURANÇA: Forçar apenas CPU para evitar travamentos silenciosos da IA
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["ORT_LOGGING_LEVEL"] = "3"
os.environ["ONNXRUNTIME_PROVIDERS"] = "CPUExecutionProvider"

if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Força o rembg a procurar o modelo na pasta que vamos embutir
os.environ["U2NET_HOME"] = os.path.join(BASE_DIR, "models")
os.environ["REM_BG_CHECK_MODEL"] = "0"  # Desativa check online que pode travar

try:
    import onnxruntime as ort
    os.environ["ORT_LOGGING_LEVEL"] = "3"
    ort.set_default_logger_severity(3)
except Exception:
    pass

# ── Configuração de configurações persistentes ───────────────────
if getattr(sys, "frozen", False):
    CONFIG_DIR = os.path.dirname(sys.executable)
else:
    CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_ENV = os.path.join(CONFIG_DIR, ".shopee_config")
load_dotenv()        # Carrega .env do diretório do projeto
load_dotenv(CONFIG_ENV)  # Sobrepõe com .shopee_config (prioridade maior)

API_KEY = os.getenv("GOOGLE_API_KEY")

def get_client():
    """
    Retorna o cliente Gemini cacheado na sessão do Streamlit.
    
    Por quê session_state e não um global?
    - O httpx.Client interno do genai.Client é fechado quando o objeto é GC'd.
    - Criar um novo Client a cada chamada causa 'client has been closed'.
    - Usar session_state garante que o mesmo objeto sobreviva entre reruns
      e seja invalidado automaticamente quando a API key mudar.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY não configurada. Insira sua chave no painel lateral.")
    # Invalida o cache se a chave mudou (ex: usuário reconfigurou)
    if (st.session_state.get("_gemini_api_key") != api_key
            or "_gemini_client" not in st.session_state):
        st.session_state["_gemini_client"] = genai.Client(api_key=api_key)
        st.session_state["_gemini_api_key"] = api_key
    return st.session_state["_gemini_client"]

# Alias para compatibilidade — não usar diretamente, sempre chamar get_client()
client = get_client

# Modelos para tarefas COM imagem (multimodal) — cota limitada, usar com parcimônia
MODELOS_VISION = ["gemini-2.5-flash"]

# Modelos para tarefas só de TEXTO — priorizando os de maior cota diária
MODELOS_TEXTO = [
    "gemini-3.1-flash-lite-preview",  # 500 RPD — principal
    "gemini-2.5-flash-lite",          # 20 RPD — fallback
    "gemini-2.5-flash",               # 20 RPD — último recurso
]



# ══════════════════════════════════════════════════════════════════
# UTILITÁRIOS
# ══════════════════════════════════════════════════════════════════

def salvar_ou_baixar(label: str, data: bytes | str, file_name: str, mime: str, key: str):
    """
    No .exe (pywebview): salva direto em ~/Downloads e avisa o usuário.
    No navegador normal: usa st.download_button normalmente.
    """
    if getattr(sys, "frozen", False):
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        caminho = os.path.join(downloads, file_name)

        if st.button(f"⬇️ {label}", key=key):
            try:
                modo = "wb" if isinstance(data, bytes) else "w"
                enc = None if isinstance(data, bytes) else "utf-8"
                with open(caminho, modo, encoding=enc) as f:
                    f.write(data)
                st.success(f"✅ Salvo em: `{caminho}`")
                import subprocess as _sp
                _sp.Popen(["explorer", "/select,", caminho])
            except Exception as e:
                st.error(f"Erro ao salvar: {e}")
    else:
        st.download_button(label=f"⬇️ {label}", data=data,
                           file_name=file_name, mime=mime, key=key)


def resolve_shopee_url(url):
    match = re.search(r"i\.([0-9]+)\.([0-9]+)", url)
    if match:
        return {"type": "product", "shopid": match.group(1), "itemid": match.group(2), "full_url": url}
    if "shopee.com.br/" in url:
        username = url.split("shopee.com.br/")[1].split("?")[0]
        return {"type": "shop", "username": username}
    return None


# ══════════════════════════════════════════════════════════════════
# PLAYWRIGHT — INTERCEPTAÇÃO DE APIS
# ══════════════════════════════════════════════════════════════════

def playwright_intercept(script: str) -> dict | list | None:
    import tempfile
    try:
        if getattr(sys, "frozen", False):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(script)
                script_path = f.name
            try:
                result = subprocess.run(
                    [sys.executable, "runscript", script_path],
                    capture_output=True, text=True, timeout=150
                )
            finally:
                try:
                    os.unlink(script_path)
                except Exception:
                    pass
        else:
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

                    price_raw = 0
                    for price_key in ["item_card_display_price", "price_obj", "price_info"]:
                        po = card.get(price_key, {{}})
                        if isinstance(po, dict):
                            price_raw = po.get("price", po.get("current_price", po.get("min_price", 0)))
                            if price_raw: break
                    if not price_raw:
                        price_raw = card.get("price", card.get("price_min", 0))

                    sold = 0
                    for sold_key in ["item_card_display_sold_count", "sold_obj"]:
                        so = card.get(sold_key, {{}})
                        if isinstance(so, dict):
                            sold = so.get("historical_sold_count", so.get("sold", 0))
                            if sold: break
                    if not sold:
                        sold = card.get("historical_sold", card.get("sold", 0))

                    asset = card.get("item_card_displayed_asset") or {{}}
                    name = asset.get("name") or ""

                    img = ""
                    for img_key in ["image", "cover", "thumbnail"]:
                        val = asset.get(img_key)
                        if val and isinstance(val, str):
                            img = val
                            break
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


def fetch_reviews_intercept(item_id: str, shop_id: str, product_url: str = "", product_name_override: str = "") -> tuple[list, list]:
    logs = []

    product_name = ""

    if product_name_override:
        product_name = product_name_override
        logs.append(f"📌 Nome direto: **{product_name}**")
    elif product_url:
        slug_match = re.search(r"shopee\.com\.br/([^?#/]+)-i\.", product_url)
        if slug_match:
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

    kw = "".join(
        c for c in unicodedata.normalize("NFD", product_name)
        if unicodedata.category(c) != "Mn"
    )
    kw_short = " ".join(kw.split()[:3])
    logs.append(f"🔍 Buscando no ML: **{kw_short}**")

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

        all_mlb = await page.query_selector_all("a[href*='/MLB']")
        print(f"Links MLB encontrados: {{len(all_mlb)}}", file=sys.stderr)
        if all_mlb:
            first_href = await all_mlb[0].get_attribute("href")
            print(f"Primeiro link: {{first_href[:100]}}", file=sys.stderr)

        product_link = None
        try:
            hrefs = await page.evaluate('''
                () => Array.from(document.querySelectorAll('a'))
                    .map(a => a.href)
                    .filter(h =>
                        h.includes('mercadolivre.com.br/') &&
                        h.includes('/MLB') &&
                        !h.includes('/up/') &&
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

        if not product_link:
            try:
                hrefs = await page.evaluate('''
                    () => {{
                        const cards = document.querySelectorAll(
                            '.ui-search-item__image-link, .poly-card__portada, [data-item-id]'
                        );
                        return Array.from(cards)
                            .map(el => el.closest('a') ? el.closest('a').href : el.href)
                            .filter(h => h && h.includes('mercadolivre.com.br/') && h.includes('/MLB') && !h.includes('/up/'))
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

        clean_url = product_link.split("?")[0]
        print(f"Abrindo produto: {{clean_url}}", file=sys.stderr)
        try:
            await page.goto(clean_url + "#reviews", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print("Goto product erro: " + str(e), file=sys.stderr)
        await asyncio.sleep(3)

        for _ in range(10):
            await page.mouse.wheel(0, 600)
            await asyncio.sleep(0.5)
        await asyncio.sleep(2)

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
                        if len(txt) > 15 and txt not in reviews and not txt.startswith("Avalia"):
                            reviews.append(txt)
                    if reviews:
                        break
            except Exception:
                continue

        if not reviews:
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


# ══════════════════════════════════════════════════════════════════
# GERAÇÃO DE CONTEÚDO COM GEMINI
# ══════════════════════════════════════════════════════════════════

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
            response = get_client().models.generate_content(
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
    contents = [catalog_context + "\n\n---\nInício da conversa com o cliente:\n"]
    for turn in history:
        contents.append(f"Cliente: {turn['user']}")
        contents.append(f"Assistente: {turn['assistant']}")
    contents.append(f"Cliente: {user_message}\nAssistente:")

    prompt = "\n".join(contents)

    ultimo_erro = ""
    _client = get_client()
    for m in MODELOS_TEXTO:
        try:
            config = {"thinking_config": {"thinking_budget": 0}} if "preview" in m or "flash" in m else {}
            response = _client.models.generate_content(
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
            response = get_client().models.generate_content(
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


# ══════════════════════════════════════════════════════════════════
# PROCESSAMENTO DE IMAGENS
# ══════════════════════════════════════════════════════════════════

def generate_ai_scenario(prompt_text: str, segmento: str = "") -> Image.Image | None:
    """Gera cenário via Hugging Face (FLUX.1-dev), Together AI ou Pollinations com fallback gradiente."""

    # 1. TENTATIVA: Hugging Face (FLUX.1-dev) - QUALIDADE SUPERIOR
    hf_token = os.getenv("HF_TOKEN", "")
    if hf_token:
        try:
            from huggingface_hub import InferenceClient
            client_hf = InferenceClient(api_key=hf_token)

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
                    model="black-forest-labs/FLUX.1-dev",
                )
                return img.convert("RGBA")
            except Exception:
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
        "Escolar / Juvenil": ((255, 240, 248), (220, 210, 245)),
        "Profissional / Tech": ((240, 245, 255), (210, 220, 240)),
        "Viagem": ((255, 248, 235), (235, 220, 200)),
        "Moda": ((255, 252, 255), (240, 230, 245)),
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
