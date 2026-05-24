#!/usr/bin/env python3
"""
scripts/radar_store_smoke.py — Smoke automatizado do Espelho da Loja (R7.0A).

Fluxo:
  1. Criar loja de teste ou reusar slug informado
  2. Salvar snapshot inicial com 5 produtos fake/realistas
  3. Inspecionar cache
  4. Salvar segundo snapshot com:
       - 1 produto novo
       - 1 produto com preco alterado
       - 1 produto ausente
  5. Imprimir diff
  6. Confirmar radar_products own_product vinculados
  7. Limpar ao final (use --no-cleanup para preservar)

Uso:
    python scripts/radar_store_smoke.py
    python scripts/radar_store_smoke.py --shop-slug minha-loja --no-cleanup
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_db import DB_PATH, get_connection, init_db
from shopee_core.radar_store_service import (
    diff_store_snapshot,
    get_cached_store_products,
    get_store_snapshot_status,
    save_store_snapshot,
)
RUN_ID = uuid.uuid4().hex[:8]


def _make_snapshots(run_id: str) -> tuple[list[dict], list[dict]]:
    """Gera snapshots com IDs unicos por run para evitar conflitos entre runs."""
    shop_id = f"smoke-{run_id}"
    snap1 = [
        {"itemid": f"{run_id}-s001", "shopid": shop_id, "name": "Mochila Escolar Infantil Rosa 20L", "price": 89.90, "image": "https://example.com/img1.jpg"},
        {"itemid": f"{run_id}-s002", "shopid": shop_id, "name": "Mochila Feminina Casual Preta", "price": 129.90, "image": "https://example.com/img2.jpg"},
        {"itemid": f"{run_id}-s003", "shopid": shop_id, "name": "Mochila Masculina Impermeavel Azul", "price": 149.90, "image": "https://example.com/img3.jpg"},
        {"itemid": f"{run_id}-s004", "shopid": shop_id, "name": "Mochila com Rodas Juvenil Vermelha", "price": 199.90, "image": "https://example.com/img4.jpg"},
        {"itemid": f"{run_id}-s005", "shopid": shop_id, "name": "Kit Escolar Completo Infantil", "price": 59.90, "image": "https://example.com/img5.jpg"},
    ]
    # Snap2: s003 preco alterado, s005 ausente, s006 novo
    snap2 = [
        {"itemid": f"{run_id}-s001", "shopid": shop_id, "name": "Mochila Escolar Infantil Rosa 20L", "price": 89.90, "image": "https://example.com/img1.jpg"},
        {"itemid": f"{run_id}-s002", "shopid": shop_id, "name": "Mochila Feminina Casual Preta", "price": 129.90, "image": "https://example.com/img2.jpg"},
        {"itemid": f"{run_id}-s003", "shopid": shop_id, "name": "Mochila Masculina Impermeavel Azul", "price": 169.90, "image": "https://example.com/img3.jpg"},  # preco alterado
        {"itemid": f"{run_id}-s004", "shopid": shop_id, "name": "Mochila com Rodas Juvenil Vermelha", "price": 199.90, "image": "https://example.com/img4.jpg"},
        # s005 ausente
        {"itemid": f"{run_id}-s006", "shopid": shop_id, "name": "Mochila Anti-Furto USB Cinza", "price": 219.90, "image": "https://example.com/img6.jpg"},  # novo
    ]
    return snap1, snap2


def _print_section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _print_json(data: dict | list) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _check_own_products(store_uid: str) -> list[dict]:
    """Retorna radar_products vinculados como own_product para esta loja."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.product_uid, p.title, p.price, p.source_type, p.status,
                   sp.store_product_uid, sp.status AS sp_status
            FROM radar_store_products sp
            JOIN radar_products p ON p.product_uid = sp.radar_product_uid
            WHERE sp.store_uid = ?
            ORDER BY sp.last_seen_at DESC
            """,
            (store_uid,),
        ).fetchall()
    return [dict(row) for row in rows]


def _cleanup(store_uid: str) -> None:
    """Remove dados de teste do radar.db."""
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        # Remove produtos do radar que eram own_products desta loja
        conn.execute(
            """
            DELETE FROM radar_products
            WHERE product_uid IN (
                SELECT radar_product_uid FROM radar_store_products
                WHERE store_uid = ? AND radar_product_uid IS NOT NULL
            )
            """,
            (store_uid,),
        )
        conn.execute("DELETE FROM radar_store_products WHERE store_uid = ?", (store_uid,))
        conn.execute("DELETE FROM radar_stores WHERE store_uid = ?", (store_uid,))
        conn.execute("PRAGMA foreign_keys = ON")
    print("\n[CLEANUP] Dados de teste removidos do radar.db.")



def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test do Espelho da Loja (R7.0A).")
    parser.add_argument(
        "--shop-slug",
        default=None,
        help="Slug da loja de teste (padrao: gerado automaticamente por run)",
    )
    parser.add_argument(
        "--shop-uid",
        default=None,
        help="shop_uid (padrao: gerado automaticamente por run)",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Nao remover dados de teste ao final",
    )
    args = parser.parse_args()

    shop_slug = args.shop_slug or f"smoke-r70a-{RUN_ID}"
    shop_uid = args.shop_uid or f"smoke-uid-{RUN_ID}"

    SNAPSHOT_1, SNAPSHOT_2 = _make_snapshots(RUN_ID)

    store_info = {
        "shop_uid": shop_uid,
        "shop_slug": shop_slug,
        "shop_name": f"Loja Smoke Test ({shop_slug})",
        "marketplace": "shopee",
        "source_url": f"https://shopee.com.br/{shop_slug}",
    }

    print(f"\n[R7.0A] Smoke test do Espelho da Loja")
    print(f"[R7.0A] DB: {DB_PATH}")
    print(f"[R7.0A] run_id={RUN_ID}")
    print(f"[R7.0A] shop_slug={shop_slug}  shop_uid={shop_uid}")

    # ── PASSO 1: Snapshot inicial ─────────────────────────────────────────
    _print_section("PASSO 1 — Snapshot inicial (5 produtos)")
    summary1 = save_store_snapshot(store_info, SNAPSHOT_1, source="smoke_test")
    store_uid_val = summary1["store_uid"]
    print(f"store_uid     : {store_uid_val}")
    print(f"total_received: {summary1['total_received']}")
    print(f"created       : {summary1['created']}")
    print(f"updated       : {summary1['updated']}")
    print(f"errors        : {summary1['errors']}")

    assert summary1["created"] == 5, f"Esperado 5 created, got {summary1['created']}"
    assert summary1["errors"] == [], f"Erros inesperados: {summary1['errors']}"
    print("[OK] Snapshot 1 OK")

    # ── PASSO 2: Inspecionar cache ────────────────────────────────────────
    _print_section("PASSO 2 — Inspecionar cache após snapshot 1")
    cached = get_cached_store_products(shop_slug=shop_slug)
    status = get_store_snapshot_status(store_uid_val)
    print(f"Produtos no cache: {len(cached)}")
    print(f"Status agregado:")
    _print_json(status)
    for p in cached:
        print(f"  [{p.get('cache_status')}] {p.get('title')} — R$ {p.get('price')}")
        print(f"    radar_product_uid: {p.get('radar_product_uid')}")
    assert len(cached) == 5, f"Esperado 5 produtos no cache, got {len(cached)}"
    print("[OK] Cache OK")

    # ── PASSO 3: Verificar own_products ──────────────────────────────────
    _print_section("PASSO 3 — Verificar radar_products own_product")
    own_products = _check_own_products(store_uid_val)
    print(f"radar_products vinculados: {len(own_products)}")
    for op in own_products:
        print(f"  source_type={op.get('source_type')} status={op.get('status')}")
        print(f"  title: {op.get('title')} | price: {op.get('price')}")
    all_own = all(op["source_type"] == "own_product" for op in own_products)
    assert all_own, "Todos os products deveriam ter source_type='own_product'"
    assert len(own_products) == 5, f"Esperado 5 own_products, got {len(own_products)}"
    print("[OK] own_products OK")

    # ── PASSO 4: Diff (antes do snapshot 2) ──────────────────────────────
    _print_section("PASSO 4 — Diff entre snapshot 1 e snapshot 2 (preview)")
    diff = diff_store_snapshot(store_uid_val, SNAPSHOT_2)
    print("Resumo do diff:")
    _print_json(diff["summary"])
    print(f"Novos: {[p.get('title') for p in diff['new_products']]}")
    print(f"Ausentes: {[p.get('title') for p in diff['missing_products']]}")
    print(f"Preço alterado: {[(p['old'].get('title'), p['old'].get('price'), '->', p['new'].get('price')) for p in diff['price_changed']]}")
    assert diff["summary"]["new"] == 1, f"Esperado 1 novo, got {diff['summary']['new']}"
    assert diff["summary"]["missing"] == 1, f"Esperado 1 ausente, got {diff['summary']['missing']}"
    assert diff["summary"]["price_changed"] == 1, f"Esperado 1 preco alterado, got {diff['summary']['price_changed']}"
    print("[OK] Diff OK")

    # ── PASSO 5: Snapshot 2 (aplica mudancas) ────────────────────────────
    _print_section("PASSO 5 — Snapshot 2 (1 novo, 1 preco alterado, 1 ausente)")
    summary2 = save_store_snapshot(store_info, SNAPSHOT_2, source="smoke_test_v2")
    print(f"total_received: {summary2['total_received']}")
    print(f"created       : {summary2['created']}")
    print(f"updated       : {summary2['updated']}")
    print(f"unchanged     : {summary2['unchanged']}")
    print(f"missing       : {summary2['missing']}")
    assert summary2["created"] == 1, f"Esperado 1 created (s006), got {summary2['created']}"
    assert summary2["missing"] == 1, f"Esperado 1 missing (s005), got {summary2['missing']}"
    assert summary2["updated"] >= 1, f"Esperado pelo menos 1 updated (s003), got {summary2['updated']}"
    print("[OK] Snapshot 2 OK")

    # ── PASSO 6: Estado final ─────────────────────────────────────────────
    _print_section("PASSO 6 — Estado final do espelho")
    status_final = get_store_snapshot_status(store_uid_val)
    cached_final = get_cached_store_products(shop_slug=shop_slug, include_removed=True)
    print(f"Status final:")
    _print_json(status_final)
    print(f"\nProdutos no espelho (incluindo missing):")
    for p in cached_final:
        price_val = p.get('price')
        price_str = f"R$ {price_val:.2f}" if price_val is not None else "N/A"
        print(f"  [{p.get('cache_status')}] {p.get('title')} — {price_str}")
    changed = [p for p in cached_final if p.get("cache_status") == "changed"]
    missing = [p for p in cached_final if p.get("cache_status") == "missing"]
    assert len(changed) >= 1, "Esperado pelo menos 1 produto com status 'changed'"
    assert len(missing) == 1, f"Esperado 1 missing, got {len(missing)}"
    print("[OK] Estado final OK")

    # ── RESULTADO ─────────────────────────────────────────────────────────
    _print_section("RESULTADO FINAL")
    print("[OK] Todos os checks do smoke test passaram!")
    print(f"\n[DB] DB: {DB_PATH}")
    print(f"[LOJA] store_uid: {store_uid_val}")
    print(f"[KEY] shop_slug: {shop_slug}")
    print(f"\nPara inspecionar manualmente:")
    print(f"  python scripts/radar_inspect_store.py --shop-uid {shop_slug}")

    if not args.no_cleanup:
        _cleanup(store_uid_val)
    else:
        print(f"\n[--no-cleanup] Dados de teste preservados no radar.db.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
