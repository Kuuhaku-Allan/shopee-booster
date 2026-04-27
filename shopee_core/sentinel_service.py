"""
shopee_core/sentinel_service.py — Serviço de Sentinela
=======================================================
Camada de serviço entre a API / .exe e o bot_state.py.
Encapsula toda a lógica de lock, checagem e conclusão do Sentinela.

Regra: o .exe E o WhatsApp Bot chamam este serviço antes de rodar
o Sentinela. Quem adquirir o lock primeiro roda; o outro pula.
"""

from __future__ import annotations

from shopee_core.bot_state import (
    try_acquire_sentinel_lock,
    finish_sentinel_lock,
    get_sentinel_lock_status,
)


def request_sentinel_execution(
    loja_id: str | None,
    keyword: str,
    janela_execucao: str,
    executor: str,
    user_id: str | None = None,
    shop_uid: str | None = None,
) -> dict:
    """
    Solicita o lock para executar o Sentinela nessa janela.

    Returns:
        dict com:
          ok (bool)       — True se este executor pode rodar
          message (str)   — Descrição do resultado
          executor (str)  — Quem tem/tinha o lock
    """
    acquired = try_acquire_sentinel_lock(
        loja_id=loja_id or "",
        keyword=keyword,
        janela_execucao=janela_execucao,
        executor=executor,
        user_id=user_id,
        shop_uid=shop_uid,
    )

    if acquired:
        return {
            "ok": True,
            "message": (
                f"Lock adquirido por '{executor}'. "
                f"Pode prosseguir com o Sentinela para '{keyword}'."
            ),
            "executor": executor,
            "janela_execucao": janela_execucao,
        }

    # Outra instância já tem o lock — retorna quem está executando
    existing = get_sentinel_lock_status(
        loja_id or "",
        keyword,
        janela_execucao,
        user_id=user_id,
        shop_uid=shop_uid,
    )
    existing_executor = existing["executor"] if existing else "desconhecido"
    existing_status = existing["status"] if existing else "desconhecido"

    return {
        "ok": False,
        "message": (
            f"Sentinela já foi executado ou está em execução nessa janela "
            f"(executor: '{existing_executor}', status: '{existing_status}'). "
            f"'{executor}' deve pular esta janela."
        ),
        "executor": existing_executor,
        "status": existing_status,
        "janela_execucao": janela_execucao,
    }


def mark_sentinel_finished(
    loja_id: str | None,
    keyword: str,
    janela_execucao: str,
    status: str = "done",
    user_id: str | None = None,
    shop_uid: str | None = None,
) -> dict:
    """
    Marca a execução do Sentinela como concluída.

    Args:
        status: 'done' (sucesso) ou 'error' (falha)
    """
    finish_sentinel_lock(
        loja_id=loja_id or "",
        keyword=keyword,
        janela_execucao=janela_execucao,
        status=status,
        user_id=user_id,
        shop_uid=shop_uid,
    )
    return {
        "ok": True,
        "message": f"Sentinela marcado como '{status}' para '{keyword}' na janela '{janela_execucao}'.",
    }


def check_sentinel_status(
    loja_id: str | None,
    keyword: str,
    janela_execucao: str,
    user_id: str | None = None,
    shop_uid: str | None = None,
) -> dict:
    """
    Consulta o status atual do lock — útil para o .exe verificar
    se o WhatsApp Bot já rodou antes de executar localmente.
    """
    row = get_sentinel_lock_status(
        loja_id or "",
        keyword,
        janela_execucao,
        user_id=user_id,
        shop_uid=shop_uid,
    )
    if not row:
        return {
            "exists": False,
            "message": "Nenhuma execução registrada para esta janela.",
        }
    return {
        "exists": True,
        "executor": row["executor"],
        "status": row["status"],
        "started_at": row["started_at"],
        "finished_at": row.get("finished_at"),
        "message": (
            f"Janela executada por '{row['executor']}' — status: '{row['status']}'."
        ),
    }
