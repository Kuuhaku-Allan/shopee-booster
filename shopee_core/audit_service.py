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

import logging
import os

import pandas as pd

log = logging.getLogger("audit_service")


# ── R7.0A: Helper de fallback forçado via env var ─────────────────────────


def _is_force_fallback() -> bool:
    """
    Retorna True se SHOPEE_FORCE_RADAR_STORE_FALLBACK estiver ativo.

    Aceita (case insensitive): true, 1, yes, sim
    Por padrão é False/desativado.
    Uso somente para teste/debug — nunca ativar em produção.
    """
    raw = os.environ.get("SHOPEE_FORCE_RADAR_STORE_FALLBACK", "").strip().lower()
    return raw in {"true", "1", "yes", "sim"}


# ── Funções de Auditoria ──────────────────────────────────────────


def _load_products_from_store_mirror(
    username: str,
    shopid: str | None = None,
) -> list[dict]:
    try:
        from shopee_core.radar_store_service import get_cached_store_products

        return get_cached_store_products(
            shop_uid=str(shopid) if shopid else None,
            shop_slug=username,
        )
    except Exception as exc:
        log.warning("[R7.0] Falha ao ler espelho local do Radar: %s", exc)
        return []


def load_shop_from_url(shop_url: str) -> dict:
    """
    Carrega informações da loja e lista de produtos a partir da URL.

    Retorna AuditResponse-compatível:
        ok (bool)
        message (str)
        data (dict):
          username, shop, products

    R7.0A: Quando SHOPEE_FORCE_RADAR_STORE_FALLBACK=true,
    pula Shopee/scraping e carrega direto do espelho local (só leitura).
    Snapshot novo só é salvo quando há carga real bem-sucedida.
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

    # ── R7.0A: modo de teste — força uso do espelho local, sem chamar Shopee ──
    if _is_force_fallback():
        log.info(
            "[R7.0] SHOPEE_FORCE_RADAR_STORE_FALLBACK ativo — "
            "pulando Shopee, carregando espelho local (shop_slug=%s)",
            username,
        )
        cached_products = _load_products_from_store_mirror(username)
        if cached_products:
            log.info(
                "[R7.0] Usando espelho local do Radar como fallback: "
                "shop_slug=%s produtos=%d",
                username,
                len(cached_products),
            )
            return {
                "ok": True,
                "message": (
                    f"[Fallback forçado] Loja '{username}' carregada com "
                    f"{len(cached_products)} produto(s) do espelho local do Radar."
                ),
                "data": {
                    "username": username,
                    "shop": {
                        "name": username,
                        "username": username,
                        "source": "espelho local do Radar",
                    },
                    "products": cached_products,
                    "method_used": "radar_store_mirror",
                    "source_label": "espelho local do Radar",
                },
            }
        log.warning(
            "[R7.0] Nenhum espelho local encontrado para shop_slug=%s "
            "(fallback forçado ativo)",
            username,
        )
        return {
            "ok": False,
            "message": (
                f"Nenhum espelho local encontrado para a loja '{username}'. "
                "Execute uma auditoria normal primeiro para criar o espelho."
            ),
            "data": {"username": username},
        }

    # ── Fluxo normal: busca informações da loja via Playwright ────────────
    from backend_core import fetch_shop_info
    shop_raw = fetch_shop_info(username)
    shop_data = shop_raw.get("data", shop_raw) if isinstance(shop_raw, dict) else {}

    if not shop_data:
        cached_products = _load_products_from_store_mirror(username)
        if cached_products:
            log.info(
                "[R7.0] Usando espelho local do Radar como fallback: "
                "shop_slug=%s produtos=%d",
                username,
                len(cached_products),
            )
            return {
                "ok": True,
                "message": (
                    f"Loja '{username}' carregada com {len(cached_products)} "
                    "produto(s) pelo espelho local do Radar."
                ),
                "data": {
                    "username": username,
                    "shop": {
                        "name": username,
                        "username": username,
                        "source": "espelho local do Radar",
                    },
                    "products": cached_products,
                    "method_used": "radar_store_mirror",
                    "source_label": "espelho local do Radar",
                },
            }
        log.warning(
            "[R7.0] Nenhum espelho local encontrado para shop_slug=%s "
            "(Shopee indisponível)",
            username,
        )
        return {
            "ok": False,
            "message": "Não consegui carregar os dados da loja. Verifique a URL.",
            "data": {},
        }

    shopid = shop_data.get("shopid") or shop_data.get("shop_id")

    # Carrega os produtos via Playwright
    from backend_core import fetch_shop_products_intercept
    products = fetch_shop_products_intercept(username, shopid)

    if products:
        # ── R7.0: salvar snapshot apenas com carga real bem-sucedida ──────
        try:
            from shopee_core.radar_store_service import save_store_snapshot

            summary = save_store_snapshot(
                {
                    "shop_uid": str(shopid) if shopid else None,
                    "shop_slug": username,
                    "shop_name": shop_data.get("name") or username,
                    "marketplace": "shopee",
                    "source_url": shop_url,
                },
                products,
                source="audit_service",
            )
            log.info(
                "[R7.0] Espelho da loja atualizado: store_uid=%s produtos=%d",
                summary.get("store_uid", "?"),
                summary.get("total_received", 0),
            )
        except Exception as exc:
            log.warning("[R7.0] Falha ao atualizar espelho da loja: %s", exc)
    else:
        cached_products = _load_products_from_store_mirror(username, shopid)
        if cached_products:
            log.info(
                "[R7.0] Usando espelho local do Radar como fallback: "
                "shop_slug=%s shop_uid=%s produtos=%d",
                username,
                shopid or "?",
                len(cached_products),
            )
            return {
                "ok": True,
                "message": (
                    f"Loja '{username}' carregada com {len(cached_products)} "
                    "produto(s) pelo espelho local do Radar."
                ),
                "data": {
                    "username": username,
                    "shop": shop_data,
                    "products": cached_products,
                    "method_used": "radar_store_mirror",
                    "source_label": "espelho local do Radar",
                },
            }
        log.warning(
            "[R7.0] Nenhum espelho local encontrado para shop_uid=%s shop_slug=%s",
            shopid or "?",
            username,
        )

    return {
        "ok": True,
        "message": f"Loja '{username}' carregada com {len(products)} produto(s).",
        "data": {
            "username": username,
            "shop": shop_data,
            "products": products,
            "method_used": "intercept",
        },
    }


def generate_product_optimization(
    product: dict,
    segmento: str,
    api_key: str = None,
    radar_own_product_uid: str | None = None,
) -> dict:
    """
    Executa o fluxo completo de otimização para um produto:
      1. Busca concorrentes via competitor_service (Shopee + Mercado Livre fallback)
      2. Busca avaliações no Mercado Livre (Playwright)
      3. Tenta carregar contexto do Radar (opcional)
      4. Gera o listing otimizado com Gemini

    Args:
        product: Dados do produto
        segmento: Segmento de mercado
        api_key: Gemini API Key opcional (usa GOOGLE_API_KEY se None)
        radar_own_product_uid: UID do produto no Radar (opcional)

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

    # 3. Contexto do Radar (opcional - R6.2)
    radar_context_block = None
    radar_status = None

    if radar_own_product_uid:
        log.info(f"[AUDIT] Tentando carregar contexto do Radar: {radar_own_product_uid}")
        try:
            from shopee_core.radar_audit_context_service import (
                get_radar_audit_context_status,
                build_radar_audit_context,
                build_radar_prompt_block,
            )

            radar_status = get_radar_audit_context_status(radar_own_product_uid)

            if radar_status.get("can_use"):
                log.info(f"[AUDIT] Radar disponível: {radar_status.get('reason')}")
                context = build_radar_audit_context(radar_own_product_uid)
                if context.get("ok"):
                    radar_context_block = build_radar_prompt_block(context)
                    log.info(f"[AUDIT] Contexto do Radar carregado: {len(radar_context_block)} caracteres")
                else:
                    log.warning(f"[AUDIT] Radar context falhou: {context.get('error')}")
            else:
                log.info(f"[AUDIT] Radar não disponível: {radar_status.get('reason')}")
        except Exception as e:
            log.warning(f"[AUDIT] Erro ao carregar Radar: {e}")
            # Continua sem Radar

    # 4. Otimização Gemini (passa api_key e radar_context_block)
    log.info(f"[AUDIT] Gerando otimização com Gemini...")
    from backend_core import generate_full_optimization
    optimization_text = generate_full_optimization(
        product=product,
        competitors_df=df_competitors,
        reviews=reviews or [],
        segmento=segmento,
        api_key=api_key,
        radar_context_block=radar_context_block,  # R6.2: Passa contexto do Radar
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
            "radar_used": radar_context_block is not None,  # R6.2: Indica se Radar foi usado
            "radar_status": radar_status,  # R6.2: Status do Radar
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
