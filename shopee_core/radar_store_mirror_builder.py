"""
Build the local store mirror from a shop URL.

The normal Shopee intercept remains the first path. If it returns zero products,
this builder can reuse the Radar Chrome/CDP profile and extract product cards
from the loaded shop page. The saved products flow through radar_store_service,
so each own product becomes available to the Radar.
"""

from __future__ import annotations

import json
from typing import Any

from shopee_core.radar_store_service import get_cached_store_products, save_store_snapshot
from shopee_core.store_connection_service import (
    connect_store,
    mark_store_loaded,
    normalize_shop_slug,
    normalize_shop_url,
)


def _shop_info_from_slug(shop_slug: str, shop_url: str, marketplace: str = "shopee") -> dict:
    return {
        "shop_uid": None,
        "shop_slug": shop_slug,
        "shop_name": shop_slug,
        "marketplace": marketplace,
        "source_url": shop_url,
    }


def _extract_shop_data(shop_raw: Any, shop_slug: str, shop_url: str, marketplace: str) -> dict:
    if isinstance(shop_raw, dict):
        data = shop_raw.get("data", shop_raw)
        if isinstance(data, dict) and data:
            return {
                "shop_uid": data.get("shopid") or data.get("shop_id"),
                "shop_slug": data.get("username") or data.get("account", {}).get("username") or shop_slug,
                "shop_name": data.get("name") or data.get("shop_name") or shop_slug,
                "marketplace": marketplace,
                "source_url": shop_url,
                **data,
            }
    return _shop_info_from_slug(shop_slug, shop_url, marketplace)


def _coerce_product(raw: dict, shop_slug: str, shop_uid: str | None = None) -> dict | None:
    if not isinstance(raw, dict):
        return None
    itemid = raw.get("itemid") or raw.get("item_id") or raw.get("id")
    shopid = raw.get("shopid") or raw.get("shop_id") or shop_uid
    title = raw.get("name") or raw.get("title") or raw.get("nome")
    url = raw.get("url") or raw.get("canonical_url") or raw.get("product_url")
    if not title and not itemid:
        return None
    if not title:
        title = f"Produto {itemid}"
    if not url and itemid and shopid:
        url = f"https://shopee.com.br/i.{shopid}.{itemid}"
    image = raw.get("image") or raw.get("image_url") or raw.get("thumbnail") or raw.get("cover") or ""
    price = raw.get("price") or raw.get("preco") or raw.get("valor") or 0
    return {
        **raw,
        "itemid": itemid,
        "shopid": shopid,
        "name": title,
        "title": title,
        "price": price,
        "image": image,
        "image_url": image,
        "canonical_url": url,
        "marketplace": "shopee",
        "shop_slug": shop_slug,
    }


