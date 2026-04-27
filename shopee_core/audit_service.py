"""
shopee_core/audit_service.py — Serviço de Auditoria
====================================================
Ponte entre o WhatsApp Bot / API e as funções de scraping + IA
que já existem no backend_core.py.

Regra: NÃO importar streamlit aqui.
O backend_core chama `st.caption()` internamente durante o Playwright —
isso é aceitável porque o subprocess roda em contexto separado.
O problema real seria chamar st.session_state ou st.sidebar fora do
contexto do Streamlit. Essa camada isola esse risco.
"""

from __future__ import annotations

import pandas as pd

# ── Funções de Auditoria ──────────────────────────────────────────


def load_shop_from_url(shop_url: str) -> dict:
    """
    Carrega informações da loja e lista de produtos a partir da URL.

    Retorna AuditResponse-compatível:
        ok (bool)
        message (str)
        data (dict):
          username, shop, products
    """
    from backend_core import resolve_shopee_url
    resolved = resolve_shopee_url(shop_url.strip())

    if not resolved or resolved.get("type") != "shop":
        return {
            "ok": False,
            "message": (
                "URL de loja inválida. "
                "Use o formato: https://shopee.com.br/nome_da_loja"
            ),
            "data": {},
        }

    username = resolved["username"]

    # Busca informações da loja via Playwright
    from backend_core import fetch_shop_info
    shop_raw = fetch_shop_info(username)
    shop_data = shop_raw.get("data", shop_raw) if isinstance(shop_raw, dict) else {}

    if not shop_data:
        return {
            "ok": False,
            "message": "Não consegui carregar os dados da loja. Verifique a URL.",
            "data": {},
        }

    shopid = shop_data.get("shopid") or shop_data.get("shop_id")

    # Carrega os produtos via Playwright
    from backend_core import fetch_shop_products_intercept
    products = fetch_shop_products_intercept(username, shopid)

    return {
        "ok": True,
        "message": f"Loja '{username}' carregada com {len(products)} produto(s).",
        "data": {
            "username": username,
            "shop": shop_data,
            "products": products,
        },
    }


def generate_product_optimization(product: dict, segmento: str, api_key: str = None) -> dict:
    """
    Executa o fluxo completo de otimização para um produto:
      1. Busca concorrentes via competitor_service (Shopee + Mercado Livre fallback)
      2. Busca avaliações no Mercado Livre (Playwright)
      3. Gera o listing otimizado com Gemini

    Args:
        product: Dados do produto
        segmento: Segmento de mercado
        api_key: Gemini API Key opcional (usa GOOGLE_API_KEY se None)

    Retorna AuditResponse-compatível.
    """
    import logging
    log = logging.getLogger("audit_service")
    
    if not product:
        return {
            "ok": False,
            "message": "Produto inválido ou vazio.",
            "data": {},
        }

    keyword = product.get("name", "")
    item_id = str(product.get("itemid", ""))
    shop_id = str(product.get("shopid", ""))

    # 1. Concorrentes via competitor_service (U8.2)
    log.info(f"[AUDIT] Buscando concorrentes via search_competitors_safe: keyword={keyword}")
    
    from shopee_core.competitor_service import search_competitors_safe
    
    competitors = search_competitors_safe(keyword=keyword, limit=10)
    
    log.info(f"[AUDIT] Concorrentes encontrados: {len(competitors)}")
    if competitors:
        sources = set(c.get("source", "unknown") for c in competitors)
        log.info(f"[AUDIT] Providers usados: {', '.join(sources)}")
    
    # Normaliza concorrentes para formato esperado por generate_full_optimization (U8.1)
    competitors_for_df = _normalize_competitors_for_audit(competitors)
    df_competitors = pd.DataFrame(competitors_for_df) if competitors_for_df else pd.DataFrame()
    
    log.info(f"[AUDIT] DataFrame de concorrentes: {len(df_competitors)} linhas")

    # 2. Avaliações (via Mercado Livre como proxy de qualidade de reviews)
    from backend_core import fetch_reviews_intercept
    reviews, logs = fetch_reviews_intercept(
        item_id=item_id,
        shop_id=shop_id,
        product_url="",
        product_name_override=keyword,
    )
    
    log.info(f"[AUDIT] Avaliações coletadas: {len(reviews or [])}")

    # 3. Otimização Gemini (passa api_key)
    log.info(f"[AUDIT] Gerando otimização com Gemini...")
    from backend_core import generate_full_optimization
    optimization_text = generate_full_optimization(
        product=product,
        competitors_df=df_competitors,
        reviews=reviews or [],
        segmento=segmento,
        api_key=api_key,  # Passa api_key opcional
    )
    
    log.info(f"[AUDIT] Otimização gerada: {len(optimization_text)} caracteres")

    return {
        "ok": True,
        "message": "Otimização gerada com sucesso.",
        "data": {
            "product": {
                "itemid": item_id,
                "name": keyword,
                "price": product.get("price", 0),
            },
            "optimization": optimization_text,
            "competitors": competitors,  # Lista original para contador
            "reviews": reviews or [],
            "review_logs": logs,
        },
    }


def _to_float(value) -> float:
    """
    Converte valor para float, tratando strings com formato brasileiro.
    
    Args:
        value: Valor a converter (str, int, float)
    
    Returns:
        Float convertido ou 0.0 se falhar
    """
    try:
        if isinstance(value, str):
            # Remove R$, pontos de milhar e troca vírgula por ponto
            value = value.replace("R$", "").replace(".", "").replace(",", ".").strip()
        return float(value or 0)
    except Exception:
        return 0.0


def _normalize_competitors_for_audit(competitors: list[dict]) -> list[dict]:
    """
    Normaliza concorrentes para o formato esperado por generate_full_optimization.
    
    O backend_core espera DataFrame com colunas:
        - nome (str)
        - preco (float)
        - avaliações (int)
        - estrelas (float)
        - curtidas (int) - opcional
        - source (str) - opcional
        - url (str) - opcional
    
    Args:
        competitors: Lista de concorrentes do competitor_service
    
    Returns:
        Lista normalizada para criar DataFrame
    """
    normalized = []
    
    for c in competitors or []:
        normalized.append({
            "nome": c.get("titulo") or c.get("nome") or "",
            "preco": _to_float(c.get("preco")),
            "avaliações": c.get("avaliações", c.get("avaliacoes", 0)),
            "curtidas": c.get("curtidas", 0),
            "estrelas": c.get("estrelas", 0),
            "source": c.get("source", ""),
            "url": c.get("url", ""),
        })
    
    return normalized


def list_products_summary(products: list) -> list[dict]:
    """
    Retorna um resumo compacto dos produtos para apresentação no WhatsApp.
    Cada item: {index, name, price}
    """
    return [
        {
            "index": i,
            "name": p.get("name", f"Produto {i}"),
            "price": p.get("price", 0),
        }
        for i, p in enumerate(products)
    ]
