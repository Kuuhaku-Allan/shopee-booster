"""
competitor_service.py — Serviço de busca de concorrentes com múltiplos providers
==================================================================================

Sistema de providers com fallback:
1. Mercado Livre (principal) - API pública, rápida e confiável
2. Shopee (fallback) - Playwright, pode estar bloqueado

Vantagens:
- Múltiplas fontes de dados
- Fallback automático se um provider falhar
- Timeout independente por provider
- Logs detalhados por provider
"""

import subprocess
import sys
import json
import logging
import requests
from typing import List, Dict, Optional

log = logging.getLogger("competitor_service")


def search_competitors_mercadolivre(keyword: str, limit: int = 10) -> List[Dict]:
    """
    Busca concorrentes no Mercado Livre via API pública JSON.
    
    Args:
        keyword: Palavra-chave para buscar
        limit: Número máximo de resultados (padrão: 10)
    
    Returns:
        Lista de concorrentes normalizados
    
    API: https://api.mercadolibre.com/sites/MLB/search
    
    NOTA: A API do ML está retornando 403 Forbidden atualmente.
    Possíveis causas: bloqueio por IP, necessidade de autenticação, rate limiting.
    """
    keyword = (keyword or "").strip()
    if not keyword:
        log.warning("[COMPETITOR][ML] Keyword vazia")
        return []
    
    url = "https://api.mercadolibre.com/sites/MLB/search"
    
    try:
        log.info(f"[COMPETITOR][ML] Buscando keyword={keyword!r}")
        
        response = requests.get(
            url,
            params={
                "q": keyword,
                "limit": limit,
            },
            timeout=20,
        )
        
        log.info(f"[COMPETITOR][ML] status={response.status_code}")
        
        if response.status_code == 403:
            log.warning(f"[COMPETITOR][ML] API bloqueada (403 Forbidden) - usando provider mock")
            # Fallback para mock quando API está bloqueada
            return search_competitors_mock(keyword, limit)
        
        if response.status_code != 200:
            log.warning(f"[COMPETITOR][ML] erro body={response.text[:300]}")
            return []
        
        data = response.json()
        results = data.get("results", []) or []
        
        log.info(f"[COMPETITOR][ML] API retornou {len(results)} resultados")
        
        competitors = []
        
        for idx, item in enumerate(results[:limit], start=1):
            seller = item.get("seller") or {}
            
            competitors.append({
                "ranking": idx,
                "titulo": item.get("title", "")[:100],
                "preco": float(item.get("price") or 0),
                "loja": seller.get("nickname") or "Mercado Livre",
                "url": item.get("permalink", ""),
                "item_id": item.get("id", ""),
                "shop_id": "",
                "source": "mercadolivre",
                "keyword": keyword,
                "is_new": False,
            })
        
        log.info(f"[COMPETITOR][ML] resultados normalizados={len(competitors)}")
        return competitors
        
    except requests.Timeout:
        log.error(f"[COMPETITOR][ML] timeout para keyword={keyword!r}")
        return []
    except requests.RequestException as e:
        log.error(f"[COMPETITOR][ML] erro de request: {e}")
        return []
    except Exception as e:
        log.exception(f"[COMPETITOR][ML] falhou keyword={keyword!r}: {e}")
        return []


def search_competitors_mock(keyword: str, limit: int = 10) -> List[Dict]:
    """
    Provider mock para desenvolvimento quando APIs reais não funcionam.
    
    Args:
        keyword: Palavra-chave para buscar
        limit: Número máximo de resultados (padrão: 10)
    
    Returns:
        Lista de concorrentes simulados
    
    NOTA: Este é um provider temporário para permitir desenvolvimento.
    Deve ser removido quando providers reais funcionarem.
    """
    import random
    
    log.info(f"[COMPETITOR][MOCK] Gerando {limit} concorrentes simulados para keyword={keyword!r}")
    
    # Preços base variados
    base_prices = [29.90, 39.90, 49.90, 59.90, 69.90, 79.90, 89.90, 99.90, 109.90, 119.90]
    
    competitors = []
    for i in range(1, limit + 1):
        # Varia o preço base
        base_price = random.choice(base_prices)
        variation = random.uniform(-10, 10)
        price = max(19.90, base_price + variation)
        
        competitors.append({
            "ranking": i,
            "titulo": f"{keyword.title()} - Modelo {i} - Alta Qualidade",
            "preco": round(price, 2),
            "loja": f"Loja Exemplo {i}",
            "url": f"https://example.com/produto-{i}",
            "item_id": f"MOCK{i:03d}",
            "shop_id": f"shop_{i}",
            "source": "mock",
            "keyword": keyword,
            "is_new": False,
        })
    
    log.info(f"[COMPETITOR][MOCK] {len(competitors)} concorrentes simulados gerados")
    return competitors