def _dedupe_products(products: list[dict], shop_slug: str, shop_uid: str | None = None) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for raw in products or []:
        item = _coerce_product(raw, shop_slug=shop_slug, shop_uid=shop_uid)
        if not item:
            continue
        key = str(item.get("itemid") or item.get("canonical_url") or item.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _collect_products_via_scraping(shop_slug: str) -> tuple[dict, list[dict], list[str]]:
    warnings: list[str] = []
    try:
        from backend_core import fetch_shop_info, fetch_shop_products_intercept

        shop_raw = fetch_shop_info(shop_slug)
        shop_data = shop_raw.get("data", shop_raw) if isinstance(shop_raw, dict) else {}
        shop_uid = shop_data.get("shopid") or shop_data.get("shop_id") if isinstance(shop_data, dict) else None
        products = fetch_shop_products_intercept(shop_slug, shop_uid)
        if not shop_data and products:
            warnings.append("Metadados da loja indisponiveis; produtos foram coletados pela vitrine.")
        return shop_data or {}, products or [], warnings
    except Exception as exc:
        warnings.append(f"Scraping da loja falhou: {exc}")
        return {}, [], warnings


def _collect_products_via_cdp(
    shop_url: str,
    shop_slug: str,
    cdp_url: str = "http://127.0.0.1:9222",
    max_products: int = 100,
) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    try:
        from shopee_core.radar_cdp_service import ensure_radar_chrome_ready

        chrome = ensure_radar_chrome_ready(cdp_url)
        if not chrome.get("ok"):
            return [], [chrome.get("message") or "Chrome do Radar/CDP indisponivel."]
    except Exception as exc:
        return [], [f"Falha ao abrir Chrome do Radar: {exc}"]

    script = f"""
import asyncio, json, re, sys
from playwright.async_api import async_playwright

SHOP_URL = {json.dumps(shop_url)}
SHOP_SLUG = {json.dumps(shop_slug)}
CDP_URL = {json.dumps(cdp_url)}
MAX_PRODUCTS = {int(max_products)}

def normalize_price(value):
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return value / 100000 if value > 1000 else value
    text = str(value).replace("R$", "").replace("\\xa0", " ").strip()
    if not text:
        return 0
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return 0

def from_card(card):
    iid = card.get("itemid") or card.get("item_id")
    sid = card.get("shopid") or card.get("shop_id")
    asset = card.get("item_card_displayed_asset") or card.get("displayed_asset") or {{}}
    title = asset.get("name") or card.get("name") or card.get("title")
    image = asset.get("image") or asset.get("cover") or asset.get("thumbnail") or ""
    images = asset.get("images") or asset.get("image_list") or []
    if not image and images:
        image = images[0]
    price = 0
    for key in ("item_card_display_price", "price_obj", "price_info"):
        value = card.get(key)
        if isinstance(value, dict):
            price = value.get("price") or value.get("current_price") or value.get("min_price") or 0
            if price:
                break
    if not price:
        price = card.get("price") or card.get("price_min") or card.get("price_max") or 0
    if not title and not iid:
        return None
    return {{
        "itemid": iid,
        "shopid": sid,
        "name": title or f"Produto {{iid}}",
        "title": title or f"Produto {{iid}}",
        "price": normalize_price(price),
        "image": image,
        "image_url": image,
        "canonical_url": f"https://shopee.com.br/i.{{sid}}.{{iid}}" if sid and iid else "",
        "source": "cdp_response",
    }}

async def run():
    products = []
    seen = set()

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0] if browser.contexts else await browser.new_context(locale="pt-BR")
        page = await context.new_page()

        async def add_product(item):
            if not item:
                return
            key = str(item.get("itemid") or item.get("canonical_url") or item.get("name") or "").lower()
            if not key or key in seen:
                return
            seen.add(key)
            products.append(item)

        async def handle_response(response):
            if response.request.method == "OPTIONS":
                return
            url = response.url
            if "rcmd_items" not in url and "shop_page" not in url and "search_items" not in url:
                return
            try:
                data = await response.json()
                containers = [
                    data.get("data", {{}}).get("centralize_item_card", {{}}).get("item_cards", []),
                    data.get("data", {{}}).get("items", []),
                    data.get("items", []),
                ]
                for group in containers:
                    if not isinstance(group, list):
                        continue
                    for card in group:
                        if isinstance(card, dict) and "item_basic" in card:
                            card = card.get("item_basic") or card
                        await add_product(from_card(card or {{}}))
                        if len(products) >= MAX_PRODUCTS:
                            return
            except Exception as exc:
                print(f"response parse error: {{exc}}", file=sys.stderr)

        page.on("response", handle_response)
        try:
            await page.goto(SHOP_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            print(f"goto error: {{exc}}", file=sys.stderr)

        for _ in range(10):
            if len(products) >= MAX_PRODUCTS:
                break
            await page.mouse.wheel(0, 900)
            await asyncio.sleep(1.0)

        if len(products) < 1:
            anchors = await page.locator("a[href*='-i.'], a[href*='/i.']").evaluate_all('''
            els => els.slice(0, 120).map(a => {{
                const text = (a.innerText || a.textContent || '').trim();
                const img = a.querySelector('img');
                const priceMatch = text.match(/R\\$\\s*[0-9.,]+/);
                const href = a.href || '';
                const itemMatch = href.match(/(?:-|\\.)i\\.(\\d+)\\.(\\d+)/);
                return {{
                    name: text.split('\\n').find(Boolean) || (img && img.alt) || '',
                    title: text.split('\\n').find(Boolean) || (img && img.alt) || '',
                    price: priceMatch ? priceMatch[0] : 0,
                    image: img ? (img.currentSrc || img.src || '') : '',
                    image_url: img ? (img.currentSrc || img.src || '') : '',
                    canonical_url: href,
                    shopid: itemMatch ? itemMatch[1] : '',
                    itemid: itemMatch ? itemMatch[2] : '',
                    source: 'cdp_dom'
                }};
            }})
            ''')
            for item in anchors:
                await add_product(item)
                if len(products) >= MAX_PRODUCTS:
                    break

        await page.close()
        print(json.dumps(products[:MAX_PRODUCTS], ensure_ascii=False))

asyncio.run(run())
"""
    try:
        from backend_core import playwright_intercept

        result = playwright_intercept(script)
        if isinstance(result, list):
            return result, warnings
        warnings.append("CDP nao retornou lista de produtos.")
    except Exception as exc:
        warnings.append(f"Coleta via CDP falhou: {exc}")
    return [], warnings


def build_store_mirror_from_url(
    shop_url: str,
    marketplace: str = "shopee",
    browser_mode: str = "cdp",
    cdp_url: str = "http://127.0.0.1:9222",
    max_products: int = 100,
) -> dict:
    """Connect the store, collect products, save the mirror and activate it."""
    warnings: list[str] = []
    normalized_url = normalize_shop_url(shop_url, marketplace=marketplace)
    shop_slug = normalize_shop_slug(normalized_url)
    if not shop_slug:
        return {
            "ok": False,
            "status": "invalid_url",
            "store_uid": None,
            "products_found": 0,
            "products_saved": 0,
            "source": "none",
            "warnings": ["URL de loja invalida."],
        }

    connection = connect_store(normalized_url, marketplace=marketplace)
    store_uid = connection.get("store_uid")

    shop_data_raw, products_raw, scrape_warnings = _collect_products_via_scraping(shop_slug)
    warnings.extend(scrape_warnings)
    shop_data = _extract_shop_data(shop_data_raw, shop_slug, normalized_url, marketplace)
    products = _dedupe_products(
        products_raw,
        shop_slug=shop_slug,
        shop_uid=str(shop_data.get("shop_uid") or shop_data.get("shopid") or ""),
    )
    source = "scraping" if products else "none"

    if not products and browser_mode == "cdp":
        cdp_products, cdp_warnings = _collect_products_via_cdp(
            normalized_url,
            shop_slug=shop_slug,
            cdp_url=cdp_url,
            max_products=max_products,
        )
        warnings.extend(cdp_warnings)
        products = _dedupe_products(
            cdp_products,
            shop_slug=shop_slug,
            shop_uid=str(shop_data.get("shop_uid") or shop_data.get("shopid") or ""),
        )
        if products:
            source = "cdp"

    if not products and store_uid:
        cached = get_cached_store_products(store_uid=store_uid)
        if cached:
            mark_store_loaded(store_uid)
            return {
                "ok": True,
                "status": "cache_used",
                "store_uid": store_uid,
                "products_found": len(cached),
                "products_saved": 0,
                "source": "mirror_cache",
                "products": cached[:max_products],
                "shop": shop_data,
                "warnings": warnings + ["Usei o espelho local existente porque a coleta retornou 0 produtos."],
            }

    if not products:
        return {
            "ok": False,
            "status": "no_products",
            "store_uid": store_uid,
            "products_found": 0,
            "products_saved": 0,
            "source": source,
            "products": [],
            "shop": shop_data,
            "warnings": warnings + ["Nao encontrei produtos para salvar no espelho."],
        }

    summary = save_store_snapshot(shop_data, products[:max_products], source=f"store_mirror_builder:{source}")
    store_uid = summary.get("store_uid") or store_uid
    if store_uid:
        mark_store_loaded(store_uid, mirror_at=summary.get("updated_at"))

    cached_products = get_cached_store_products(store_uid=store_uid) if store_uid else products
    return {
        "ok": True,
        "status": "mirrored",
        "store_uid": store_uid,
        "products_found": len(products),
        "products_saved": summary.get("created", 0) + summary.get("updated", 0) + summary.get("unchanged", 0),
        "source": source,
        "products": cached_products[:max_products],
        "shop": shop_data,
        "summary": summary,
        "warnings": warnings,
    }
