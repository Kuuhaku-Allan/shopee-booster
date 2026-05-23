#!/usr/bin/env python3
"""
Start the dedicated Chrome profile used by Radar CDP mode.

Usage:
    python scripts/radar_start_browser_cdp.py
    python scripts/radar_start_browser_cdp.py --marketplace shopee
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
START_SCRIPT = ROOT_DIR / "deploy" / "local" / "start-radar-chrome.ps1"


def main() -> int:
    parser = argparse.ArgumentParser(description="Abre o Chrome real dedicado do Radar.")
    parser.add_argument("--marketplace", choices=["mercadolivre", "shopee"], default="mercadolivre")
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--dry-run", action="store_true", help="Mostra o comando sem abrir o Chrome")
    args = parser.parse_args()

    if not START_SCRIPT.exists():
        print(f"Script PowerShell nao encontrado: {START_SCRIPT}", file=sys.stderr)
        return 1

    command = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(START_SCRIPT),
        "-Port",
        str(args.port),
        "-Marketplace",
        args.marketplace,
    ]
    if args.dry_run:
        command.append("-DryRun")

    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
