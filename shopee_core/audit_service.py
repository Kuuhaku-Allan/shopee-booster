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

# ── Importa as funções existentes do backend_core ───────────────────
# Atenção: backend_core.py importa `streamlit` no nível do módulo,
# então ao importarmos aqui o Streamlit é carregado.  Isso é OK
# enquanto não há reruns de UI; em produção o FastAPI nunca vai
# renderizar componentes Streamlit — apenas chama as funções puras.
from backend_core import (
    resolve_shopee_url,
    fetch_shop_info,
    fetch_shop_products_intercept,
    fetch_competitors_intercept,
    fetch_reviews_intercept,
    generate_full_optimization,
)


def load_shop_from_url(shop_url: str) -> dict:
    """
    Carrega informações da loja e lista de produtos a partir da URL.

    Retorna AuditResponse-compatível:
        ok (bool)
        message (str)
        data (dict):
          username, shop, products
    """
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


def generate_product_optimization(product: dict, segmento: str) -> dict:
    """
    Executa o fluxo completo de otimização para um produto:
      1. Busca concorrentes na Shopee (Playwright)
      2. Busca avaliações no Mercado Livre (Playwright)
      3. Gera o listing otimizado com Gemini

    Retorna AuditResponse-compatível.
    """
    if not product:
        return {
            "ok": False,
            "message": "Produto inválido ou vazio.",
            "data": {},
        }

    keyword = product.get("name", "")
    item_id = str(product.get("itemid", ""))
    shop_id = str(product.get("shopid", ""))

    # 1. Concorrentes
    competitors = fetch_competitors_intercept(keyword)
    df_competitors = pd.DataFrame(competitors) if competitors else pd.DataFrame()

    # 2. Avaliações (via Mercado Livre como proxy de qualidade de reviews)
    reviews, logs = fetch_reviews_intercept(
        item_id=item_id,
        shop_id=shop_id,
        product_url="",
        product_name_override=keyword,
    )

    # 3. Otimização Gemini
    optimization_text = generate_full_optimization(
        product=product,
        competitors_df=df_competitors,
        reviews=reviews or [],
        segmento=segmento,
    )

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
            "competitors": competitors,
            "reviews": reviews or [],
            "review_logs": logs,
        },
    }


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
