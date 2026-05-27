"""
shopee_core/radar_audit_context_service.py - Adaptador do Radar para Auditoria.

R6.1 transforma relatórios do Radar em contexto estruturado para a Auditoria usar.
Não altera fluxos existentes, apenas cria uma saída limpa e testável.
"""

from __future__ import annotations

from .radar_patterns_service import get_latest_pattern_report
from .radar_relevance_service import get_matches_for_product
from .radar_service import get_product


def build_radar_audit_context(own_product_uid: str) -> dict:
    """
    Constrói contexto estruturado do Radar para uso na Auditoria.
    
    Retorna um dicionário com:
    - ok: bool
    - own_product: dados do produto próprio
    - market_summary: resumo do mercado
    - title_strategy: estratégia de título
    - feature_strategy: estratégia de features
    - description_strategy: estratégia de descrição
    - image_strategy: estratégia de imagens
    - competitors: lista de concorrentes resumidos
    - recommendations: recomendações com evidência
    - warnings: avisos importantes
    """
    own_product = get_product(own_product_uid)
    if not own_product:
        return {
            "ok": False,
            "error": f"Produto próprio não encontrado: {own_product_uid}",
            "reason": "Produto não existe no banco de dados do Radar.",
        }
    
    report = get_latest_pattern_report(own_product_uid)
    if not report:
        return {
            "ok": False,
            "error": "Nenhum relatório do Radar encontrado para este produto.",
            "reason": "Execute o Radar primeiro para gerar padrões de mercado.",
            "own_product": {
                "product_uid": own_product["product_uid"],
                "title": own_product.get("title"),
                "price": own_product.get("price"),
                "marketplace": own_product.get("marketplace"),
            },
        }
    
    direct_count = report.get("direct_count", 0)
    confidence = _calculate_confidence(direct_count)
    
    if direct_count < 3:
        return {
            "ok": False,
            "error": "Base de concorrentes insuficiente para análise confiável.",
            "reason": f"Apenas {direct_count} concorrentes diretos encontrados. Mínimo recomendado: 3.",
            "own_product": {
                "product_uid": own_product["product_uid"],
                "title": own_product.get("title"),
                "price": own_product.get("price"),
                "marketplace": own_product.get("marketplace"),
            },
            "confidence": confidence,
        }
    
    # Carregar concorrentes diretos
    matches = get_matches_for_product(own_product_uid, verdict="competitor_direct")
    competitors = [
        {
            "title": match.get("title"),
            "price": match.get("price"),
            "relevance_score": match.get("relevance_score"),
            "reasons": match.get("reasons") or [],
        }
        for match in matches[:10]  # Limitar a 10 para não poluir
    ]
    
    # Extrair dados do relatório
    raw = report.get("raw") or {}
    title_terms = report.get("title_terms") or {}
    features = report.get("features") or {}
    description_patterns = report.get("description_patterns") or {}
    image_patterns = report.get("image_patterns") or {}
    recommendations = report.get("recommendations") or []
    warnings = report.get("warnings") or []
    
    # Separar features in-niche e off-niche
    in_niche_features = [
        row["feature"]
        for row in features.get("strong_patterns", [])
    ]
    off_niche_features = [
        row["feature"]
        for row in features.get("off_niche_features", [])
    ]
    
    # Termos fortes (frequência >= 40%)
    strong_terms = [
        row["term"]
        for row in title_terms.get("strong_terms", [])
    ]
    
    # Argumentos comerciais comuns (frequência >= 40%)
    commercial_arguments = [
        row["argument"]
        for row in description_patterns.get("common_promises", [])
    ]
    
    # Construir contexto estruturado
    context = {
        "ok": True,
        "own_product": {
            "product_uid": own_product["product_uid"],
            "title": own_product.get("title"),
            "price": own_product.get("price"),
            "marketplace": own_product.get("marketplace"),
        },
        "market_summary": {
            "competitor_count": direct_count,
            "price_min": report.get("price_min"),
            "price_avg": report.get("price_avg"),
            "price_median": report.get("price_median"),
            "price_max": report.get("price_max"),
            "confidence": confidence,
        },
        "title_strategy": {
            "strong_terms": strong_terms,
            "avoid_terms": off_niche_features,
            "notes": [
                f"Termos aparecem em pelo menos 40% dos concorrentes diretos.",
                f"Evitar termos off-niche: {', '.join(off_niche_features) if off_niche_features else 'nenhum'}.",
            ],
        },
        "feature_strategy": {
            "recommended_features": in_niche_features,
            "off_niche_features": off_niche_features,
            "warnings": [
                row.get("warning")
                for row in features.get("off_niche_features", [])
                if row.get("warning")
            ],
        },
        "description_strategy": {
            "commercial_arguments": commercial_arguments,
            "notes": [
                "Argumentos aparecem em pelo menos 40% dos concorrentes diretos.",
                "Use como evidência, não como verdade absoluta.",
            ],
        },
        "image_strategy": {
            "avg_image_count": image_patterns.get("avg_image_count"),
            "recommendations": [
                rec["recommendation"]
                for rec in recommendations
                if rec.get("type") == "images"
            ],
        },
        "competitors": competitors,
        "recommendations": recommendations,
        "warnings": warnings,
    }
    
    return context


