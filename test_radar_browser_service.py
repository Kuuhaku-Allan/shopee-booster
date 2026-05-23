#!/usr/bin/env python3
"""
test_radar_browser_service.py - R5.1A CDP browser helpers.

These tests do not open Chrome and do not use the internet.

Run:
    python test_radar_browser_service.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import shopee_core.radar_browser_service as browser_service
from shopee_core.radar_collector import is_collection_blocked_or_empty


ROOT_DIR = Path(__file__).resolve().parent


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return b'{"Browser":"Chrome/126","webSocketDebuggerUrl":"ws://127.0.0.1/devtools/browser/1"}'


class _FakeContext:
    def __init__(self):
        self.pages = []
        self.created = 0

    def new_page(self):
        self.created += 1
        page = _FakePage("about:blank")
        self.pages.append(page)
        return page


class _FakePage:
    def __init__(self, url):
        self.url = url


class _FakeBrowser:
    def __init__(self):
        self.contexts = [_FakeContext()]


def test_is_cdp_available_with_mock():
    original = browser_service.urlopen
    try:
        browser_service.urlopen = lambda *args, **kwargs: _FakeResponse()
        assert browser_service.is_cdp_available("http://127.0.0.1:9222") is True
        return True
    finally:
        browser_service.urlopen = original


def test_is_cdp_available_handles_error():
    original = browser_service.urlopen
    try:
        def _raise(*args, **kwargs):
            raise OSError("offline")

        browser_service.urlopen = _raise
        assert browser_service.is_cdp_available("http://127.0.0.1:9222") is False
        return True
    finally:
        browser_service.urlopen = original


def test_connect_to_cdp_unavailable_error():
    original = browser_service.is_cdp_available
    try:
        browser_service.is_cdp_available = lambda *args, **kwargs: False
        try:
            browser_service.connect_to_cdp_browser(object(), "http://127.0.0.1:9222")
        except RuntimeError as exc:
            assert "Chrome do Radar nao esta aberto" in str(exc)
            assert "start-radar-chrome.ps1" in str(exc)
            return True
        raise AssertionError("CDP indisponivel deveria gerar erro amigavel")
    finally:
        browser_service.is_cdp_available = original


def test_get_or_create_page_from_cdp_uses_default_context():
    browser = _FakeBrowser()
    context, page = browser_service.get_or_create_page_from_cdp(browser)
    assert context is browser.contexts[0]
    assert page.url == "about:blank"
    assert context.created == 1
    return True


def test_scripts_expose_browser_mode_options():
    scripts = [
        "radar_collect_url.py",
        "radar_collect_deep_url.py",
        "radar_collect_pending.py",
        "radar_run_full_market_smoke.py",
    ]
    for script in scripts:
        result = subprocess.run(
            [sys.executable, str(ROOT_DIR / "scripts" / script), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert "--browser-mode" in output
        assert "--cdp-url" in output
    return True


def test_login_verification_detection():
    data = {
        "marketplace": "mercadolivre",
        "title": "Para continuar, acesse sua conta",
        "price": None,
        "description": None,
        "image_urls": [],
        "raw": {
            "page_title": "account-verification",
            "body_excerpt": "Ja tenho conta. Erro de Carregamento.",
        },
    }
    assert is_collection_blocked_or_empty(data) is True
    return True


if __name__ == "__main__":
    print("\nTESTE R5.1A - Chrome real via CDP\n")

    tests = [
        ("is_cdp_available com mock", test_is_cdp_available_with_mock),
        ("is_cdp_available trata erro", test_is_cdp_available_handles_error),
        ("erro amigavel quando CDP indisponivel", test_connect_to_cdp_unavailable_error),
        ("get_or_create_page_from_cdp usa contexto padrao", test_get_or_create_page_from_cdp_uses_default_context),
        ("scripts expoem browser_mode/cdp_url", test_scripts_expose_browser_mode_options),
        ("deteccao de login/verificacao", test_login_verification_detection),
    ]

    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"PASS - {name}")
        except Exception as exc:
            print(f"FAIL - {name}: {exc}")
            raise

    print(f"\nTotal: {passed}/{len(tests)} testes passaram")
