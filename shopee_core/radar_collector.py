"""
shopee_core/radar_collector.py - Assisted product page collector for Radar R2.

This collector opens a visible Chromium browser with a persistent local profile.
It is transparent by design: if a marketplace asks for login, captcha or manual
verification, the user solves it in the browser. There is no stealth, bypass or
anti-bot circumvention here.
"""

from __future__ import annotations

import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Callable

from .radar_browser_service import DEFAULT_CDP_URL, connect_to_cdp_browser
from .radar_service import (
    add_product_asset,
    detect_marketplace,
    get_pending_jobs,
    mark_job_done,
    mark_job_failed,
    mark_job_running,
    mark_product_collected,
    mark_product_failed,
    normalize_product_url,
)


BASE_DIR = Path(__file__).resolve().parent.parent
BROWSER_PROFILE_DIR = BASE_DIR / "data" / "browser_profile"
MAX_PRODUCT_IMAGE_URLS = 20
MAX_WARNING_IMAGE_URLS = 30
MAX_ERROR_IMAGE_URLS = 80
MAX_ASSET_IMAGES_PER_PRODUCT = 5
ASSET_IMAGE_TIMEOUT_SECONDS = 5.0
ASSET_TOTAL_TIMEOUT_SECONDS = 30.0
GENERIC_PRODUCT_TITLES = {
    "mochilas",
    "mochila",
    "produtos",
    "produto",
    "mercado livre",
    "resultado de busca",
    "resultados de busca",
    "ofertas",
}


def parse_price(text: str) -> float | None:
    """Parse common Brazilian and decimal price formats."""
    if not text:
        return None

    normalized_text = text.replace("\xa0", " ").strip()
    match = re.search(
        r"(?:R\$\s*)?(\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})|\d+(?:[.,]\d{2})?)",
        normalized_text,
    )
    if not match:
        return None

    value = match.group(1).replace(" ", "")

    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif "." in value:
        parts = value.split(".")
        if len(parts[-1]) == 3 and all(part.isdigit() for part in parts):
            value = "".join(parts)

    try:
        return float(value)
    except ValueError:
        return None


def normalize_image_urls(urls: list[str]) -> list[str]:
    """Remove empty, duplicate and non-downloadable media URLs."""
    normalized = []
    seen = set()

    for url in urls or []:
        if not url:
            continue

        clean_url = str(url).strip()
        if not clean_url:
            continue
        if clean_url.startswith("//"):
            clean_url = "https:" + clean_url
        if clean_url.startswith(("data:", "blob:")):
            continue
        if not clean_url.startswith(("http://", "https://")):
            continue

        dedupe_key = clean_url.rstrip("/")
        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        normalized.append(clean_url)

    return normalized


def filter_product_image_urls(image_urls: list[str]) -> list[str]:
    """Keep likely product images, deduplicate them and cap noisy captures."""
    filtered = []
    seen_keys = set()

    for url in normalize_image_urls(image_urls or []):
        lowered = url.lower()
        if _looks_like_layout_image_url(lowered):
            continue

        image_key = _product_image_key(url) or url.rstrip("/")
        if image_key in seen_keys:
            continue

        seen_keys.add(image_key)
        filtered.append(url)
        if len(filtered) >= MAX_PRODUCT_IMAGE_URLS:
            break

    return filtered


def is_plausible_price(price: float | None, category_hint: str | None = None) -> bool:
    """Return True when a price looks usable for pattern analysis."""
    value = _coerce_float(price)
    if value is None:
        return False

    hint = _normalize_text(category_hint or "")
    if hint == "mochila" or "mochila" in hint:
        return 20 <= value <= 1500

    return 10 <= value <= 5000


def validate_product_extraction(data: dict, expected_marketplace: str) -> dict:
    """Validate whether extracted data looks like a real product page."""
    warnings: list[str] = []
    errors: list[str] = []

    if not isinstance(data, dict):
        return {
            "ok": False,
            "quality_score": 0.0,
            "warnings": [],
            "errors": ["Dados coletados nao sao um dict."],
        }

    marketplace = data.get("marketplace")
    if expected_marketplace and marketplace != expected_marketplace:
        errors.append(
            f"Marketplace inesperado: {marketplace or 'vazio'}; esperado {expected_marketplace}."
        )

    if is_collection_blocked_or_empty(data):
        errors.append("Pagina parece login/verificacao, bloqueio ou coleta vazia.")

    title = data.get("title")
    if not _clean_text(title):
        errors.append("Titulo vazio.")
    elif _is_generic_product_title(title):
        errors.append(f"Titulo generico demais: {title}.")

    canonical_url = data.get("canonical_url") or data.get("url")
    if not _looks_like_product_url(canonical_url, expected_marketplace or marketplace):
        errors.append("URL canonica nao parece pagina individual de produto.")

    category_hint = _category_hint_from_data(data)
    price = _coerce_float(data.get("price"))
    if not is_plausible_price(price, category_hint=category_hint):
        errors.append(
            f"Preco suspeito para {category_hint or 'marketplace'}: {price}."
        )

    image_count = len(data.get("image_urls") or [])
    description_image_count = len(data.get("description_image_urls") or [])
    total_image_count = image_count + description_image_count
    if image_count > MAX_WARNING_IMAGE_URLS:
        warnings.append(f"Imagens principais demais: {image_count}.")
    if total_image_count > MAX_ERROR_IMAGE_URLS:
        errors.append(f"Assets/imagens demais para um produto: {total_image_count}.")

    quality_score = 1.0
    quality_score -= min(0.75, len(errors) * 0.25)
    quality_score -= min(0.25, len(warnings) * 0.05)
    quality_score = round(max(0.0, quality_score), 4)

    return {
        "ok": not errors,
        "quality_score": quality_score,
        "warnings": warnings,
        "errors": errors,
    }


def _quality_error_message(quality: dict) -> str:
    errors = quality.get("errors") or []
    if not errors:
        return "Coleta de baixa qualidade."
    return "Coleta de baixa qualidade: " + "; ".join(str(error) for error in errors[:4])


