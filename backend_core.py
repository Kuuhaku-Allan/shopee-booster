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
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=150
                )
            finally:
                try:
                    os.unlink(script_path)
                except Exception:
                    pass
        else:
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=150
            )

        # Proteção contra None (pode acontecer com erros de encoding)
        stderr_text = (result.stderr or "").strip()
        stdout_text = (result.stdout or "").strip()

        if stderr_text:
            st.caption(f"🔍 Debug stderr: {stderr_text[:2000]}")
        if result.returncode != 0:
            st.caption(f"🔍 Debug returncode: {result.returncode}")
            st.caption(f"🔍 Debug stdout: {stdout_text[:500]}")
        if result.returncode == 0 and stdout_text:
            return json.loads(stdout_text)
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
    """
    Carrega produtos da loja via Playwright esperando por elementos DOM.
    
    NOTA: A Shopee mudou a arquitetura em 2026 e não usa mais endpoints
    rcmd_items ou shop_page. Agora os produtos são carregados dinamicamente
    via Module Federation (Webpack 5) + React.
    
    Esta versão espera os produtos aparecerem no DOM após o JavaScript carregar.
    """
    script = f"""
import asyncio, json, sys, re
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
        
        try:
            print("[LOADER] Navegando para loja...", file=sys.stderr)
            await page.goto(
                "https://shopee.com.br/{username}",
                wait_until="domcontentloaded",
                timeout=50000
            )
            
            print("[LOADER] Aguardando produtos aparecerem no DOM...", file=sys.stderr)
            
            # Espera por links de produtos (seletor comum da Shopee)
            # Tenta múltiplos seletores possíveis
            selectors = [
                'a[href*="/product/"]',  # Links de produtos
                '[data-sqe="link"]',  # Atributo data comum
                '.shopee-search-item-result__item a',  # Grid de produtos
                '.shop-search-result-view__item a',  # Outro formato
            ]
            
            product_elements = None
            for selector in selectors:
                try:
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
                await browser.close()
                print(json.dumps([]))
                return
            
            # Extrai dados dos elementos
            seen_ids = set()
            for elem in product_elements[:30]:  # Limita a 30 produtos
                try:
                    # Extrai href
                    href = await elem.get_attribute('href')
                    if not href or '/product/' not in href:
                        continue
                    
                    # Extrai itemid e shopid do href
                    # Formato: /product/123456/789012 ou /Nome-do-Produto-i.123456.789012
                    match = re.search(r'[.-]i\\.?(\\d+)\\.(\\d+)', href)
                    if not match:
                        match = re.search(r'/product/(\\d+)/(\\d+)', href)
                    
                    if not match:
                        continue
                    
                    itemid = int(match.group(1))
                    product_shopid = int(match.group(2))
                    
                    if itemid in seen_ids:
                        continue
                    seen_ids.add(itemid)
                    
                    # Extrai nome (title ou texto)
                    name = await elem.get_attribute('title')
                    if not name:
                        name = await elem.inner_text()
                    name = (name or "").strip()
                    
                    # Busca imagem no elemento ou pai
                    img = ""
                    try:
                        img_elem = await elem.query_selector('img')
                        if img_elem:
                            img = await img_elem.get_attribute('src') or await img_elem.get_attribute('data-src') or ""
                    except:
                        pass
                    
                    # Busca preço no elemento ou pai
                    price = 0
                    try:
                        # Tenta encontrar elemento de preço próximo
                        parent = await elem.evaluate_handle('el => el.closest("div")')
                        price_text = await parent.inner_text()
                        # Procura por padrão R$ 123,45 ou 123.45
                        price_match = re.search(r'R\\$\\s*([\\d.,]+)', price_text)
                        if price_match:
                            price_str = price_match.group(1).replace('.', '').replace(',', '.')
                            price = float(price_str)
                    except:
                        pass
                    
                    print(f"[LOADER] Produto: itemid={{itemid}}, name={{name[:30]}}", file=sys.stderr)
                    
                    products.append({{
                        "itemid": itemid,
                        "shopid": product_shopid,
                        "name": name or f"Produto {{itemid}}",
                        "price": price,
                        "sold": 0,  # Não disponível facilmente no DOM
                        "image": img,
                    }})
                    
                except Exception as e:
                    print(f"[LOADER] Erro ao processar elemento: {{e}}", file=sys.stderr)
                    continue
            
            print(f"[LOADER] Total de produtos extraídos: {{len(products)}}", file=sys.stderr)
            
        except Exception as e:
            print(f"[LOADER] Erro geral: {{e}}", file=sys.stderr)
        
        await browser.close()
        print(json.dumps(products[:30]))

asyncio.run(run())
"""
    result = playwright_intercept(script)
    return result if isinstance(result, list) else []


def fetch_competitors_intercept(keyword: str) -> list:
    kw_encoded = keyword.replace(" ", "+")
    script = f"""
import asyncio, json, sys
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

def parse_items(data):
    items = data.get("items") or data.get("data", {{}}).get("items") or []
    competitors = []
    seen_ids = set()

    for item in items[:20]:
        b = item.get("item_basic", item) or {{}}
        item_id = b.get("itemid") or item.get("itemid")
        if not item_id or item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        rating = b.get("item_rating") or {{}}
        price_raw = b.get("price_min") or b.get("price") or 0
        competitors.append({{
            "item_id":    item_id,
            "shop_id":    b.get("shopid") or item.get("shopid"),
            "nome":       (b.get("name") or "")[:65],
            "preco":      price_raw / 100000 if price_raw > 1000 else price_raw,
            "avaliações": b.get("cmt_count", 0),
            "curtidas":   b.get("liked_count", 0),
            "estrelas":   round(rating.get("rating_star", 0), 1),
        }})

    return competitors[:10]

def is_search_response(response):
    if response.request.method == "OPTIONS":
        return False
    url = response.url
    return "api/v4/search/search_items" in url or "v4/search/search_items" in url

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
        search_url = "https://shopee.com.br/search?keyword={kw_encoded}&sortBy=sales"

        try:
            async with page.expect_response(is_search_response, timeout=30000) as response_info:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            response = await response_info.value
            data = await response.json()
            competitors = parse_items(data)
            print(f"search_items url: {{response.url}}", file=sys.stderr)
            print(f"competitors parsed: {{len(competitors)}}", file=sys.stderr)
        except PlaywrightTimeoutError as e:
            print(f"search_items timeout: {{e}}", file=sys.stderr)
        except Exception as e:
            print(f"search_items parse err: {{e}}", file=sys.stderr)

        if not competitors:
            try:
                await page.goto(search_url, wait_until="load", timeout=45000)
            except Exception as e:
                print(f"fallback goto err: {{e}}", file=sys.stderr)
            await asyncio.sleep(5)

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

# ══════════════════════════════════════════════════════════════
# CONTEXTO ENRIQUECIDO (Auditoria → Chatbot)
# ══════════════════════════════════════════════════════════════

def build_full_chat_context(
    shop_data: dict | None,
    produtos: list | None,
    selected_product: dict | None,
    df_competitors,          # pd.DataFrame | None
    optimization_reviews: list | None,
    shop_name: str = "Loja",
) -> str:
    """
    Monta o contexto completo para o chatbot, aproveitando tudo que
    foi coletado na Auditoria. Nenhum campo é obrigatório.
    """
    linhas = [
        f"Você é o assistente inteligente da loja '{shop_name}' na Shopee Brasil.",
        "Você combina três papéis: atendimento ao cliente, especialista em e-commerce e estúdio de imagens.",
        "Responda SEMPRE em português brasileiro, de forma simpática e objetiva.",
        "Use emojis com moderação. Nunca invente informações que não estão nos dados abaixo.",
        "",
    ]

    # ── Catálogo de produtos ────────────────────────────────
    if produtos:
        linhas.append(f"=== CATÁLOGO DA LOJA ({len(produtos)} produtos) ===")
        for i, p in enumerate(produtos, 1):
            linhas.append(f"{i}. {p['name']} — R$ {p['price']:.2f} (ID: {p['itemid']})")
        linhas.append("")

    # ── Produto atualmente selecionado para análise ─────────
    if selected_product:
        linhas.append("=== PRODUTO EM FOCO (selecionado na Auditoria) ===")
        linhas.append(f"Nome:    {selected_product.get('name', '')}")
        linhas.append(f"Preço:   R$ {selected_product.get('price', 0):.2f}")
        linhas.append(f"Item ID: {selected_product.get('itemid', '')}")
        linhas.append(f"Shop ID: {selected_product.get('shopid', '')}")
        img = selected_product.get("image", "")
        if img:
            img_url = img if img.startswith("http") else f"https://down-br.img.susercontent.com/file/{img}"
            linhas.append(f"Imagem:  {img_url}")
        linhas.append("")

    # ── Dados de concorrentes ───────────────────────────────
    if df_competitors is not None and not df_competitors.empty:
        linhas.append("=== TOP CONCORRENTES COLETADOS ===")
        for _, r in df_competitors.iterrows():
            linhas.append(
                f"• {r['nome']} | R$ {r['preco']:.2f} | "
                f"{r.get('avaliações', 0)} avaliações | ⭐{r.get('estrelas', 0)}"
            )
        pm = df_competitors["preco"].mean()
        linhas.append(f"Preço médio de mercado: R$ {pm:.2f}")
        linhas.append("")

    # ── Avaliações do mercado coletadas ────────────────────
    if optimization_reviews:
        linhas.append("=== AVALIAÇÕES/RECLAMAÇÕES DO MERCADO ===")
        for rv in optimization_reviews[:6]:
            linhas.append(f"• {rv}")
        linhas.append("")

    linhas.append("=== FIM DO CONTEXTO ===")
    return "\n".join(linhas)


# ══════════════════════════════════════════════════════════════
# DETECÇÃO DE INTENÇÃO
# ══════════════════════════════════════════════════════════════

_INTENT_PROMPT = """Você é um classificador de intenção para um assistente de e-commerce.
Analise a mensagem do usuário e classifique em UMA das categorias:

