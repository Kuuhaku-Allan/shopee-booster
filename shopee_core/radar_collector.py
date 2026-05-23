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

from .radar_service import (
    detect_marketplace,
    get_pending_jobs,
    mark_job_done,
    mark_job_failed,
    mark_job_running,
    mark_product_collected,
    mark_product_failed,
    normalize_product_url,
    save_product_assets,
)


BASE_DIR = Path(__file__).resolve().parent.parent
BROWSER_PROFILE_DIR = BASE_DIR / "data" / "browser_profile"


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


def collect_product_page(
    url: str,
    marketplace: str | None = None,
    interactive: bool = False,
    interactive_wait_seconds: int | None = None,
    browser_channel: str | None = None,
) -> dict:
    """Open a visible browser, collect one product page and return normalized data."""
    canonical_url = normalize_product_url(url)
    detected_marketplace = marketplace or detect_marketplace(canonical_url)

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
        context = playwright.chromium.launch_persistent_context(
            **_browser_context_options(browser_channel=browser_channel)
        )

        page = context.pages[0] if context.pages else context.new_page()

        try:
            try:
                page.goto(canonical_url, wait_until="domcontentloaded", timeout=60000)
            except PlaywrightTimeoutError:
                page.goto(canonical_url, wait_until="load", timeout=60000)

            if manual_wait_ms > 0:
                page.wait_for_timeout(manual_wait_ms)

            if _needs_manual_intervention(page):
                if interactive:
                    _wait_for_manual_confirmation(
                        page,
                        "Resolva login/verificacao no navegador e pressione ENTER para continuar.",
                        timeout_seconds=interactive_wait_seconds,
                    )
                    _reload_product_page(page, canonical_url, PlaywrightTimeoutError)
                else:
                    page.wait_for_timeout(_manual_intervention_seconds() * 1000)

            scroll_product_page(page)

            if detected_marketplace == "shopee":
                data = collect_shopee_product(page, canonical_url)
            else:
                data = collect_mercadolivre_product(page, canonical_url)

            if interactive and _needs_interactive_retry(data):
                _wait_for_manual_confirmation(
                    page,
                    "Dados essenciais vieram vazios. Confira a pagina no navegador e pressione ENTER para tentar novamente.",
                    timeout_seconds=interactive_wait_seconds,
                )
                _reload_product_page(page, canonical_url, PlaywrightTimeoutError)
                scroll_product_page(page)

                if detected_marketplace == "shopee":
                    data = collect_shopee_product(page, canonical_url)
                else:
                    data = collect_mercadolivre_product(page, canonical_url)

            return data
        finally:
            context.close()


