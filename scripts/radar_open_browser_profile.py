#!/usr/bin/env python3
"""
Open the Radar persistent browser profile for manual marketplace login.

Usage:
    python scripts/radar_open_browser_profile.py --marketplace shopee
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_collector import BROWSER_PROFILE_DIR
from shopee_core.radar_collector import _browser_context_options


MARKETPLACE_URLS = {
    "shopee": "https://shopee.com.br/",
    "mercadolivre": "https://www.mercadolivre.com.br/",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Abre o navegador persistente do Radar para login manual."
    )
    parser.add_argument(
        "--marketplace",
        choices=sorted(MARKETPLACE_URLS),
        default="shopee",
        help="Marketplace a abrir no perfil persistente",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="URL opcional para abrir em vez da home do marketplace",
    )
    parser.add_argument(
        "--auto-close-seconds",
        type=int,
        default=None,
        help="Opcional: fecha automaticamente apos N segundos",
    )
    parser.add_argument(
        "--browser-channel",
        choices=["chromium", "chrome", "msedge"],
        default=None,
        help="Usa Chromium padrao, Google Chrome ou Microsoft Edge instalado",
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright nao esta instalado. Instale com 'pip install playwright' "
            "e rode 'python -m playwright install chromium'."
        ) from exc

    target_url = args.url or MARKETPLACE_URLS[args.marketplace]
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[RADAR] Perfil persistente: {BROWSER_PROFILE_DIR}")
    print(f"[RADAR] Navegador: {args.browser_channel or 'chromium'}")
    print("[RADAR] Faca login/verificacao manualmente.")
    print("[RADAR] Quando terminar, feche o navegador ou pressione ENTER no terminal.")
    print("[RADAR] O sistema nao preenche senha, captcha ou token automaticamente.")

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            **_browser_context_options(browser_channel=args.browser_channel)
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

        done = threading.Event()

        def wait_for_enter() -> None:
            try:
                input()
            except EOFError:
                print("[RADAR] Entrada de terminal indisponivel; feche o navegador para encerrar.")
                return
            done.set()

        threading.Thread(target=wait_for_enter, daemon=True).start()
        deadline = (
            time.monotonic() + args.auto_close_seconds
            if args.auto_close_seconds
            else None
        )

        try:
            while not done.is_set():
                if deadline is not None and time.monotonic() >= deadline:
                    print("[RADAR] Tempo de auto-fechamento atingido.")
                    break
                try:
                    page.wait_for_timeout(500)
                except Exception:
                    break
        finally:
            context.close()

    print("[RADAR] Navegador persistente fechado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
