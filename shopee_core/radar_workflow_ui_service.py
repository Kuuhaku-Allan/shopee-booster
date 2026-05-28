import uuid
import time
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from shopee_core.radar_db import get_connection, init_db
from shopee_core.radar_collector import detect_marketplace, normalize_product_url
from shopee_core.radar_relevance_service import classify_candidates_for_product
from shopee_core.radar_patterns_service import generate_pattern_report

def _now():
    return datetime.utcnow().isoformat()

def list_own_products_for_radar(limit=200):
    """
    Retorna uma lista de produtos próprios elegíveis para o Radar de Concorrentes.
    (Produtos marcados como own_product na radar_products ou vinculados na radar_store_products).
    """
    init_db()
    
    query = """
    SELECT 
        p.product_uid, p.title, p.price, p.marketplace, p.source_type AS source,
        p.shop_name, p.updated_at,
        (SELECT COUNT(*) FROM radar_pattern_reports rpr WHERE rpr.own_product_uid = p.product_uid) AS has_pattern_report,
        (SELECT COUNT(*) FROM radar_competitor_matches rcm WHERE rcm.own_product_uid = p.product_uid AND rcm.verdict = 'competitor_direct') AS direct_count
    FROM radar_products p
    WHERE p.source_type = 'own_product'
    
    UNION
    
    SELECT 
        sp.radar_product_uid AS product_uid, sp.title, sp.price, s.marketplace, 'store_mirror' AS source,
        s.shop_name, sp.updated_at,
        (SELECT COUNT(*) FROM radar_pattern_reports rpr WHERE rpr.own_product_uid = sp.radar_product_uid) AS has_pattern_report,
        (SELECT COUNT(*) FROM radar_competitor_matches rcm WHERE rcm.own_product_uid = sp.radar_product_uid AND rcm.verdict = 'competitor_direct') AS direct_count
    FROM radar_store_products sp
    JOIN radar_stores s ON s.store_uid = sp.store_uid
    WHERE sp.radar_product_uid IS NOT NULL
      AND sp.radar_product_uid NOT IN (SELECT product_uid FROM radar_products WHERE source_type = 'own_product')
      
    ORDER BY updated_at DESC
    LIMIT ?
    """
    
    with get_connection() as conn:
        rows = conn.execute(query, (limit,)).fetchall()
        
    return [dict(r) for r in rows]

def format_own_product_label(product: dict) -> str:
    title = product.get("title") or "Produto sem título"
    price = product.get("price")
    directs = product.get("direct_count", 0)
    
    if len(title) > 60:
        title = title[:57] + "..."
        
    price_str = f"R$ {price:.2f}" if price is not None else "Sem preço"
    return f"{title} — {price_str} — {directs} concorrentes diretos"

