#!/usr/bin/env python3
"""
Collect one Mercado Livre product URL with the R3 deep collector.

Usage:
    python scripts/radar_collect_deep_url.py "https://produto.mercadolivre.com.br/..." --save-assets
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_assets_service import download_asset, download_product_images
from shopee_core.radar_collector import collect_product_page, is_collection_blocked_or_empty
from shopee_core.radar_service import (
    add_product_url,
    detect_marketplace,
    mark_job_done,
    mark_product_collected,
    save_product_assets,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta profunda R3 por URL.")
    parser.add_argument("url", help="URL de produto do Mercado Livre")
    parser.add_argument(
        "--save-assets",
        action="store_true",
        help="Baixa imagens/videos para data/radar_assets",
    )
    parser.add_argument(
        "--source-type",
        default="competitor_candidate",
        choices=[
            "own_product",
            "competitor_candidate",
            "competitor_direct",
            "competitor_partial",
            "rejected",
        ],
        help="Classificacao inicial quando cria o produto",
    )
    parser.add_argument("--owner-user-id", default=None)
    parser.add_argument("--niche", default=None)
    parser.add_argument(
        "--browser-channel",
        choices=["chromium", "chrome", "msedge"],
        default=None,
        help="Usa Chromium padrao, Google Chrome ou Microsoft Edge instalado",
    )
    parser.add_argument(
        "--browser-mode",
        choices=["persistent", "cdp"],
        default="persistent",
        help="persistent abre perfil Playwright; cdp conecta no Chrome real do Radar",
    )
    parser.add_argument(
        "--cdp-url",
        default="http://127.0.0.1:9222",
        help="Endpoint CDP quando --browser-mode cdp",
    )
    args = parser.parse_args()

    marketplace = detect_marketplace(args.url)
    if marketplace != "mercadolivre":
        print(
            "ERRO: R3 profunda esta focada em Mercado Livre. "
            f"Marketplace detectado: {marketplace}",
            file=sys.stderr,
        )
        return 1

    try:
        data = collect_product_page(
            args.url,
            marketplace="mercadolivre",
            browser_channel=args.browser_channel,
            browser_mode=args.browser_mode,
            cdp_url=args.cdp_url,
        )
        if is_collection_blocked_or_empty(data):
            raise RuntimeError(
                "Coleta bloqueada ou incompleta. Resolva login/verificacao "
                "manualmente e tente novamente."
            )
        created = add_product_url(
            args.url,
            source_type=args.source_type,
            owner_user_id=args.owner_user_id,
            niche=args.niche,
        )
        product_uid = created["product"]["product_uid"]
        product = mark_product_collected(product_uid, data)

        if args.save_assets:
            assets = download_product_images(product_uid, data.get("image_urls") or [])
            for image_url in data.get("description_image_urls") or []:
                try:
                    assets.append(download_asset(image_url, product_uid, "description_image"))
                except Exception as exc:
                    assets.append(_asset_download_error(product_uid, "description_image", image_url, exc))
            for video_url in data.get("video_urls") or []:
                try:
                    assets.append(download_asset(video_url, product_uid, "video"))
                except Exception as exc:
                    assets.append(_asset_download_error(product_uid, "video", video_url, exc))
        else:
            assets = save_product_assets(
                product_uid,
                image_urls=data.get("image_urls") or [],
                video_urls=data.get("video_urls") or [],
            )

        job = created.get("job")
        if job and job.get("job_uid"):
            mark_job_done(job["job_uid"])

        local_assets = [asset for asset in assets if asset.get("local_path")]
        asset_errors = [asset for asset in assets if asset.get("error")]
        summary = {
            "product_uid": product_uid,
            "status": product["status"],
            "title": data.get("title"),
            "price": data.get("price"),
            "shop_name": data.get("shop_name"),
            "rating": data.get("rating"),
            "review_count": data.get("review_count"),
            "sold_count": data.get("sold_count"),
            "description_collected": bool(data.get("description")),
            "images_found": len(data.get("image_urls") or []),
            "description_images_found": len(data.get("description_image_urls") or []),
            "assets_saved": len(assets),
            "assets_downloaded": len(local_assets),
            "asset_errors": len(asset_errors),
            "local_paths": [asset.get("local_path") for asset in local_assets],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1


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


if __name__ == "__main__":
    raise SystemExit(main())
