"""
shopee_core/chatbot_market_context_service.py - R7.6 Radar context for Chatbot.

The Chatbot should use Radar only when the user asks something that depends on
market evidence: price, competitors, title, description, tags, listing or
positioning. General app/support questions must keep the old lightweight flow.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from shopee_core.audit_market_source_service import get_radar_market_status_for_audit
from shopee_core.radar_audit_context_service import build_radar_audit_context


_PRICE_TERMS = {
    "preco", "preco?", "precificar", "precificacao", "valor", "barato",
    "caro", "faixa de preco", "margem",
}
_COMPETITOR_TERMS = {
    "concorrente", "concorrentes", "competidor", "competidores",
    "mercado", "comparar", "comparado", "produto parecido",
}
_TITLE_TERMS = {"titulo", "headline", "nome do produto", "keyword", "palavra-chave"}
_DESCRIPTION_TERMS = {"descricao", "copy", "argumento", "beneficio"}
_LISTING_TERMS = {
    "tag", "tags", "anuncio", "listing", "otimizar", "otimizacao",
    "converter", "conversao", "vendas", "venda", "vende", "vender", "nao vende",
    "posicionamento", "diferencial", "avaliacao", "review",
    "imagem", "melhorar produto", "melhorar esse produto",
}
_GENERAL_SUPPORT_TERMS = {
    "whatsapp", "sentinela", "telegram", "cloudflare", "docker", "exe",
    "cadastro", "cadastrar loja", "conectar", "como uso", "funcao",
}
_OFF_NICHE_DENYLIST = {
    "notebook", "executivo", "executiva", "corporativo", "corporativa",
    "natacao", "piscina", "praia", "esporte", "esportiva",
    "academia", "trekking", "trilha", "urbano adulto", "masculino adulto",
}


def _normalize(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.strip().lower())


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def should_use_market_context_for_chat(
    message: str,
    conversation_state: dict | None = None,
) -> dict:
    """Detect whether a Chatbot turn needs Radar/market evidence."""
    text = _normalize(message)
    if not text:
        return {
            "use_market_context": False,
            "intent": "unknown",
            "reason": "Mensagem vazia.",
        }

    if _contains_any(text, _PRICE_TERMS):
        return {"use_market_context": True, "intent": "price", "reason": "Pergunta depende de preco de mercado."}
    if _contains_any(text, _COMPETITOR_TERMS):
        return {"use_market_context": True, "intent": "competitors", "reason": "Pergunta cita concorrentes ou comparacao."}
    if _contains_any(text, _TITLE_TERMS):
        return {"use_market_context": True, "intent": "title", "reason": "Pergunta depende de estrategia de titulo."}
    if _contains_any(text, _DESCRIPTION_TERMS):
        return {"use_market_context": True, "intent": "description", "reason": "Pergunta depende de copy/descricao."}
    if _contains_any(text, _LISTING_TERMS):
        return {"use_market_context": True, "intent": "listing", "reason": "Pergunta depende de listing, conversao ou posicionamento."}

    if _contains_any(text, _GENERAL_SUPPORT_TERMS):
        return {"use_market_context": False, "intent": "general", "reason": "Pergunta geral do app, sem necessidade de mercado."}

    return {
        "use_market_context": False,
        "intent": "general",
        "reason": "Sem sinais suficientes de pergunta de mercado.",
    }


def _as_list(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("feature") or value.get("term") or value.get("argument") or value.get("name")
        text = str(value or "").strip()
        if text:
            out.append(text)
    return out


def _dedupe(values: list[str], limit: int) -> list[str]:
    seen = set()
    out = []
    for value in values:
        key = _normalize(value)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= limit:
            break
    return out


def _filter_recommended_features(recommended: list[str], off_niche: list[str]) -> list[str]:
    off_keys = {_normalize(item) for item in off_niche}
    out = []
    for item in recommended:
        key = _normalize(item)
        if not key:
            continue
        if key in off_keys or any(blocked in key for blocked in _OFF_NICHE_DENYLIST):
            continue
        out.append(item)
    return _dedupe(out, 8)


def _format_brl(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"R$ {number:.2f}".replace(".", ",")


def _resolve_product(product: dict | None, conversation_state: dict | None = None) -> dict | None:
    if product:
        return product
    if not conversation_state:
        return None
    for key in ("selected_product", "active_product", "last_audited_product", "product"):
        value = conversation_state.get(key)
        if isinstance(value, dict) and value:
            return value
    return None


def build_chatbot_market_context_block(
    radar_context: dict,
    radar_status: dict | None = None,
    intent_info: dict | None = None,
) -> str:
    """Build a compact Radar block for Chatbot prompts."""
    if not radar_context.get("ok"):
        return ""

    radar_status = radar_status or {}
    intent_info = intent_info or {}
    market = radar_context.get("market_summary") or {}
    title = radar_context.get("title_strategy") or {}
    features = radar_context.get("feature_strategy") or {}
    desc = radar_context.get("description_strategy") or {}

    strong_terms = _dedupe(_as_list(title.get("strong_terms")), 8)
    off_niche = _dedupe(_as_list(features.get("off_niche_features")), 8)
    recommended = _filter_recommended_features(
        _as_list(features.get("recommended_features")),
        off_niche,
    )
    commercial_args = _dedupe(_as_list(desc.get("commercial_arguments")), 5)
    warnings = _dedupe(
        _as_list(radar_status.get("warnings")) + _as_list(radar_context.get("warnings")),
        5,
    )

    confidence = radar_status.get("confidence_level") or market.get("confidence") or "desconhecida"
    effective_count = (
        radar_status.get("effective_competitor_count")
        or market.get("effective_competitor_count")
        or market.get("competitor_count")
        or 0
    )
    if radar_status and not radar_status.get("is_fresh", True):
        warnings = _dedupe(
            ["Base Radar vencida ou pendente de renovacao; use com cautela."] + warnings,
            5,
        )

    price_parts = []
    for label, key in (
        ("min", "price_min"),
        ("media", "price_avg"),
        ("mediana", "price_median"),
        ("max", "price_max"),
    ):
        formatted = _format_brl(market.get(key))
        if formatted:
            price_parts.append(f"{label}: {formatted}")

    lines = [
        "=== BASE RADAR PARA O CHATBOT ===",
        f"Intencao da pergunta: {intent_info.get('intent', 'market')}",
        f"Confianca Radar: {str(confidence).upper()}",
        f"Concorrentes efetivos: {effective_count}",
    ]
    if price_parts:
        lines.append("Faixa de preco observada: " + "; ".join(price_parts))
    if strong_terms:
        lines.append("Termos fortes: " + ", ".join(strong_terms))
    if recommended:
        lines.append("Features recomendadas: " + ", ".join(recommended))
    if off_niche:
        lines.append("Features fora de nicho/evitar: " + ", ".join(off_niche))
    if commercial_args:
        lines.append("Argumentos comerciais recorrentes: " + ", ".join(commercial_args))
    if warnings:
        lines.append("Avisos: " + " | ".join(warnings))

    lines.extend([
        "",
        "Regras para responder:",
        "- Use o Radar apenas como evidencia de mercado local.",
        "- Nao invente concorrentes, precos ou metricas fora deste bloco.",
        "- Se a base estiver vencida, avise com cautela.",
        "- Nao exponha JSON bruto, debug ou contexto interno ao usuario.",
        "- Nao recomende features marcadas como fora de nicho/evitar.",
        "=== FIM DA BASE RADAR PARA O CHATBOT ===",
    ])
    return "\n".join(lines)


def get_chatbot_radar_context(
    product: dict | None,
    message: str,
    shop_uid: str | None = None,
    conversation_state: dict | None = None,
) -> dict:
    """Return Radar prompt context and metadata for a Chatbot turn."""
    intent_info = should_use_market_context_for_chat(message, conversation_state)
    if not intent_info.get("use_market_context"):
        return {
            "ok": True,
            "use_market_context": False,
            "market_context_used": False,
            "market_context_source": "none",
            "intent": intent_info.get("intent"),
            "reason": intent_info.get("reason"),
            "context_block": "",
            "warnings": [],
        }

    resolved_product = _resolve_product(product, conversation_state)
    if not resolved_product:
        return {
            "ok": False,
            "use_market_context": True,
            "market_context_used": False,
            "market_context_source": "none",
            "intent": intent_info.get("intent"),
            "reason": "Produto ativo ausente.",
            "needs_product": True,
            "context_block": "",
            "warnings": [
                "Posso usar o Radar, mas preciso saber qual produto voce quer analisar.",
            ],
        }

    try:
        radar_status = get_radar_market_status_for_audit(resolved_product)
    except Exception as exc:
        return {
            "ok": False,
            "use_market_context": True,
            "market_context_used": False,
            "market_context_source": "none",
            "intent": intent_info.get("intent"),
            "reason": "Falha ao buscar status Radar.",
            "context_block": "",
            "warnings": [f"Nao consegui consultar o Radar agora: {exc}"],
        }

    warnings = _as_list(radar_status.get("warnings"))
    if not radar_status.get("has_radar"):
        return {
            "ok": False,
            "use_market_context": True,
            "market_context_used": False,
            "market_context_source": "none",
            "intent": intent_info.get("intent"),
            "reason": "Produto sem base Radar.",
            "radar_status": radar_status,
            "context_block": "",
            "warnings": warnings or [
                "Este produto ainda nao possui base Radar. Crie a base para uma analise de mercado mais precisa.",
            ],
        }

    confidence = str(radar_status.get("confidence_level") or "insufficient").lower()
    effective_count = int(
        radar_status.get("effective_competitor_count")
        or radar_status.get("effective_direct_count")
        or radar_status.get("direct_count")
        or 0
    )
    can_use_radar = confidence in {"high", "medium"} and effective_count >= 3
    if not can_use_radar:
        return {
            "ok": False,
            "use_market_context": True,
            "market_context_used": False,
            "market_context_source": "none",
            "intent": intent_info.get("intent"),
            "reason": "Base Radar insuficiente para o Chatbot.",
            "radar_status": radar_status,
            "radar_confidence": confidence,
            "radar_report_uid": radar_status.get("radar_report_uid") or radar_status.get("report_uid"),
            "context_block": "",
            "warnings": warnings or [
                "A base Radar deste produto ainda e insuficiente. Rode o Radar antes de confiar em concorrentes.",
            ],
        }

    radar_uid = radar_status.get("radar_product_uid") or radar_status.get("product_uid")
    try:
        radar_context = build_radar_audit_context(radar_uid)
    except Exception as exc:
        return {
            "ok": False,
            "use_market_context": True,
            "market_context_used": False,
            "market_context_source": "none",
            "intent": intent_info.get("intent"),
            "reason": "Falha ao montar contexto Radar.",
            "radar_status": radar_status,
            "radar_confidence": confidence,
            "radar_report_uid": radar_status.get("radar_report_uid") or radar_status.get("report_uid"),
            "context_block": "",
            "warnings": warnings + [f"Nao consegui montar o contexto Radar: {exc}"],
        }

    if not radar_context.get("ok"):
        return {
            "ok": False,
            "use_market_context": True,
            "market_context_used": False,
            "market_context_source": "none",
            "intent": intent_info.get("intent"),
            "reason": radar_context.get("reason") or radar_context.get("error") or "Radar indisponivel.",
            "radar_status": radar_status,
            "radar_confidence": confidence,
            "radar_report_uid": radar_status.get("radar_report_uid") or radar_status.get("report_uid"),
            "context_block": "",
            "warnings": warnings + [radar_context.get("reason") or "Radar sem contexto pronto."],
        }

    if not radar_status.get("is_fresh", True):
        warnings = _dedupe(
            warnings + ["Usei a base Radar existente, mas ela esta vencida. Recomendo renovar."],
            6,
        )

    context_block = build_chatbot_market_context_block(
        radar_context,
        radar_status=radar_status,
        intent_info=intent_info,
    )
    return {
        "ok": True,
        "use_market_context": True,
        "market_context_used": bool(context_block),
        "market_context_source": "radar" if context_block else "none",
        "intent": intent_info.get("intent"),
        "reason": intent_info.get("reason"),
        "radar_status": radar_status,
        "radar_confidence": confidence,
        "radar_report_uid": radar_status.get("radar_report_uid") or radar_status.get("report_uid"),
        "radar_product_uid": radar_uid,
        "context_block": context_block,
        "warnings": warnings,
    }
