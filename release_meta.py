"""
Metadados leves de release usados pelo app, updater e empacotamento.
Mantém a versão em um único lugar para evitar divergência entre UI e updater.
"""

from __future__ import annotations

import os
import sys

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLED_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLED_DIR = BASE_DIR

DEFAULT_VERSION = "4.0.0"

GITHUB_USUARIO = "Kuuhaku-Allan"
GITHUB_REPO = "shopee-booster"


def get_current_version() -> str:
    candidate_files = [
        os.path.join(BASE_DIR, "version.txt"),
        os.path.join(BUNDLED_DIR, "version.txt"),
        os.path.join(BASE_DIR, "_internal", "version.txt"),
    ]

    for version_file in candidate_files:
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                version = f.read().strip()
            if version:
                return version
        except Exception:
            continue

    return DEFAULT_VERSION


VERSAO_ATUAL = get_current_version()