remove_bg       → quer remover o fundo da imagem
generate_scene  → quer gerar cenário / fundo para o produto
upscale         → quer melhorar qualidade / aumentar resolução
analyze_image   → quer feedback, análise, avaliação ou dicas sobre a imagem
optimize_listing → quer otimizar título, descrição, tags ou preço do produto
analyze_video   → quer analisar vídeo do produto
general         → pergunta geral sobre produtos, loja, entrega, etc.

Responda APENAS com a palavra-chave da categoria, sem pontuação.

Mensagem: {msg}
Tem anexo de imagem/vídeo: {has_media}
"""

def detect_chat_intents(user_message: str, has_media: bool) -> list:
    """
    Detecta UMA OU MAIS intenções na mensagem.
    Retorna lista ordenada pelo encadeamento natural de execução.
    Exemplos:
      "remove o fundo e gera cenário"   → ["remove_bg", "generate_scene"]
      "melhora a qualidade e analisa"   → ["upscale", "analyze_image"]
      "bota um badge à prova d'água"    → ["creative_edit"]
    """
    msg = user_message.lower()
    # NORMALIZAÇÃO: Converte "amarela" -> "amarelo", "vermelhas" -> "vermelho", etc.
    msg_normalized = normalize_message_colors(msg)
    
    intents = []

    # ── Regras de Exclusividade (Filtros Prioritários) ────────
    # Se a frase for um pedido explícito de recorte, ignora outros motores para evitar poluição
    BG_ONLY_PATTERNS = [
        "remova o fundo desta imagem", "remove o fundo desta imagem",
        "deixe esta imagem com fundo transparente", "fundo transparente",
        "só o recorte", "apenas o recorte", "recortar produto"
    ]
    if any(p in msg_normalized for p in BG_ONLY_PATTERNS):
        return ["remove_bg"]

    # ── Detecção individual ───────────────────────────────────
    is_remove_bg = any(w in msg_normalized for w in [
        "remov", "sem fundo", "fundo branco", "transparente", "recort"
    ])
    is_scene = any(w in msg_normalized for w in [
        "cenário", "cena", "fundo bonito", "fundo ia", "gerar fundo",
        "estúdio", "packshot", "ambiente", "paisagem", "fundo clean",
        "fundo limpo"
    ])
    is_upscale = any(w in msg_normalized for w in [
        "qualidade", "upscale", "aumentar", "resolução", "nítid", "melhorar imagem"
    ])
    is_optimize = any(w in msg_normalized for w in [
        "otimiz", "título", "descrição", "tag", "listing", "seo", "keyword"
    ])
    is_video = any(w in msg_normalized for w in [
        "vídeo", "video", "retenção", "hook", "gancho", "analisar vídeo",
        "analise esse video", "analise o video", "ver o video", "vê o vídeo",
        "mp4", "clipe", "filmagem", "gravação", "gravaç",
        "consultoria", "consultor", "me diz o que", "o que acha do video",
    ])
    is_analyze = has_media and any(w in msg_normalized for w in [
        "boa", "ruim", "melhorar", "feedback", "avaliar", "analisar",
        "o que acha", "está bom", "tá bom", "tá boa", "está boa",
        "funciona", "serve", "adequad", "avaliaç", "opinion",
        "nota", "pontu", "qualidade da imagem"
    ])

    is_variants = any(w in msg_normalized for w in [
        "variaç", "variante", "varias versoes", "várias versões", "estilos diferentes"
    ])

    # Detecta pedido de troca de cor — rota separada do creative_edit genérico
    COLOR_WORDS = [
        "verde", "azul", "vermelho", "amarelo", "roxo", "lilás",
        "laranja", "rosa", "ciano", "turquesa", "bege", "marrom",
        "cinza", "preto", "branco", "green", "blue", "red",
        "yellow", "purple", "orange", "pink", "gray",
    ]
    # Detecta se o pedido de "branco" é para o fundo e não para o produto
    WHITE_BG_PATTERNS = ["fundo branco", "background branco", "white background", "fundo limpo", "fundo sólido"]
    is_white_bg_req = any(p in msg_normalized for p in WHITE_BG_PATTERNS)

    is_recolor = any(w in msg_normalized for w in [
        "cor ", "cores ", "variação", "variante", "versão ", "mudar a cor",
        "trocar a cor", "muda a cor", "troca a cor", "outra cor",
        "na cor", "em ", "colorir", "recolor",
    ]) and any(c in msg_normalized for c in COLOR_WORDS)
    
    # Se detectou recolor para branco, mas a frase indica fundo branco, cancela o recolor
    if is_recolor and is_white_bg_req and ("branco" in msg_normalized or "white" in msg_normalized):
        # Só cancela se não houver outras cores na mensagem (ex: "mochila verde com fundo branco")
        other_colors = [c for c in COLOR_WORDS if c in msg_normalized and c not in ["branco", "white"]]
        if not other_colors:
            is_recolor = False

    # Edição criativa: qualquer instrução que implica manipular pixels
    # de forma aberta (badge, iluminação, detalhe de material, etc.)
    is_creative = any(w in msg_normalized for w in [
        "badge", "etiqueta", "selos", "texto", "escrit", "escreve",
        "iluminaç", "luz", "brilh", "sombra", "contrast", "saturação",
        "cor", "trocar", "mudar", "mude a", "verde", "azul", "preto", "rosa",
        "amarelo", "vermelho", "laranja", "roxo", "branco", "cinza", "marrom",
        "filtro", "efeito",
        "detal", "ampli", "zoom", "mostra",
        "prova", "resistente", "imperme", "material", "tecido",
        "profissional", "montag", "composição",
    ])

    # ── Ordem natural de encadeamento ────────────────────────
    # upscale → remove_bg → generate_scene → recolor → analyze → creative_edit
    if is_upscale:
        intents.append("upscale")
    if is_remove_bg:
        intents.append("remove_bg")
    if is_scene:
        intents.append("generate_scene")
    if is_recolor:
        intents.append("recolor")
    
    # Se já detectamos recolor para uma cor específica, não fazemos variantes de estilo genéricas
    if is_variants and "recolor" not in intents:
        intents.append("generate_variants")
        
    if is_analyze and not any(i in ["recolor", "creative_edit"] for i in intents):
        intents.append("analyze_image")
        
    if is_creative and "analyze_image" not in intents and "recolor" not in intents:
        # Criativo coexiste com processamento mas não com análise pura ou recolor dedicado
        intents.append("creative_edit")

    # Se tem mídia mas não classificou → análise genérica
    if has_media and not intents:
        intents.append("analyze_image")

    if is_optimize:
        intents.append("optimize_listing")

    if is_video:
        intents.append("analyze_video")

    if not intents:
        intents.append("general")

    return intents


# Manter alias para compatibilidade reversa (caso haja código antigo chamando)
def detect_chat_intent(user_message: str, has_media: bool) -> str:
    return detect_chat_intents(user_message, has_media)[0]


# ══════════════════════════════════════════════════════════════
# ADICIONAR creative_edit_with_vision() — nova função
# ══════════════════════════════════════════════════════════════

def composite_layers(layers: list) -> Image.Image | None:
    """
    Mescla uma lista de camadas (dicts com 'img' e 'visible') em uma única imagem.
    Layers: [{ "name": str, "img": PIL, "visible": bool, "type": str, "offset_x": float, "offset_y": float }]
    Offsets são em % (0 a 100).
    """
    from PIL import Image

    visible_layers = [l for l in layers if l.get("visible", True)]
    if not visible_layers:
        return None

    # Encontra a camada base (se houver) ou usa a primeira para definir o canvas
    base_layers = [l for l in visible_layers if l.get("type") == "base"]
    ref_layer = base_layers[0] if base_layers else visible_layers[0]

    ref_img = ref_layer["img"]
    w_base, h_base = ref_img.size
    composite = Image.new("RGBA", (w_base, h_base), (0, 0, 0, 0))

    for layer in visible_layers:
        l_img = layer["img"].convert("RGBA")
        
        # Redimensionamento personalizado (opcional)
        if layer.get("width_pct") and layer.get("height_pct"):
            new_w = int((layer["width_pct"] / 100.0) * w_base)
            new_h = int((layer["height_pct"] / 100.0) * h_base)
            if new_w > 0 and new_h > 0:
                l_img = l_img.resize((new_w, new_h), Image.LANCZOS)

        # Posição personalizada (offset em % tem prioridade)
        if "offset_x" in layer and "offset_y" in layer:
            x = int((layer["offset_x"] / 100.0) * w_base)
            y = int((layer["offset_y"] / 100.0) * h_base)
        else:
            x = int(layer.get("x", 0))
            y = int(layer.get("y", 0))

        if layer.get("type") == "base" and l_img.size != (w_base, h_base):
            l_img.thumbnail((w_base, h_base), Image.LANCZOS)
            temp = Image.new("RGBA", (w_base, h_base), (0, 0, 0, 0))
            paste_x = (w_base - l_img.width) // 2
            paste_y = (h_base - l_img.height) // 2
            temp.paste(l_img, (paste_x, paste_y))
            l_img = temp
            x, y = 0, 0

        # Camada de composição intermediária para suportar transparência na colagem
        overlay = Image.new("RGBA", (w_base, h_base), (0, 0, 0, 0))
        overlay.paste(l_img, (x, y))
        composite = Image.alpha_composite(composite, overlay)

    return composite.convert("RGBA")

def infer_primary_benefit_with_vision(
    image: "Image.Image",
    product_context: str,
    segmento: str,
) -> dict:
    """
    Analisa a imagem e o contexto para inferir o benefício comercial mais forte.
    Retorna {"benefit": str, "icon": str, "reason": str}
    """
    from backend_core import get_client, MODELOS_VISION
    import time as _time

    prompt = f"""Analise esta imagem de produto e o contexto abaixo.
