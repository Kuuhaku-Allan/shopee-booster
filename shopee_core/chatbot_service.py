"""
shopee_core/chatbot_service.py — Serviço de Chat
=================================================
Ponte entre o WhatsApp Bot / API e o process_chat_turn()
do backend_core.py.

Diferença importante do Streamlit:
- Streamlit guarda session_state (histórico, imagem ativa etc.) entre reruns.
- O WhatsApp Bot precisa receber esses dados na requisição (stateless HTTP).
- Essa camada adapta a assinatura para funcionar nos dois contextos.
"""

from __future__ import annotations

from typing import Any

from backend_core import process_chat_turn


def run_chatbot_turn(
    user_message: str,
    segmento: str,
    chat_history: list[dict[str, str]] | None = None,
    full_context: str = "",
    attachments: list | None = None,
    attachment_types: list[str] | None = None,
    channel: str = "desktop",
    **kwargs: Any,
) -> dict:
    """
    Executa um turno do chat e retorna o resultado normalizado.

    Parâmetros:
        user_message    — Mensagem do usuário
        segmento        — Nicho do produto ("Escolar / Juvenil", etc.)
        chat_history    — Lista de turnos anteriores [{user, assistant}]
        full_context    — Contexto de catálogo/loja gerado por build_catalog_context()
        attachments     — Lista de bytes/PIL.Image de mídia anexada
        attachment_types — Lista de "image" | "video" por anexo
        **kwargs        — Repassados para process_chat_turn()
                          (selected_product, df_competitors, optimization_reviews, etc.)

    Retorna dict com:
        text        — Resposta textual
        intent      — Intent detectado
        images      — Lista de PIL.Image geradas
        captions    — Legendas das imagens
        post_actions — Ações sugeridas de follow-up
    """
    result = process_chat_turn(
        user_message=user_message,
        attachments=attachments or [],
        attachment_types=attachment_types or [],
        chat_history=chat_history or [],
        full_context=full_context,
        segmento=segmento,
        channel=channel,
        **kwargs,
    )

    # Garante que o retorno sempre tenha os campos esperados
    return {
        "text": result.get("text", ""),
        "intent": result.get("intent", "general"),
        "images": result.get("images", []),
        "captions": result.get("captions", []),
        "post_actions": result.get("post_actions", []),
    }


def build_shop_context(products: list, shop_name: str) -> str:
    """
    Gera o contexto de catálogo a partir da lista de produtos.
    Reutiliza build_catalog_context() do backend_core.
    """
    from backend_core import build_catalog_context
    return build_catalog_context(produtos=products, shop_name=shop_name)
