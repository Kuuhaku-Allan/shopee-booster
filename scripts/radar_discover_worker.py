import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from shopee_core.radar_discovery_service import _discover_marketplace_candidate_urls_direct


def main():
    if len(sys.argv) < 7:
        print(json.dumps({
            "ok": False,
            "error": "Argumentos insuficientes",
            "urls_found": 0,
            "urls_inserted": 0,
            "errors": ["Argumentos insuficientes"],
        }))
        sys.exit(1)

    own_uid = sys.argv[1]
    marketplace = sys.argv[2]
    max_queries = int(sys.argv[3])
    max_urls_per_query = int(sys.argv[4])
    browser_mode = sys.argv[5]
    cdp_url = sys.argv[6] if sys.argv[6] != "None" else None

    try:
        res = _discover_marketplace_candidate_urls_direct(
            own_product_uid=own_uid,
            marketplace=marketplace,
            max_queries=max_queries,
            max_urls_per_query=max_urls_per_query,
            browser_mode=browser_mode,
            cdp_url=cdp_url or "http://127.0.0.1:9222",
        )
        print(json.dumps(res))
        if not res.get("ok"):
            sys.exit(1)
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "error": str(e),
            "urls_found": 0,
            "urls_inserted": 0,
            "errors": [str(e)],
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