def collect_shopee_product(page, url: str) -> dict:
    """Collect basic Shopee product data from an already loaded page."""
    body_text = _body_text(page)
    title = (
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
    shop_name = _first_text(
        page,
        [
            "[data-testid='shop-name']",
            "a[href*='/shop/']",
            "a[href*='shopee.com.br/'] span",
            "div[class*='shop'] a",
        ],
    )
    description = _first_text(
        page,
        [
            "[data-testid='product-description']",
            "div[class*='product-detail']",
            "section:has-text('Descricao')",
            "section:has-text('Descri')",
        ],
    )
    image_urls, video_urls = _collect_media_urls(page)
    rating_text = _first_text(
        page,
        [
            "[data-testid='product-rating']",
            "div[class*='rating']",
            "section:has-text('estrelas')",
        ],
    )

    return _result(
        url=url,
        marketplace="shopee",
        title=title,
        price=parse_price(price_text or ""),
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


def collect_mercadolivre_product(page, url: str) -> dict:
    """Collect basic Mercado Livre product data from an already loaded page."""
    body_text = _body_text(page)
    page_title = _page_title(page)
    title = (
        _first_text(page, ["h1.ui-pdp-title", "h1", "[data-testid='title']"])
        or _first_meta(page, ["meta[property='og:title']", "meta[name='title']"])
    )
    if _looks_like_intervention_title(title) and page_title:
        title = page_title.split("|")[0].strip()
    price_text = (
        _first_meta(page, ["meta[itemprop='price']", "meta[property='product:price:amount']"])
        or _first_text(
            page,
            [
                ".ui-pdp-price .andes-money-amount",
                "[data-testid='price-part']",
                "div.ui-pdp-price",
                "span.andes-money-amount",
            ],
        )
        or _first_price_text(body_text)
    )
    shop_name = _first_text(
        page,
        [
            ".ui-pdp-seller__header__title",
            ".ui-pdp-seller__link-trigger",
            "a[href*='/perfil/']",
            "a[href*='/loja/']",
        ],
    )
    description = _first_text(
        page,
        [
            "#description",
            ".ui-pdp-description",
            "[data-testid='content']",
            "section:has-text('Descricao')",
            "section:has-text('Descri')",
        ],
    )
    image_urls, video_urls = _collect_media_urls(page)

    return _result(
        url=url,
        marketplace="mercadolivre",
        title=title,
        price=parse_price(price_text or ""),
        shop_name=shop_name,
        rating=_parse_rating(body_text),
        review_count=_parse_count_near_keywords(body_text, ["avaliacoes", "avaliacao", "opinioes"]),
        sold_count=_parse_count_near_keywords(body_text, ["vendidos", "vendido"]),
        description=description,
        image_urls=image_urls,
        video_urls=video_urls,
        raw={
            "page_title": page_title,
            "price_text": price_text,
            "body_excerpt": body_text[:3000],
        },
    )


def scroll_product_page(page) -> None:
    """Scroll gradually to trigger lazy images and visible description content."""
    for _ in range(8):
        page.evaluate("window.scrollBy(0, Math.floor(window.innerHeight * 0.8))")
        page.wait_for_timeout(700)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(500)


def collect_pending_jobs(
    limit: int = 5,
    collector_func: Callable[[str], dict] | None = None,
) -> dict:
    """Collect pending radar jobs and persist product data/assets."""
    collector = collector_func or collect_product_page
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
            product = mark_product_collected(product_uid, data)
            assets = save_product_assets(
                product_uid,
                image_urls=data.get("image_urls") or [],
                video_urls=data.get("video_urls") or [],
            )
            done_job = mark_job_done(job_uid)

            summary["done"] += 1
            summary["results"].append(
                {
                    "job": done_job,
                    "product": product,
                    "assets_saved": len(assets),
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


def _manual_wait_seconds() -> int:
    raw_value = os.getenv("RADAR_MANUAL_WAIT_SECONDS", "8")
    try:
        return max(0, int(raw_value))
    except ValueError:
        return 8


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
        "fazer login",
        "entre na sua conta",
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


def _first_text(page, selectors: list[str]) -> str | None:
    for selector in selectors:
        try:
            text = page.locator(selector).first.text_content(timeout=1500)
        except Exception:
            continue

        clean = _clean_text(text)
        if clean:
            return clean

    return None


def _first_meta(page, selectors: list[str]) -> str | None:
    for selector in selectors:
        try:
            value = page.locator(selector).first.get_attribute("content", timeout=1000)
        except Exception:
            continue

        clean = _clean_text(value)
        if clean:
            return clean

    return None


def _body_text(page) -> str:
    try:
        return _clean_text(page.locator("body").inner_text(timeout=3000)) or ""
    except Exception:
        return ""


def _page_title(page) -> str | None:
    try:
        return _clean_text(page.title())
    except Exception:
        return None


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
                const absolutize = (value) => {
                    if (!value) return null;
                    try { return new URL(value.trim(), location.href).href; }
                    catch (_) { return null; }
                };
                const images = [];
                const videos = [];

                document.querySelectorAll('img').forEach((img) => {
                    [img.currentSrc, img.src, img.getAttribute('data-src'), img.getAttribute('data-lazy')]
                        .forEach((value) => {
                            const url = absolutize(value);
                            if (url) images.push(url);
                        });

                    const srcset = img.getAttribute('srcset') || '';
                    srcset.split(',').forEach((part) => {
                        const value = part.trim().split(/\\s+/)[0];
                        const url = absolutize(value);
                        if (url) images.push(url);
                    });
                });

                document.querySelectorAll('[style]').forEach((el) => {
                    const bg = getComputedStyle(el).backgroundImage || '';
                    const matches = bg.matchAll(/url\\(["']?([^"')]+)["']?\\)/g);
                    for (const match of matches) {
                        const url = absolutize(match[1]);
                        if (url) images.push(url);
                    }
                });

                document.querySelectorAll('video, video source').forEach((video) => {
                    [video.currentSrc, video.src, video.getAttribute('src')]
                        .forEach((value) => {
                            const url = absolutize(value);
                            if (url) videos.push(url);
                        });
                });

                return { images, videos };
            }
            """
        )
    except Exception:
        return [], []

    return data.get("images", []), data.get("videos", [])


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
