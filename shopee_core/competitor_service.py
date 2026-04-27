"""
competitor_service.py — Serviço leve de busca de concorrentes
==============================================================

Não importa backend_core diretamente, usa subprocess isolado para evitar
travamentos do FastAPI causados por imports pesados (streamlit, pandas, etc.)

Vantagens:
- Isolamento completo: backend_core roda em processo separado
- Timeout REAL: subprocess.run(timeout=X) mata o processo se exceder
- Sem conflitos: não há deadlock ou conflito de threads
- Logs claros: erros aparecem no stderr do subprocess
"""

import subprocess
import sys
import json
import logging

log = logging.getLogger("competitor_service")


def fetch_competitors(keyword: str, timeout_seconds: int = 120) -> list:
    """
    Busca concorrentes via subprocess isolado.
    
    Args:
        keyword: Palavra-chave para buscar
        timeout_seconds: Timeout em segundos (padrão: 120s = 2min)
    
    Returns:
        Lista de concorrentes encontrados (máximo 10)
        Cada concorrente é um dict com: nome, preco, shop_id, item_id, etc.
    
    Raises:
        TimeoutError: Se exceder o timeout
        RuntimeError: Se o scraping falhar
    
    Exemplo:
        >>> competitors = fetch_competitors("mochila roxa", timeout_seconds=90)
        >>> print(f"Encontrados {len(competitors)} concorrentes")
    """
    log.info(f"[COMPETITOR] Buscando concorrentes para: {keyword!r}")
    
    # Código Python que será executado no subprocess
    # Importa backend_core DENTRO do subprocess, não no processo principal
    code = r"""
import sys
import json

try:
    from backend_core import fetch_competitors_intercept
    
    keyword = sys.argv[1]
    result = fetch_competitors_intercept(keyword)
    print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e)}), file=sys.stderr)
    sys.exit(1)
"""
    
    try:
        # Executa o código em um processo Python separado
        result = subprocess.run(
            [sys.executable, "-c", code, keyword],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        
        # Se o processo retornou erro
        if result.returncode != 0:
            error_msg = result.stderr[-500:] if result.stderr else "Erro desconhecido"
            log.error(f"[COMPETITOR] Erro no scraping: {error_msg}")
            raise RuntimeError(f"Scraping falhou: {error_msg}")
        
        # Parse do JSON retornado
        data = json.loads(result.stdout or "[]")
        log.info(f"[COMPETITOR] Encontrados {len(data)} concorrentes")
        return data
        
    except subprocess.TimeoutExpired:
        log.error(f"[COMPETITOR] Timeout de {timeout_seconds}s excedido para {keyword!r}")
        raise TimeoutError(f"Busca de concorrentes excedeu {timeout_seconds}s")
    except json.JSONDecodeError as e:
        log.error(f"[COMPETITOR] Erro ao decodificar JSON: {e}")
        log.error(f"[COMPETITOR] stdout: {result.stdout[:500] if result.stdout else 'vazio'}")
        return []
    except Exception as e:
        log.error(f"[COMPETITOR] Erro inesperado: {e}")
        raise
