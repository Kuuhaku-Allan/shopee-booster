import uuid
import time
from datetime import datetime
from shopee_core.radar_db import get_connection, init_db
from shopee_core.radar_collector import detect_marketplace, normalize_product_url
from shopee_core.radar_relevance_service import classify_candidates_for_product
from shopee_core.radar_patterns_service import generate_pattern_report

def _now():
    return datetime.utcnow().isoformat()

def list_own_products_for_radar(limit=200):
    """
    Retorna uma lista de produtos próprios elegíveis para o Radar Assistido.
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
        try:
            mkt = detect_marketplace(url)
            norm = normalize_product_url(url)
            if mkt == "unknown" or not norm:
                invalid_count += 1
            else:
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
    init_db()
    query = """
        SELECT 
            c.candidate_product_uid AS product_uid,
            p.title, p.price, p.marketplace, p.shop_name, p.canonical_url, p.status AS product_status,
            m.verdict, m.relevance_score, m.reasons_json,
            m.updated_at AS match_updated_at,
            j.status AS job_status, j.last_error
        FROM radar_candidate_links c
        JOIN radar_products p ON p.product_uid = c.candidate_product_uid
        LEFT JOIN radar_competitor_matches m ON m.candidate_product_uid = c.candidate_product_uid AND m.own_product_uid = c.own_product_uid
        LEFT JOIN radar_collection_jobs j ON j.product_uid = c.candidate_product_uid
        WHERE c.own_product_uid = ?
        ORDER BY m.relevance_score DESC NULLS LAST, p.created_at DESC
    """
    
    with get_connection() as conn:
        rows = conn.execute(query, (own_product_uid,)).fetchall()
        
    out = []
    for r in rows:
        d = dict(r)
        
        # Consolida verdict
        if not d["verdict"]:
            if d["job_status"] == "pending" or d["job_status"] == "running":
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

def classify_linked_candidates_for_product(own_product_uid: str) -> dict:
    """
    Roda classify_candidates_for_product, mas no futuro ele pode ser refinado
    para classificar apenas os links na radar_candidate_links se a função core
    for genérica. A função classify_candidates_for_product atualmente já é scoped 
    por own_product_uid internamente e busca candidatos compatíveis. 
    Aqui vamos garantir que apenas candidatos da radar_candidate_links do próprio sejam
    alimentados para o serviço central caso a arquitetura exija.
    
    Na verdade classify_candidates_for_product varre a radar_products procurando 'competitor_candidate'.
    Para respeitar a separação (R7.2), o serviço precisará apenas buscar os vinculados.
    """
    from shopee_core.radar_relevance_service import classify_candidate, get_product
    init_db()
    
    own = get_product(own_product_uid)
    if not own:
        return {"ok": False, "error": "Produto próprio não encontrado."}
        
    query = """
        SELECT c.candidate_product_uid 
        FROM radar_candidate_links c
        JOIN radar_products p ON p.product_uid = c.candidate_product_uid
        WHERE c.own_product_uid = ? AND p.status = 'collected'
    """
    
    with get_connection() as conn:
        candidates = conn.execute(query, (own_product_uid,)).fetchall()
        
    results = []
    for row in candidates:
        cand_uid = row["candidate_product_uid"]
        cand = get_product(cand_uid)
        if cand:
            res = classify_candidate(own, cand)
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

def run_pattern_analysis_for_product(own_product_uid: str) -> dict:
    try:
        report = generate_pattern_report(own_product_uid)
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
        "skipped_done": 0
    }
    
    with get_connection() as conn:
        candidates = conn.execute(
            """
            SELECT p.product_uid, p.status, p.url, p.title
            FROM radar_candidate_links l
            JOIN radar_products p ON p.product_uid = l.candidate_product_uid
            WHERE l.own_product_uid = ?
            """, (own_product_uid,)
        ).fetchall()
        
        summary["linked_candidates"] = len(candidates)
        now = _now()
        
        for cand in candidates:
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

def _run_linked_collection_for_product_direct(own_product_uid: str, limit: int = 5, save_assets: bool = True, browser_mode: str = "cdp", cdp_url: str | None = None) -> dict:
    """
    Executa a coleta de candidatos vinculados de forma direta.
    """
    import shopee_core.radar_collector as rc
    from shopee_core.radar_service import (
        mark_job_running,
        mark_job_done,
        mark_job_failed,
        mark_product_collected,
        mark_product_failed,
    )
    init_db()
    
    if browser_mode == "cdp":
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
        "errors": []
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
                browser_mode=browser_mode,
                candidate_uid=product_uid,
                job_uid=job_uid,
                url_start_time=url_start_time,
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
            
            # 4. Salva produto no banco
            print("[R7.2D] SAVING_DB", flush=True)
            try:
                mark_product_collected(product_uid, data)
            except Exception as db_err:
                raise RuntimeError(f"db_save_error: {db_err}")
            
            if time.monotonic() - url_start_time > 90:
                raise TimeoutError("total_per_url_timeout_after_90s")
            
            # 5. Salva assets/imagens
            if save_assets:
                rc._persist_collected_assets(
                    product_uid,
                    data,
                    save_assets_to_disk=False,
                    timeout=30.0,
                    url_start_time=url_start_time
                )
                
            if time.monotonic() - url_start_time > 90:
                raise TimeoutError("total_per_url_timeout_after_90s")
            
            print("[R7.2D] FINALIZING_URL", flush=True)

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
            
            # Se o candidato não tem título ou preço, volta para pending para retentativa limpa
            if not job["title"] or not job["price"]:
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

def run_linked_collection_for_product(own_product_uid: str, limit: int = 5, save_assets: bool = True, browser_mode: str = "cdp", cdp_url: str | None = None, progress_callback = None) -> dict:
    """
    Coleta os candidatos vinculados ao own_product_uid que possuem jobs pending.
    Em produção/Streamlit, executa a coleta em um subprocesso separado para evitar conflitos de event loop,
    lendo o stdout unbuffered em tempo real e disparando o progress_callback.
    """
    import sys
    
    # Se browser_mode for cdp, verifica ou tenta abrir o Chrome do Radar no processo principal
    # para retornar erro imediatamente sem precisar disparar o subprocesso.
    if browser_mode == "cdp":
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
            
    is_testing = "pytest" in sys.modules or "unittest" in sys.modules
    if is_testing:
        # Recupera jobs running antigos antes
        mark_stale_running_jobs_as_pending_or_failed()
        return _run_linked_collection_for_product_direct(
            own_product_uid=own_product_uid,
            limit=limit,
            save_assets=save_assets,
            browser_mode=browser_mode,
            cdp_url=cdp_url
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
        str(cdp_url) if cdp_url is not None else "None"
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
            
            if "[R7.2D]" in line_str or "[R7.2C]" in line_str:
                clean_line = line_str.replace("[R7.2D]", "").replace("[R7.2C]", "").strip()
                
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

                # EXTRACTING_IMAGES
                elif clean_line.startswith("EXTRACTING_IMAGES"):
                    state["stage"] = "EXTRACTING_IMAGES"
                    state["message"] = "Extraindo imagens"

                # EXTRACTING
                elif clean_line.startswith("EXTRACTING"):
                    state["stage"] = "EXTRACTING"
                    state["message"] = "Extraindo dados do produto concorrente"
                    
                # SAVING_DB
                elif clean_line.startswith("SAVING_DB"):
                    state["stage"] = "SAVING_DB"
                    state["message"] = "Salvando no banco"

                # SAVING
                elif clean_line.startswith("SAVING"):
                    state["stage"] = "SAVING"
                    state["message"] = "Persistindo dados no banco de dados"

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
