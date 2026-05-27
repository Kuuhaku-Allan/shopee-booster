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


def select_sentinel_competitors(
    product: dict,
    current_competitors: list[dict] | None = None,
    limit: int = 10,
) -> dict:
    """
    Seleciona a fonte de concorrentes sem alterar lock, trigger ou estado.

    Se a camada Radar falhar por qualquer motivo, retorna a fonte atual ja
    normalizada. Falha no Radar nunca deve deixar a Sentinela presa.
    """
    keyword = (product or {}).get("keyword") or (product or {}).get("name") or ""
    try:
        from shopee_core.sentinel_competitor_source_service import (
            choose_sentinel_competitor_source,
            normalize_sentinel_competitors,
        )

        chosen = choose_sentinel_competitor_source(
            product or {},
            current_competitors=current_competitors or [],
            limit=limit,
        )
        chosen = dict(chosen)
        chosen["competitors"] = normalize_sentinel_competitors(
            chosen.get("competitors") or [],
            keyword=keyword,
            limit=limit,
        )
        return chosen
    except Exception as exc:
        from shopee_core.sentinel_competitor_source_service import normalize_sentinel_competitors

        fallback = normalize_sentinel_competitors(
            current_competitors or [],
            keyword=keyword,
            limit=limit,
        )
        return {
            "ok": bool(fallback),
            "source": "current" if fallback else "none",
            "reason": "Radar falhou durante a escolha da fonte; mantive a fonte atual da Sentinela.",
            "competitors": fallback,
            "current_used": bool(fallback),
            "radar_used": False,
            "confidence": None,
            "report_uid": None,
            "effective_competitor_count": 0,
            "warnings": [f"Falha ao avaliar Radar para Sentinela: {exc}"],
        }