def add_competitor_urls_for_product(own_product_uid: str, urls_text: str, niche: str | None = None) -> dict:
    """
    Recebe um bloco de texto com URLs, limpa, desduplica, valida o marketplace,
    cria na radar_products como pending e vincula via radar_candidate_links.
    """
    init_db()
    lines = [L.strip() for L in urls_text.splitlines() if L.strip()]
    
    total_received = len(lines)
    valid_urls = []
    invalid_count = 0
    
    for url in lines:
        # R7.2G: Bloquear URLs fake de teste antes de qualquer processamento
        if _is_fake_competitor_url(url):
            invalid_count += 1
            continue
        try:
            mkt = detect_marketplace(url)
            norm = normalize_product_url(url)
            if mkt == "unknown" or not norm:
                invalid_count += 1
            else:
                # R7.2G: Normalização ML adicional — remove parâmetros de rastreamento
                norm = _normalize_mercadolivre_url(norm)
                valid_urls.append((mkt, norm, url))
        except Exception:
            invalid_count += 1
            
    # Desduplicar
    unique_map = {}
    for mkt, norm, original in valid_urls:
        if norm not in unique_map:
            unique_map[norm] = (mkt, original)
            
    duplicates_count = len(valid_urls) - len(unique_map)
    created_count = 0
    now = _now()
    
    with get_connection() as conn:
        for norm, (mkt, original) in unique_map.items():
            # Verifica se o produto já existe no radar
            row = conn.execute("SELECT product_uid FROM radar_products WHERE canonical_url = ?", (norm,)).fetchone()
            if row:
                candidate_uid = row["product_uid"]
            else:
                candidate_uid = uuid.uuid4().hex
                conn.execute(
                    """
                    INSERT INTO radar_products (product_uid, source_type, marketplace, url, canonical_url, status, niche, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (candidate_uid, 'competitor_candidate', mkt, original, norm, 'pending', niche, now, now)
                )
                
                # Cria job de coleta
                job_uid = uuid.uuid4().hex
                conn.execute(
                    """
                    INSERT INTO radar_collection_jobs (job_uid, product_uid, url, job_type, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (job_uid, candidate_uid, original, 'product_data', 'pending', now, now)
                )
            
            # Cria vínculo, ignorando duplicatas se o usuário colar repetidas vezes para o MESMO próprio
            try:
                conn.execute(
                    """
                    INSERT INTO radar_candidate_links (link_uid, own_product_uid, candidate_product_uid, source, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, own_product_uid, candidate_uid, 'manual_url', now, now)
                )
                created_count += 1
            except Exception:
                # Falha de UNIQUE(own, candidate) - já estava vinculado
                duplicates_count += 1

    return {
        "total_received": total_received,
        "created": created_count,
        "duplicates": duplicates_count,
        "invalid": invalid_count
    }

def get_radar_queue_summary(own_product_uid: str | None = None) -> dict:
    """
    Retorna totais de coleta pendentes, etc. Filtrado pelo produto próprio se informado,
    através da radar_candidate_links.
    """
    init_db()
    with get_connection() as conn:
        if own_product_uid:
            # Conta jobs de coleta de candidatos VINCULADOS
            q_jobs = """
                SELECT j.status, COUNT(j.job_uid) as c 
                FROM radar_collection_jobs j
                JOIN radar_candidate_links L ON L.candidate_product_uid = j.product_uid
                WHERE L.own_product_uid = ?
            """
            rows_jobs = conn.execute(q_jobs + " GROUP BY j.status", (own_product_uid,)).fetchall()
            
            # Conta matches de candidatos VINCULADOS
            q_matches = """
                SELECT m.verdict, COUNT(m.match_uid) as c
                FROM radar_competitor_matches m
                WHERE m.own_product_uid = ?
            """
            rows_matches = conn.execute(q_matches + " GROUP BY m.verdict", (own_product_uid,)).fetchall()
            
            # Conta total de candidatos vinculados rejeitados que nunca viraram match
            q_candidates = """
                SELECT p.status, COUNT(p.product_uid) as c
                FROM radar_products p
                JOIN radar_candidate_links L ON L.candidate_product_uid = p.product_uid
                WHERE L.own_product_uid = ?
            """
            rows_cand = conn.execute(q_candidates + " GROUP BY p.status", (own_product_uid,)).fetchall()
            
        else:
            rows_jobs = conn.execute("SELECT status, COUNT(job_uid) as c FROM radar_collection_jobs GROUP BY status").fetchall()
            rows_matches = conn.execute("SELECT verdict, COUNT(match_uid) as c FROM radar_competitor_matches GROUP BY verdict").fetchall()
            rows_cand = conn.execute("SELECT status, COUNT(product_uid) as c FROM radar_products GROUP BY status").fetchall()

    res = {
        "jobs_pending": 0,
        "jobs_failed": 0,
        "jobs_collected": 0, # Na verdade o status da job de sucesso é 'done' ou a gnt olha products
        "candidates": 0,
        "competitor_direct": 0,
        "competitor_partial": 0,
        "rejected": 0
    }
    
    for r in rows_jobs:
        if r["status"] == "pending" or r["status"] == "running":
            res["jobs_pending"] += r["c"]
        elif r["status"] == "failed":
            res["jobs_failed"] += r["c"]
        elif r["status"] == "done":
            res["jobs_collected"] += r["c"]
            
    for r in rows_matches:
        if r["verdict"] == "competitor_direct":
            res["competitor_direct"] += r["c"]
        elif r["verdict"] == "competitor_partial":
            res["competitor_partial"] += r["c"]
        elif r["verdict"] == "rejected":
            res["rejected"] += r["c"]
            
    # Contabiliza candidatos que ainda não estão no matches
    for r in rows_cand:
        if r["status"] in ["pending", "collected"]:
            res["candidates"] += r["c"]
            
    return res

def get_competitor_table_for_product(own_product_uid: str) -> list[dict]:
    """R7.2G: Retorna exatamente 1 linha por candidate_product_uid, sem duplicatas."""
    init_db()
    # Usa subquery para pegar o job mais recente por produto (ROW_NUMBER seria ideal mas
    # SQLite < 3.25 pode não ter; usamos subquery com MAX + desempate por job_uid).
    query = """
        SELECT
            c.candidate_product_uid AS product_uid,
            p.title, p.price, p.marketplace, p.shop_name, p.canonical_url, p.status AS product_status,
            m.verdict, m.relevance_score, m.reasons_json,
            m.updated_at AS match_updated_at,
            j.status AS job_status, j.last_error
        FROM radar_candidate_links c
        JOIN radar_products p ON p.product_uid = c.candidate_product_uid
        LEFT JOIN radar_competitor_matches m
            ON m.candidate_product_uid = c.candidate_product_uid
            AND m.own_product_uid = c.own_product_uid
        LEFT JOIN (
            SELECT j1.product_uid, j1.status, j1.last_error
            FROM radar_collection_jobs j1
            INNER JOIN (
                SELECT product_uid, MAX(updated_at || job_uid) AS max_key
                FROM radar_collection_jobs
                GROUP BY product_uid
            ) j2 ON j1.product_uid = j2.product_uid
                AND (j1.updated_at || j1.job_uid) = j2.max_key
        ) j ON j.product_uid = c.candidate_product_uid
        WHERE c.own_product_uid = ?
        ORDER BY m.relevance_score DESC NULLS LAST, p.created_at DESC
    """

    with get_connection() as conn:
        rows = conn.execute(query, (own_product_uid,)).fetchall()

    # Deduplicate by product_uid in Python (failsafe obrigatório — ajuste GPT #1)
    seen: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        uid = d["product_uid"]
        if uid not in seen:
            seen[uid] = d
        else:
            # Manter a linha com maior relevance_score; em empate, a mais recente
            prev = seen[uid]
            prev_score = prev.get("relevance_score") or -1
            curr_score = d.get("relevance_score") or -1
            if curr_score > prev_score:
                seen[uid] = d
            elif curr_score == prev_score:
                prev_updated = prev.get("match_updated_at") or ""
                curr_updated = d.get("match_updated_at") or ""
                if curr_updated > prev_updated:
                    seen[uid] = d

    out = []
    for d in seen.values():
        # R7.2G: Filtrar URLs fake da tabela
        if _is_fake_competitor_url(d.get("canonical_url")):
            continue

        # Consolida verdict / status
        if not d["verdict"]:
            if d["job_status"] in ("pending", "running"):
                d["status"] = "pending"
            elif d["job_status"] == "failed":
                d["status"] = "failed"
            elif d["product_status"] == "collected":
                d["status"] = "collected"
            else:
                d["status"] = d["product_status"]
        else:
            d["status"] = d["verdict"]

        out.append(d)

    return out

def classify_linked_candidates_for_product(own_product_uid: str, force_reclassify: bool = False) -> dict:
    """
    Roda classify_candidates_for_product, mas no futuro ele pode ser refinado
    para classificar apenas os links na radar_candidate_links se a função core
    for genérica. A função classify_candidates_for_product atualmente já é scoped 
    por own_product_uid internamente e busca candidatos compatíveis. 
    Aqui vamos garantir que apenas candidatos da radar_candidate_links do próprio sejam
    alimentados para o serviço central caso a arquitetura exija.
    
    Na verdade classify_candidates_for_product varre a radar_products procurando 'competitor_candidate'.
    Para respeitar a separação (R7.2), o serviço precisará apenas buscar os vinculados.
    
    Se force_reclassify=True, roda dedupe_radar_links_and_matches antes e reclassifica
    todos os candidatos vinculados, sobrescrevendo matches antigos.
    """
    from shopee_core.radar_relevance_service import classify_candidate
    init_db()
    
    # R7.2K: Se force, limpa links e matches duplicados antes de reclassificar
    if force_reclassify:
        dedupe_radar_links_and_matches(own_product_uid)

    # Validate own_product exists by checking if classify_candidate can proceed
    # (classify_candidate will raise ValueError if not found)

    query = """
        SELECT c.candidate_product_uid 
        FROM radar_candidate_links c
        JOIN radar_products p ON p.product_uid = c.candidate_product_uid
        WHERE c.own_product_uid = ?
          AND p.status IN ('collected', 'rejected', 'competitor_direct', 'competitor_partial')
    """
    
    with get_connection() as conn:
        candidates = conn.execute(query, (own_product_uid,)).fetchall()
        
    results = []
    for row in candidates:
        cand_uid = row["candidate_product_uid"]
        res = classify_candidate(own_product_uid, cand_uid)
        results.append(res)

    # Resumo
    summary = {"total": len(results), "direct": 0, "partial": 0, "rejected": 0, "avg_score": 0.0}
    scores = []
    for r in results:
        if r["verdict"] == "competitor_direct":
            summary["direct"] += 1
            scores.append(r["score"])
        elif r["verdict"] == "competitor_partial":
            summary["partial"] += 1
            scores.append(r["score"])
        else:
            summary["rejected"] += 1
            
    if scores:
        summary["avg_score"] = sum(scores) / len(scores)
        
    summary["ok"] = True
    return summary

def run_pattern_analysis_for_product(own_product_uid: str, candidate_scope: str = "direct_only") -> dict:
    try:
        report = generate_pattern_report(own_product_uid, candidate_scope=candidate_scope)
        if not report:
            return {"ok": False, "error": "Relatório vazio ou insuficiente concorrentes."}
        return {"ok": True, "report": report}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def ensure_collection_jobs_for_linked_candidates(own_product_uid: str) -> dict:
    """
    Garante que todo candidato vinculado que ainda precisa de dados tenha um job pending.
    """
    init_db()
    
    summary = {
        "linked_candidates": 0,
        "jobs_created": 0,
        "jobs_existing": 0,
        "skipped_done": 0,
        "skipped_invalid": 0
    }
    
    with get_connection() as conn:
        candidates = conn.execute(
            """
            SELECT p.product_uid, p.status, p.url, p.title, p.price, p.rejection_reason
            FROM radar_candidate_links l
            JOIN radar_products p ON p.product_uid = l.candidate_product_uid
            WHERE l.own_product_uid = ?
            """, (own_product_uid,)
        ).fetchall()
        
        summary["linked_candidates"] = len(candidates)
        now = _now()
        
        for cand in candidates:
            if _is_invalid_empty_placeholder_candidate(cand):
                error = _invalid_placeholder_error(cand["url"])
                conn.execute(
                    """
                    UPDATE radar_products
                    SET status = 'failed', rejection_reason = ?, updated_at = ?
                    WHERE product_uid = ?
                    """,
                    (error, now, cand["product_uid"]),
                )
                conn.execute(
                    """
                    UPDATE radar_collection_jobs
                    SET status = 'failed', last_error = ?, updated_at = ?, finished_at = COALESCE(finished_at, ?)
                    WHERE product_uid = ? AND status IN ('pending', 'running')
                    """,
                    (error, now, now, cand["product_uid"]),
                )
                summary["skipped_invalid"] += 1
                continue

            # Se ja tem titulo, pode ser que ja tenha sido coletado e perdeu status?
            # Mas vamos nos basear no status: pending, failed, ou se title is null
            if cand["status"] in ["pending", "failed"] or not cand["title"]:
                # Verifica se ja existe job que não seja failed/done
                existing_job = conn.execute(
                    "SELECT status FROM radar_collection_jobs WHERE product_uid = ? ORDER BY created_at DESC LIMIT 1",
                    (cand["product_uid"],)
                ).fetchone()
                
                if existing_job and existing_job["status"] in ["pending", "running"]:
                    summary["jobs_existing"] += 1
                else:
                    # Se o candidato estava failed, reseta o status para pending no banco
                    if cand["status"] == "failed":
                        conn.execute(
                            "UPDATE radar_products SET status = 'pending', updated_at = ? WHERE product_uid = ?",
                            (now, cand["product_uid"])
                        )
                    
                    # Cria novo job pending
                    job_uid = uuid.uuid4().hex
                    conn.execute(
                        """
                        INSERT INTO radar_collection_jobs (job_uid, product_uid, url, job_type, status, created_at, updated_at)
                        VALUES (?, ?, ?, 'product_data', 'pending', ?, ?)
                        """,
                        (job_uid, cand["product_uid"], cand["url"], now, now)
                    )
                    summary["jobs_created"] += 1
            else:
                summary["skipped_done"] += 1
                
    return summary


def _is_invalid_empty_placeholder_candidate(candidate: dict) -> bool:
    candidate = dict(candidate)
    reason = str(candidate.get("rejection_reason") or "")
    return reason.startswith("invalid_empty_shopee_placeholder_url")


def _invalid_placeholder_error(url: str | None) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", str(url or "empty")).strip("_").lower()
    return f"invalid_empty_shopee_placeholder_url_{clean[:80]}"


def _is_fake_competitor_url(url: str | None) -> bool:
    """R7.2G: Detecta URLs claramente de teste (ex: shopee.com.br/product/1/1)."""
    if not url:
        return False
    return bool(re.search(r'shopee\.com\.br/product/\d{1,2}/\d{1,2}$', str(url).strip(), re.I))


def _normalize_mercadolivre_url(url: str) -> str:
    """R7.2G: Remove parâmetros de rastreamento de URLs do Mercado Livre."""
    _ML_NOISE_PARAMS = {
        'searchVariation', 'tracking_id', 'position', 'polycard_client',
        'be_origin', 'search_layout', 'wid', 'sid',
    }
    try:
        parsed = urlparse(url)
        if 'mercadolivre.com.br' not in parsed.netloc:
            return url
        qs = parse_qs(parsed.query, keep_blank_values=False)
        clean_qs = {k: v for k, v in qs.items() if k not in _ML_NOISE_PARAMS}
        new_query = urlencode(clean_qs, doseq=True)
        # Remove fragment/hash
        return urlunparse(parsed._replace(query=new_query, fragment=''))
    except Exception:
        return url

def _run_linked_collection_for_product_direct(own_product_uid: str, limit: int = 5, save_assets: bool = False, browser_mode: str = "cdp", cdp_url: str | None = None, collect_image_urls: bool = True) -> dict:
    """
    Executa a coleta de candidatos vinculados de forma direta.
    """
    import sys
    import shopee_core.radar_collector as rc
    from shopee_core.radar_service import (
        mark_job_running,
        mark_job_done,
        mark_job_failed,
        mark_product_collected,
        mark_product_failed,
    )
    init_db()
    
    is_testing = "pytest" in sys.modules or "unittest" in sys.modules
    if browser_mode == "cdp" and not is_testing:
        from shopee_core.radar_cdp_service import ensure_radar_chrome_ready
        url_cdp = cdp_url or "http://127.0.0.1:9222"
        ready_res = ensure_radar_chrome_ready(url_cdp)
        if not ready_res["ok"]:
            return {
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "environment_error": True,
                "message": ready_res["message"]
            }
            
    ensure_collection_jobs_for_linked_candidates(own_product_uid)
    
    res = {
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
        "assets_saved": 0,
        "assets_skipped": 0,
        "asset_warnings": []
    }
    
    from pathlib import Path
    flag_file = Path("data/radar_stop_collection.flag")
    if flag_file.exists():
        try:
            flag_file.unlink()
        except Exception:
            pass
            
    with get_connection() as conn:
        # Pega APENAS jobs pendentes dos candidatos vinculados
        pending_jobs = conn.execute(
            """
            SELECT j.*, p.marketplace 
            FROM radar_collection_jobs j
            JOIN radar_candidate_links l ON l.candidate_product_uid = j.product_uid
            JOIN radar_products p ON p.product_uid = j.product_uid
            WHERE l.own_product_uid = ? AND j.status = 'pending'
            ORDER BY j.created_at ASC
            LIMIT ?
            """, (own_product_uid, limit)
        ).fetchall()
    
    pending_jobs = [dict(j) for j in pending_jobs]
    total = len(pending_jobs)
    
    for idx, job in enumerate(pending_jobs, 1):
        # Checa flag de cancelamento
        if flag_file.exists():
            try:
                flag_file.unlink()
            except Exception:
                pass
            remaining = total - res["processed"]
            res["skipped"] += remaining
            print(f"[R7.2D] FAILED candidate={job['product_uid']} error=Coleta cancelada pelo usuario", flush=True)
            break
            
        res["processed"] += 1
        job_uid = job["job_uid"]
        product_uid = job["product_uid"]
        url = job["url"]
        url_start_time = time.monotonic()
        
        try:
            # 1. Marca job como running no banco
            running_job = mark_job_running(job_uid)
            
            # Print formatado para progresso
            print(f"[R7.2D] START index={idx} total={total} candidate={product_uid}", flush=True)
            
            # 2. Coleta os dados da página abrindo o browser
            opts = {}
            if cdp_url:
                opts["cdp_url"] = cdp_url
            
            data = rc.collect_product_page(
                url=running_job["url"],
                marketplace=job["marketplace"],
                interactive_retry=False,
                browser_mode=browser_mode,
                candidate_uid=product_uid,
                job_uid=job_uid,
                url_start_time=url_start_time,
                collect_image_urls=collect_image_urls,
                **opts
            )
            
            # 3. Validar se a página veio bloqueada ou vazia
            if rc.is_collection_blocked_or_empty(data):
                raise RuntimeError(
                    "blocked_or_login_required"
                )
            
            # Se ambos title e price faltarem, marcar failed claro
            has_title = bool(data.get("title"))
            has_price = data.get("price") is not None
            
            if not has_title and not has_price:
                raise RuntimeError("missing_title_and_price_after_extraction")
            
            if time.monotonic() - url_start_time > 90:
                raise TimeoutError("total_per_url_timeout_after_90s")

            if not save_assets:
                _annotate_asset_status(
                    data,
                    status="skipped",
                    message="Download de imagens desativado - pulando assets",
                )

            # 4. Salva produto no banco antes de qualquer asset opcional
            print("[R7.2E] SAVING_MAIN_DATA", flush=True)
            try:
                mark_product_collected(product_uid, data)
            except Exception as db_err:
                raise RuntimeError(f"db_save_error: {db_err}")
            
            if time.monotonic() - url_start_time > 90:
                raise TimeoutError("total_per_url_timeout_after_90s")
            
            # 5. Salva assets/imagens como etapa opcional e nao bloqueante
            if save_assets:
                print("[R7.2E] DOWNLOADING_ASSETS", flush=True)
                asset_errors = []
                assets_saved = 0
                try:
                    assets = rc._persist_collected_assets(
                        product_uid,
                        data,
                        save_assets_to_disk=False,
                        timeout=30.0,
                        url_start_time=url_start_time,
                        max_images_per_product=5,
                        per_image_timeout=5.0,
                    )
                    asset_errors = [asset for asset in assets if asset.get("error")]
                    assets_saved = len(assets) - len(asset_errors)
                    res["assets_saved"] += assets_saved
                except Exception as asset_exc:
                    asset_errors = [{"error": str(asset_exc), "asset_type": "asset"}]

                if asset_errors:
                    warning = _asset_warning(product_uid, url, asset_errors, assets_saved)
                    res["asset_warnings"].append(warning)
                    print(f"[R7.2E] ASSETS_WARNING candidate={product_uid} error={warning['error']}", flush=True)
                    _annotate_asset_status(
                        data,
                        status="warning",
                        message=warning["error"],
                        errors=asset_errors,
                        assets_saved=assets_saved,
                    )
                    try:
                        mark_product_collected(product_uid, data)
                    except Exception:
                        pass
            else:
                res["assets_skipped"] += 1
                res["asset_warnings"].append({
                    "candidate_product_uid": product_uid,
                    "url": url,
                    "status": "skipped",
                    "error": "save_assets_false",
                })
                print("[R7.2E] ASSETS_SKIPPED reason=save_assets_false", flush=True)

            print("[R7.2E] FINALIZING_URL", flush=True)

            # 6. Marca job como done
            mark_job_done(job_uid)
            print(f"[R7.2D] DONE candidate={product_uid}", flush=True)
            res["succeeded"] += 1
            
        except Exception as e:
            err_msg = str(e)
            print(f"[R7.2D] FAILED candidate={product_uid} error={err_msg}", flush=True)
            
            # Recupera o screenshot_path salvo (se houver) no erro
            screenshot_path = getattr(e, "screenshot_path", None)
            
            try:
                mark_product_failed(product_uid, err_msg)
            except Exception:
                pass
            try:
                mark_job_failed(job_uid, err_msg)
            except Exception:
                pass
                
            res["failed"] += 1
            res["errors"].append({
                "candidate_product_uid": product_uid,
                "error": err_msg,
                "url": url,
                "screenshot_path": screenshot_path
            })
            
    return res


def _annotate_asset_status(
    data: dict,
    status: str,
    message: str,
    errors: list[dict] | None = None,
    assets_saved: int = 0,
) -> None:
    raw = data.get("raw") if isinstance(data.get("raw"), dict) else {}
    raw["asset_status"] = status
    raw["asset_message"] = message
    raw["assets_saved"] = assets_saved
    if errors:
        raw["asset_errors"] = errors
        data["asset_errors"] = errors
    data["raw"] = raw


def _asset_warning(
    product_uid: str,
    url: str,
    asset_errors: list[dict],
    assets_saved: int,
) -> dict:
    first_error = asset_errors[0] if asset_errors else {}
    return {
        "candidate_product_uid": product_uid,
        "url": url,
        "status": "warning",
        "error": str(first_error.get("error") or "asset_error"),
        "assets_saved": assets_saved,
        "asset_errors": asset_errors,
    }


def dedupe_radar_links_and_matches(own_product_uid: str) -> dict:
    """
    R7.2G: Remove duplicatas reais em radar_candidate_links e radar_competitor_matches
    para um dado own_product_uid. Também marca URLs fake como invalid_test_url.

    Retorna:
        {"links_removed": X, "matches_removed": Y, "products_flagged_as_fake": Z}
    """
    init_db()
    now = _now()
    links_removed = 0
    matches_removed = 0
    products_flagged_as_fake = 0

    with get_connection() as conn:
        # --- 1. Dedupe radar_candidate_links ---
        # Para cada (own, candidate) duplicado, manter o link_uid mais antigo
        dup_links = conn.execute("""
            SELECT candidate_product_uid, MIN(link_uid) AS keep_uid
            FROM radar_candidate_links
            WHERE own_product_uid = ?
            GROUP BY candidate_product_uid
            HAVING COUNT(*) > 1
        """, (own_product_uid,)).fetchall()

        for row in dup_links:
            deleted = conn.execute("""
                DELETE FROM radar_candidate_links
                WHERE own_product_uid = ?
                  AND candidate_product_uid = ?
                  AND link_uid != ?
            """, (own_product_uid, row["candidate_product_uid"], row["keep_uid"])).rowcount
            links_removed += deleted

        # --- 2. Dedupe radar_competitor_matches ---
        # Para cada (own, candidate) duplicado, manter o match mais recente (updated_at DESC)
        dup_matches = conn.execute("""
            SELECT candidate_product_uid, MAX(updated_at || match_uid) AS keep_key
            FROM radar_competitor_matches
            WHERE own_product_uid = ?
            GROUP BY candidate_product_uid
            HAVING COUNT(*) > 1
        """, (own_product_uid,)).fetchall()

        for row in dup_matches:
            keep_key = row["keep_key"]
            # keep_key = updated_at || match_uid, então match_uid = últimos 32 chars
            keep_uid = keep_key[-32:] if keep_key and len(keep_key) >= 32 else None
            if keep_uid:
                deleted = conn.execute("""
                    DELETE FROM radar_competitor_matches
                    WHERE own_product_uid = ?
                      AND candidate_product_uid = ?
                      AND match_uid != ?
                """, (own_product_uid, row["candidate_product_uid"], keep_uid)).rowcount
                matches_removed += deleted

        # --- 3. Flaggar URLs fake ---
        fake_candidates = conn.execute("""
            SELECT p.product_uid, p.canonical_url
            FROM radar_candidate_links l
            JOIN radar_products p ON p.product_uid = l.candidate_product_uid
            WHERE l.own_product_uid = ?
        """, (own_product_uid,)).fetchall()

        for cand in fake_candidates:
            if _is_fake_competitor_url(cand["canonical_url"]):
                conn.execute("""
                    UPDATE radar_products
                    SET status = 'failed', rejection_reason = 'invalid_test_url', updated_at = ?
                    WHERE product_uid = ? AND status != 'failed'
                """, (now, cand["product_uid"]))
                products_flagged_as_fake += 1

    return {
        "links_removed": links_removed,
        "matches_removed": matches_removed,
        "products_flagged_as_fake": products_flagged_as_fake,
    }


def mark_stale_running_jobs_as_pending_or_failed(max_age_minutes: int = 10) -> int:
    """
    Encontra jobs 'running' antigos no radar e os marca como 'failed' com last_error.
    O candidato/produto correspondente volta para 'pending' se não tiver título ou preço,
    evitando travamento definitivo.
    """
    from datetime import datetime, timedelta
    init_db()
    
    count = 0
    now = _now()
    cutoff = (datetime.utcnow() - timedelta(minutes=max_age_minutes)).isoformat()
    
    with get_connection() as conn:
        stale_jobs = conn.execute(
            """
            SELECT j.job_uid, j.product_uid, p.title, p.price 
            FROM radar_collection_jobs j
            JOIN radar_products p ON p.product_uid = j.product_uid
            WHERE j.status = 'running' AND j.updated_at < ?
            """,
            (cutoff,)
        ).fetchall()
        
        for job in stale_jobs:
            # Marca o job como failed
            conn.execute(
                """
                UPDATE radar_collection_jobs 
                SET status = 'failed', last_error = 'stale_running_job_recovered', updated_at = ?
                WHERE job_uid = ?
                """,
                (now, job["job_uid"])
            )
            
            # Se nao tem nenhum dado principal, volta para pending para retentativa limpa.
            # Se titulo ou preco ja foram salvos, preserva como collected.
            if not job["title"] and job["price"] is None:
                conn.execute(
                    "UPDATE radar_products SET status = 'pending', updated_at = ? WHERE product_uid = ?",
                    (now, job["product_uid"])
                )
            else:
                conn.execute(
                    "UPDATE radar_products SET status = 'collected', updated_at = ? WHERE product_uid = ?",
                    (now, job["product_uid"])
                )
            count += 1
            
    return count

def run_linked_collection_for_product(own_product_uid: str, limit: int = 5, save_assets: bool = False, browser_mode: str = "cdp", cdp_url: str | None = None, progress_callback = None, collect_image_urls: bool = True) -> dict:
    """
    Coleta os candidatos vinculados ao own_product_uid que possuem jobs pending.
    Em produção/Streamlit, executa a coleta em um subprocesso separado para evitar conflitos de event loop,
    lendo o stdout unbuffered em tempo real e disparando o progress_callback.
    """
    import sys
    is_testing = "pytest" in sys.modules or "unittest" in sys.modules
    
    # Se browser_mode for cdp, verifica ou tenta abrir o Chrome do Radar no processo principal
    # para retornar erro imediatamente sem precisar disparar o subprocesso.
    if browser_mode == "cdp" and not is_testing:
        from shopee_core.radar_cdp_service import ensure_radar_chrome_ready
        url_cdp = cdp_url or "http://127.0.0.1:9222"
        ready_res = ensure_radar_chrome_ready(url_cdp)
        if not ready_res["ok"]:
            return {
                "processed": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "environment_error": True,
                "message": ready_res["message"]
            }
            
    if is_testing:
        # Recupera jobs running antigos antes
        mark_stale_running_jobs_as_pending_or_failed()
        return _run_linked_collection_for_product_direct(
            own_product_uid=own_product_uid,
            limit=limit,
            save_assets=save_assets,
            browser_mode=browser_mode,
            cdp_url=cdp_url,
            collect_image_urls=collect_image_urls,
        )
        
    # Em produção/Streamlit, chama via subprocesso lendo stdout unbuffered
    import subprocess
    import json
    import re
    from pathlib import Path
    
    worker_path = Path(__file__).resolve().parent.parent / "scripts" / "radar_collect_linked_worker.py"
    
    # Executa com python -u para desabilitar buffer de saída
    cmd = [
        sys.executable,
        "-u",
        str(worker_path),
        own_product_uid,
        str(limit),
        str(save_assets).lower(),
        browser_mode,
        str(cdp_url) if cdp_url is not None else "None",
        str(collect_image_urls).lower(),
    ]
    
    try:
        # Recupera jobs running antigos antes do disparo do subprocesso
        mark_stale_running_jobs_as_pending_or_failed()
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            bufsize=1
        )
        
        stdout_lines = []
        final_json_str = None
        
        state = {
            "index": 0,
            "total": 0,
            "candidate_uid": "",
            "url": "",
            "stage": "",
            "message": ""
        }
        
        for line in iter(process.stdout.readline, ""):
            line_str = line.strip()
            if not line_str:
                continue
            stdout_lines.append(line_str)
            
            if "[R7.2F]" in line_str or "[R7.2E]" in line_str or "[R7.2D]" in line_str or "[R7.2C]" in line_str or "[R7.2H]" in line_str:
                clean_line = (
                    line_str
                    .replace("[R7.2F]", "")
                    .replace("[R7.2E]", "")
                    .replace("[R7.2D]", "")
                    .replace("[R7.2C]", "")
                    .replace("[R7.2H]", "")
                    .strip()
                )
                
                # START index=1 total=5 candidate=...
                if clean_line.startswith("START"):
                    m = re.search(r"index=(\d+)\s+total=(\d+)\s+candidate=([^\s]+)", clean_line)
                    if m:
                        state["index"] = int(m.group(1))
                        state["total"] = int(m.group(2))
                        state["candidate_uid"] = m.group(3)
                    state["stage"] = "START"
                    state["message"] = f"Iniciando coleta do candidato {state['candidate_uid']}"
                    
                # OPENING url=...
                elif clean_line.startswith("OPENING"):
                    m = re.search(r"url=([^\s]+)", clean_line)
                    if m:
                        state["url"] = m.group(1)
                    state["stage"] = "OPENING"
                    state["message"] = "Abrindo página do concorrente..."
                    
                # LOADED
                elif clean_line.startswith("LOADED"):
                    state["stage"] = "LOADED"
                    state["message"] = "Página carregada com sucesso"
                    
                # SCROLLING
                elif clean_line.startswith("SCROLLING"):
                    state["stage"] = "SCROLLING"
                    state["message"] = "Fazendo scroll da página"
                    
                # EXTRACTING_TITLE_PRICE
                elif clean_line.startswith("EXTRACTING_TITLE_PRICE"):
                    state["stage"] = "EXTRACTING_TITLE_PRICE"
                    state["message"] = "Extraindo título e preço"

                # EXTRACTING_DESC
                elif clean_line.startswith("EXTRACTING_DESC"):
                    state["stage"] = "EXTRACTING_DESC"
                    state["message"] = "Extraindo descrição"

                # EXTRACTING_IMAGE_URLS
                elif clean_line.startswith("EXTRACTING_IMAGE_URLS"):
                    state["stage"] = "EXTRACTING_IMAGE_URLS"
                    state["message"] = "Buscando imagens no HTML"

                # EXTRACTING_IMAGES (legacy)
                elif clean_line.startswith("EXTRACTING_IMAGES"):
                    state["stage"] = "EXTRACTING_IMAGE_URLS"
                    state["message"] = "Coletando URLs de imagens"

                # R7.2H: DISMISSING_OVERLAYS
                elif clean_line.startswith("DISMISSING_OVERLAYS"):
                    state["stage"] = "DISMISSING_OVERLAYS"
                    state["message"] = "Fechando avisos da página"

                # R7.2H: IMAGE_META (og:image)
                elif clean_line.startswith("IMAGE_META"):
                    state["stage"] = "IMAGE_META"
                    state["message"] = "Buscando imagem principal em metadados"

                # R7.2H: IMAGE_GALLERY
                elif clean_line.startswith("IMAGE_GALLERY"):
                    state["stage"] = "IMAGE_GALLERY"
                    state["message"] = "Buscando imagens na galeria"

                # R7.2H: IMAGE_HTML
                elif clean_line.startswith("IMAGE_HTML"):
                    state["stage"] = "IMAGE_HTML"
                    state["message"] = "Buscando imagens no HTML"

                # R7.2H: IMAGE_DESC
                elif clean_line.startswith("IMAGE_DESC"):
                    state["stage"] = "IMAGE_DESC"
                    state["message"] = "Buscando imagens na descrição"

                # R7.2H: IMAGE_TIMEOUT
                elif clean_line.startswith("IMAGE_TIMEOUT"):
                    state["stage"] = "IMAGE_TIMEOUT"
                    state["message"] = "Pulando imagens: timeout/sem resultado"

                # R7.2H: OVERLAYS_DISMISSED
                elif clean_line.startswith("OVERLAYS_DISMISSED"):
                    state["stage"] = "OVERLAYS_DISMISSED"
                    state["message"] = "Avisos da página fechados"

                # EXTRACTING
                elif clean_line.startswith("EXTRACTING"):
                    state["stage"] = "EXTRACTING"
                    state["message"] = "Extraindo dados do produto concorrente"
                    
                # SAVING_MAIN_DATA
                elif clean_line.startswith("SAVING_MAIN_DATA"):
                    state["stage"] = "SAVING_MAIN_DATA"
                    state["message"] = "Salvando dados principais"

                # SAVING_DB (legacy)
                elif clean_line.startswith("SAVING_DB"):
                    state["stage"] = "SAVING_MAIN_DATA"
                    state["message"] = "Salvando dados principais"

                # SAVING
                elif clean_line.startswith("SAVING"):
                    state["stage"] = "SAVING"
                    state["message"] = "Persistindo dados no banco de dados"

                # DOWNLOADING_ASSETS
                elif clean_line.startswith("DOWNLOADING_ASSETS"):
                    state["stage"] = "DOWNLOADING_ASSETS"
                    state["message"] = "Baixando imagens opcionais"

                # ASSETS_SKIPPED
                elif clean_line.startswith("ASSETS_SKIPPED") or clean_line.startswith("SKIPPING_ASSETS"):
                    state["stage"] = "ASSETS_SKIPPED"
                    state["message"] = "Download de imagens desativado - pulando assets"

                # ASSETS_WARNING
                elif clean_line.startswith("ASSETS_WARNING"):
                    state["stage"] = "ASSETS_WARNING"
                    state["message"] = "Assets tiveram aviso; continuando coleta"

                # SKIPPING_OPTIONAL_DETAILS
                elif clean_line.startswith("SKIPPING_OPTIONAL_DETAILS"):
                    state["stage"] = "SKIPPING_OPTIONAL_DETAILS"
                    state["message"] = "Coleta rapida: pulando descricao e detalhes opcionais"

                # FAST_PRIMARY_READY
                elif clean_line.startswith("FAST_PRIMARY_READY"):
                    state["stage"] = "FAST_PRIMARY_READY"
                    state["message"] = "Dados principais coletados; preparando salvamento"

                # CDP_PAGE_RELEASED
                elif clean_line.startswith("CDP_PAGE_RELEASED"):
                    state["stage"] = "CDP_PAGE_RELEASED"
                    state["message"] = "Navegador liberado; preparando salvamento"

                # FINALIZING_URL
                elif clean_line.startswith("FINALIZING_URL"):
                    state["stage"] = "FINALIZING_URL"
                    state["message"] = "Finalizando URL"
                    
                # DONE candidate=...
                elif clean_line.startswith("DONE"):
                    state["stage"] = "DONE"
                    state["message"] = "Coleta concluída com sucesso"
                    
                # FAILED candidate=... error=...
                elif clean_line.startswith("FAILED"):
                    m = re.search(r"candidate=([^\s]+).*?error=(.*)", clean_line)
                    if m:
                        state["candidate_uid"] = m.group(1)
                        state["message"] = f"Falha na coleta: {m.group(2)}"
                    state["stage"] = "FAILED"
                
                # SCREENSHOT_SAVED path=...
                elif clean_line.startswith("SCREENSHOT_SAVED"):
                    m = re.search(r"path=([^\s]+)", clean_line)
                    if m:
                        state["screenshot_path"] = m.group(1)
                
                if progress_callback:
                    try:
                        progress_callback(dict(state))
                    except Exception:
                        pass
            
            # O último print do worker é o JSON de retorno
            if line_str.startswith("{") and line_str.endswith("}"):
                final_json_str = line_str
                
        process.stdout.close()
        returncode = process.wait()
        
        if returncode == 0 and final_json_str:
            try:
                return json.loads(final_json_str)
            except Exception as e:
                return {
                    "processed": 0,
                    "succeeded": 0,
                    "failed": 1,
                    "skipped": 0,
                    "errors": [{"candidate_product_uid": "all", "error": f"Erro decodificando retorno JSON do subprocesso: {e}. Output bruto: {final_json_str}", "url": "none"}]
                }
        else:
            err_msg = f"Erro executando subprocesso (code {returncode})"
            if stdout_lines:
                err_msg += f". Últimas linhas: {stdout_lines[-3:]}"
            return {
                "processed": 0,
                "succeeded": 0,
                "failed": 1,
                "skipped": 0,
                "errors": [{"candidate_product_uid": "all", "error": err_msg, "url": "none"}]
            }
    except Exception as e:
        return {
            "processed": 0,
            "succeeded": 0,
            "failed": 1,
            "skipped": 0,
            "errors": [{"candidate_product_uid": "all", "error": f"Erro disparando subprocesso: {e}", "url": "none"}]
        }


# ══════════════════════════════════════════════════════════════════════════
# R7.3: Radar automatico de concorrentes
# ══════════════════════════════════════════════════════════════════════════


def generate_search_queries_for_product(own_product_uid: str) -> list[dict]:
    """Generate search queries for a product (passthrough)."""
    from shopee_core.radar_discovery_service import generate_competitor_search_queries as _gq
    from shopee_core.radar_service import get_product
    product = get_product(own_product_uid)
    if not product:
        return []
    return _gq(product)


def run_automatic_radar_cycle(
    own_product_uid: str,
    marketplace: str = "mercadolivre",
    target_confidence: str = "high",
    max_queries: int = 6,
    max_urls_per_query: int = 10,
    max_collect: int = 15,
    max_collect_per_cycle: int | None = None,
    max_cycles: int = 3,
    max_total_candidates: int = 60,
    max_total_runtime_minutes: int = 20,
    candidate_scope: str = "direct_plus_partial",
    browser_mode: str = "cdp",
    cdp_url: str = "http://127.0.0.1:9222",
    discover_new_urls: bool = True,
    progress_callback=None,
) -> dict:
    """Run the full automatic radar cycle (passthrough)."""
    from shopee_core.radar_discovery_service import run_automatic_radar_cycle as _rc
    return _rc(
        own_product_uid=own_product_uid,
        marketplace=marketplace,
        target_confidence=target_confidence,
        max_queries=max_queries,
        max_urls_per_query=max_urls_per_query,
        max_collect=max_collect,
        max_collect_per_cycle=max_collect_per_cycle,
        max_cycles=max_cycles,
        max_total_candidates=max_total_candidates,
        max_total_runtime_minutes=max_total_runtime_minutes,
        candidate_scope=candidate_scope,
        browser_mode=browser_mode,
        cdp_url=cdp_url,
        discover_new_urls=discover_new_urls,
        progress_callback=progress_callback,
    )


# ══════════════════════════════════════════════════════════════════════════
# R7.4: Renovação semanal do Radar
# ══════════════════════════════════════════════════════════════════════════


def get_refresh_status(own_product_uid: str) -> dict:
    """Get refresh status for a product (passthrough)."""
    from shopee_core.radar_refresh_service import get_radar_refresh_status
    return get_radar_refresh_status(own_product_uid)


def list_due_for_refresh(days: int = 7) -> list[dict]:
    """List products due for refresh (passthrough)."""
    from shopee_core.radar_refresh_service import list_products_due_for_refresh
    return list_products_due_for_refresh(days=days)


def refresh_product(own_product_uid: str, **kwargs) -> dict:
    """Refresh radar for a product (passthrough)."""
    from shopee_core.radar_refresh_service import refresh_radar_for_product
    return refresh_radar_for_product(own_product_uid, **kwargs)
