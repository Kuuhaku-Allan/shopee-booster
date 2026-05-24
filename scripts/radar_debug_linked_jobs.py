import sys
import json
from pathlib import Path

# Adiciona a raiz do projeto ao sys.path para importar shopee_core
sys.path.append(str(Path(__file__).resolve().parent.parent))

from shopee_core.radar_db import get_connection, init_db

def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/radar_debug_linked_jobs.py OWN_PRODUCT_UID")
        sys.exit(1)
        
    own_uid = sys.argv[1]
    init_db()
    
    with get_connection() as conn:
        print(f"\n--- Diagnóstico para: {own_uid} ---\n")
        
        # Pega links
        links = conn.execute(
            """
            SELECT l.candidate_product_uid, l.created_at, p.canonical_url, p.url, p.marketplace, p.status, p.title, p.price
            FROM radar_candidate_links l
            JOIN radar_products p ON p.product_uid = l.candidate_product_uid
            WHERE l.own_product_uid = ?
            """, (own_uid,)
        ).fetchall()
        
        if not links:
            print("Nenhum candidato vinculado encontrado na radar_candidate_links.")
            return
            
        print(f"Encontrados {len(links)} candidatos vinculados:\n")
        
        for idx, row in enumerate(links):
            cand_uid = row["candidate_product_uid"]
            print(f"[{idx+1}] Cand UID: {cand_uid}")
            print(f"    URL: {row['canonical_url'] or row['url']}")
            print(f"    Marketplace: {row['marketplace']}")
            print(f"    Status em radar_products: {row['status']}")
            print(f"    Title: {row['title']} | Price: {row['price']}")
            
            # Pega jobs para esse candidato
            jobs = conn.execute(
                "SELECT job_uid, status, attempts, last_error, created_at, updated_at FROM radar_collection_jobs WHERE product_uid = ?",
                (cand_uid,)
            ).fetchall()
            
            if not jobs:
                print("    -> ALERTA: Nenhum job encontrado em radar_collection_jobs para esse candidato!")
            else:
                from datetime import datetime
                for j in jobs:
                    run_info = ""
                    if j["status"] == "running" and j["updated_at"]:
                        try:
                            # Calcula há quanto tempo está rodando
                            updated_dt = datetime.fromisoformat(j["updated_at"])
                            delta = datetime.utcnow() - updated_dt
                            run_info = f" (rodando ha {int(delta.total_seconds())}s)"
                        except Exception:
                            pass
                            
                    print(f"    -> Job {j['job_uid'][:8]}... | Status: {j['status']}{run_info} | Attempts: {j['attempts']} | Error: {j['last_error']}")
                    
                    # Verifica screenshots de depuração
                    screenshot_dir = Path("data") / "radar_debug" / "screenshots"
                    if screenshot_dir.exists():
                        # Procura imagens contendo cand_uid e job_uid
                        matching_screenshots = list(screenshot_dir.glob(f"{cand_uid}_{j['job_uid']}_*.png"))
                        # Fallback simples por cand_uid
                        if not matching_screenshots:
                            matching_screenshots = list(screenshot_dir.glob(f"{cand_uid}_*.png"))
                        for screenshot in matching_screenshots:
                            print(f"       Debug Screenshot: {screenshot.resolve()}")
            
            print("-" * 40)

if __name__ == "__main__":
    main()