def collect_product_page(
    url: str,
    marketplace: str | None = None,
    interactive: bool = False,
    interactive_wait_seconds: int | None = None,
    browser_channel: str | None = None,
    browser_mode: str = "persistent",
    cdp_url: str = DEFAULT_CDP_URL,
    candidate_uid: str | None = None,
    job_uid: str | None = None,
    url_start_time: float | None = None,
    collect_image_urls: bool = True,
) -> dict:
    """Open a visible browser, collect one product page and return normalized data."""
    if url_start_time is None:
        url_start_time = time.monotonic()

    canonical_url = normalize_product_url(url)
    detected_marketplace = marketplace or detect_marketplace(canonical_url)
    browser_mode = _normalize_browser_mode(browser_mode)
    fast_primary_collection = not collect_image_urls

    if detected_marketplace == "unknown":
        raise ValueError(
            "Marketplace unknown nao tem coletor R2. Cadastre URLs da Shopee "
            "ou Mercado Livre nesta fase."
        )

    if detected_marketplace not in {"shopee", "mercadolivre"}:
        raise ValueError(f"Marketplace nao suportado na R2: {detected_marketplace}")

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright nao esta instalado. Instale com 'pip install playwright' "
            "e rode 'python -m playwright install chromium'."
        ) from exc

    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    manual_wait_ms = _manual_wait_seconds() * 1000

    with sync_playwright() as playwright:
        browser = None
        if browser_mode == "cdp":
            browser, context, page = connect_to_cdp_browser(playwright, cdp_url=cdp_url)
        else:
            context = playwright.chromium.launch_persistent_context(
                **_browser_context_options(browser_channel=browser_channel)
            )
            page = context.pages[0] if context.pages else context.new_page()

        # Set default Playwright timeouts
        page.set_default_timeout(5000)
        page.set_default_navigation_timeout(30000)

        try:
            try:
                print(f"[R7.2D] OPENING url={canonical_url}", flush=True)
                page.goto(canonical_url, wait_until="domcontentloaded", timeout=30000)
            except PlaywrightTimeoutError:
                page.goto(canonical_url, wait_until="load", timeout=30000)

            print("[R7.2D] LOADED", flush=True)

            if time.monotonic() - url_start_time > 90:
                raise TimeoutError("total_per_url_timeout_after_90s")

            # Check 1: immediately after load
            if _needs_manual_intervention(page):
                raise RuntimeError("blocked_or_login_required")

            if manual_wait_ms > 0:
                page.wait_for_timeout(manual_wait_ms)

            # Check 2: before scroll
            if _needs_manual_intervention(page):
                raise RuntimeError("blocked_or_login_required")

            print("[R7.2D] SCROLLING", flush=True)
            scroll_product_page(page)

            if time.monotonic() - url_start_time > 90:
                raise TimeoutError("total_per_url_timeout_after_90s")

            # Check 3: after scroll (and BEFORE extraction!)
            if _needs_manual_intervention(page):
                raise RuntimeError("blocked_or_login_required")

            print("[R7.2D] EXTRACTING", flush=True)
            if detected_marketplace == "shopee":
                data = collect_shopee_product(
                    page,
                    canonical_url,
                    url_start_time=url_start_time,
                    collect_image_urls=collect_image_urls,
                )
            else:
                data = collect_mercadolivre_product(
                    page,
                    canonical_url,
                    url_start_time=url_start_time,
                    collect_image_urls=collect_image_urls,
                )
            data = _finalize_collected_data(data, detected_marketplace)

            if fast_primary_collection:
                print("[R7.2F] FAST_PRIMARY_READY", flush=True)
                return data

            if time.monotonic() - url_start_time > 90:
                raise TimeoutError("total_per_url_timeout_after_90s")

            # Check 4: after extraction / empty data retry
            if _needs_manual_intervention(page) or _needs_interactive_retry(data):
                if _needs_manual_intervention(page):
                    raise RuntimeError("blocked_or_login_required")

                if interactive or browser_mode == "cdp":
                    _wait_for_manual_confirmation(
                        page,
                        _empty_data_retry_message(browser_mode),
                        timeout_seconds=interactive_wait_seconds,
                    )
                    _reload_product_page(page, canonical_url, PlaywrightTimeoutError)
                    scroll_product_page(page)

                    if time.monotonic() - url_start_time > 90:
                        raise TimeoutError("total_per_url_timeout_after_90s")

                    if detected_marketplace == "shopee":
                        data = collect_shopee_product(
                            page,
                            canonical_url,
                            url_start_time=url_start_time,
                            collect_image_urls=collect_image_urls,
                        )
                    else:
                        data = collect_mercadolivre_product(
                            page,
                            canonical_url,
                            url_start_time=url_start_time,
                            collect_image_urls=collect_image_urls,
                        )
                    data = _finalize_collected_data(data, detected_marketplace)

            return data
        except Exception as e:
            # Capture best-effort debug screenshot on failure
            try:
                import datetime
                from pathlib import Path
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                cand_name = candidate_uid if candidate_uid else "unknown"
                job_name = job_uid if job_uid else "nojob"
                screenshot_dir = Path("data") / "radar_debug" / "screenshots"
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                
                screenshot_path = screenshot_dir / f"{cand_name}_{job_name}_{ts}.png"
                page.screenshot(path=str(screenshot_path), timeout=5000)
                print(f"[R7.2D] SCREENSHOT_SAVED path={screenshot_path}", flush=True)
                
                try:
                    e.screenshot_path = str(screenshot_path)
                except Exception:
                    pass
            except Exception as ss_err:
                print(f"[R7.2D] SCREENSHOT_ERROR error={ss_err}", flush=True)
            raise e
        finally:
            if browser_mode == "cdp":
                # Closing a CDP tab can hang on busy marketplace pages and block
                # persistence. Let the Playwright CDP connection drop instead.
                print("[R7.2F] CDP_PAGE_RELEASED", flush=True)
                browser = None
            else:
                try:
                    context.close()
                except Exception:
                    pass