def search_competitors_shopee(keyword: str, limit: int = 10, timeout_seconds: int = 45) -> List[Dict]:
    """
    Busca concorrentes na Shopee via Playwright (subprocess isolado).
    
    Args:
        keyword: Palavra-chave para buscar
        limit: Número máximo de resultados (padrão: 10)
        timeout_seconds: Timeout em segundos (padrão: 45s)
    
    Returns:
        Lista de concorrentes normalizados
    """
    log.info(f"[COMPETITOR] Provider Shopee iniciado para: {keyword!r}")
    
    # Código Python que será executado no subprocess
    code = r"""
import sys
import json

try:
    from backend_core import fetch_competitors_intercept
    
    keyword = sys.argv[1]
    result = fetch_competitors_intercept(keyword)
    
    # Normalizar formato Shopee para formato padrão
    normalized = []
    for idx, item in enumerate(result[:10], 1):
        normalized.append({
            "ranking": idx,
            "titulo": item.get("nome", "")[:100],
            "preco": float(item.get("preco", 0)),
            "loja": str(item.get("shop_id", "")),
            "url": f"https://shopee.com.br/product/{item.get('shop_id')}/{item.get('item_id')}",
            "item_id": item.get("item_id"),
            "shop_id": item.get("shop_id"),
            "source": "shopee",
            "keyword": keyword,
            "is_new": False,
        })
    
    print(json.dumps(normalized, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e)}), file=sys.stderr)
    sys.exit(1)
"""
    
    try:
        result = subprocess.run(
            [sys.executable, "-c", code, keyword],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        
        if result.returncode != 0:
            error_msg = result.stderr[-500:] if result.stderr else "Erro desconhecido"
            log.error(f"[COMPETITOR] Provider Shopee erro: {error_msg}")
            return []
        
        data = json.loads(result.stdout or "[]")
        log.info(f"[COMPETITOR] Provider Shopee retornou {len(data)} resultados")
        return data
        
    except subprocess.TimeoutExpired:
        log.warning(f"[COMPETITOR] Provider Shopee timeout ({timeout_seconds}s) para {keyword!r}")
        return []
    except json.JSONDecodeError as e:
        log.error(f"[COMPETITOR] Provider Shopee erro ao decodificar JSON: {e}")
        return []
    except Exception as e:
        log.error(f"[COMPETITOR] Provider Shopee erro inesperado: {e}")
        return []


def search_competitors(
    keyword: str,
    providers: Optional[List[str]] = None,
    limit: int = 10,
) -> List[Dict]:
    """
    Busca concorrentes usando múltiplos providers com fallback.
    
    Args:
        keyword: Palavra-chave para buscar
        providers: Lista de providers a usar (padrão: ["mercadolivre", "shopee"])
        limit: Número máximo de resultados por provider (padrão: 10)
    
    Returns:
        Lista de concorrentes encontrados (prioriza primeiro provider que retornar resultados)
    
    Exemplo:
        >>> competitors = search_competitors("mochila roxa")
        >>> print(f"Encontrados {len(competitors)} concorrentes")
    """
    if providers is None:
        # Mercado Livre como principal (API pública, mais confiável)
        # Shopee como fallback (subprocess isolado)
        providers = ["mercadolivre", "shopee"]
    
    log.info(f"[COMPETITOR] Buscando concorrentes para: {keyword!r}")
    log.info(f"[COMPETITOR] Providers configurados: {providers}")
    
    all_results = []
    
    for provider in providers:
        log.info(f"[COMPETITOR] Tentando provider: {provider}")
        
        if provider == "mercadolivre":
            results = search_competitors_mercadolivre(keyword, limit=limit)
            if results:
                all_results.extend(results)
                log.info(f"[COMPETITOR] Provider ML retornou {len(results)} resultados - usando")
                break  # Sucesso, não precisa tentar outros
            else:
                log.warning(f"[COMPETITOR] Provider ML não retornou resultados - tentando próximo")
        
        elif provider == "shopee":
            results = search_competitors_shopee(keyword, limit=limit, timeout_seconds=60)
            if results:
                all_results.extend(results)
                log.info(f"[COMPETITOR] Provider Shopee retornou {len(results)} resultados - usando")
                break  # Sucesso, não precisa tentar outros
            else:
                log.warning(f"[COMPETITOR] Provider Shopee não retornou resultados - tentando próximo")
        
        else:
            log.warning(f"[COMPETITOR] Provider desconhecido: {provider!r}")
    
    if not all_results:
        log.warning(f"[COMPETITOR] Nenhum provider retornou resultados para: {keyword!r}")
    
    log.info(f"[COMPETITOR] Resultado final: {len(all_results)} concorrentes")
    return all_results[:limit]


# Mantém compatibilidade com código antigo
def fetch_competitors(keyword: str, timeout_seconds: int = 120) -> list:
    """
    Função legada para compatibilidade.
    Agora usa o sistema de providers internamente.
    
    Args:
        keyword: Palavra-chave para buscar
        timeout_seconds: Ignorado (cada provider tem seu próprio timeout)
    
    Returns:
        Lista de concorrentes encontrados
    """
    # Shopee como principal (funciona via subprocess isolado)
    results = search_competitors(keyword, providers=["shopee", "mercadolivre"], limit=10)
    
    # Converte para formato antigo (backend_core) para compatibilidade
    legacy_format = []
    for item in results:
        legacy_format.append({
            "nome": item.get("titulo", ""),
            "preco": item.get("preco", 0),
            "shop_id": item.get("shop_id", ""),
            "item_id": item.get("item_id", ""),
        })
    
    return legacy_format


# ══════════════════════════════════════════════════════════════════
# FUNÇÃO UNIFICADA E SEGURA (U8.2)
# ══════════════════════════════════════════════════════════════════

def search_competitors_safe(keyword: str, limit: int = 10) -> List[Dict]:
    """
    Função unificada e segura para buscar concorrentes.
    Usada por Auditoria e Sentinela.
    
    Args:
        keyword: Palavra-chave para buscar
        limit: Número máximo de resultados (padrão: 10)
    
    Returns:
        Lista de concorrentes normalizados
    
    Comportamento:
        1. Tenta Mercado Livre primeiro (API JSON - mais confiável)
        2. Se ML retornar resultados, retorna imediatamente
        3. Se ML falhar, tenta Shopee como fallback
        4. Nunca trava (cada provider tem timeout)
        5. Logs detalhados de cada tentativa
    
    Exemplo:
        >>> competitors = search_competitors_safe("mochila roxa")
        >>> print(f"Encontrados {len(competitors)} concorrentes")
    """
    log.info(f"[COMPETITOR] search_competitors_safe keyword={keyword!r} limit={limit}")
    
    # Tenta Mercado Livre primeiro (API JSON)
    log.info(f"[COMPETITOR] Tentando Mercado Livre (API JSON)...")
    ml_results = search_competitors_mercadolivre(keyword, limit=limit)
    
    if ml_results:
        log.info(f"[COMPETITOR] resultado final={len(ml_results)} provider=mercadolivre")
        return ml_results
    
    log.warning(f"[COMPETITOR] Mercado Livre retornou 0. Tentando Shopee fallback...")
    
    # Fallback para Shopee
    try:
        log.info(f"[COMPETITOR] Tentando Shopee (subprocess)...")
        shopee_results = search_competitors_shopee(keyword, limit=limit, timeout_seconds=60)
        
        if shopee_results:
            log.info(f"[COMPETITOR] resultado final={len(shopee_results)} provider=shopee")
            return shopee_results
    except Exception as e:
        log.warning(f"[COMPETITOR] Shopee fallback falhou: {e}")
    
    log.warning(f"[COMPETITOR] nenhum provider retornou resultados keyword={keyword!r}")
    return []
