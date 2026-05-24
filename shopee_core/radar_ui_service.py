"""
shopee_core/radar_ui_service.py - Helper para UI do Radar na Auditoria.

R6.3 fornece funções para listar produtos do Radar, formatar labels e gerar previews
para a interface Streamlit, sem quebrar se o Radar não estiver disponível.
"""

from __future__ import annotations

from .radar_service import list_products
from .radar_patterns_service import get_latest_pattern_report
from .radar_audit_context_service import (
    get_radar_audit_context_status,
    build_radar_audit_context,
)


def list_radar_products_for_audit(limit: int = 100) -> list[dict]:
    """
    Lista produtos próprios do Radar disponíveis para uso na Auditoria.
    
    Retorna produtos com:
    - source_type = own_product
    - status = collected
    - Informações sobre pattern report e confiança
    
    Args:
        limit: Número máximo de produtos a retornar
    
    Returns:
        Lista de dicionários com:
        - product_uid: UID do produto
        - title: Título do produto
        - price: Preço
        - marketplace: Marketplace (shopee/mercadolivre)
        - updated_at: Data de atualização
        - has_pattern_report: Se tem relatório de padrões
        - direct_count: Número de concorrentes diretos
        - confidence: Nível de confiança (high/medium/low/insufficient)
        - can_use: Se pode ser usado na Auditoria
    """
    try:
        # Listar produtos próprios coletados
        products = list_products(
            source_type="own_product",
            status="collected",
            limit=limit,
        )
        
        # Enriquecer com informações do Radar
        enriched = []
        for product in products:
            product_uid = product.get("product_uid")
            
            # Verificar status do Radar
            status = get_radar_audit_context_status(product_uid)
            
            # Obter relatório de padrões
            report = get_latest_pattern_report(product_uid)
            
            enriched.append({
                "product_uid": product_uid,
                "title": product.get("title", ""),
                "price": product.get("price", 0),
                "marketplace": product.get("marketplace", ""),
                "updated_at": product.get("updated_at", ""),
                "has_pattern_report": report is not None,
                "direct_count": status.get("direct_count", 0),
                "confidence": status.get("confidence"),
                "can_use": status.get("can_use", False),
            })
        
        return enriched
    
    except Exception:
        # Se houver erro (ex: banco não existe), retorna lista vazia
        return []


def format_radar_product_label(product: dict) -> str:
    """
    Formata label para exibição no selectbox da UI.
    
    Args:
        product: Dicionário com dados do produto
    
    Returns:
        String formatada para exibição
    
    Exemplo:
        "Mochila Infantil Princesa Rosa — 5 concorrentes diretos — confiança média"
    """
    title = product.get("title", "Produto sem título")
    direct_count = product.get("direct_count", 0)
    confidence = product.get("confidence", "desconhecida")
    
    # Traduzir confiança
    confidence_map = {
        "high": "alta",
        "medium": "média",
        "low": "baixa",
        "insufficient": "insuficiente",
    }
    confidence_pt = confidence_map.get(confidence, confidence)
    
    # Truncar título se muito longo
    if len(title) > 50:
        title = title[:47] + "..."
    
    return f"{title} — {direct_count} concorrentes diretos — confiança {confidence_pt}"


def get_radar_preview_for_ui(product_uid: str) -> dict:
    """
    Gera preview do contexto do Radar para exibição na UI.
    
    Args:
        product_uid: UID do produto no Radar
    
    Returns:
        Dicionário com:
        - ok: Se preview foi gerado com sucesso
        - confidence: Nível de confiança
        - direct_count: Número de concorrentes diretos
        - price_min: Preço mínimo
        - price_avg: Preço médio
        - price_median: Preço mediano
        - price_max: Preço máximo
        - strong_terms: Lista de termos fortes
        - recommended_features: Lista de features recomendadas
        - off_niche_features: Lista de features off-niche
        - commercial_arguments: Lista de argumentos comerciais
        - warnings: Lista de avisos
        - error: Mensagem de erro (se ok=False)
    """
    try:
        # Verificar status
        status = get_radar_audit_context_status(product_uid)
        
        if not status.get("can_use"):
            return {
                "ok": False,
                "error": status.get("reason", "Radar não disponível"),
                "confidence": status.get("confidence"),
                "direct_count": status.get("direct_count", 0),
            }
        
        # Construir contexto
        context = build_radar_audit_context(product_uid)
        
        if not context.get("ok"):
            return {
                "ok": False,
                "error": context.get("error", "Erro ao construir contexto"),
                "confidence": None,
                "direct_count": 0,
            }
        
        # Extrair dados para preview
        market = context.get("market_summary", {})
        title_strat = context.get("title_strategy", {})
        feature_strat = context.get("feature_strategy", {})
        desc_strat = context.get("description_strategy", {})
        warnings = context.get("warnings", [])
        
        return {
            "ok": True,
            "confidence": market.get("confidence"),
            "direct_count": market.get("competitor_count", 0),
            "price_min": market.get("price_min", 0),
            "price_avg": market.get("price_avg", 0),
            "price_median": market.get("price_median", 0),
            "price_max": market.get("price_max", 0),
            "strong_terms": title_strat.get("strong_terms", []),
            "recommended_features": feature_strat.get("recommended_features", []),
            "off_niche_features": feature_strat.get("off_niche_features", []),
            "commercial_arguments": desc_strat.get("commercial_arguments", []),
            "warnings": warnings,
        }
    
    except Exception as e:
        return {
            "ok": False,
            "error": f"Erro ao gerar preview: {str(e)}",
            "confidence": None,
            "direct_count": 0,
        }