def collect_shopee_product(
    page,
    url: str,
    url_start_time: float | None = None,
    collect_image_urls: bool = True,
) -> dict:
    """Collect basic Shopee product data from an already loaded page."""
    extract_start = time.monotonic()
    if url_start_time is None:
        url_start_time = extract_start

    current_stage = "Extraindo título e preço"
    try:
        # Check block before starting extraction
        if _needs_manual_intervention(page):
            raise RuntimeError("blocked_or_login_required")

        print("[R7.2D] EXTRACTING_TITLE_PRICE", flush=True)
        body_text = _body_text(page)
        visual_title = (
            _first_text(
                page,
                [
                    "h1",
                    "[data-sqe='name']",
                    "section h1",
                    "div[class*='product-briefing'] h1",
                ],
            )
            or _first_meta(page, ["meta[property='og:title']", "meta[name='title']"])
        )
        title = visual_title
        if not title:
            title = _extract_title_from_url(url)

        price_text = (
            _first_meta(page, ["meta[property='product:price:amount']"])
            or _first_text(
                page,
                [
                    "[data-testid='product-price']",
                    "div[class*='price']",
                    "section div:has-text('R$')",
                ],
            )
            or _first_price_text(body_text)
        )
        parsed_price = parse_price(price_text or "")

        if time.monotonic() - extract_start > 25:
            raise TimeoutError("extract_timeout_after_25s")
        if time.monotonic() - url_start_time > 90:
            raise TimeoutError("total_per_url_timeout_after_90s")

        # If both title and price are missing, return early
        if not visual_title and parsed_price is None:
            return _result(
                url=url,
                marketplace="shopee",
                title=None,
                price=None,
                shop_name=None,
                rating=None,
                review_count=None,
                sold_count=None,
                description=None,
                image_urls=[],
                video_urls=[],
                raw={"error": "Dados mínimos não encontrados (título e preço vazios)"}
            )

        current_stage = "Extraindo descrição"
        if not collect_image_urls:
            print("[R7.2F] SKIPPING_OPTIONAL_DETAILS reason=fast_primary_collection", flush=True)
            meta_image = _first_meta(page, ["meta[property='og:image']", "meta[name='twitter:image']"])
            image_urls = normalize_image_urls([meta_image] if meta_image else [])
            return _result(
                url=url,
                marketplace="shopee",
                title=title,
                price=parsed_price,
                shop_name=None,
                rating=_parse_rating(body_text),
                review_count=_parse_count_near_keywords(body_text, ["avaliacoes", "avaliacao", "reviews"]),
                sold_count=_parse_count_near_keywords(body_text, ["vendidos", "vendido"]),
                description=None,
                image_urls=image_urls,
                video_urls=[],
                raw={
                    "page_title": _page_title(page),
                    "price_text": price_text,
                    "body_excerpt": body_text[:3000],
                    "optional_details_status": "skipped_fast_primary_collection",
                },
            )

        print("[R7.2D] EXTRACTING_DESC", flush=True)
        shop_name = _first_text_quick(
            page,
            [
                "[data-testid='shop-name']",
                "a[href*='/shop/']",
                "a[href*='shopee.com.br/'] span",
                "div[class*='shop'] a",
            ],
        )
        description = _first_text_quick(
            page,
            [
                "[data-testid='product-description']",
                "div[class*='product-detail']",
            ],
        )

        if time.monotonic() - extract_start > 25:
            raise TimeoutError("extract_timeout_after_25s")
        if time.monotonic() - url_start_time > 90:
            raise TimeoutError("total_per_url_timeout_after_90s")

        image_urls = []
        video_urls = []
        if collect_image_urls:
            current_stage = "Coletando URLs de imagens"
            print("[R7.2E] EXTRACTING_IMAGE_URLS", flush=True)
            image_urls, video_urls = _collect_media_urls(page)
        else:
            meta_image = _first_meta(page, ["meta[property='og:image']", "meta[name='twitter:image']"])
            image_urls = normalize_image_urls([meta_image] if meta_image else [])
        rating_text = _first_text(
            page,
            [
                "[data-testid='product-rating']",
                "div[class*='rating']",
                "section:has-text('estrelas')",
            ],
        )

        if time.monotonic() - extract_start > 25:
            raise TimeoutError("extract_timeout_after_25s")
        if time.monotonic() - url_start_time > 90:
            raise TimeoutError("total_per_url_timeout_after_90s")

        return _result(
            url=url,
            marketplace="shopee",
            title=title,
            price=parsed_price,
            shop_name=shop_name,
            rating=_parse_rating(rating_text or body_text),
            review_count=_parse_count_near_keywords(body_text, ["avaliacoes", "avaliacao", "reviews"]),
            sold_count=_parse_count_near_keywords(body_text, ["vendidos", "vendido"]),
            description=description,
            image_urls=image_urls,
            video_urls=video_urls,
            raw={
                "page_title": _page_title(page),
                "price_text": price_text,
                "rating_text": rating_text,
                "body_excerpt": body_text[:3000],
            },
        )
    except Exception as e:
        try:
            e.stage = current_stage
        except Exception:
            pass
        raise e


