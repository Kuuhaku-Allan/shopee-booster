#!/usr/bin/env python3
"""
Collect one Radar product URL in a visible browser.

Usage:
    python scripts/radar_collect_url.py "https://shopee.com.br/produto..."
    python scripts/radar_collect_url.py "https://produto.mercadolivre.com.br/..." --save
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_collector import collect_product_page
from shopee_core.radar_service import (
    add_product_url,
    mark_job_done,
    mark_product_collected,
    save_product_assets,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta uma URL de produto do Radar R2.")
    parser.add_argument("url", help="URL de produto da Shopee ou Mercado Livre")
    parser.add_argument(
        "--save",
        action="store_true",
        help="Salva/atualiza o produto no data/radar.db",
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
        help="Classificacao inicial quando --save cria o produto",
    )
    parser.add_argument("--owner-user-id", default=None)
    parser.add_argument("--niche", default=None)

    args = parser.parse_args()

    try:
        data = collect_product_page(args.url)

        if args.save:
            created = add_product_url(
                args.url,
                source_type=args.source_type,
                owner_user_id=args.owner_user_id,
                niche=args.niche,
            )
            product_uid = created["product"]["product_uid"]
            product = mark_product_collected(product_uid, data)
            assets = save_product_assets(
                product_uid,
                image_urls=data.get("image_urls") or [],
                video_urls=data.get("video_urls") or [],
            )
            job = created.get("job")
            if job and job.get("job_uid"):
                mark_job_done(job["job_uid"])
            data["_saved"] = {
                "product_uid": product_uid,
                "status": product["status"],
                "assets_saved": len(assets),
            }

        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
