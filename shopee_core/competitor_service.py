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
    Busca concorrentes no Mercado Livre via scraping do HTML.
    
    Args:
        keyword: Palavra-chave para buscar
        limit: Número máximo de resultados (padrão: 10)
    
    Returns:
        Lista de concorrentes normalizados
    """
    log.info(f"[COMPETITOR] Provider ML iniciado para: {keyword!r}")
    
    try:
        from bs4 import BeautifulSoup
        import re
        
        # URL de busca do Mercado Livre
        keyword_encoded = keyword.replace(" ", "-")
        url = f"https://lista.mercadolivre.com.br/{keyword_encoded}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Encontra os itens de produto
        items = soup.find_all('li', class_='ui-search-layout__item')
        
        competitors = []
        for idx, item in enumerate(items[:limit], 1):
            try:
                # Título
                title_elem = item.find('h2', class_='ui-search-item__title')
                titulo = title_elem.get_text(strip=True) if title_elem else ""
                
                # Preço
                price_elem = item.find('span', class_='andes-money-amount__fraction')
                preco_str = price_elem.get_text(strip=True) if price_elem else "0"
                preco_str = preco_str.replace(".", "").replace(",", ".")
                preco = float(preco_str) if preco_str else 0.0
                
                # URL
                link_elem = item.find('a', class_='ui-search-link')
                url_produto = link_elem.get('href', '') if link_elem else ""
                
                # Extrai item_id da URL
                item_id = ""
                if url_produto:
                    match = re.search(r'MLB-?(\d+)', url_produto)
                    if match:
                        item_id = f"MLB{match.group(1)}"
                
                if titulo and preco > 0:
                    competitors.append({
                        "ranking": idx,
                        "titulo": titulo[:100],
                        "preco": preco,
                        "loja": "Mercado Livre",
                        "url": url_produto,
                        "item_id": item_id,
                        "shop_id": "",
                        "source": "mercadolivre",
                        "keyword": keyword,
                        "is_new": False,
                    })
            except Exception as e:
                log.debug(f"[COMPETITOR] Erro ao parsear item ML: {e}")
                continue
        
        log.info(f"[COMPETITOR] Provider ML retornou {len(competitors)} resultados")
        return competitors
        
    except ImportError:
        log.error(f"[COMPETITOR] Provider ML requer beautifulsoup4: pip install beautifulsoup4")
        return []
    except requests.Timeout:
        log.error(f"[COMPETITOR] Provider ML timeout para {keyword!r}")
        return []
    except requests.RequestException as e:
        log.error(f"[COMPETITOR] Provider ML erro: {e}")
        return []
    except Exception as e:
        log.error(f"[COMPETITOR] Provider ML erro inesperado: {e}")
        return []


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
        1. Tenta Mercado Livre primeiro (mais confiável)
        2. Se ML retornar resultados, retorna imediatamente
        3. Se ML falhar, tenta Shopee como fallback
        4. Nunca trava (cada provider tem timeout)
        5. Logs detalhados de cada tentativa
    
    Exemplo:
        >>> competitors = search_competitors_safe("mochila roxa")
        >>> print(f"Encontrados {len(competitors)} concorrentes")
    """
    log.info(f"[COMPETITOR] search_competitors_safe: keyword={keyword!r}, limit={limit}")
    
    # Tenta Mercado Livre primeiro
    log.info(f"[COMPETITOR] Tentando ML...")
    ml_results = search_competitors_mercadolivre(keyword, limit=limit)
    
    if ml_results:
        log.info(f"[COMPETITOR] ML retornou {len(ml_results)} resultados - usando")
        return ml_results[:limit]
    
    log.warning(f"[COMPETITOR] ML não retornou resultados - tentando Shopee")
    
    # Fallback para Shopee
    log.info(f"[COMPETITOR] Tentando Shopee...")
    shopee_results = search_competitors_shopee(keyword, limit=limit, timeout_seconds=60)
    
    if shopee_results:
        log.info(f"[COMPETITOR] Shopee retornou {len(shopee_results)} resultados - usando")
        return shopee_results[:limit]
    
    log.error(f"[COMPETITOR] Nenhum provider retornou resultados para: {keyword!r}")
    return []