def collect_mercadolivre_product(
    page,
    url: str,
    url_start_time: float | None = None,
    collect_image_urls: bool = True,
) -> dict:
    """Collect deep Mercado Livre product data from an already loaded page."""
    extract_start = time.monotonic()
    if url_start_time is None:
        url_start_time = extract_start

    current_stage = "Extraindo título e preço"
    try:
        # Check block before starting extraction
        if _needs_manual_intervention(page):
            raise RuntimeError("blocked_or_login_required")

        print("[R7.2D] EXTRACTING_TITLE_PRICE", flush=True)
        body_text = _body_text(page)
        page_title = _page_title(page)
        json_ld_product = _extract_json_ld_product(page)
        visual_title = _best_product_title(
            [
                _first_text(page, ["h1.ui-pdp-title", "[data-testid='title']"]),
                json_ld_product.get("name"),
                _first_meta(page, ["meta[property='og:title']", "meta[name='title']"]),
                _first_text(page, ["h1"]),
                page_title.split("|")[0].strip() if page_title else None,
            ]
        )
        if _looks_like_intervention_title(visual_title) and page_title:
            visual_title = page_title.split("|")[0].strip()
        title = visual_title
        if not title:
            title = _extract_title_from_url(url)
        json_ld_price = _coerce_float(json_ld_product.get("price"))
        price_text = (
            _first_meta(page, ["meta[itemprop='price']", "meta[property='product:price:amount']"])
            or _first_text(
                page,
                [
                    ".ui-pdp-price .andes-money-amount",
                    "[data-testid='price-part']",
                    "div.ui-pdp-price",
                    "span.andes-money-amount",
                    ".ui-search-price__second-line .andes-money-amount__fraction",
                    ".andes-price__fraction",
                    ".price-tag-fraction",
                ],
            )
            or _first_price_text(body_text)
        )
        parsed_price = json_ld_price if json_ld_price is not None else parse_price(price_text or "")

        if time.monotonic() - extract_start > 25:
            raise TimeoutError("extract_timeout_after_25s")
        if time.monotonic() - url_start_time > 90:
            raise TimeoutError("total_per_url_timeout_after_90s")

        # If both title and price are missing, return early
        if not visual_title and parsed_price is None:
            return _result(
                url=url,
                marketplace="mercadolivre",
                title=None,
                price=None,
                shop_name=None,
                rating=None,
                review_count=None,
                sold_count=None,
                description=None,
                image_urls=[],
                video_urls=[],
                raw={"error": "Dados mínimos não encontrados (título e preço vazios)"}
            )

        current_stage = "Extraindo descrição"
        if not collect_image_urls:
            print("[R7.2F] SKIPPING_OPTIONAL_DETAILS reason=fast_primary_collection", flush=True)
            image_urls = filter_product_image_urls(
                _normalize_mercadolivre_image_urls(json_ld_product.get("image_urls") or [])
            )
            rating = _parse_rating(body_text)
            review_count = _parse_count_near_keywords(body_text, ["avaliacoes", "avaliacao", "opinioes"])
            sold_count = _parse_count_near_keywords(body_text, ["vendidos", "vendido"])
            raw = {
                "page_title": page_title,
                "price_text": price_text,
                "title": _clean_text(title),
                "price": parsed_price,
                "rating": rating,
                "review_count": review_count,
                "sold_count": sold_count,
                "image_urls": filter_product_image_urls(image_urls),
                "json_ld_product": json_ld_product,
                "body_excerpt": body_text[:5000],
                "optional_details_status": "skipped_fast_primary_collection",
            }
            data = _result(
                url=url,
                marketplace="mercadolivre",
                title=title,
                price=parsed_price,
                shop_name=None,
                rating=rating,
                review_count=review_count,
                sold_count=sold_count,
                description=None,
                image_urls=image_urls,
                video_urls=[],
                raw=raw,
            )
            data.update(
                {
                    "description_image_urls": [],
                    "attributes": {},
                    "category_path": [],
                    "variation_labels": [],
                }
            )
            return data

        print("[R7.2D] EXTRACTING_DESC", flush=True)
        original_price_text = _first_text_quick(
            page,
            [
                ".ui-pdp-price__original-value",
                ".andes-money-amount--previous",
                "s.andes-money-amount",
            ],
        )
        discount_text = _first_text_quick(
            page,
            [
                ".andes-money-amount__discount",
                ".ui-pdp-price__second-line__label",
            ],
        )
        shop_name = _first_text_quick(
            page,
            [
                ".ui-pdp-seller__header__title",
                ".ui-pdp-seller__link-trigger",
                "a[href*='/perfil/']",
                "a[href*='/loja/']",
            ],
        )
        seller_reputation = _extract_seller_reputation(page, body_text)
        description = _first_text_quick(
            page,
            [
                "#description",
                ".ui-pdp-description",
                "[data-testid='content']",
            ],
        )

        if time.monotonic() - extract_start > 25:
            raise TimeoutError("extract_timeout_after_25s")
        if time.monotonic() - url_start_time > 90:
            raise TimeoutError("total_per_url_timeout_after_90s")

        image_urls = []
        video_urls = []
        description_image_urls = []
        if collect_image_urls:
            current_stage = "Coletando URLs de imagens"
            print("[R7.2E] EXTRACTING_IMAGE_URLS", flush=True)
            image_urls, video_urls = _collect_media_urls(page)
            gallery_image_urls = (
                _collect_mercadolivre_gallery_image_urls(page)
                or json_ld_product.get("image_urls")
                or []
            )
            if gallery_image_urls:
                image_urls = filter_product_image_urls(_normalize_mercadolivre_image_urls(gallery_image_urls))
            else:
                image_urls = filter_product_image_urls(_normalize_mercadolivre_image_urls(image_urls))
            description_image_urls = filter_product_image_urls(_collect_description_image_urls(page))
        else:
            image_urls = filter_product_image_urls(
                _normalize_mercadolivre_image_urls(json_ld_product.get("image_urls") or [])
            )
        if time.monotonic() - extract_start > 25:
            raise TimeoutError("extract_timeout_after_25s")
        if time.monotonic() - url_start_time > 90:
            raise TimeoutError("total_per_url_timeout_after_90s")

        attributes = _extract_mercadolivre_attributes(page)
        if time.monotonic() - extract_start > 25:
            raise TimeoutError("extract_timeout_after_25s")
        if time.monotonic() - url_start_time > 90:
            raise TimeoutError("total_per_url_timeout_after_90s")

        category_path = _extract_category_path(page)
        if time.monotonic() - extract_start > 25:
            raise TimeoutError("extract_timeout_after_25s")
        if time.monotonic() - url_start_time > 90:
            raise TimeoutError("total_per_url_timeout_after_90s")

        variation_labels = _extract_variation_labels(page)
        rating = _parse_rating(body_text)
        review_count = _parse_count_near_keywords(body_text, ["avaliacoes", "avaliacao", "opinioes"])
        sold_count = _parse_count_near_keywords(body_text, ["vendidos", "vendido"])
        original_price = parse_price(original_price_text or "")
        discount_percent = _parse_discount_percent(discount_text or body_text)

        if time.monotonic() - extract_start > 25:
            raise TimeoutError("extract_timeout_after_25s")
        if time.monotonic() - url_start_time > 90:
            raise TimeoutError("total_per_url_timeout_after_90s")

        raw = {
            "page_title": page_title,
            "price_text": price_text,
            "original_price_text": original_price_text,
            "discount_text": discount_text,
            "title": _clean_text(title),
            "price": parsed_price,
            "original_price": original_price,
            "discount_percent": discount_percent,
            "shop_name": _clean_text(shop_name),
            "seller_reputation": seller_reputation,
            "rating": rating,
            "review_count": review_count,
            "sold_count": sold_count,
            "description": _clean_text(description),
            "attributes": attributes,
            "category_path": category_path,
            "image_urls": filter_product_image_urls(image_urls),
            "description_image_urls": filter_product_image_urls(description_image_urls),
            "variation_labels": variation_labels,
            "json_ld_product": json_ld_product,
            "body_excerpt": body_text[:5000],
        }

        data = _result(
            url=url,
            marketplace="mercadolivre",
            title=title,
            price=parsed_price,
            shop_name=shop_name,
            rating=rating,
            review_count=review_count,
            sold_count=sold_count,
            description=description,
            image_urls=image_urls,
            video_urls=video_urls,
            raw=raw,
        )
        data.update(
            {
                "original_price": original_price,
                "discount_percent": discount_percent,
                "seller_reputation": seller_reputation,
                "attributes": attributes,
                "category_path": category_path,
                "description_image_urls": filter_product_image_urls(description_image_urls),
                "variation_labels": variation_labels,
            }
        )
        return data
    except Exception as e:
        try:
            e.stage = current_stage
        except Exception:
            pass
        raise e


def scroll_product_page(page) -> None:
    """Scroll gradually to trigger lazy images and visible description content."""
    for _ in range(8):
        try:
            page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 0.8))")
        except Exception:
            page.wait_for_timeout(1000)
            continue
        page.wait_for_timeout(700)
    try:
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    page.wait_for_timeout(500)


def collect_pending_jobs(
    limit: int = 5,
    collector_func: Callable[[str], dict] | None = None,
    save_assets_to_disk: bool = False,
    browser_channel: str | None = None,
    browser_mode: str = "persistent",
    cdp_url: str = DEFAULT_CDP_URL,
) -> dict:
    """Collect pending radar jobs and persist product data/assets."""
    if collector_func:
        collector = collector_func
    else:
        collector = lambda url: collect_product_page(
            url,
            browser_channel=browser_channel,
            browser_mode=browser_mode,
            cdp_url=cdp_url,
        )
    jobs = get_pending_jobs(limit=limit)
    summary = {
        "total": len(jobs),
        "done": 0,
        "failed": 0,
        "results": [],
    }

    for job in jobs:
        job_uid = job["job_uid"]
        product_uid = job["product_uid"]

        try:
            running_job = mark_job_running(job_uid)
            data = collector(running_job["url"])
            if is_collection_blocked_or_empty(data):
                raise RuntimeError(
                    "Coleta bloqueada ou incompleta. Resolva login/verificacao "
                    "manualmente e tente novamente."
                )
            quality = data.get("quality") if isinstance(data.get("quality"), dict) else None
            if quality and not quality.get("ok"):
                raise RuntimeError(_quality_error_message(quality))
            product = mark_product_collected(product_uid, data)
            assets = _persist_collected_assets(
                product_uid,
                data,
                save_assets_to_disk=save_assets_to_disk,
            )
            asset_errors = [asset for asset in assets if asset.get("error")]
            done_job = mark_job_done(job_uid)

            summary["done"] += 1
            summary["results"].append(
                {
                    "job": done_job,
                    "product": product,
                    "assets_saved": len(assets) - len(asset_errors),
                    "asset_errors": len(asset_errors),
                    "ok": True,
                }
            )
        except Exception as exc:
            error = str(exc)
            try:
                mark_product_failed(product_uid, error)
            except Exception:
                pass
            try:
                failed_job = mark_job_failed(job_uid, error)
            except Exception:
                failed_job = {"job_uid": job_uid, "status": "failed", "last_error": error}

            summary["failed"] += 1
            summary["results"].append({"job": failed_job, "ok": False, "error": error})

    return summary


