#!/usr/bin/env python3
"""
Collect pending Radar jobs in a visible browser.

Usage:
    python scripts/radar_collect_pending.py --limit 5
    python scripts/radar_collect_pending.py --limit 5 --deep --save-assets
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_collector import collect_pending_jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Coleta jobs pendentes do Radar.")
    parser.add_argument("--limit", type=int, default=5, help="Numero maximo de jobs pendentes")
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Usa a coleta profunda disponivel para Mercado Livre",
    )
    parser.add_argument(
        "--save-assets",
        action="store_true",
        help="Baixa assets para data/radar_assets quando suportado",
    )
    parser.add_argument(
        "--browser-channel",
        choices=["chromium", "chrome", "msedge"],
        default=None,
        help="Usa Chromium padrao, Google Chrome ou Microsoft Edge instalado",
    )
    args = parser.parse_args()

    try:
        summary = collect_pending_jobs(
            limit=args.limit,
            save_assets_to_disk=args.save_assets,
            browser_channel=args.browser_channel,
        )
        if args.deep:
            summary["mode"] = "deep"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["failed"] == 0 else 1
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
