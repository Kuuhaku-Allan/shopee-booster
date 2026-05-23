"""
shopee_core/radar_browser_service.py - Browser helpers for Radar CDP mode.

This module does not launch stealth browsers or bypass login/captcha. It only
connects to a user-started Chrome instance that exposes the Chrome DevTools
Protocol on localhost.
"""

from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_CDP_URL = "http://127.0.0.1:9222"


def is_cdp_available(cdp_url: str = DEFAULT_CDP_URL, timeout: float = 2.0) -> bool:
    """Return True when a Chrome CDP endpoint is reachable."""
    version_url = cdp_url.rstrip("/") + "/json/version"
    try:
        with urlopen(version_url, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                return False
            try:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            except Exception:
                return True
            return bool(payload.get("Browser") or payload.get("webSocketDebuggerUrl"))
    except (OSError, URLError, TimeoutError, ValueError):
        return False


def connect_to_cdp_browser(playwright, cdp_url: str = DEFAULT_CDP_URL):
    """Connect Playwright to a user-started Chrome through CDP."""
    if not is_cdp_available(cdp_url):
        raise RuntimeError(
            "Chrome do Radar nao esta aberto. Rode "
            "deploy/local/start-radar-chrome.ps1 primeiro e depois tente "
            f"novamente com --browser-mode cdp --cdp-url {cdp_url}."
        )

    browser = playwright.chromium.connect_over_cdp(cdp_url)
    context, page = get_or_create_page_from_cdp(browser)
    return browser, context, page


def get_or_create_page_from_cdp(browser):
    """Return the default Chrome context and a fresh page for collection."""
    contexts = list(getattr(browser, "contexts", []) or [])
    if contexts:
        context = contexts[0]
    else:
        context = browser.new_context()

    pages = list(getattr(context, "pages", []) or [])
    if pages and _blank_page(pages[0]):
        return context, pages[0]

    return context, context.new_page()


def open_radar_browser_instructions() -> None:
    """Print the manual setup instructions for the dedicated Radar Chrome."""
    print(
        "Abra o Chrome real dedicado do Radar com:\n"
        "powershell -ExecutionPolicy Bypass -File .\\deploy\\local\\start-radar-chrome.ps1\n\n"
        "Faca login/verificacao manualmente no Mercado Livre ou Shopee nesse "
        "navegador. Depois rode o coletor com --browser-mode cdp."
    )


def _blank_page(page) -> bool:
    try:
        url = (page.url or "").strip().lower()
    except Exception:
        return False
    return url in {"", "about:blank", "chrome://newtab/"}
