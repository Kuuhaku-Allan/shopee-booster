"""
clear_sentinel_locks.py — Limpa locks antigos do Sentinela
============================================================

Remove locks com status timeout/error/failed/cancelled para permitir nova execução.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopee_core.bot_state import get_conn
from shopee_core.sentinel_whatsapp_service import generate_janela_execucao

def clear_locks(user_id: str, shop_uid: str, janela: str = None):
    """Limpa locks retryable do Sentinela."""
    if janela is None:
        janela = generate_janela_execucao()
    
    conn = get_conn()
    cur = conn.execute(
        """
        DELETE FROM sentinela_locks 
        WHERE user_id = ? 
          AND shop_uid = ? 
          AND janela_execucao = ? 
          AND status IN ('timeout', 'error', 'failed', 'cancelled')
        """,
        (user_id, shop_uid, janela)
    )
    conn.commit()
    
    print(f"Janela: {janela}")
    print(f"Locks removidos: {cur.rowcount}")
    return cur.rowcount


if __name__ == "__main__":
    user = "5511988600050@s.whatsapp.net"
    shop = "8de0c133-f9b3-475b-bf68-cd59be13f461"
    
    count = clear_locks(user, shop)
    
    if count > 0:
        print(f"\n✅ {count} locks removidos com sucesso!")
        print("\nAgora você pode rodar: /sentinela rodar")
    else:
        print("\n⚠️ Nenhum lock encontrado para remover.")
