#!/usr/bin/env python3
"""
Collect pending Radar jobs in a visible browser.

Usage:
    python scripts/radar_collect_pending.py --limit 5
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
    parser = argparse.ArgumentParser(description="Coleta jobs pendentes do Radar R2.")
    parser.add_argument("--limit", type=int, default=5, help="Numero maximo de jobs pendentes")
    args = parser.parse_args()

    try:
        summary = collect_pending_jobs(limit=args.limit)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["failed"] == 0 else 1
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
