#!/usr/bin/env python3
"""
test_radar_assets_service.py - R3 asset service unit tests.

These tests do not use the internet or open a browser.

Run:
    python test_radar_assets_service.py
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path


RUN_ID = uuid.uuid4().hex
os.environ["SHOPEE_RADAR_DB_PATH"] = str(Path("data") / f"radar_assets_test_{RUN_ID}.db")

from shopee_core import radar_assets_service
from shopee_core.radar_assets_service import (
    download_asset,
    download_product_images,
    guess_extension_from_url_or_content_type,
    sanitize_filename,
)
from shopee_core.radar_service import add_product_url, list_product_assets


class FakeResponse:
    def __init__(self, status_code=200, content=b"fake-image", content_type="image/jpeg"):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type}


def _create_product() -> str:
    suffix = uuid.uuid4().hex[:8]
    created = add_product_url(
        f"https://produto.mercadolivre.com.br/MLB-{RUN_ID[:8]}{suffix}-asset-test-_JM",
        "competitor_candidate",
    )
    return created["product"]["product_uid"]


def _patch_get(response_or_exc):
    def fake_get(url, timeout=30, headers=None):
        if isinstance(response_or_exc, Exception):
            raise response_or_exc
        return response_or_exc

    radar_assets_service.requests.get = fake_get


def test_sanitize_filename():
    assert sanitize_filename(" Mochila / Escolar: Ação 2026! ") == "Mochila_Escolar_Acao_2026"
    assert sanitize_filename("...") == "asset"
    return True


def test_guess_extension_from_url_or_content_type():
    assert guess_extension_from_url_or_content_type("https://x.test/a.webp?size=1", None) == ".webp"
    assert guess_extension_from_url_or_content_type("https://x.test/a", "image/jpeg") == ".jpg"
    assert guess_extension_from_url_or_content_type("https://x.test/a", "image/png; charset=binary") == ".png"
    return True


def test_download_creates_product_folder_and_file():
    with tempfile.TemporaryDirectory() as tmp_dir:
        radar_assets_service.ASSETS_BASE_DIR = Path(tmp_dir)
        _patch_get(FakeResponse(content=b"abc", content_type="image/jpeg"))
        product_uid = _create_product()

        asset = download_asset("https://img.example.com/produto.jpg", product_uid, "image")
        local_path = Path(asset["local_path"])

        assert asset["downloaded"] is True
        assert local_path.exists()
        assert local_path.read_bytes() == b"abc"
        assert local_path.parent == Path(tmp_dir) / product_uid / "images"
        return True


def test_download_product_images_deduplicates():
    with tempfile.TemporaryDirectory() as tmp_dir:
        radar_assets_service.ASSETS_BASE_DIR = Path(tmp_dir)
        _patch_get(FakeResponse(content=b"abc", content_type="image/jpeg"))
        product_uid = _create_product()

        assets = download_product_images(
            product_uid,
            [
                "https://img.example.com/a.jpg",
                "https://img.example.com/a.jpg",
                "https://img.example.com/b.jpg",
            ],
        )

        assert len(assets) == 2
        assert len(list_product_assets(product_uid, "image")) == 2
        return True


def test_download_asset_registers_local_path_and_reuses_existing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        radar_assets_service.ASSETS_BASE_DIR = Path(tmp_dir)
        _patch_get(FakeResponse(content=b"abc", content_type="image/jpeg"))
        product_uid = _create_product()

        first = download_asset("https://img.example.com/reuse.jpg", product_uid, "image")
        second = download_asset("https://img.example.com/reuse.jpg", product_uid, "image")

        assert first["local_path"] == second["local_path"]
        assert second["downloaded"] is False
        assert len(list_product_assets(product_uid, "image")) == 1
        return True


def test_download_failure_does_not_register_asset():
    with tempfile.TemporaryDirectory() as tmp_dir:
        radar_assets_service.ASSETS_BASE_DIR = Path(tmp_dir)
        _patch_get(FakeResponse(status_code=500, content=b"", content_type="text/html"))
        product_uid = _create_product()

        try:
            download_asset("https://img.example.com/fail.jpg", product_uid, "image")
        except RuntimeError:
            assert len(list_product_assets(product_uid, "image")) == 0
            return True
        raise AssertionError("download_asset deveria falhar com HTTP 500")


if __name__ == "__main__":
    print("\nTESTE R3 - Assets do Radar\n")

    tests = [
        ("sanitize_filename", test_sanitize_filename),
        ("guess_extension_from_url_or_content_type", test_guess_extension_from_url_or_content_type),
        ("download cria pasta por product_uid", test_download_creates_product_folder_and_file),
        ("download_product_images deduplica", test_download_product_images_deduplicates),
        ("download registra local_path e reutiliza", test_download_asset_registers_local_path_and_reuses_existing),
        ("download falho nao registra asset", test_download_failure_does_not_register_asset),
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