def is_collection_blocked_or_empty(data: dict) -> bool:
    """Return True when the page is login/verification instead of a product."""
    if not isinstance(data, dict):
        return True

    marketplace = data.get("marketplace")
    title = data.get("title")
    raw = data.get("raw") or {}
    if (
        isinstance(raw, dict)
        and raw.get("optional_details_status") == "skipped_fast_primary_collection"
        and data.get("title")
    ):
        return False

    raw_text = " ".join(
        str(value or "")
        for value in [
            title,
            raw.get("page_title"),
            raw.get("body_excerpt"),
        ]
    )
    folded = _strip_accents(raw_text).lower()

    blocked_patterns = [
        "captcha",
        "verificacao",
        "para continuar acesse sua conta",
        "acesse sua conta",
        "ja tenho conta",
        "fazer login",
        "entre na sua conta",
        "iniciar sessao",
        "account-verification",
        "e-mail ou telefone",
        "recaptcha",
        "negative_traffic",
        "access denied",
        "verify you are human",
        "robo",
        "ola! para continuar, acesse sua conta",
        "erro de carregamento",
        "problemas ao carregar",
    ]
    if any(pattern in folded for pattern in blocked_patterns):
        return True

    if _looks_like_intervention_title(title):
        return True

    if marketplace == "mercadolivre":
        return not data.get("title") or (
            data.get("price") is None
            and not data.get("description")
            and not data.get("image_urls")
        )

    return False


def _persist_collected_assets(
    product_uid: str,
    data: dict,
    save_assets_to_disk: bool = False,
    timeout: float = ASSET_TOTAL_TIMEOUT_SECONDS,
    url_start_time: float | None = None,
    max_images_per_product: int = MAX_ASSET_IMAGES_PER_PRODUCT,
    per_image_timeout: float = ASSET_IMAGE_TIMEOUT_SECONDS,
) -> list[dict]:
    start_time = time.monotonic()

    if save_assets_to_disk and data.get("marketplace") == "mercadolivre":
        from .radar_assets_service import download_asset

        assets = []
        seen = set()
        image_items = _limited_asset_image_items(data, max_images_per_product)

        for asset_type, image_url in image_items:
            timeout_error = _asset_timeout_error(
                product_uid,
                asset_type,
                image_url,
                start_time,
                timeout,
                url_start_time,
            )
            if timeout_error:
                assets.append(timeout_error)
                break
            clean_url = str(image_url or "").strip()
            if not clean_url or clean_url in seen:
                continue
            seen.add(clean_url)
            try:
                assets.append(
                    download_asset(
                        clean_url,
                        product_uid,
                        asset_type,
                        timeout=per_image_timeout,
                    )
                )
            except Exception as exc:
                assets.append(_asset_download_error(product_uid, asset_type, clean_url, exc))
        return assets

    assets = []
    seen = set()
    try:
        for asset_type, image_url in _limited_asset_image_items(data, max_images_per_product):
            timeout_error = _asset_timeout_error(
                product_uid,
                asset_type,
                image_url,
                start_time,
                timeout,
                url_start_time,
            )
            if timeout_error:
                assets.append(timeout_error)
                break
            clean_url = str(image_url or "").strip()
            if not clean_url or clean_url in seen:
                continue
            seen.add(clean_url)
            assets.append(add_product_asset(product_uid, asset_type, source_url=clean_url))
    except Exception as exc:
        assets.append(_asset_download_error(product_uid, "image", "", exc))

    return assets


def _limited_asset_image_items(data: dict, max_images_per_product: int) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    max_images = max(0, int(max_images_per_product or 0))
    for image_url in data.get("image_urls") or []:
        if len(items) >= max_images:
            break
        items.append(("image", image_url))
    if len(items) < max_images:
        for image_url in data.get("description_image_urls") or []:
            if len(items) >= max_images:
                break
            items.append(("description_image", image_url))
    return items


def _asset_timeout_error(
    product_uid: str,
    asset_type: str,
    source_url: str,
    start_time: float,
    timeout: float,
    url_start_time: float | None,
) -> dict | None:
    if time.monotonic() - start_time > timeout:
        return _asset_download_error(
            product_uid,
            asset_type,
            source_url,
            TimeoutError("assets_timeout_after_30s"),
        )
    if url_start_time and time.monotonic() - url_start_time > 90:
        return _asset_download_error(
            product_uid,
            asset_type,
            source_url,
            TimeoutError("total_per_url_timeout_after_90s"),
        )
    return None


def _asset_download_error(
    product_uid: str,
    asset_type: str,
    source_url: str,
    exc: Exception,
) -> dict:
    return {
        "product_uid": product_uid,
        "asset_type": asset_type,
        "source_url": source_url,
        "local_path": None,
        "downloaded": False,
        "error": str(exc),
    }


def _manual_wait_seconds() -> int:
    raw_value = os.getenv("RADAR_MANUAL_WAIT_SECONDS", "8")
    try:
        return max(0, int(raw_value))
    except ValueError:
        return 8


def _normalize_browser_mode(browser_mode: str | None) -> str:
    mode = (browser_mode or "persistent").strip().lower()
    if mode not in {"persistent", "cdp"}:
        raise ValueError("browser_mode invalido. Use: persistent ou cdp")
    return mode


def _manual_intervention_message(browser_mode: str) -> str:
    if browser_mode == "cdp":
        return "Resolva a verificacao/login no Chrome do Radar e pressione ENTER para continuar."
    return "Resolva login/verificacao no navegador e pressione ENTER para continuar."


def _empty_data_retry_message(browser_mode: str) -> str:
    if browser_mode == "cdp":
        return (
            "Dados essenciais vieram vazios. Confira a pagina no Chrome do Radar "
            "e pressione ENTER para tentar novamente."
        )
    return (
        "Dados essenciais vieram vazios. Confira a pagina no navegador e pressione "
        "ENTER para tentar novamente."
    )


