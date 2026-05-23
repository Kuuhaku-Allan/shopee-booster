#!/usr/bin/env python3
"""
Run the R5.1 full market smoke for Mercado Livre backpack URLs.

Usage:
    python scripts/radar_run_full_market_smoke.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shopee_core.radar_assets_service import download_asset, download_product_images
from shopee_core.radar_browser_service import (
    DEFAULT_CDP_URL,
    is_cdp_available,
    open_radar_browser_instructions,
)
from shopee_core.radar_collector import (
    collect_product_page,
    is_collection_blocked_or_empty,
    validate_product_extraction,
)
from shopee_core.radar_patterns_service import generate_pattern_report
from shopee_core.radar_relevance_service import classify_candidate, get_matches_for_product
from shopee_core.radar_service import (
    add_product_url,
    classify_product,
    detect_marketplace,
    mark_job_done,
    mark_job_failed,
    mark_product_collected,
    mark_product_failed,
    save_product_assets,
)


SMOKE_OWNER_ID = "radar-r5-1-market-smoke"
SMOKE_NICHE = "mochila-infantil-feminina-escolar"
DEFAULT_URLS_PATH = ROOT_DIR / "data" / "radar_smoke_urls_mochilas_ml.txt"
OWN_PRODUCT = {
    "url": "https://produto.mercadolivre.com.br/MLB-4200000001-radar-r51-own-mochila-infantil-princesa-rosa-_JM",
    "title": "Mochila Infantil Princesa Rosa Escolar Feminina Grande",
    "price": 89.90,
    "description": (
        "Mochila infantil feminina rosa para escola, ideal para meninas, "
        "com tema princesa, espaco para cadernos, estojo e material escolar. "
        "Produto voltado para criancas em idade escolar."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke real R5.1 com URLs do Mercado Livre.")
    parser.add_argument("--urls-file", default=str(DEFAULT_URLS_PATH))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-success", type=int, default=8)
    parser.add_argument("--min-quality-ok", type=int, default=12)
    parser.add_argument("--min-direct", type=int, default=5)
    parser.add_argument("--min-report-direct", type=int, default=5)
    parser.add_argument(
        "--browser-channel",
        choices=["chromium", "chrome", "msedge"],
        default=os.getenv("RADAR_BROWSER_CHANNEL", "chrome"),
    )
    parser.add_argument(
        "--browser-mode",
        choices=["persistent", "cdp"],
        default="persistent",
        help="persistent abre perfil Playwright; cdp conecta no Chrome real do Radar",
    )
    parser.add_argument(
        "--cdp-url",
        default=DEFAULT_CDP_URL,
        help="Endpoint CDP quando --browser-mode cdp",
    )
    parser.add_argument(
        "--manual-login-check",
        action="store_true",
        help="Confirma CDP aberto e pausa para login manual antes da coleta",
    )
    parser.add_argument("--refresh", action="store_true", help="Recoleta produtos ja coletados")
    parser.add_argument("--no-save-assets", action="store_true", help="Registra URLs sem baixar assets")
    args = parser.parse_args()

    if args.browser_mode == "cdp":
        try:
            _check_cdp_or_fail(args.cdp_url)
        except RuntimeError as exc:
            print(f"ERRO: {exc}", file=sys.stderr)
            return 1
        if args.manual_login_check:
            input(
                "Confirme login/verificacao no Chrome do Radar e pressione ENTER para iniciar o smoke."
            )

    urls = _read_urls(Path(args.urls_file))
    if args.limit:
        urls = urls[: args.limit]

    own = _ensure_own_product()
    candidates = []
    collection_results = []

    for index, url in enumerate(urls, start=1):
        result = _process_candidate_url(
            url=url,
            index=index,
            total=len(urls),
            browser_channel=args.browser_channel,
            browser_mode=args.browser_mode,
            cdp_url=args.cdp_url,
            refresh=args.refresh,
            save_assets=not args.no_save_assets,
        )
        collection_results.append(result)
        if result.get("ok") and result.get("product_uid"):
            candidates.append(result["product_uid"])

    classification_results = []
    for product_uid in candidates:
        try:
            result = classify_candidate(own["product_uid"], product_uid)
            classification_results.append(
                {
                    "product_uid": product_uid,
                    "title": result["candidate_product"].get("title"),
                    "verdict": result["verdict"],
                    "score": result["score"],
                    "confidence": result["confidence"],
                    "reasons": result["reasons"],
                    "ok": True,
                }
            )
        except Exception as exc:
            classification_results.append(
                {
                    "product_uid": product_uid,
                    "ok": False,
                    "error": str(exc),
                }
            )

    report = generate_pattern_report(
        own["product_uid"],
        include_partial=False,
        min_direct=args.min_report_direct,
        save=True,
    )
    summary = _build_summary(
        urls=urls,
        own=own,
        collection_results=collection_results,
        classification_results=classification_results,
        report=report,
    )
    _print_summary(summary, report)

    if summary["collected_success"] < args.min_success:
        print(
            f"\nERRO: apenas {summary['collected_success']} coletas com sucesso; minimo esperado {args.min_success}.",
            file=sys.stderr,
        )
        return 1
    if summary["quality_ok"] < args.min_quality_ok:
        print(
            f"\nERRO: apenas {summary['quality_ok']} coletas com qualidade OK; minimo esperado {args.min_quality_ok}.",
            file=sys.stderr,
        )
        return 1
    if summary["direct"] < args.min_direct:
        print(
            f"\nERRO: apenas {summary['direct']} concorrentes diretos; minimo esperado {args.min_direct}.",
            file=sys.stderr,
        )
        return 1

    return 0


def _read_urls(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de URLs nao encontrado: {path}")
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        urls.append(clean)
    return urls


def _check_cdp_or_fail(cdp_url: str) -> None:
    if is_cdp_available(cdp_url):
        return
    open_radar_browser_instructions()
    raise RuntimeError(
        "Chrome do Radar nao esta aberto. Rode deploy/local/start-radar-chrome.ps1 "
        "e faca login manual antes de usar --browser-mode cdp."
    )


def _ensure_quality(data: dict, product: dict) -> dict:
    data = dict(data)
    data.setdefault("url", product.get("url"))
    data.setdefault("canonical_url", product.get("canonical_url"))
    data.setdefault("marketplace", product.get("marketplace"))
    data.setdefault("title", product.get("title"))
    data.setdefault("price", product.get("price"))
    quality = data.get("quality")
    if not isinstance(quality, dict):
        quality = validate_product_extraction(data, product.get("marketplace") or "mercadolivre")
        data["quality"] = quality
        raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
        raw["quality"] = quality
        data["raw"] = raw
    return data


def _quality_error_message(quality: dict) -> str:
    return "Coleta de baixa qualidade: " + "; ".join(
        str(error) for error in (quality.get("errors") or ["sem detalhe"])[:4]
    )


def _ensure_own_product() -> dict:
    created = add_product_url(
        OWN_PRODUCT["url"],
        "own_product",
        owner_user_id=SMOKE_OWNER_ID,
        niche=SMOKE_NICHE,
    )
    product_uid = created["product"]["product_uid"]
    classify_product(product_uid, "own_product", 0.0, None)
    return mark_product_collected(
        product_uid,
        {
            "title": OWN_PRODUCT["title"],
            "price": OWN_PRODUCT["price"],
            "shop_name": "Radar R5.1 Smoke",
            "marketplace": "mercadolivre",
            "description": OWN_PRODUCT["description"],
            "category_path": ["Moda", "Mochilas e Bolsas", "Escolar"],
            "attributes": {
                "Tipo": "mochila",
                "Publico": "infantil feminino",
                "Uso": "escolar",
            },
            "image_urls": [],
            "video_urls": [],
            "raw": {"smoke_phase": "R5.1", "role": "own_product"},
        },
    )


def _process_candidate_url(
    *,
    url: str,
    index: int,
    total: int,
    browser_channel: str | None,
    browser_mode: str,
    cdp_url: str,
    refresh: bool,
    save_assets: bool,
) -> dict:
    print(f"\n[R5.1] ({index}/{total}) {url}", flush=True)
    if detect_marketplace(url) != "mercadolivre":
        return {"url": url, "ok": False, "error": "Marketplace nao suportado"}

    created = add_product_url(
        url,
        "competitor_candidate",
        owner_user_id=SMOKE_OWNER_ID,
        niche=SMOKE_NICHE,
    )
    product = created["product"]
    product_uid = product["product_uid"]
    classify_product(product_uid, "competitor_candidate", 0.0, None)

    if product.get("raw_json") and product.get("status") == "collected" and not refresh:
        data = json.loads(product["raw_json"])
        data = _ensure_quality(data, product)
        if data["quality"].get("ok"):
            mark_product_collected(product_uid, data)
            assets = _persist_assets(product_uid, data, save_assets=save_assets)
            local_assets = [asset for asset in assets if asset.get("local_path")]
            asset_errors = [asset for asset in assets if asset.get("error")]
            print(f"[R5.1] Reaproveitado: {product.get('title')}", flush=True)
            return {
                "url": url,
                "product_uid": product_uid,
                "ok": True,
                "reused": True,
                "title": product.get("title"),
                "price": product.get("price"),
                "quality": data["quality"],
                "assets_saved": len(assets),
                "assets_downloaded": len(local_assets),
                "asset_errors": len(asset_errors),
            }
        print(
            "[R5.1] Recoletando por baixa qualidade: "
            + "; ".join(data["quality"].get("errors") or []),
            flush=True,
        )

    job = created.get("job")
    try:
        data = collect_product_page(
            url,
            marketplace="mercadolivre",
            browser_channel=browser_channel,
            browser_mode=browser_mode,
            cdp_url=cdp_url,
        )
        if is_collection_blocked_or_empty(data):
            raise RuntimeError("Coleta bloqueada ou incompleta")
        quality = data.get("quality") or validate_product_extraction(data, "mercadolivre")
        if not quality.get("ok"):
            error = _quality_error_message(quality)
            mark_product_failed(product_uid, error)
            if job and job.get("job_uid"):
                mark_job_failed(job["job_uid"], error)
            print(f"[R5.1] Ignorado por baixa qualidade: {error}", flush=True)
            return {
                "url": url,
                "product_uid": product_uid,
                "ok": False,
                "low_quality": True,
                "quality": quality,
                "error": error,
                "title": data.get("title"),
                "price": data.get("price"),
                "assets_saved": 0,
                "assets_downloaded": 0,
                "asset_errors": 0,
            }

        product = mark_product_collected(product_uid, data)
        assets = _persist_assets(product_uid, data, save_assets=save_assets)
        if job and job.get("job_uid"):
            mark_job_done(job["job_uid"])

        local_assets = [asset for asset in assets if asset.get("local_path")]
        asset_errors = [asset for asset in assets if asset.get("error")]
        print(
            f"[R5.1] Coletado: {product.get('title')} | assets={len(assets)}",
            flush=True,
        )
        return {
            "url": url,
            "product_uid": product_uid,
            "ok": True,
            "reused": False,
            "title": product.get("title"),
            "price": product.get("price"),
            "quality": quality,
            "assets_saved": len(assets),
            "assets_downloaded": len(local_assets),
            "asset_errors": len(asset_errors),
        }
    except Exception as exc:
        error = str(exc)
        try:
            mark_product_failed(product_uid, error)
        except Exception:
            pass
        if job and job.get("job_uid"):
            try:
                mark_job_failed(job["job_uid"], error)
            except Exception:
                pass
        print(f"[R5.1] Falha: {error}", flush=True)
        return {"url": url, "product_uid": product_uid, "ok": False, "error": error}


def _persist_assets(product_uid: str, data: dict, save_assets: bool) -> list[dict]:
    if not save_assets:
        return save_product_assets(
            product_uid,
            image_urls=data.get("image_urls") or [],
            video_urls=data.get("video_urls") or [],
        )

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
    return assets


def _asset_download_error(product_uid: str, asset_type: str, source_url: str, exc: Exception) -> dict:
    return {
        "product_uid": product_uid,
        "asset_type": asset_type,
        "source_url": source_url,
        "local_path": None,
        "downloaded": False,
        "error": str(exc),
    }


def _build_summary(
    *,
    urls: list[str],
    own: dict,
    collection_results: list[dict],
    classification_results: list[dict],
    report: dict,
) -> dict:
    collected_success = sum(1 for item in collection_results if item.get("ok"))
    reused = sum(1 for item in collection_results if item.get("reused"))
    failures = [item for item in collection_results if not item.get("ok")]
    quality_ok = sum(
        1
        for item in collection_results
        if item.get("ok") and (item.get("quality") or {}).get("ok")
    )
    quality_warnings = sum(
        1
        for item in collection_results
        if item.get("ok") and (item.get("quality") or {}).get("warnings")
    )
    ignored_low_quality = sum(1 for item in collection_results if item.get("low_quality"))
    generic_title_count = _count_quality_problem(collection_results, "Titulo generico")
    suspicious_price_count = _count_quality_problem(collection_results, "Preco suspeito")
    too_many_assets_count = _count_quality_problem(collection_results, "Assets/imagens demais")
    asset_counts = [
        int(item.get("assets_saved") or 0)
        for item in collection_results
        if item.get("ok")
    ]
    verdict_counts = {"competitor_direct": 0, "competitor_partial": 0, "rejected": 0}
    for item in classification_results:
        verdict = item.get("verdict")
        if verdict in verdict_counts:
            verdict_counts[verdict] += 1

    matches = get_matches_for_product(own["product_uid"])
    return {
        "own_product_uid": own["product_uid"],
        "total_urls": len(urls),
        "collected_success": collected_success,
        "quality_ok": quality_ok,
        "quality_warnings": quality_warnings,
        "ignored_low_quality": ignored_low_quality,
        "generic_title_count": generic_title_count,
        "suspicious_price_count": suspicious_price_count,
        "too_many_assets_count": too_many_assets_count,
        "avg_assets_per_product": round(sum(asset_counts) / len(asset_counts), 2) if asset_counts else 0,
        "reused": reused,
        "failures": len(failures),
        "direct": verdict_counts["competitor_direct"],
        "partial": verdict_counts["competitor_partial"],
        "rejected": verdict_counts["rejected"],
        "average_score": _average_score(classification_results),
        "report_uid": report["report_uid"],
        "price": {
            "min": report.get("price_min"),
            "avg": report.get("price_avg"),
            "median": report.get("price_median"),
            "max": report.get("price_max"),
        },
        "top_title_terms": report["title_terms"].get("top_terms", [])[:10],
        "top_features": report["features"].get("features", [])[:10],
        "top_description_arguments": report["description_patterns"].get("commercial_arguments", [])[:10],
        "recommendations": report.get("recommendations") or [],
        "warnings": report.get("warnings") or [],
        "collection_results": collection_results,
        "classification_results": classification_results,
        "matches": matches,
    }


def _average_score(results: list[dict]) -> float:
    scores = [float(item["score"]) for item in results if item.get("ok") and item.get("score") is not None]
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _count_quality_problem(collection_results: list[dict], needle: str) -> int:
    total = 0
    for item in collection_results:
        quality = item.get("quality") or {}
        messages = list(quality.get("errors") or []) + list(quality.get("warnings") or [])
        if any(needle in str(message) for message in messages):
            total += 1
    return total


def _print_summary(summary: dict, report: dict) -> None:
    print("\n===== R5.1 Smoke Mercado Livre =====")
    print(f"Produto proprio: {summary['own_product_uid']}")
    print(f"Total URLs recebidas: {summary['total_urls']}")
    print(f"Coletadas com sucesso: {summary['collected_success']} (reaproveitadas: {summary['reused']})")
    print(f"Coletadas com qualidade OK: {summary['quality_ok']}")
    print(f"Coletadas com warnings: {summary['quality_warnings']}")
    print(f"Ignoradas por baixa qualidade: {summary['ignored_low_quality']}")
    print(f"Assets medios por produto OK: {summary['avg_assets_per_product']}")
    print(f"Titulos genericos: {summary['generic_title_count']}")
    print(f"Precos suspeitos: {summary['suspicious_price_count']}")
    print(f"Produtos com assets demais: {summary['too_many_assets_count']}")
    print(f"Falhas: {summary['failures']}")
    print(f"Diretos: {summary['direct']}")
    print(f"Parciais: {summary['partial']}")
    print(f"Rejeitados: {summary['rejected']}")
    print(f"Score medio: {summary['average_score']}")
    print(f"Relatorio: {summary['report_uid']}")
    print(
        "Preco: "
        f"min={summary['price']['min']} avg={summary['price']['avg']} "
        f"median={summary['price']['median']} max={summary['price']['max']}"
    )

    print("\nTop termos de titulo:")
    for row in summary["top_title_terms"]:
        print(f"- {row['term']} ({row['count']} / {row['frequency']:.0%})")

    print("\nTop features:")
    for row in summary["top_features"]:
        print(f"- {row['feature']} ({row['count']} / {row['frequency']:.0%})")

    print("\nTop argumentos de descricao:")
    for row in summary["top_description_arguments"]:
        print(f"- {row['argument']} ({row['count']} / {row['frequency']:.0%})")

    print("\nRecomendacoes:")
    for item in summary["recommendations"]:
        print(f"- [{item['priority']}] {item['recommendation']}")
        print(f"  {item['evidence']}")

    if summary["warnings"]:
        print("\nWarnings:")
        for warning in summary["warnings"]:
            print(f"- {warning}")


if __name__ == "__main__":
    raise SystemExit(main())