CONTEXTO: {product_context}
NICHO: {segmento}

Identifique o principal benefício comercial/emocional deste produto.
REGRAS:
1. Se a imagem for clara, seja específico (ex: 'Alça Acolchoada', 'Couro Legítimo').
2. Se a imagem for ambígua ou o produto for genérico, use benefícios seguros como 'Qualidade Garantida', 'Praticidade no Dia a Dia' ou 'Design Moderno'.
3. Retorne APENAS um JSON no formato:
{{"benefit": "texto curto", "icon": "emoji", "confidence": 0.0 a 1.0, "reason": "explicação"}}
"""
    # ... (resto da função infer_primary_benefit_with_vision)

    # Thumbnail para economizar tokens e evitar latência
    img_v = image.copy()
    img_v.thumbnail((1024, 1024))

    for m in MODELOS_VISION:
        try:
            resp = get_client().models.generate_content(model=m, contents=[prompt, img_v])
            text = resp.text.strip().replace("```json", "").replace("```", "").strip()
            import json as _json
            return _json.loads(text)
        except Exception:
            _time.sleep(1)

    return {
        "benefit": "Qualidade Premium",
        "icon": "✨",
        "reason": "fallback"
    }


# Mapa de nomes de cor → hue (0-360) e saturação mínima garantida
_COLOR_MAP = {
    # Português
    "verde":    (120, 0.55), "azul":     (210, 0.60),
    "vermelho": (  0, 0.65), "amarelo":  ( 55, 0.65),
    "roxo":     (270, 0.55), "lilás":    (280, 0.45),
    "laranja":  ( 25, 0.70), "rosa":     (335, 0.50),
    "ciano":    (185, 0.60), "turquesa": (175, 0.55),
    "bege":     ( 35, 0.25), "marrom":   ( 25, 0.55),
    "cinza":    (  0, 0.00), "preto":    (  0, 0.00),
    "branco":   (  0, 0.00),
    # Inglês (vindo do Gemini)
    "green":    (120, 0.55), "blue":     (210, 0.60),
    "red":      (  0, 0.65), "yellow":   ( 55, 0.65),
    "purple":   (270, 0.55), "orange":   ( 25, 0.70),
    "pink":     (335, 0.50), "cyan":     (185, 0.60),
    "gray":     (  0, 0.00), "grey":     (  0, 0.00),
    "black":    (  0, 0.00), "white":    (  0, 0.00),
    "brown":    ( 25, 0.55), "beige":    ( 35, 0.25),
}

_COLOR_ALIASES = {
    "amarela": "amarelo", "amarelas": "amarelo", "amarelos": "amarelo",
    "vermelha": "vermelho", "vermelhas": "vermelho", "vermelhos": "vermelho",
    "roxa": "roxo", "roxas": "roxo", "roxos": "roxo",
    "preta": "preto", "pretas": "preto", "pretos": "preto",
    "branca": "branco", "brancas": "branco", "brancos": "branco",
    "verdes": "verde", "azuis": "azul", "rosas": "rosa",
    "laranjas": "laranja", "cinzas": "cinza", "marrons": "marrom",
}

# Cores que mudam valor (brilho) em vez de hue
_ACHROMATIC = {"cinza", "gray", "grey", "preto", "black", "branco", "white", "bege", "beige"}

def normalize_message_colors(text: str) -> str:
    """Normaliza variações de gênero e plural de cores para a forma canônica."""
    t = text.lower()
    # Ordem decrescente de tamanho para evitar trocas parciais (ex: amarelas antes de amarela)
    sorted_aliases = sorted(_COLOR_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
    for alias, canonical in sorted_aliases:
        # Tenta substituir como palavra inteira primeiro usando regex
        t = re.sub(rf"\b{alias}\b", canonical, t)
    return t


def recolor_product_image(
    image: "Image.Image",
    target_color: str,
    strength: float = 0.88,
) -> tuple:
    """
    Recolore o produto principal preservando textura, brilho e sombra.

    Pipeline:
      1. Obtém máscara do produto via rembg (ou usa alpha existente)
      2. Converte pixels do produto para HSV
      3. Substitui H pelo hue alvo, preserva S e V
      4. Para pixels de baixa saturação (brancos/cinzas), aumenta S
         progressivamente para tornar a cor visível
      5. Valida a mudança comparando médias de canal antes/depois
      6. Recompõe no fundo original (não descarta fundo)

    Retorna: (imagem_resultado, sucesso: bool, descricao: str)
    """
    import io as _io
    import numpy as np

    orig = image.convert("RGBA")
    w, h = orig.size
    arr  = np.array(orig, dtype=np.float32)   # H W 4  (R G B A)

    target_lower = target_color.strip().lower()

    # ── 1. Máscara do produto ──────────────────────────────────
    # Tenta usar alpha existente; se fundo não foi removido, faz rembg
    alpha_chan = arr[:, :, 3]
    product_mask = alpha_chan > 30   # pixels do produto

    has_transparency = product_mask.sum() < (w * h * 0.95)
    if not has_transparency:
        # Fundo ainda presente — remove para obter máscara
        try:
            from rembg import remove as _rembg
            img_for_mask = orig.convert("RGB")
            if img_for_mask.width > 1024 or img_for_mask.height > 1024:
                img_for_mask = img_for_mask.copy()
                img_for_mask.thumbnail((1024, 1024), Image.LANCZOS)
            buf = _io.BytesIO()
            img_for_mask.save(buf, format="PNG")
            no_bg_bytes = _rembg(buf.getvalue())
            mask_img = Image.open(_io.BytesIO(no_bg_bytes)).convert("RGBA")
            if mask_img.size != (w, h):
                mask_img = mask_img.resize((w, h), Image.LANCZOS)
            mask_arr  = np.array(mask_img, dtype=np.float32)
            product_mask = mask_arr[:, :, 3] > 30
        except Exception:
            # Fallback: usa todos os pixels não-brancos como produto
            rgb_arr = arr[:, :, :3]
            product_mask = ~((rgb_arr[:, :, 0] > 240) &
                             (rgb_arr[:, :, 1] > 240) &
                             (rgb_arr[:, :, 2] > 240))

    if product_mask.sum() < 100:
        return orig, False, "⚠️ Não foi possível identificar o produto na imagem para recolorir."

    # ── 2. Converte para HSV ───────────────────────────────────
    rgb_norm = arr[:, :, :3] / 255.0          # H W 3 float [0,1]
    h_ch = np.zeros((h, w), dtype=np.float32)
    s_ch = np.zeros((h, w), dtype=np.float32)
    v_ch = np.zeros((h, w), dtype=np.float32)

    # Vetorizado via numpy — sem loop Python por pixel
    r, g, b = rgb_norm[:, :, 0], rgb_norm[:, :, 1], rgb_norm[:, :, 2]
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    delta = maxc - minc

    v_ch = maxc
    s_ch = np.where(maxc > 0, delta / maxc, 0.0)

    # Hue
    with np.errstate(invalid="ignore", divide="ignore"):
        h_r = np.where(delta > 0,
                       np.where(maxc == r, (g - b) / delta % 6,
                       np.where(maxc == g, (b - r) / delta + 2,
                                            (r - g) / delta + 4)),
                       0.0)
    h_ch = (h_r / 6.0) % 1.0   # normalizado [0,1]

    # ── 3. Troca de hue ───────────────────────────────────────
    if target_lower in _ACHROMATIC:
        # Cores sem hue: ajustar V e S
        if target_lower in ("preto", "black"):
            v_new = v_ch * 0.25
            s_new = s_ch * 0.2
        elif target_lower in ("branco", "white"):
            v_new = np.clip(v_ch * 1.3, 0, 1)
            s_new = s_ch * 0.15
        else:  # cinza
            v_new = v_ch
            s_new = s_ch * 0.15
        h_new = h_ch
    else:
        target_hue, min_sat = _COLOR_MAP.get(target_lower, (120, 0.55))
        target_h_norm = target_hue / 360.0

        # Preserva variação relativa de hue (sombras mantêm tons diferentes)
        h_new = np.where(product_mask, target_h_norm, h_ch)

        # Garante saturação mínima para pixels de baixa saturação
        s_boost = np.clip(min_sat - s_ch, 0, 1) * 0.7  # complemento suavizado
        s_new   = np.where(
            product_mask,
            np.clip(s_ch * (1 - strength) + (s_ch + s_boost) * strength, 0, 1),
            s_ch
        )
        v_new = v_ch  # preserva brilho/sombra integralmente

    # ── 4. Converte HSV → RGB ──────────────────────────────────
    # Vetorizado
    i_h = (h_new * 6.0).astype(np.int32) % 6
    f   = h_new * 6.0 - np.floor(h_new * 6.0)
    p   = v_new * (1 - s_new)
    q_v = v_new * (1 - f * s_new)
    t_v = v_new * (1 - (1 - f) * s_new)

    r_new = np.select(
        [i_h == 0, i_h == 1, i_h == 2, i_h == 3, i_h == 4, i_h == 5],
        [v_new, q_v, p, p, t_v, v_new], default=v_new,
    )
    g_new = np.select(
        [i_h == 0, i_h == 1, i_h == 2, i_h == 3, i_h == 4, i_h == 5],
        [t_v, v_new, v_new, q_v, p, p], default=v_new,
    )
    b_new = np.select(
        [i_h == 0, i_h == 1, i_h == 2, i_h == 3, i_h == 4, i_h == 5],
        [p, p, t_v, v_new, v_new, q_v], default=v_new,
    )

    # ── 5. Compõe resultado ────────────────────────────────────
    result_arr = arr.copy()
    mask_3d = np.stack([product_mask] * 3, axis=-1)

    result_arr[:, :, 0] = np.where(mask_3d[:, :, 0], np.clip(r_new * 255, 0, 255), arr[:, :, 0])
    result_arr[:, :, 1] = np.where(mask_3d[:, :, 1], np.clip(g_new * 255, 0, 255), arr[:, :, 1])
    result_arr[:, :, 2] = np.where(mask_3d[:, :, 2], np.clip(b_new * 255, 0, 255), arr[:, :, 2])
    result_arr[:, :, 3] = arr[:, :, 3]  # preserva alpha original

    result_img = Image.fromarray(result_arr.astype(np.uint8), "RGBA")

    # ── 6. Validação visual ────────────────────────────────────
    # Compara média de canal nos pixels do produto antes e depois
    before_r = arr[:, :, 0][product_mask].mean()
    before_g = arr[:, :, 1][product_mask].mean()
    after_r  = result_arr[:, :, 0][product_mask].mean()
    after_g  = result_arr[:, :, 1][product_mask].mean()
    delta_r  = abs(after_r - before_r)
    delta_g  = abs(after_g - before_g)
    mudanca  = max(delta_r, delta_g)

    COLOR_NAMES_PT = {
        "green": "verde", "blue": "azul", "red": "vermelho", "yellow": "amarelo",
        "purple": "roxo", "orange": "laranja", "pink": "rosa", "cyan": "ciano",
        "gray": "cinza", "grey": "cinza", "black": "preto", "white": "branco",
        "brown": "marrom", "beige": "bege",
    }
    nome_pt = COLOR_NAMES_PT.get(target_lower, target_lower)

    if mudanca < 8 and target_lower not in _ACHROMATIC:
        # Mudança imperceptível
        return result_img, False, (
            f"⚠️ A tentativa de recoloração para **{nome_pt}** não ficou convincente "
            f"nesta imagem (variação média: {mudanca:.1f}/255). "
            f"Isso pode acontecer com imagens de fundo complexo ou produto muito claro."
        )

    return result_img, True, (
        f"✅ Variação **{nome_pt}** gerada com sucesso! "
        f"Textura, sombras e brilho foram preservados."
    )


def creative_edit_with_vision(
    image: "Image.Image",
    instruction: str,
    product_context: str,
    segmento: str,
) -> tuple:
    """
    Usa Gemini Vision para interpretar uma instrução criativa aberta
    e aplica as operações via PIL.

    Retorna (imagem_editada, descricao_do_que_foi_feito).
    """
    import io as _io
    import time as _time
    import json as _json
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

    # ── 1. Gemini interpreta a instrução ─────────────────────
    schema_prompt = f"""Você é um especialista em edição de imagens para e-commerce.