def _browser_context_options(browser_channel: str | None = None) -> dict:
    channel = (browser_channel or os.getenv("RADAR_BROWSER_CHANNEL", "")).strip().lower()
    options = {
        "user_data_dir": str(BROWSER_PROFILE_DIR),
        "headless": False,
        "viewport": {"width": 1366, "height": 900},
        "locale": "pt-BR",
    }
    if channel and channel != "chromium":
        options["channel"] = channel
    return options


def _manual_intervention_seconds() -> int:
    raw_value = os.getenv("RADAR_MANUAL_INTERVENTION_SECONDS", "60")
    try:
        return max(0, int(raw_value))
    except ValueError:
        return 60


def _reload_product_page(page, url: str, timeout_error_cls) -> None:
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except timeout_error_cls:
        page.goto(url, wait_until="load", timeout=60000)

    wait_ms = _manual_wait_seconds() * 1000
    if wait_ms > 0:
        page.wait_for_timeout(wait_ms)


def _wait_for_manual_confirmation(
    page,
    message: str,
    timeout_seconds: int | None = None,
) -> None:
    print(f"\n[RADAR] {message}", flush=True)
    print("[RADAR] O coletor nao preenche senha, captcha ou token automaticamente.", flush=True)
    if timeout_seconds:
        print(f"[RADAR] Continuarei automaticamente em {timeout_seconds}s se ENTER nao for usado.", flush=True)

    done = threading.Event()

    def wait_for_enter() -> None:
        try:
            input()
        except EOFError:
            return
        done.set()

    threading.Thread(target=wait_for_enter, daemon=True).start()
    deadline = time.monotonic() + timeout_seconds if timeout_seconds else None

    while not done.is_set():
        if deadline is not None and time.monotonic() >= deadline:
            print("[RADAR] Tempo de espera manual encerrado; tentando extrair novamente.", flush=True)
            done.set()
            break
        try:
            page.wait_for_timeout(500)
        except Exception:
            done.set()


def _needs_manual_intervention(page) -> bool:
    text = _strip_accents((_body_text(page) or "").lower())
    patterns = [
        "captcha",
        "verificacao",
        "verifique",
        "para continuar acesse sua conta",
        "acesse sua conta",
        "ja tenho conta",
        "fazer login",
        "entre na sua conta",
        "account-verification",
        "por seguranca",
        "complete esta etapa",
        "erro de carregamento",
        "problemas ao carregar",
        "access denied",
        "verify you are human",
    ]
    return any(pattern in text for pattern in patterns)


def _needs_interactive_retry(data: dict) -> bool:
    title = data.get("title")
    marketplace = data.get("marketplace")
    quality = data.get("quality") if isinstance(data.get("quality"), dict) else {}

    if quality and not quality.get("ok"):
        return True

    if not title or _looks_like_intervention_title(title):
        return True

    if marketplace == "shopee" and (
        data.get("price") is None
        or "shopee brasil | ofertas" in _strip_accents(title).lower()
    ):
        return True

    if marketplace == "mercadolivre" and data.get("price") is None:
        return True

    return False


def _result(
    *,
    url: str,
    marketplace: str,
    title: str | None,
    price: float | None,
    shop_name: str | None,
    rating: float | None,
    review_count: int | None,
    sold_count: int | None,
    description: str | None,
    image_urls: list[str],
    video_urls: list[str],
    raw: dict[str, Any],
) -> dict:
    canonical_url = normalize_product_url(url)
    return {
        "url": url,
        "canonical_url": canonical_url,
        "marketplace": marketplace,
        "title": _clean_text(title),
        "price": price,
        "shop_name": _clean_text(shop_name),
        "rating": rating,
        "review_count": review_count,
        "sold_count": sold_count,
        "description": _clean_text(description),
        "image_urls": normalize_image_urls(image_urls),
        "video_urls": normalize_image_urls(video_urls),
        "raw": raw,
    }


def _finalize_collected_data(data: dict, expected_marketplace: str) -> dict:
    if not isinstance(data, dict):
        return data

    if data.get("marketplace") == "mercadolivre":
        data["image_urls"] = filter_product_image_urls(data.get("image_urls") or [])
        data["description_image_urls"] = filter_product_image_urls(
            data.get("description_image_urls") or []
        )
        raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
        raw["image_urls"] = data["image_urls"]
        raw["description_image_urls"] = data["description_image_urls"]
        raw["price"] = data.get("price")
        raw["title"] = data.get("title")
        data["raw"] = raw

    quality = validate_product_extraction(data, expected_marketplace)
    data["quality"] = quality
    raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
    raw["quality"] = quality
    data["raw"] = raw
    return data


def _best_product_title(candidates: list[str | None]) -> str | None:
    fallback = None
    for candidate in candidates:
        clean = _clean_mercadolivre_title(candidate)
        if not clean:
            continue
        if fallback is None:
            fallback = clean
        if not _is_generic_product_title(clean) and not _looks_like_intervention_title(clean):
            return clean
    return fallback


def _clean_mercadolivre_title(title: str | None) -> str | None:
    clean = _clean_text(title)
    if not clean:
        return None
    clean = re.sub(r"\s*\|\s*Mercado\s*Livre.*$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*\|\s*MercadoLivre.*$", "", clean, flags=re.IGNORECASE)
    return _clean_text(clean)


def _extract_json_ld_product(page) -> dict:
    try:
        data = page.evaluate(
            """
            () => {
                const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
                const flatten = (value) => {
                    if (!value) return [];
                    if (Array.isArray(value)) return value.flatMap(flatten);
                    if (value['@graph']) return flatten(value['@graph']);
                    return [value];
                };
                for (const script of scripts) {
                    try {
                        const parsed = JSON.parse(script.textContent || '{}');
                        for (const item of flatten(parsed)) {
                            const type = item['@type'];
                            const types = Array.isArray(type) ? type : [type];
                            if (!types.map(String).some((entry) => entry.toLowerCase() === 'product')) continue;
                            const offers = Array.isArray(item.offers) ? item.offers[0] : item.offers || {};
                            const images = Array.isArray(item.image) ? item.image : (item.image ? [item.image] : []);
                            return {
                                name: item.name || null,
                                price: offers.price || offers.lowPrice || null,
                                image_urls: images.filter(Boolean)
                            };
                        }
                    } catch (_) {}
                }
                return {};
            }
            """
        )
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _first_text(page, selectors: list[str]) -> str | None:
    for selector in selectors:
        try:
            el = page.query_selector(selector)
            if el:
                text = el.text_content()
                clean = _clean_text(text)
                if clean:
                    return clean
        except Exception:
            continue

    return None


def _first_text_quick(page, selectors: list[str]) -> str | None:
    try:
        data = page.evaluate(
            """
            (selectors) => {
                const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                for (const selector of selectors) {
                    try {
                        const node = document.querySelector(selector);
                        if (!node) continue;
                        const text = clean(node.innerText || node.textContent || '');
                        if (text) return text;
                    } catch (_) {}
                }
                return null;
            }
            """,
            selectors,
        )
    except Exception:
        return None

    return _clean_text(data)