def build_radar_prompt_block(context: dict) -> str:
    """
    Transforma o contexto em um bloco de texto seguro para entrar em prompt.
    
    Formato estruturado e legível para o Gemini usar como evidência.
    """
    if not context.get("ok"):
        return f"=== CONTEXTO DO RADAR DE CONCORRENTES ===\n\nStatus: Indisponível\nMotivo: {context.get('reason', 'Erro desconhecido')}\n"
    
    market = context.get("market_summary", {})
    title_strat = context.get("title_strategy", {})
    feature_strat = context.get("feature_strategy", {})
    desc_strat = context.get("description_strategy", {})
    image_strat = context.get("image_strategy", {})
    recommendations = context.get("recommendations", [])
    warnings = context.get("warnings", [])
    
    lines = [
        "=== CONTEXTO DO RADAR DE CONCORRENTES ===",
        "",
        "Base analisada:",
        f"- Concorrentes diretos: {market.get('competitor_count', 0)}",
        f"- Confiança: {market.get('confidence', 'desconhecida')}",
        f"- Preço mínimo: R$ {market.get('price_min', 0):.2f}",
        f"- Preço médio: R$ {market.get('price_avg', 0):.2f}",
        f"- Preço mediano: R$ {market.get('price_median', 0):.2f}",
        f"- Preço máximo: R$ {market.get('price_max', 0):.2f}",
        "",
        "Termos fortes em títulos:",
        f"- {', '.join(title_strat.get('strong_terms', []))}",
        "",
        "Features recorrentes recomendadas:",
        f"- {', '.join(feature_strat.get('recommended_features', []))}",
        "",
    ]
    
    # Features off-niche
    off_niche = feature_strat.get("off_niche_features", [])
    if off_niche:
        lines.extend([
            "Features fora de nicho / evitar:",
            f"- {', '.join(off_niche)}",
            "",
        ])
    
    # Argumentos comerciais
    args = desc_strat.get("commercial_arguments", [])
    if args:
        lines.extend([
            "Argumentos comerciais recorrentes:",
            f"- {', '.join(args)}",
            "",
        ])
    
    # Imagens
    avg_images = image_strat.get("avg_image_count")
    if avg_images:
        lines.extend([
            "Padrões de imagem:",
            f"- Média de imagens: {avg_images:.1f}",
            "",
        ])
    
    # Recomendações
    if recommendations:
        lines.append("Recomendações baseadas em evidência:")
        for rec in recommendations[:5]:  # Limitar a 5
            priority = rec.get("priority", "medium")
            recommendation = rec.get("recommendation", "")
            evidence = rec.get("evidence", "")
            lines.append(f"- [{priority}] {recommendation}")
            if evidence:
                lines.append(f"  Evidência: {evidence}")
        lines.append("")
    
    # Warnings
    if warnings:
        lines.append("Atenção:")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")
    
    # Instruções de uso
    lines.extend([
        "Instruções de uso:",
        "- Não inventar dados fora do Radar.",
        "- Não recomendar features marcadas como off-niche.",
        "- Usar o Radar como evidência, não como verdade absoluta.",
        "- Priorizar recomendações de alta prioridade.",
    ])
    
    return "\n".join(lines)


def get_radar_audit_context_status(own_product_uid: str) -> dict:
    """
    Retorna status do contexto do Radar para um produto.
    
    Indica se o Radar pode ser usado na Auditoria e por quê.
    """
    own_product = get_product(own_product_uid)
    if not own_product:
        return {
            "can_use": False,
            "reason": f"Produto próprio não encontrado: {own_product_uid}",
            "confidence": None,
        }
    
    report = get_latest_pattern_report(own_product_uid)
    if not report:
        return {
            "can_use": False,
            "reason": "Nenhum relatório do Radar encontrado para este produto.",
            "confidence": None,
        }
    
    direct_count = report.get("direct_count", 0)
    effective_direct_count = report.get("effective_direct_count", direct_count)
    effective_competitor_count = report.get("effective_competitor_count", direct_count)
    confidence = _calculate_confidence(direct_count)
    effective_confidence = report.get("confidence") or _calculate_confidence(effective_direct_count)
    
    if direct_count < 3:
        return {
            "can_use": False,
            "reason": f"Base insuficiente: apenas {direct_count} concorrentes diretos. Mínimo: 3.",
            "confidence": confidence,
            "direct_count": direct_count,
            "effective_direct_count": effective_direct_count,
            "effective_competitor_count": effective_competitor_count,
            "effective_confidence": effective_confidence,
            "report_uid": report.get("report_uid"),
        }
    
    return {
        "can_use": True,
        "reason": f"Radar disponível com {direct_count} concorrentes diretos.",
        "confidence": confidence,
        "direct_count": direct_count,
        "effective_direct_count": effective_direct_count,
        "effective_competitor_count": effective_competitor_count,
        "effective_confidence": effective_confidence,
        "report_uid": report.get("report_uid"),
    }


def _calculate_confidence(direct_count: int) -> str:
    """
    Calcula nível de confiança baseado na quantidade de concorrentes diretos.
    
    Regras:
    - >= 10: high
    - >= 5: medium
    - >= 3: low
    - < 3: insufficient
    """
    if direct_count >= 10:
        return "high"
    elif direct_count >= 5:
        return "medium"
    elif direct_count >= 3:
        return "low"
    else:
        return "insufficient"