Analise esta imagem de produto e a instrução do usuário.

INSTRUÇÃO: "{instruction}"
SEGMENTO: {segmento}
CONTEXTO DO PRODUTO: {product_context[:500]}

Responda APENAS com JSON válido (sem markdown), com as operações a executar:

{{
  "operations": [
    // Operações disponíveis (use apenas as necessárias):
    
    // Ajuste global de imagem:
    // {{"type": "brightness", "value": 1.0}}   → 0.5=escuro, 1.5=claro
    // {{"type": "contrast", "value": 1.0}}     → 0.5=baixo, 1.5=alto
    // {{"type": "saturation", "value": 1.0}}   → 0=pb, 1.5=saturado
    // {{"type": "sharpness", "value": 1.0}}    → 0=blur, 2=nítido
    // {{"type": "warmth", "value": 0}}          → -50=frio, +50=quente
    
    // Badge/Texto sobre a imagem:
    // {{"type": "badge", "text": "À prova d'água", "position": "bottom-right",
    //   "text_color": "#FFFFFF", "bg_color": "#1565C0",
    //   "icon": "💧"}}
    // position: "top-left" | "top-right" | "bottom-left" | "bottom-right" | "center"
    
    // Recorte de detalhe (cria uma miniatura circular num canto):
    // {{"type": "detail_callout", "region": "top-left",
    //   "crop_hint": "canto superior esquerdo com textura",
    //   "label": "Tecido Ripstop", "callout_position": "bottom-left"}}
    // region: onde está o detalhe na imagem original
    // callout_position: onde colocar o medallhão de detalhe
    
    // Vinheta (escurece as bordas para dar foco ao produto):
    // {{"type": "vignette", "intensity": 0.4}}  → 0.1=suave, 0.7=forte
    
    // Borda clean ao redor do produto (borda fina colorida):
    // {{"type": "border", "color": "#E0E0E0", "width": 8}},

    // Troca de cor (específico para regiões ou produto inteiro):
    // {{"type": "recolor", "target_color": "green", "hue_shift": 120}}
    ],

  "description": "Explicação em português do que foi feito"
}}