def _first_meta(page, selectors: list[str]) -> str | None:
    for selector in selectors:
        try:
            el = page.query_selector(selector)
            if el:
                value = el.get_attribute("content")
                clean = _clean_text(value)
                if clean:
                    return clean
        except Exception:
            continue

    return None


def _body_text(page) -> str:
    try:
        el = page.query_selector("body")
        return _clean_text(el.inner_text() if el else "") or ""
    except Exception:
        return ""


def _page_title(page) -> str | None:
    try:
        return _clean_text(page.title())
    except Exception:
        return None


def _extract_title_from_url(url: str) -> str:
    try:
        from urllib.parse import urlsplit
        path = urlsplit(url).path
        parts = [p for p in path.split("/") if p.strip()]
        if parts:
            slug = parts[0]
            if slug in ("p", "pdp", "produto") and len(parts) > 1:
                slug = parts[1]
            title = slug.replace("-", " ").replace("_", " ").strip()
            return title.title()
    except Exception:
        pass
    return "Concorrente Sem Titulo"


def _first_price_text(text: str) -> str | None:
    if not text:
        return None

    match = re.search(
        r"R\$\s*\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?|R\$\s*\d+(?:[.,]\d{2})?",
        text,
    )
    if match:
        return match.group(0)

    match = re.search(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2}", text)
    return match.group(0) if match else None


def _collect_media_urls(page) -> tuple[list[str], list[str]]:
    try:
        data = page.evaluate(
            """
            () => {
                const MAX_IMAGES = 30;
                const MAX_VIDEOS = 5;
                const absolutize = (value) => {
                    if (!value) return null;
                    try { return new URL(value.trim(), location.href).href; }
                    catch (_) { return null; }
                };
                const images = [];
                const videos = [];

                const pushImage = (value) => {
                    if (images.length >= MAX_IMAGES) return;
                    const url = absolutize(value);
                    if (url) images.push(url);
                };
                const pushVideo = (value) => {
                    if (videos.length >= MAX_VIDEOS) return;
                    const url = absolutize(value);
                    if (url) videos.push(url);
                };

                Array.from(document.images || []).slice(0, MAX_IMAGES).forEach((img) => {
                    [img.currentSrc, img.src, img.getAttribute('data-src'), img.getAttribute('data-lazy')]
                        .forEach(pushImage);

                    const srcset = img.getAttribute('srcset') || '';
                    srcset.split(',').forEach((part) => {
                        const value = part.trim().split(/\\s+/)[0];
                        pushImage(value);
                    });
                });

                Array.from(document.querySelectorAll('video, video source')).slice(0, MAX_VIDEOS).forEach((video) => {
                    [video.currentSrc, video.src, video.getAttribute('src')]
                        .forEach(pushVideo);
                });

                return { images, videos };
            }
            """
        )
    except Exception:
        return [], []

    return data.get("images", []), data.get("videos", [])


def _collect_description_image_urls(page) -> list[str]:
    try:
        urls = page.evaluate(
            """
            () => {
                const scope = document.querySelector('#description, .ui-pdp-description');
                if (!scope) return [];
                const absolutize = (value) => {
                    if (!value) return null;
                    try { return new URL(value.trim(), location.href).href; }
                    catch (_) { return null; }
                };
                const images = [];
                Array.from(scope.querySelectorAll('img')).slice(0, 10).forEach((img) => {
                    [img.currentSrc, img.src, img.getAttribute('data-src'), img.getAttribute('data-lazy')]
                        .forEach((value) => {
                            const url = absolutize(value);
                            if (url) images.push(url);
                        });
                });
                return images;
            }
            """
        )
    except Exception:
        return []

    return urls or []


def _collect_mercadolivre_gallery_image_urls(page) -> list[str]:
    try:
        urls = page.evaluate(
            """
            () => {
                const absolutize = (value) => {
                    if (!value) return null;
                    try { return new URL(value.trim(), location.href).href; }
                    catch (_) { return null; }
                };
                const urls = [];
                const selectors = [
                    'meta[property="og:image"]',
                    '.ui-pdp-gallery img',
                    '.ui-pdp-gallery__figure img',
                    '.ui-pdp-image',
                    '.ui-pdp-thumbnail img',
                    '[data-testid="image-gallery"] img'
                ];

                selectors.forEach((selector) => {
                    if (urls.length >= 20) return;
                    Array.from(document.querySelectorAll(selector)).slice(0, 20).forEach((node) => {
                        if (urls.length >= 20) return;
                        if (node.tagName === 'META') {
                            const url = absolutize(node.getAttribute('content'));
                            if (url) urls.push(url);
                            return;
                        }

                        [node.currentSrc, node.src, node.getAttribute('data-src'), node.getAttribute('data-lazy')]
                            .forEach((value) => {
                                const url = absolutize(value);
                                if (url) urls.push(url);
                            });

                        const srcset = node.getAttribute('srcset') || '';
                        srcset.split(',').forEach((part) => {
                            const value = part.trim().split(/\\s+/)[0];
                            const url = absolutize(value);
                            if (url) urls.push(url);
                        });
                    });
                });

                return urls;
            }
            """
        )
    except Exception:
        return []

    return normalize_image_urls(urls or [])


def _normalize_mercadolivre_image_urls(urls: list[str]) -> list[str]:
    normalized = []
    seen_keys = set()

    for url in normalize_image_urls(urls):
        lowered = url.lower()
        if lowered.endswith(".svg") or "frontend-assets" in lowered:
            continue
        if "negative_traffic" in lowered or "backgr_logo" in lowered:
            continue

        image_key = _mercadolivre_image_key(url) or url
        if image_key in seen_keys:
            continue

        seen_keys.add(image_key)
        normalized.append(url)

    return normalized


def _mercadolivre_image_key(url: str) -> str | None:
    match = re.search(r"(\d+-ML[A-Z]\d+_\d+)", url)
    return match.group(1) if match else None


def _extract_mercadolivre_attributes(page) -> dict[str, str]:
    try:
        data = page.evaluate(
            """
            () => {
                const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                const attrs = {};

                document.querySelectorAll(
                    '.andes-table tr, .ui-pdp-striped-specs__row, .ui-vpp-striped-specs__row, tr'
                ).forEach((row) => {
                    const cells = Array.from(row.querySelectorAll('th, td, .andes-table__header, .andes-table__column'));
                    if (cells.length < 2) return;
                    const key = clean(cells[0].innerText).replace(/:$/, '');
                    const value = clean(cells.slice(1).map((cell) => cell.innerText).join(' '));
                    if (key && value && key.length <= 80 && value.length <= 300) attrs[key] = value;
                });

                document.querySelectorAll('.ui-pdp-specs__table, .ui-pdp-specs').forEach((section) => {
                    section.querySelectorAll('p, span, div').forEach((node) => {
                        const text = clean(node.innerText);
                        const match = text.match(/^([^:]{2,80}):\\s*(.{1,300})$/);
                        if (match) attrs[clean(match[1])] = clean(match[2]);
                    });
                });

                return attrs;
            }
            """
        )
    except Exception:
        return {}

    return {str(key): str(value) for key, value in (data or {}).items() if key and value}


