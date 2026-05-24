import sys
import json
from pathlib import Path

# Adiciona a raiz do projeto ao sys.path para permitir importações do shopee_core
sys.path.append(str(Path(__file__).resolve().parent.parent))

from shopee_core.radar_workflow_ui_service import _run_linked_collection_for_product_direct

def main():
    if len(sys.argv) < 5:
        print(json.dumps({
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [{"candidate_product_uid": "all", "error": "Argumentos insuficientes", "url": "none"}]
        }))
        sys.exit(1)
        
    own_uid = sys.argv[1]
    limit = int(sys.argv[2])
    save_assets = sys.argv[3].lower() == "true"
    browser_mode = sys.argv[4]
    cdp_url = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] != "None" else None
    
    try:
        res = _run_linked_collection_for_product_direct(
            own_product_uid=own_uid,
            limit=limit,
            save_assets=save_assets,
            browser_mode=browser_mode,
            cdp_url=cdp_url
        )
        print(json.dumps(res))
    except Exception as e:
        print(json.dumps({
            "processed": 0,
            "succeeded": 0,
            "failed": 1,
            "skipped": 0,
            "errors": [{"candidate_product_uid": "all", "error": str(e), "url": "none"}]
        }))

if __name__ == "__main__":
    main()