REGRAS:
- Use apenas operações da lista acima
- Para badges de feature do produto (à prova d'água, resistente, etc.) use badge com ícone
- Se a instrução pedir iluminação mais quente → warmth positivo + brightness +0.1
- Se pedir mais profissional → contrast +0.1 + sharpness +0.2 + vinheta suave
- Máximo 4 operações para não poluir a imagem
- description deve ser amigável e explicar o que foi feito
"""

    ops = []
    description = "Edição criativa aplicada."

    from backend_core import get_client, MODELOS_VISION
    for m in MODELOS_VISION:
        try:
            img_rgb = image.convert("RGB") if image.mode != "RGB" else image
            response = get_client().models.generate_content(
                model=m,
                contents=[schema_prompt, img_rgb]
            )
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            parsed = _json.loads(raw)
            ops = parsed.get("operations", [])
            description = parsed.get("description", description)
            break
        except Exception as e:
            _time.sleep(1)
            continue

    if not ops:
        return image, "⚠️ Não foi possível interpretar a instrução. Tente descrever de forma mais específica."

    # ── 2. Aplica as operações com PIL ───────────────────────
    result = image.convert("RGBA")
    w, h = result.size

    for op in ops:
        op_type = op.get("type", "")

        try:
            # ── Ajustes globais ──────────────────────────────
            if op_type == "brightness":
                base = result.convert("RGB")
                base = ImageEnhance.Brightness(base).enhance(float(op.get("value", 1.0)))
                result = base.convert("RGBA") if result.mode == "RGBA" else base

            elif op_type == "contrast":
                base = result.convert("RGB")
                base = ImageEnhance.Contrast(base).enhance(float(op.get("value", 1.0)))
                result = base.convert("RGBA") if result.mode == "RGBA" else base

            elif op_type == "saturation":
                base = result.convert("RGB")
                base = ImageEnhance.Color(base).enhance(float(op.get("value", 1.0)))
                result = base.convert("RGBA") if result.mode == "RGBA" else base

            elif op_type == "sharpness":
                base = result.convert("RGB")
                base = ImageEnhance.Sharpness(base).enhance(float(op.get("value", 1.0)))
                result = base.convert("RGBA") if result.mode == "RGBA" else base

            elif op_type == "warmth":
                import numpy as np
                val = float(op.get("value", 0))
                base = result.convert("RGB")
                arr = np.array(base, dtype=np.float32)
                if val > 0:
                    arr[:, :, 0] = np.clip(arr[:, :, 0] + val, 0, 255)   # mais vermelho
                    arr[:, :, 2] = np.clip(arr[:, :, 2] - val * 0.5, 0, 255)  # menos azul
                else:
                    arr[:, :, 2] = np.clip(arr[:, :, 2] - val, 0, 255)   # mais azul
                    arr[:, :, 0] = np.clip(arr[:, :, 0] + val * 0.5, 0, 255)
                base = Image.fromarray(arr.astype(np.uint8), "RGB")
                result = base.convert("RGBA") if result.mode == "RGBA" else base

            # ── Badge de texto ────────────────────────────────
            elif op_type == "badge":
                canvas = result.copy().convert("RGBA")
                draw = ImageDraw.Draw(canvas)

                text    = str(op.get("text", ""))
                icon    = str(op.get("icon", ""))
                full_text = f"{icon} {text}".strip() if icon else text
                pos     = op.get("position", "bottom-right")
                bg_hex  = op.get("bg_color", "#1565C0")
                fg_hex  = op.get("text_color", "#FFFFFF")

                # Converte hex → RGB
                def hex2rgb(h):
                    h = h.lstrip("#")
                    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

                bg_color = hex2rgb(bg_hex)
                fg_color = hex2rgb(fg_hex)

                # Tenta carregar fonte, fallback para default
                try:
                    fsize = max(18, w // 28)
                    font = ImageFont.truetype("arial.ttf", fsize)
                except Exception:
                    try:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
                    except Exception:
                        font = ImageFont.load_default()

                # Mede o texto
                bbox = draw.textbbox((0, 0), full_text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]

                pad_x, pad_y = 18, 10
                bw = tw + pad_x * 2
                bh = th + pad_y * 2
                margin = max(16, w // 40)

                # Posição do badge
                pos_map = {
                    "top-left":     (margin, margin),
                    "top-right":    (w - bw - margin, margin),
                    "bottom-left":  (margin, h - bh - margin),
                    "bottom-right": (w - bw - margin, h - bh - margin),
                    "center":       ((w - bw) // 2, (h - bh) // 2),
                }
                x0, y0 = pos_map.get(pos, pos_map["bottom-right"])
                x1, y1 = x0 + bw, y0 + bh

                # Desenha badge com cantos arredondados (via ellipse nas bordas)
                radius = bh // 3
                badge_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                bd = ImageDraw.Draw(badge_layer)
                bd.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                                     fill=(*bg_color, 220))
                canvas = Image.alpha_composite(canvas, badge_layer)

                # Texto
                draw2 = ImageDraw.Draw(canvas)
                tx = x0 + pad_x
                ty = y0 + pad_y
                draw2.text((tx, ty), full_text, font=font, fill=(*fg_color, 255))
                result = canvas

            # ── Detail callout (medallhão de detalhe) ─────────
            elif op_type == "detail_callout":
                base_img = result.convert("RGBA")
                bw, bh   = base_img.size

                # Região da imagem original a recortar
                region_map = {
                    "top-left":     (0, 0, bw // 3, bh // 3),
                    "top-right":    (bw * 2 // 3, 0, bw, bh // 3),
                    "center":       (bw // 3, bh // 3, bw * 2 // 3, bh * 2 // 3),
                    "bottom-left":  (0, bh * 2 // 3, bw // 3, bh),
                    "bottom-right": (bw * 2 // 3, bh * 2 // 3, bw, bh),
                }
                reg = op.get("region", "top-right")
                crop_box = region_map.get(reg, region_map["top-right"])
                detail = base_img.crop(crop_box)

                # Tamanho do medallhão
                medal_size = max(120, bw // 5)
                detail = detail.resize((medal_size, medal_size), Image.LANCZOS)

                # Máscara circular
                mask = Image.new("L", (medal_size, medal_size), 0)
                md   = ImageDraw.Draw(mask)
                md.ellipse([0, 0, medal_size, medal_size], fill=255)

                circle_img = Image.new("RGBA", (medal_size, medal_size), (0, 0, 0, 0))
                circle_img.paste(detail, (0, 0))
                circle_img.putalpha(mask)

                # Borda branca
                border_size = medal_size + 8
                bordered = Image.new("RGBA", (border_size, border_size), (0, 0, 0, 0))
                bd_draw  = ImageDraw.Draw(bordered)
                bd_draw.ellipse([0, 0, border_size, border_size], fill=(255, 255, 255, 230))
                bordered.paste(circle_img, (4, 4), circle_img)

                # Posição do medallhão no canvas
                callout_pos = op.get("callout_position", "bottom-left")
                medal_margin = 20
                cpos_map = {
                    "top-left":     (medal_margin, medal_margin),
                    "top-right":    (bw - border_size - medal_margin, medal_margin),
                    "bottom-left":  (medal_margin, bh - border_size - medal_margin),
                    "bottom-right": (bw - border_size - medal_margin,
                                     bh - border_size - medal_margin),
                }
                cx, cy = cpos_map.get(callout_pos, cpos_map["bottom-left"])

                canvas = base_img.copy()
                canvas.paste(bordered, (cx, cy), bordered)

                # Label abaixo do medallhão
                label = str(op.get("label", ""))
                if label:
                    draw = ImageDraw.Draw(canvas)
                    try:
                        fsize = max(14, bw // 38)
                        font = ImageFont.truetype("arial.ttf", fsize)
                    except Exception:
                        font = ImageFont.load_default()

                    bbox = draw.textbbox((0, 0), label, font=font)
                    lw = bbox[2] - bbox[0]
                    lx = cx + (border_size - lw) // 2
                    ly = cy + border_size + 4

                    # Fundo semitransparente atrás do texto
                    if 0 <= ly < bh:
                        lb = draw.textbbox((lx, ly), label, font=font)
                        draw.rounded_rectangle(
                            [lb[0]-4, lb[1]-2, lb[2]+4, lb[3]+2],
                            radius=4, fill=(0, 0, 0, 160)
                        )
                        draw.text((lx, ly), label, font=font, fill=(255, 255, 255, 255))

                result = canvas

            # ── Vinheta ──────────────────────────────────────
            elif op_type == "vignette":
                import numpy as np
                intensity = float(op.get("intensity", 0.4))
                base = result.convert("RGBA")
                arr  = np.array(base, dtype=np.float32)

                yw = np.linspace(-1, 1, h)
                xw = np.linspace(-1, 1, w)
                X, Y = np.meshgrid(xw, yw)
                dist = np.sqrt(X**2 + Y**2)
                dist = dist / dist.max()
                vign = 1 - intensity * dist**1.5
                vign = np.clip(vign, 0, 1)

                for c in range(3):
                    arr[:, :, c] *= vign

                result = Image.fromarray(arr.astype(np.uint8), "RGBA")

            # ── Borda fina ────────────────────────────────────
            elif op_type == "border":
                def hex2rgb(h):
                    h = h.lstrip("#")
                    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

                brd_color = hex2rgb(op.get("color", "#E0E0E0"))
                brd_width = int(op.get("width", 8))
                canvas    = result.convert("RGBA")
                draw_brd  = ImageDraw.Draw(canvas)
                draw_brd.rectangle(
                    [brd_width // 2, brd_width // 2,
                     w - brd_width // 2, h - brd_width // 2],
                    outline=(*brd_color, 255), width=brd_width
                )
                result = canvas

            # ── Recoloração do produto ────────────────────────
            elif op_type == "recolor":
                tgt = str(op.get("target_color", op.get("color", ""))).lower().strip()
                if tgt:
                    recolored, ok, recolor_desc = recolor_product_image(result, tgt)
                    result      = recolored
                    # Sobrescreve a description com o resultado real da mudança
                    description = recolor_desc

        except Exception as op_err:
            # Operação falhou silenciosamente — continua com as outras
            continue

    return result, description



# ══════════════════════════════════════════════════════════════
# ANÁLISE DE IMAGEM (Gemini Vision)
# ══════════════════════════════════════════════════════════════

def apply_region_edit_with_vision(
    image: "Image.Image",
    roi: dict, # {"x": %, "y": %, "w": %, "h": %, "shape": "rect"|"circle"|"freehand"}
    instruction: str,
    product_context: str,
    segmento: str,
    freehand_mask: "Image.Image" = None
) -> tuple:
    """
    Recorta a região selecionada (ROI), processa com Gemini Vision
    e retorna uma nova camada de imagem com a edição aplicada naquela região,
    respeitando a máscara da forma (retângulo, círculo ou livre).
    """
    from PIL import Image, ImageDraw
    import io as _io
    
    # 1. Calcula coordenadas reais do crop
    w, h = image.size
    x0 = int(roi["x"] * w / 100)
    y0 = int(roi["y"] * h / 100)
    w0 = int(roi["w"] * w / 100)
    h0 = int(roi["h"] * h / 100)
    
    # Garante que w0/h0 não sejam zero
    w0 = max(1, w0)
    h0 = max(1, h0)
    
    crop_box = (x0, y0, x0 + w0, y0 + h0)
    region_img = image.crop(crop_box)
    
    # 2. Processa a região (ex: "mude a cor", "adicione brilho")
    edited_region, desc = creative_edit_with_vision(
        region_img, instruction, product_context, segmento
    )
    
    # 3. Cria a máscara de forma
    shape = roi.get("shape", "rect")
    mask = Image.new("L", (w0, h0), 0)
    draw = ImageDraw.Draw(mask)
    
    if shape == "circle":
        draw.ellipse([0, 0, w0, h0], fill=255)
    elif shape == "freehand" and freehand_mask:
        # Redimensiona a máscara livre para o tamanho real do crop
        mask = freehand_mask.resize((w0, h0), Image.NEAREST)
    else: # rect ou fallback
        mask.paste(255, [0, 0, w0, h0])
    
    # 4. Cria uma camada transparente e aplica a região editada através da máscara
    layer_img = Image.new("RGBA", image.size, (0, 0, 0, 0))
    # Converte a região editada para RGBA
    edited_rgba = edited_region.convert("RGBA")
    
    # Aplica a máscara na região editada (cropada) antes de colar no layer total
    final_region = Image.new("RGBA", (w0, h0), (0, 0, 0, 0))
    final_region.paste(edited_rgba, (0, 0), mask)
    
    layer_img.paste(final_region, (x0, y0), final_region)
    
    return layer_img, desc


def analyze_product_image_vision(
    image: "Image.Image",
    user_message: str,
    product_context: str,
    segmento: str,
) -> str:
    """
    Usa Gemini Vision para analisar a imagem do produto em contexto
    de e-commerce e responder à pergunta do usuário.
    """
    from PIL import Image as PILImage
    import io as _io
    import time as _time

    system_prompt = f"""Você é um especialista em fotografia de produto para e-commerce Shopee Brasil.
Segmento do produto: {segmento}

{product_context}

Analise a imagem enviada e responda à pergunta do usuário de forma objetiva e prática.
Forneça feedback específico sobre: qualidade, iluminação, composição, fundo, apelo visual.
Pontue de 1-10 e dê sugestões concretas de melhoria.
"""
    full_prompt = f"{system_prompt}\n\nPergunta do usuário: {user_message}"

    for m in MODELOS_VISION:
        try:
            response = get_client().models.generate_content(
                model=m,
                contents=[full_prompt, image]
            )
            return response.text
        except Exception:
            _time.sleep(1)
            continue

    return "⏳ Não foi possível analisar a imagem agora. Verifique sua cota de API."


# ══════════════════════════════════════════════════════════════
# ANÁLISE DE VÍDEO (Gemini Files API)
# ══════════════════════════════════════════════════════════════

def analyze_video_with_gemini(
    video_bytes: bytes,
    user_message: str,
    full_context: str,
    segmento: str,
) -> str:
    """
    Faz upload do vídeo para a Gemini Files API e devolve uma
    consultoria completa — gancho, iluminação, CTA, boas práticas,
    pontuação e recomendações para o nicho.

    Inclui logging técnico para debug e observabilidade.
    """
    import time as _time
    import tempfile as _tempfile
    import os as _os
    import logging as _logging

    _log = _logging.getLogger("shopee.video")
    t_start = _time.time()

    video_size_mb = len(video_bytes) / (1024 * 1024)
    _log.info(f"[VIDEO] Início da análise | tamanho={video_size_mb:.1f} MB")

    CONSULTING_PROMPT = f"""Você é um consultor especialista em vídeos de produto para marketplace Shopee Brasil.
Segmento: {segmento}

{full_context[:600]}

Analise este vídeo de produto COM PROFUNDIDADE e devolva um relatório estruturado:

## 🎯 PONTUAÇÃO GERAL: [X]/10

## ✅ O QUE ESTÁ BOM
[pontos fortes — gancho, iluminação, edição, ritmo, apresentação do produto]

## ❌ O QUE PRECISA MELHORAR
[problemas concretos com exemplos do próprio vídeo]

## 🚀 RECOMENDAÇÕES PRIORITÁRIAS
[3–5 ações específicas, em ordem de impacto nas vendas]

## 📊 ANÁLISE TÉCNICA
- Gancho (primeiros 3s): [nota /10 + comentário]
- Iluminação geral: [nota /10 + comentário]
- Clareza do produto em cena: [nota /10 + comentário]
- Prova de benefício mostrada: [sim/não + detalhe]
- CTA (chamada à ação): [presente/ausente + qualidade]
- Adequação ao nicho "{segmento}": [nota /10 + comentário]

## 📚 BOAS PRÁTICAS PARA ESTE NICHO NO SHOPEE BRASIL
[3 dicas específicas e acionáveis para {segmento}]
{f'{chr(10)}Pergunta adicional do usuário: {user_message}' if user_message and len(user_message) > 5 else ''}
"""

    tmp_path = None
    file_ref = None
    _client = get_client()

    try:
        # 1. Salva em arquivo temporário para a API de upload
        with _tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            tmp_path = tmp.name

        # 2. Upload para Gemini Files API
        t_upload = _time.time()
        file_ref = _client.files.upload(
            file=tmp_path,
            config={"mime_type": "video/mp4", "display_name": "produto_video.mp4"},
        )
        t_upload_done = _time.time()
        _log.info(f"[VIDEO] Upload concluído | tempo={t_upload_done - t_upload:.1f}s")

        # 3. Aguarda processamento (máx. 90s)
        t_proc = _time.time()
        espera = 0
        while espera < 90:
            # o SDK pode retornar state como enum, int ou string — normalizamos tudo
            raw_state = file_ref.state
            state_str = getattr(raw_state, "name", str(raw_state)).upper()
            if state_str != "PROCESSING":
                break
            _time.sleep(3)
            file_ref = _client.files.get(name=file_ref.name)
            espera += 3

        # Reavalia o estado final após o loop
        raw_state = file_ref.state
        state_str = getattr(raw_state, "name", str(raw_state)).upper()
        t_proc_done = _time.time()
        _log.info(
            f"[VIDEO] Processamento API | estado_raw={raw_state!r} | estado_str={state_str} | "
            f"file_name={file_ref.name} | tempo={t_proc_done - t_proc:.1f}s"
        )

        if state_str != "ACTIVE":
            return (
                f"⏳ O processamento do vídeo falhou na API (estado: `{state_str}`).\n"
                f"Arquivo: `{file_ref.name}` | Tamanho: {video_size_mb:.1f} MB\n\n"
                "Tente um arquivo menor (≤ 50 MB, duração < 60s)."
            )

        # 4. Gera a análise — retry automático para 503/529, erro real exposto para outros
        t_gen = _time.time()
        ultimo_erro = None
        MAX_RETRIES = 3  # retentativas para erros de sobrecarga (503/529)

        for m in MODELOS_VISION:
            for tentativa in range(MAX_RETRIES):
                try:
                    _log.info(
                        f"[VIDEO] Tentando generate_content | modelo={m} | tentativa={tentativa+1}/{MAX_RETRIES} | "
                        f"file={file_ref.name} | state={state_str} | tamanho={video_size_mb:.1f}MB"
                    )
                    response = _client.models.generate_content(
                        model=m,
                        contents=[CONSULTING_PROMPT, file_ref],
                    )
                    t_total = _time.time() - t_start
                    _log.info(
                        f"[VIDEO] Análise concluída | modelo={m} | "
                        f"tempo_total={t_total:.1f}s | tamanho={video_size_mb:.1f}MB"
                    )
                    return response.text
                except Exception as e:
                    err_str = str(e)
                    # 503/529 = sobrecarga temporária → vale a pena retentar
                    is_overload = "503" in err_str or "529" in err_str or "UNAVAILABLE" in err_str
                    ultimo_erro = e
                    if is_overload and tentativa < MAX_RETRIES - 1:
                        wait_s = 5 * (tentativa + 1)  # 5s → 10s → 15s
                        _log.warning(
                            f"[VIDEO] Modelo {m} sobrecarga (tentativa {tentativa+1}) — aguardando {wait_s}s | erro={e}"
                        )
                        _time.sleep(wait_s)
                    else:
                        _log.warning(
                            f"[VIDEO] Modelo {m} falhou definitivamente | tipo={type(e).__name__} | erro={e}"
                        )
                        break  # passa para o próximo modelo

        # Todos os modelos falharam — expõe o erro real
        t_total = _time.time() - t_start
        err_tipo = type(ultimo_erro).__name__ if ultimo_erro else "desconhecido"
        err_msg  = str(ultimo_erro) if ultimo_erro else "sem detalhes"
        _log.error(f"[VIDEO] Todos os modelos falharam | ultimo_erro={err_tipo}: {err_msg}")
        return (
            f"⏳ Falha ao processar o vídeo no modelo multimodal.\n\n"
            f"**Erro técnico:** `{err_tipo}` — {err_msg}\n\n"
            f"*Tamanho: {video_size_mb:.1f} MB | Arquivo API: `{file_ref.name}` | "
            f"Tempo total: {t_total:.0f}s*"
        )

    except Exception as e:
        import traceback as _tb
        t_total = _time.time() - t_start
        _log.error(
            f"[VIDEO] Erro fatal | tipo={type(e).__name__} | "
            f"tempo={t_total:.1f}s | erro={e}"
        )
        return (
            f"❌ Erro na análise de vídeo: {type(e).__name__} — {e}\n\n"
            f"Detalhes técnicos:\n```\n{_tb.format_exc()[:400]}\n```"
        )
    finally:
        # Limpeza obrigatória — arquivo temporário e crédito de storage
        try:
            if tmp_path and _os.path.exists(tmp_path):
                _os.unlink(tmp_path)
        except Exception:
            pass
        try:
            if file_ref:
                _client.files.delete(name=file_ref.name)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# PROCESSAMENTO COMPLETO DE MÍDIA NO CHAT
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
# BLOCO A — generate_color_variants()
# ══════════════════════════════════════════════════════════════

def generate_color_variants(
    image: "Image.Image",
    segmento: str,
    n_variants: int = 3,
) -> list:
    """
    Gera N variantes da mesma imagem com fundos/estilos diferentes.
    Cada variante = produto com fundo removido + background diferente.

    Retorna lista de dicts:
      [{"image": PIL.Image, "label": str}, ...]
    """
    import io as _io
    import time as _time
    from PIL import Image

    ESTILOS = [
        {
            "label": "🧼 Clean White",
            "prompt": "minimalist pure white studio background soft shadows product photography",
            "segmento_override": None,
        },
        {
            "label": "🎨 Gradiente Pastel",
            "prompt": "soft pastel gradient background product photography minimal",
            "segmento_override": None,
        },
        {
            "label": "🏙️ Lifestyle",
            "prompt": "modern lifestyle background home environment natural light soft",
            "segmento_override": None,
        },
        {
            "label": "🌟 Premium Dark",
            "prompt": "dark premium studio background luxury product photography dramatic lighting",
            "segmento_override": None,
        },
    ]

    # Remove fundo uma vez, reutiliza para todas as variantes
    img_no_bg = None
    try:
        from rembg import remove as rembg_remove
        orig_size = image.size
        img_work  = image.convert("RGB")
        if img_work.width > 1024 or img_work.height > 1024:
            img_work = img_work.copy()
            img_work.thumbnail((1024, 1024), Image.LANCZOS)

        buf = _io.BytesIO()
        img_work.save(buf, format="PNG")
        no_bg_bytes = rembg_remove(buf.getvalue())
        removed = Image.open(_io.BytesIO(no_bg_bytes)).convert("RGBA")

        if removed.size != orig_size:
            removed = removed.resize(orig_size, Image.LANCZOS)
        img_no_bg = removed
    except Exception:
        img_no_bg = image.convert("RGBA")

    results = []
    for estilo in ESTILOS[:n_variants]:
        try:
            seg_use = estilo["segmento_override"] or segmento
            bg = generate_ai_scenario(estilo["prompt"], seg_use)
            if not bg:
                bg = generate_gradient_background(seg_use)

            bg = bg.resize((1024, 1024)).convert("RGBA")
            fg = img_no_bg.copy()
            fg.thumbnail((800, 800))
            offset = (
                (bg.width  - fg.width)  // 2,
                int((bg.height - fg.height) * 0.6),
            )
            bg = apply_contact_shadow(bg, fg, offset)
            bg.paste(fg, offset, fg)
            results.append({"image": bg, "label": estilo["label"]})
            _time.sleep(0.5)  # pequena pausa entre chamadas de API
        except Exception as e:
            results.append({"image": img_no_bg, "label": f"{estilo['label']} (fallback)"})

    return results


# ══════════════════════════════════════════════════════════════
# BLOCO B — generate_post_actions()
# ══════════════════════════════════════════════════════════════

def generate_post_actions(intent: str, has_image_result: bool) -> list:
    """
    Retorna lista de ações de follow-up baseadas no intent executado.
    Cada item: {"label": str, "prompt": str, "icon": str}
    """
    IMAGE_ACTIONS = [
        {"icon": "🌈", "label": "Gerar variações",     "prompt": "gere 3 variações desta imagem com estilos diferentes"},
        {"icon": "🧼", "label": "Fundo branco",         "prompt": "remova o fundo e coloque fundo branco limpo"},
        {"icon": "🎨", "label": "Outro cenário",        "prompt": "gere um cenário diferente para este produto"},
        {"icon": "🏷️", "label": "Adicionar benefício",  "prompt": "adicione um badge de benefício principal nesta imagem"},
        {"icon": "📱", "label": "Versão mobile",        "prompt": "optimize esta imagem para capa principal do anúncio mobile"},
    ]
    VIDEO_ACTIONS = [
        {"icon": "📋", "label": "Transformar em checklist", "prompt": "transforme esta análise em um checklist de regravação prático"},
        {"icon": "🎬", "label": "Gerar roteiro novo",        "prompt": "crie um roteiro melhorado de 30 segundos baseado neste produto e nicho"},
        {"icon": "📅", "label": "Plano de melhoria",         "prompt": "crie um plano de ação de 7 dias para melhorar os vídeos deste produto"},
        {"icon": "✅", "label": "Boas práticas do nicho",    "prompt": "quais são as melhores práticas de vídeo para este nicho no Shopee Brasil?"},
    ]
    ANALYSIS_ACTIONS = [
        {"icon": "📊", "label": "Resumir em 3 pontos",   "prompt": "resuma os principais pontos desta análise em 3 bullets acionáveis"},
        {"icon": "🚀", "label": "Gerar versão otimizada", "prompt": "com base nesta análise, gere o listing completo otimizado"},
        {"icon": "🏆", "label": "Comparar com top lojas", "prompt": "compare este produto com as melhores práticas dos concorrentes"},
    ]

    if intent == "analyze_video":
        return VIDEO_ACTIONS
    elif intent in ("remove_bg", "generate_scene", "creative_edit", "upscale", "generate_variants") or has_image_result:
        return IMAGE_ACTIONS
    elif intent in ("analyze_image", "optimize_listing"):
        return ANALYSIS_ACTIONS
    else:
        return []


def process_chat_turn(
    user_message: str,
    attachments: list,
    attachment_types: list,
    chat_history: list,
    full_context: str,
    segmento: str,
    channel: str = "desktop",
    **kwargs,
) -> dict:
    """
    Orquestra um turno do chat com suporte a multi-intent encadeado.
    kwargs aceita: selected_product, df_competitors, optimization_reviews
    """
    import io as _io
    import time as _time
    from PIL import Image

    has_media = len(attachments) > 0
    active_img_fallback = kwargs.get("active_image")
    
    # Se não houver anexo, mas houver imagem ativa no editor, usa como anexo implícito
    if not has_media and active_img_fallback:
        attachments = [active_img_fallback]
        attachment_types = ["image"]
        has_media = True

    intents   = detect_chat_intents(user_message, has_media)

    result = {"text": "", "images": [], "intent": intents[0], "captions": []}

    # ── Intent de mídia sem anexo → instrui o usuário ────────
    MEDIA_INTENTS = {"remove_bg", "generate_scene", "upscale",
                     "analyze_image", "analyze_video", "creative_edit", "generate_variants", "recolor"}
    if not has_media and any(i in MEDIA_INTENTS for i in intents):
        msgs = {
            "remove_bg":     "📎 Para remover o fundo, clique em **📎 Anexar imagem / vídeo**, selecione a foto e reenvie.",
            "generate_scene":"📎 Para gerar um cenário, anexe a foto pelo botão **📎 Anexar imagem / vídeo** e reenvie.",
            "upscale":       "📎 Para aumentar a qualidade, anexe a imagem e reenvie.",
            "analyze_image": "📎 Para analisar a imagem, anexe a foto e reenvie sua pergunta.",
            "analyze_video": "📎 Para analisar o vídeo, anexe o arquivo MP4 e reenvie.",
            "creative_edit": "📎 Para editar a imagem, anexe a foto pelo botão **📎 Anexar imagem / vídeo** e reenvie com a instrução.",
            "generate_variants": "📎 Para gerar variações, anexe a foto e reenvie.",
            "recolor":       "📎 Para trocar a cor, anexe a foto e diga qual cor deseja.",
        }
        media_intent = next((i for i in intents if i in MEDIA_INTENTS), intents[0])
        result["text"] = msgs.get(media_intent, "📎 Por favor, anexe o arquivo e reenvie.")
        return result

    # ── Otimização de listing sem mídia ─────────────────────
    from backend_core import get_client, MODELOS_TEXTO
    if "optimize_listing" in intents and not has_media:
        prod    = kwargs.get("selected_product")
        df_comp = kwargs.get("df_competitors")
        reviews = kwargs.get("optimization_reviews") or []
        if prod:
            from backend_core import generate_full_optimization
            result["text"] = generate_full_optimization(prod, df_comp, reviews, segmento)
        else:
            if channel == "whatsapp":
                result["text"] = (
                    "⚡ Posso te ajudar de duas formas:\n\n"
                    "1. Se quiser uma *dica rápida* (títulos ou ideias), apenas me descreva o produto e o diferencial dele!\n"
                    "2. Se quiser uma *otimização completa* (com dados de concorrentes e avaliações reais da Shopee), envie o comando /auditar."
                )
            else:
                result["text"] = (
                    "⚡ Para gerar uma otimização completa, selecione um produto na aba "
                    "**Auditoria Pro** clicando em '⚡ Otimizar'. Assim terei acesso ao "
                    "preço, imagem e dados de concorrentes para gerar um listing preciso.\n\n"
                    "Se quiser, posso analisar o mercado em geral — é só descrever o produto!"
                )
        result["post_actions"] = generate_post_actions("optimize_listing", False)
        return result

    # ── Chat geral sem mídia ─────────────────────────────────
    if not has_media or intents == ["general"]:
        channel_instruction = ""
        if channel == "whatsapp":
            channel_instruction = (
                "[INSTRUÇÕES DE SISTEMA - ORIGEM WHATSAPP]\n"
                "Você está respondendo via WhatsApp.\n"
                "1. NÃO mencione abas, botões, Streamlit, '.exe', interface desktop ou ferramentas visuais.\n"
                "2. Para otimização de listing completa, oriente a usar o comando '/auditar'.\n"
                "3. Responda de forma rápida e conversacional. Se faltar contexto, peça as características do produto (preço, benefícios).\n"
                "4. Use formatação de WhatsApp (*negrito*, _itálico_).\n\n"
            )
        contents = [channel_instruction + full_context + "\n\n---\nHistórico:\n"]
        for turn in chat_history[-8:]:
            contents.append(f"Usuário: {turn['user']}")
            contents.append(f"Assistente: {turn['assistant']}")
        contents.append(f"Usuário: {user_message}\nAssistente:")
        prompt = "\n".join(contents)
        text = ""
        for m in MODELOS_TEXTO:
            try:
                cfg = {"thinking_config": {"thinking_budget": 0}} if ("3.1" in m or "2.5" in m) else {}
                resp = get_client().models.generate_content(
                    model=m, contents=[prompt], config=cfg if cfg else None
                )
                text = resp.text.strip()
                break
            except Exception:
                _time.sleep(2)
        result["text"]         = text or "⏳ Erro de API. Tente novamente."
        result["post_actions"] = generate_post_actions("general", False)
        return result

    # ── Processamento de mídia com encadeamento multi-intent ─
    processed_images = []
    captions         = []
    text_parts       = []

    from backend_core import upscale_image, improve_image_quality, generate_ai_scenario, generate_gradient_background, apply_contact_shadow, analyze_product_image_vision
    for i, attachment in enumerate(attachments):
        atype = attachment_types[i] if i < len(attachment_types) else "image"

        if atype == "video":
            # ── Análise real via Gemini Files API ─────────────────
            video_bytes = attachment if isinstance(attachment, bytes) else None
            if video_bytes is None:
                result["text"] = (
                    "❌ Não consegui ler o arquivo de vídeo. "
                    "Certifique-se de enviar um MP4 válido."
                )
                result["intent"] = "analyze_video"
                result["post_actions"] = generate_post_actions("analyze_video", False)
                return result

            # Limita a 80 MB para não exceder quota da Files API
            MAX_VIDEO_BYTES = 80 * 1024 * 1024
            if len(video_bytes) > MAX_VIDEO_BYTES:
                size_mb = len(video_bytes) // (1024 * 1024)
                result["text"] = (
                    f"⚠️ Vídeo muito grande ({size_mb} MB). "
                    "O limite é 80 MB. Comprima o vídeo ou corte trechos "
                    "desnecessários antes de enviar."
                )
                result["intent"] = "analyze_video"
                result["post_actions"] = generate_post_actions("analyze_video", False)
                return result

            from backend_core import analyze_video_with_gemini
            analise = analyze_video_with_gemini(
                video_bytes, user_message, full_context, segmento
            )
            result["text"]   = analise
            result["intent"] = "analyze_video"
            result["post_actions"] = generate_post_actions("analyze_video", False)
            return result

        # Converte para PIL
        if isinstance(attachment, bytes):
            img = Image.open(_io.BytesIO(attachment)).convert("RGBA")
        else:
            img = attachment.convert("RGBA") if attachment.mode != "RGBA" else attachment

        # ── Encadeia as operações de imagem ───────────────────
        current_img = img

        for intent in intents:
            if intent == "upscale":
                from backend_core import upscale_image, improve_image_quality
                current_img = upscale_image(current_img.convert("RGB"), scale=2)
                current_img = improve_image_quality(current_img)
                current_img = current_img.convert("RGBA")
                text_parts.append(f"🔍 Qualidade aumentada para **{current_img.width}×{current_img.height}px** (2×).")

            elif intent == "remove_bg":
                import logging as _logging
                _rembg_log = _logging.getLogger("shopee.rembg")
                t_rembg = _time.time()
                try:
                    from rembg import remove as rembg_remove
                    # ── Resize preventivo para evitar OOM (bad allocation) ──
                    # Imagens > 1280px no maior lado estouram memória do ONNX.
                    # Redimensionamos, processamos e restauramos o tamanho original.
                    orig_size = current_img.size
                    img_for_rembg = current_img.convert("RGB")
                    MAX_SIDE = 1280
                    needs_resize = img_for_rembg.width > MAX_SIDE or img_for_rembg.height > MAX_SIDE
                    if needs_resize:
                        img_for_rembg = img_for_rembg.copy()
                        img_for_rembg.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
                        _rembg_log.info(
                            f"[REMBG] Resize preventivo: {orig_size} → {img_for_rembg.size}"
                        )

                    buf = _io.BytesIO()
                    img_for_rembg.save(buf, format="PNG")
                    no_bg = rembg_remove(buf.getvalue())
                    removed = Image.open(_io.BytesIO(no_bg)).convert("RGBA")

                    # Restaura tamanho original se foi encolhida
                    if removed.size != orig_size:
                        removed = removed.resize(orig_size, Image.LANCZOS)

                    current_img = removed
                    t_elapsed = _time.time() - t_rembg
                    _rembg_log.info(f"[REMBG] Sucesso | tempo={t_elapsed:.1f}s | tamanho_original={orig_size}")
                    text_parts.append("✂️ Fundo removido com sucesso.")
                except Exception as e:
                    t_elapsed = _time.time() - t_rembg
                    _rembg_log.warning(
                        f"[REMBG] Falha | tipo={type(e).__name__} | "
                        f"tempo={t_elapsed:.1f}s | erro={e}"
                    )
                    # ── Fallback explícito: não interrompe o pipeline ────────
                    text_parts.append(
                        f"⚠️ **Remoção de fundo falhou** ({type(e).__name__}). "
                        "Os próximos passos continuarão usando a imagem original. "
                        "Se o cenário foi solicitado, ele será gerado com o fundo atual."
                    )
                    # current_img permanece inalterada → pipeline continua

            elif intent == "generate_scene":
                from backend_core import generate_ai_scenario, generate_gradient_background, apply_contact_shadow
                prompt_map = {
                    "Escolar / Juvenil": "minimalist white geometric podium soft lavender background",
                    "Viagem":            "stone platform outdoors golden hour soft focus",
                    "Profissional / Tech": "sleek white desk surface modern office lighting",
                    "Moda":              "white marble floor fashion studio aesthetic",
                }
                prompt_cenario = prompt_map.get(
                    segmento, "product photography studio white background soft lighting"
                )
                # Garante transparência antes de compor cenário
                img_fg = current_img
                alpha = img_fg.split()[-1] if img_fg.mode == "RGBA" else None
                if alpha is None or alpha.getextrema()[0] == 255:
                    try:
                        from rembg import remove as rembg_remove
                        buf = _io.BytesIO()
                        img_fg.convert("RGB").save(buf, format="PNG")
                        no_bg = rembg_remove(buf.getvalue())
                        img_fg = Image.open(_io.BytesIO(no_bg)).convert("RGBA")
                        if "✂️ Fundo removido" not in " ".join(text_parts):
                            text_parts.append("✂️ Fundo removido automaticamente para compor o cenário.")
                    except Exception:
                        pass

                bg = generate_ai_scenario(prompt_cenario, segmento)
                if not bg:
                    bg = generate_gradient_background(segmento)
                    text_parts.append("🎨 Cenário gradiente gerado (APIs de imagem indisponíveis).")
                else:
                    text_parts.append("🎨 Cenário IA gerado com sucesso!")

                bg = bg.resize((1024, 1024))
                fg = img_fg.copy()
                fg.thumbnail((800, 800))
                offset = (
                    (bg.width - fg.width) // 2,
                    int((bg.height - fg.height) * 0.6),
                )
                bg = apply_contact_shadow(bg, fg, offset)
                bg.paste(fg, offset, fg)
                current_img = bg

            elif intent == "recolor":
                # Extrai nome da cor do pedido do usuário (normalizado para capturar amarela/amarelo, etc.)
                msg_normalized = normalize_message_colors(user_message)
                COLOR_WORDS = [
                    "verde", "azul", "vermelho", "amarelo", "roxo", "lilás",
                    "laranja", "rosa", "ciano", "turquesa", "bege", "marrom",
                    "cinza", "preto", "branco", "green", "blue", "red",
                    "yellow", "purple", "orange", "pink", "gray",
                ]
                target_color = next(
                    (c for c in COLOR_WORDS if c in msg_normalized), "green"
                )
                recolored, ok, recolor_desc = recolor_product_image(
                    current_img, target_color
                )
                current_img = recolored
                text_parts.append(recolor_desc)

            elif intent == "creative_edit":
                from backend_core import creative_edit_with_vision, infer_primary_benefit_with_vision
                
                # ── Lógica especial para Benefício Automático ─────────
                effective_instruction = user_message
                if user_message == "ADICIONAR_BENEFICIO_AUTO":
                    text_parts.append("🔍 Analisando produto para identificar benefício principal...")
                    inference = infer_primary_benefit_with_vision(current_img, full_context, segmento)
                    benefit = inference.get("benefit", "Qualidade Garantida")
                    icon    = inference.get("icon", "✨")
                    effective_instruction = f"adicione um badge com o benefício principal: {icon} {benefit}"
                    text_parts.append(f"💡 Benefício identificado: **{benefit}**")

                edited, desc = creative_edit_with_vision(
                    current_img, effective_instruction, full_context, segmento
                )
                current_img = edited
                text_parts.append(f"✨ {desc}")

            elif intent == "analyze_image":
                from backend_core import analyze_product_image_vision
                feedback = analyze_product_image_vision(
                    current_img.convert("RGB"),
                    user_message,
                    full_context,
                    segmento,
                )
                text_parts.append(feedback)

            elif intent == "generate_variants":
                # Gera variantes e adiciona ao resultado final
                text_parts.append("🌈 Gerando 3 variações de estilo...")
                variants = generate_color_variants(current_img, segmento, n_variants=3)
                for var in variants:
                    processed_images.append(var["image"])
                    captions.append(var["label"])
                # A imagem principal do loop continua sendo current_img

        if "generate_variants" not in intents:
            processed_images.append(current_img)
            cap_parts = []
            if "remove_bg" in intents:   cap_parts.append("✂️ sem fundo")
            if "generate_scene" in intents: cap_parts.append("🎨 cenário IA")
            if "upscale" in intents:     cap_parts.append("🔍 upscale 2×")
            if "recolor" in intents:     cap_parts.append("🌈 variação de cor")
            if "creative_edit" in intents: cap_parts.append("✨ edição criativa")
            if "analyze_image" in intents: cap_parts.append("🔍 análise")
            captions.append(" · ".join(cap_parts) if cap_parts else "Processado")

    result["text"]     = "\n\n".join(text_parts) if text_parts else "✅ Processamento concluído!"
    result["images"]   = processed_images
    result["captions"] = captions
    result["post_actions"] = generate_post_actions(
        intent           = result["intent"],
        has_image_result = bool(processed_images),
    )
    return result


# ══════════════════════════════════════════════════════════════
# FAQ INTELIGENTE — Sugestão automática a partir do histórico
# ══════════════════════════════════════════════════════════════

def suggest_faq_from_history(chat_history: list, shop_name: str, segmento: str = "") -> list:
    """
    Analisa o histórico do chat e extrai pares de pergunta/resposta
    adequados para o FAQ do Seller Centre da Shopee.

    Retorna uma lista de dicts: [{"pergunta": str, "resposta": str}, ...]
    """
    import time as _time

    if not chat_history:
        return []

    # Formata o histórico para o modelo
    historico_txt = ""
    for i, turn in enumerate(chat_history[-20:], 1):  # Últimos 20 turnos
        historico_txt += f"[{i}] Cliente: {turn['user']}\nAssistente: {turn['assistant']}\n\n"

    prompt = f"""Você é um especialista em e-commerce Shopee Brasil.

Analise este histórico de atendimento ao cliente da loja '{shop_name}' (segmento: {segmento or 'geral'}):

{historico_txt}

Extraia as perguntas mais relevantes que os clientes fizeram e transforme-as em pares de FAQ.
REGRAS:
- Selecione de 3 a 6 pares mais úteis
- Cada pergunta: máximo 80 caracteres, linguagem natural
- Cada resposta: máximo 500 caracteres, simpática, em português brasileiro
- Perguntas GENÉRICAS, sem mencionar nomes específicos de produtos
- Se o histórico for sobre processamento de imagens ou otimização de listings, IGNORE — foque em atendimento ao cliente
- Se não houver turnos úteis para FAQ de cliente, retorne lista vazia: []

Responda APENAS com JSON válido, sem markdown, sem explicações:
[
  {{"pergunta": "Texto da pergunta", "resposta": "Texto da resposta"}},
  ...
]
"""

    from backend_core import get_client, MODELOS_TEXTO
    for m in MODELOS_TEXTO:
        try:
            cfg = {"thinking_config": {"thinking_budget": 0}} if ("3.1" in m or "2.5" in m) else {}
            resp = get_client().models.generate_content(
                model=m, contents=[prompt],
                config=cfg if cfg else None
            )
            raw = resp.text.strip()
            # Limpa possível markdown
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            import json as _json
            pares = _json.loads(raw)
            if isinstance(pares, list):
                # Valida e trunca campos
                result = []
                for p in pares:
                    if isinstance(p, dict) and p.get("pergunta") and p.get("resposta"):
                        result.append({
                            "pergunta": str(p["pergunta"])[:80],
                            "resposta": str(p["resposta"])[:500],
                        })
                return result[:6]
        except Exception:
            _time.sleep(2)
            continue

    return []