def _extract_category_path(page) -> list[str]:
    try:
        data = page.evaluate(
            """
            () => Array.from(document.querySelectorAll(
                '.andes-breadcrumb__link, .ui-pdp-breadcrumb__link, nav[aria-label*="breadcrumb"] a'
            ))
                .map((node) => (node.innerText || '').replace(/\\s+/g, ' ').trim())
                .filter(Boolean)
            """
        )
    except Exception:
        return []
    return data or []


def _extract_variation_labels(page) -> list[str]:
    try:
        data = page.evaluate(
            """
            () => {
                const labels = new Set();
                document.querySelectorAll(
                    '.ui-pdp-variations label, .ui-pdp-variations button, [class*="variation"] label, [class*="variation"] button'
                ).forEach((node) => {
                    const text = (node.innerText || node.getAttribute('aria-label') || '')
                        .replace(/\\s+/g, ' ')
                        .trim();
                    if (text && text.length <= 120) labels.add(text);
                });
                return Array.from(labels);
            }
            """
        )
    except Exception:
        return []
    return data or []


def _extract_seller_reputation(page, body_text: str) -> str | None:
    reputation = _first_text_quick(
        page,
        [
            ".ui-pdp-seller__reputation-info",
            ".ui-pdp-seller__status-title",
            ".ui-pdp-seller__reputation",
        ],
    )
    if reputation:
        return reputation

    folded = _strip_accents(body_text)
    match = re.search(
        r"(MercadoLider(?:\s+Gold|\s+Platinum)?|Reputacao\s+[^\n.]{1,80})",
        folded,
        flags=re.IGNORECASE,
    )
    return _clean_text(match.group(1)) if match else None


def _parse_discount_percent(text: str) -> int | None:
    if not text:
        return None
    match = re.search(r"(\d{1,2})\s*%\s*OFF", _strip_accents(text), flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _parse_rating(text: str) -> float | None:
    if not text:
        return None

    folded_text = _strip_accents(text)
    patterns = [
        r"(\d(?:[,.]\d)?)\s*(?:de\s*5|/5|estrelas)",
        r"Nota\s*(\d(?:[,.]\d)?)",
        r"Avaliacao\s*(\d(?:[,.]\d)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, folded_text, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            rating = float(match.group(1).replace(",", "."))
        except ValueError:
            continue
        if 0 <= rating <= 5:
            return rating

    return None


def _parse_count_near_keywords(text: str, keywords: list[str]) -> int | None:
    if not text:
        return None

    normalized = _strip_accents(text).lower()
    keyword_pattern = "|".join(re.escape(_strip_accents(keyword).lower()) for keyword in keywords)
    patterns = [
        rf"(\d[\d.,]*\s*(?:mil|k)?)\s*(?:{keyword_pattern})",
        rf"(?:{keyword_pattern})\D{{0,30}}(\d[\d.,]*\s*(?:mil|k)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            return _parse_count(match.group(1))

    return None


def _parse_count(text: str) -> int | None:
    if not text:
        return None

    clean = text.strip().lower().replace("+", "")
    multiplier = 1
    if "mil" in clean or clean.endswith("k"):
        multiplier = 1000

    clean = clean.replace("mil", "").replace("k", "").strip()
    clean = clean.replace(".", "").replace(",", ".")

    try:
        return int(float(clean) * multiplier)
    except ValueError:
        return None


def _looks_like_layout_image_url(lowered_url: str) -> bool:
    blocked_fragments = [
        ".svg",
        "sprite",
        "logo",
        "icon",
        "favicon",
        "placeholder",
        "transparent",
        "frontend-assets",
        "navigation",
        "avatar",
        "profile",
        "banner",
        "ads",
        "advertis",
        "negative_traffic",
        "backgr_logo",
    ]
    if any(fragment in lowered_url for fragment in blocked_fragments):
        return True

    if "http2.mlstatic.com" in lowered_url:
        return "d_nq_np" not in lowered_url and "-ml" not in lowered_url

    return False


def _product_image_key(url: str) -> str | None:
    match = re.search(r"(\d+-ML[A-Z]\d+_\d+)", url, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    match = re.search(r"(D_NQ_NP[_-][^/?]+)", url, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def _is_generic_product_title(title: str | None) -> bool:
    normalized = _normalize_text(title or "")
    if not normalized:
        return True
    if normalized in GENERIC_PRODUCT_TITLES:
        return True
    tokens = [token for token in normalized.split() if token]
    return len(tokens) <= 1 and tokens[0] in {"mochila", "mochilas", "produto", "produtos"}


def _looks_like_product_url(url: str | None, marketplace: str | None) -> bool:
    if not url:
        return False
    normalized_url = str(url).strip().lower()
    if any(fragment in normalized_url for fragment in ["/lista/", "/categorias/", "/ofertas", "/search"]):
        return False

    detected = detect_marketplace(normalized_url)
    if marketplace and detected != marketplace:
        return False
    if detected == "mercadolivre":
        return bool(re.search(r"/MLB-[a-z0-9]+", normalized_url, flags=re.IGNORECASE))
    if detected == "shopee":
        return "/i." in normalized_url or "/product/" in normalized_url or bool(
            re.search(r"i\.\d+\.\d+", normalized_url)
        )
    return False


def _category_hint_from_data(data: dict) -> str | None:
    text_parts = [
        data.get("title") or "",
        data.get("description") or "",
        " ".join(str(item) for item in data.get("category_path") or []),
    ]
    raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
    text_parts.extend(
        [
            raw.get("title") or "",
            raw.get("description") or "",
            " ".join(str(item) for item in raw.get("category_path") or []),
        ]
    )
    normalized = _normalize_text(" ".join(text_parts))
    if "mochila" in normalized:
        return "mochila"
    return None


def _coerce_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_text.lower()).strip()


def _clean_text(text: str | None) -> str | None:
    if text is None:
        return None
    clean = re.sub(r"\s+", " ", str(text)).strip()
    return clean or None


def _looks_like_intervention_title(title: str | None) -> bool:
    if not title:
        return False
    folded = _strip_accents(title).lower()
    return any(
        pattern in folded
        for pattern in [
            "por seguranca",
            "complete esta etapa",
            "erro de carregamento",
            "problemas ao carregar",
            "fazer login",
            "iniciar sessao",
            "para continuar acesse sua conta",
            "acesse sua conta",
            "ja tenho conta",
            "account-verification",
            "e-mail ou telefone",
            "recaptcha",
            "captcha",
            "verificacao",
        ]
    )


def _strip_accents(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", str(text))
        if not unicodedata.combining(char)
    )
