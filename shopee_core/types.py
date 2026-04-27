"""
shopee_core/types.py — Contratos de dados do núcleo compartilhado
=================================================================
Define os modelos Pydantic usados pelo .exe, API e Bot de WhatsApp.
Nenhum import de Streamlit aqui — esses tipos são interface-agnósticos.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════
# CHAT
# ══════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    user_id: str = Field(..., description="ID único do usuário/conversa")
    message: str = Field(..., description="Mensagem enviada pelo usuário")
    segmento: str = Field("Escolar / Juvenil", description="Nicho do produto")
    has_media: bool = Field(False, description="Se há mídia (imagem/vídeo) anexada")
    media_path: Optional[str] = Field(None, description="Caminho local da mídia (se houver)")
    # Contexto de produto selecionado (opcional — alimentado pela auditoria)
    selected_product: Optional[dict[str, Any]] = Field(
        None, description="Produto atualmente selecionado na sessão"
    )
    chat_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Histórico [{user: str, assistant: str}]"
    )
    full_context: str = Field(
        "",
        description="Contexto completo da loja/catálogo para o chat"
    )


class ChatResponse(BaseModel):
    text: str = Field("", description="Resposta textual do assistente")
    intent: str = Field("general", description="Intent detectado no turno")
    images: list[str] = Field(
        default_factory=list,
        description="Paths de imagens geradas (base64 ou caminho)"
    )
    captions: list[str] = Field(
        default_factory=list,
        description="Legendas correspondentes às imagens"
    )
    post_actions: list[dict[str, str]] = Field(
        default_factory=list,
        description="Ações de follow-up sugeridas"
    )


# ══════════════════════════════════════════════════════════════
# AUDITORIA
# ══════════════════════════════════════════════════════════════

class AuditRequest(BaseModel):
    user_id: str = Field(..., description="ID único do usuário")
    shop_url: str = Field(..., description="URL da loja na Shopee")
    product_index: Optional[int] = Field(
        None,
        description="Índice do produto a otimizar (0-based). None = listar todos."
    )
    segmento: str = Field("Escolar / Juvenil", description="Nicho do produto")


class AuditResponse(BaseModel):
    ok: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


# ══════════════════════════════════════════════════════════════
# SENTINELA / LOCK
# ══════════════════════════════════════════════════════════════

class SentinelLockRequest(BaseModel):
    loja_id: Optional[str] = Field(
        None,
        description="Identificador único da loja monitorada (legado / desktop)"
    )
    user_id: Optional[str] = Field(
        None,
        description="ID do usuário (WhatsApp JID) para lock multiusuário"
    )
    shop_uid: Optional[str] = Field(
        None,
        description="UID da loja ativa do usuário para lock multiusuário"
    )
    keyword: str = Field(..., description="Keyword sendo monitorada")
    janela_execucao: str = Field(
        ...,
        description="Identificador único da janela de execução (ex: '2026-04-25-15h')"
    )
    executor: str = Field(
        ...,
        description="Quem está tentando adquirir o lock: 'desktop' ou 'whatsapp'"
    )


class SentinelLockResponse(BaseModel):
    ok: bool
    message: str
    executor: Optional[str] = None
    janela_execucao: Optional[str] = None


class SentinelFinishRequest(BaseModel):
    loja_id: Optional[str] = None
    user_id: Optional[str] = None
    shop_uid: Optional[str] = None
    keyword: str
    janela_execucao: str
    status: str = Field("done", description="'done' ou 'error'")
