#!/usr/bin/env python3
"""
Seed R4.1 smoke products for the rule-based relevance filter.

Usage:
    python scripts/radar_seed_relevance_smoke.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_service import (
    add_product_url,
    classify_product,
    mark_product_collected,
)


SMOKE_OWNER_ID = "radar-r4-1-smoke"
SMOKE_NICHE = "mochila-infantil-feminina-escolar"

SMOKE_PRODUCTS = [
    {
        "key": "own",
        "source_type": "own_product",
        "url": "https://produto.mercadolivre.com.br/MLB-4100000001-radar-r41-own-mochila-infantil-princesa-rosa-_JM",
        "title": "Mochila Infantil Princesa Rosa Escolar Feminina Grande",
        "description": (
            "Mochila infantil feminina rosa para escola, ideal para meninas, "
            "com tema princesa, espaco para cadernos, estojo e material escolar. "
            "Produto voltado para criancas em idade escolar."
        ),
        "price": 89.90,
        "expected": "own_product",
    },
    {
        "key": "direct_rodinhas",
        "source_type": "competitor_candidate",
        "url": "https://produto.mercadolivre.com.br/MLB-4100000002-radar-r41-mochila-princesa-rodinhas-_JM",
        "title": "Mochila Escolar Infantil Feminina Princesa Rosa com Rodinhas",
        "description": (
            "Mochila infantil feminina rosa com tema princesa para escola, "
            "com rodinhas e alcas para meninas."
        ),
        "price": 99.90,
        "expected": "competitor_direct",
    },
    {
        "key": "direct_or_partial_grande",
        "source_type": "competitor_candidate",
        "url": "https://produto.mercadolivre.com.br/MLB-4100000003-radar-r41-mochila-infantil-rosa-grande-_JM",
        "title": "Mochila Infantil Feminina Rosa Escolar Grande",
        "description": (
            "Mochila infantil feminina rosa grande para rotina escolar, "
            "com bom espaco interno para cadernos e material escolar."
        ),
        "price": 84.90,
        "expected": "competitor_direct_or_partial_high",
    },
    {
        "key": "partial_juvenil",
        "source_type": "competitor_candidate",
        "url": "https://produto.mercadolivre.com.br/MLB-4100000004-radar-r41-mochila-juvenil-colorida-_JM",
        "title": "Mochila Escolar Juvenil Feminina Colorida",
        "description": (
            "Mochila escolar feminina juvenil colorida para adolescentes, "
            "com compartimentos para cadernos e material de aula."
        ),
        "price": 109.90,
        "expected": "competitor_partial",
    },
    {
        "key": "low_notebook",
        "source_type": "competitor_candidate",
        "url": "https://produto.mercadolivre.com.br/MLB-4100000005-radar-r41-mochila-universitaria-notebook-preta-_JM",
        "title": "Mochila Universitaria Notebook Executiva Preta",
        "description": (
            "Mochila adulta executiva preta para trabalho e faculdade, "
            "com compartimento para notebook."
        ),
        "price": 249.90,
        "expected": "rejected_or_low_partial",
    },
    {
        "key": "rejected_lancheira",
        "source_type": "competitor_candidate",
        "url": "https://produto.mercadolivre.com.br/MLB-4100000006-radar-r41-lancheira-infantil-rosa-princesa-_JM",
        "title": "Lancheira Infantil Rosa Princesa Termica",
        "description": (
            "Lancheira termica infantil rosa com tema princesa para levar "
            "lanche escolar."
        ),
        "price": 39.90,
        "expected": "rejected",
    },
    {
        "key": "rejected_estojo",
        "source_type": "competitor_candidate",
        "url": "https://produto.mercadolivre.com.br/MLB-4100000007-radar-r41-estojo-escolar-infantil-rosa-_JM",
        "title": "Estojo Escolar Infantil Rosa",
        "description": (
            "Estojo escolar infantil rosa para lapis, canetas e pequenos "
            "materiais escolares."
        ),
        "price": 24.90,
        "expected": "rejected",
    },
]


def main() -> int:
    seeded = []
    for item in SMOKE_PRODUCTS:
        result = add_product_url(
            item["url"],
            item["source_type"],
            owner_user_id=SMOKE_OWNER_ID,
            niche=SMOKE_NICHE,
        )
        product_uid = result["product"]["product_uid"]
        classify_product(product_uid, item["source_type"], 0.0, rejection_reason=None)
        product = mark_product_collected(product_uid, _product_data(item))
        seeded.append(
            {
                "key": item["key"],
                "product_uid": product_uid,
                "source_type": product["source_type"],
                "title": product["title"],
                "expected": item["expected"],
                "created": result["created"],
            }
        )

    own = next(item for item in seeded if item["key"] == "own")
    print(json.dumps({"own_product_uid": own["product_uid"], "products": seeded}, ensure_ascii=False, indent=2))
    return 0


def _product_data(item: dict) -> dict:
    return {
        "title": item["title"],
        "price": item["price"],
        "shop_name": "Radar R4.1 Smoke",
        "marketplace": "mercadolivre",
        "description": item["description"],
        "category_path": ["Moda", "Mochilas e Bolsas", "Escolar"],
        "attributes": {
            "Tipo": _product_type_for(item),
            "Publico": "infantil feminino" if "Infantil" in item["title"] else "geral",
            "Uso": _use_case_for(item),
        },
        "image_urls": [],
        "video_urls": [],
        "raw": {
            "smoke_phase": "R4.1",
            "smoke_key": item["key"],
            "expected": item["expected"],
        },
    }


def _product_type_for(item: dict) -> str:
    title = item["title"].lower()
    if "lancheira" in title:
        return "lancheira"
    if "estojo" in title:
        return "estojo"
    if "mala" in title:
        return "mala"
    if "bolsa" in title:
        return "bolsa"
    return "mochila"


def _use_case_for(item: dict) -> str:
    title = item["title"].lower()
    if "universitaria" in title or "executiva" in title or "notebook" in title:
        return "faculdade trabalho notebook"
    if "lancheira" in title:
        return "lanche escolar"
    if "estojo" in title:
        return "material escolar"
    return "escolar"


if __name__ == "__main__":
    raise SystemExit(main())
