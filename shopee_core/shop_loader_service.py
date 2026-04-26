"""
shopee_core/shop_loader_service.py — Carregador Robusto de Lojas Shopee
========================================================================
Serviço unificado para carregar informações de lojas e produtos.
Usado tanto pela Auditoria quanto pelo Sentinela.

Estratégia:
1. Tentar intercept via Playwright (método principal)
2. Se falhar, usar APIs diretas da Shopee (fallback)
3. Normalizar formato de retorno
"""

from __future__ import annotations

import logging
import time
from typing import Optional

log = logging.getLogger("shop_loader")


def load_shop_with_fallback(shop_url: str) -> dict:
    """
    Carrega loja com fallback robusto.
    
    Returns:
        {
            "ok": bool,
            "message": str,
            "data": {
                "username": str,
                "shop": dict,
                "products": list[dict],
                "method_used": str  # "intercept" ou "fallback"
            }
        }
    """
    log.info(f"[SHOP] Carregando loja: {shop_url}")
    
    # Primeiro tenta o método padrão (intercept)
    from shopee_core.audit_service import load_shop_from_url
    
    result = load_shop_from_url(shop_url)
    
    if not result.get("ok"):
        return result
    
    data = result["data"]
    products = data.get("products", [])
    username = data.get("username", "")
    shop_data = data.get("shop", {})
    shopid = shop_data.get("shopid") or shop_data.get("shop_id")
    
    log.info(f"[SHOP] Intercept result: username={username}, products={len(products)}")
    
    # Se conseguiu produtos via intercept, retorna sucesso
    if products:
        data["method_used"] = "intercept"
        return {
            "ok": True,
            "message": f"Loja '{username}' carregada com {len(products)} produto(s) via intercept.",
            "data": data,
        }
    
    # Se não conseguiu produtos, tenta fallback
    log.warning(f"[SHOP] Intercept retornou 0 produtos. Tentando fallback para {username}")
    
    if not shopid:
        return {
            "ok": False,
            "message": f"Loja '{username}' encontrada, mas não consegui obter shopid para fallback.",
            "data": data,
        }
    
    # Tenta fallback via API direta
    fallback_products = fetch_products_fallback(username, str(shopid))
    
    if fallback_products:
        log.info(f"[SHOP] Fallback success: {len(fallback_products)} produtos")
        data["products"] = fallback_products
        data["method_used"] = "fallback"
        return {
            "ok": True,
            "message": f"Loja '{username}' carregada com {len(fallback_products)} produto(s) via fallback.",
            "data": data,
        }
    
    # Ambos falharam
    log.error(f"[SHOP] Tanto intercept quanto fallback falharam para {username}")
    return {
        "ok": False,
        "message": (
            f"Encontrei a loja '{username}', mas a Shopee não retornou produtos agora.\n"
            "Isso pode ser instabilidade da Shopee ou bloqueio temporário.\n"
            "Tente novamente em alguns minutos."
        ),
        "data": data,
    }


def fetch_products_fallback(username: str, shopid: str) -> list[dict]:
    """
    Fallback robusto para buscar produtos via APIs diretas da Shopee.
    
    Tenta múltiplos endpoints em ordem de prioridade:
    1. /api/v4/search/search_items com match_id
    2. /api/v4/shop/get_shop_items com shopid
    
    Returns:
        Lista de produtos no formato normalizado
    """
    log.info(f"[FALLBACK] Tentando APIs diretas: username={username}, shopid={shopid}")
    
    # Tenta método 1: search_items com match_id
    products = _fetch_via_search_items(shopid)
    if products:
        log.info(f"[FALLBACK] search_items success: {len(products)} produtos")
        return products
    
    # Tenta método 2: get_shop_items
    products = _fetch_via_get_shop_items(shopid)
    if products:
        log.info(f"[FALLBACK] get_shop_items success: {len(products)} produtos")
        return products
    
    log.warning(f"[FALLBACK] Todos os métodos falharam para shopid={shopid}")
    return []


def _fetch_via_search_items(shopid: str) -> list[dict]:
    """Tenta buscar produtos via /api/v4/search/search_items."""
    try:
        # Usa curl_cffi se disponível, senão requests normal
        try:
            from curl_cffi import requests as stealth_requests
            session = stealth_requests.Session(impersonate="chrome124")
            log.info("[FALLBACK] Usando curl_cffi para search_items")
        except ImportError:
            import requests
            session = requests.Session()
            log.info("[FALLBACK] Usando requests padrão para search_items")
        
        url = "https://shopee.com.br/api/v4/search/search_items"
        params = {
            "by": "sales",
            "limit": 30,
            "match_id": shopid,
            "newest": 0,
            "order": "desc",
            "keyword": "",
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://shopee.com.br/",
            "Accept": "application/json",
        }
        
        log.info(f"[FALLBACK] GET {url} params={params}")
        response = session.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            log.warning(f"[FALLBACK] search_items HTTP {response.status_code}")
            return []
        
        data = response.json()
        items = data.get("items", [])
        
        log.info(f"[FALLBACK] search_items raw items: {len(items)}")
        
        # Normaliza formato
        products = []
        for item in items:
            item_basic = item.get("item_basic", {})
            if not item_basic:
                continue
            
            product = {
                "itemid": item_basic.get("itemid"),
                "shopid": item_basic.get("shopid"),
                "name": item_basic.get("name", ""),
                "price": item_basic.get("price", 0) / 100000 if item_basic.get("price") else 0,  # Shopee usa preço * 100000
                "sold": item_basic.get("sold", 0),
                "image": item_basic.get("image", ""),
                "item_rating": item_basic.get("item_rating", {}),
            }
            
            # Filtra produtos válidos
            if product["itemid"] and product["name"]:
                products.append(product)
        
        log.info(f"[FALLBACK] search_items normalized: {len(products)} produtos")
        return products
        
    except Exception as e:
        log.error(f"[FALLBACK] Erro em search_items: {e}")
        return []


def _fetch_via_get_shop_items(shopid: str) -> list[dict]:
    """Tenta buscar produtos via /api/v4/shop/get_shop_items."""
    try:
        # Usa curl_cffi se disponível, senão requests normal
        try:
            from curl_cffi import requests as stealth_requests
            session = stealth_requests.Session(impersonate="chrome124")
            log.info("[FALLBACK] Usando curl_cffi para get_shop_items")
        except ImportError:
            import requests
            session = requests.Session()
            log.info("[FALLBACK] Usando requests padrão para get_shop_items")
        
        url = "https://shopee.com.br/api/v4/shop/get_shop_items"
        params = {
            "shopid": shopid,
            "limit": 30,
            "offset": 0,
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": f"https://shopee.com.br/shop/{shopid}",
            "Accept": "application/json",
        }
        
        log.info(f"[FALLBACK] GET {url} params={params}")
        response = session.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            log.warning(f"[FALLBACK] get_shop_items HTTP {response.status_code}")
            return []
        
        data = response.json()
        items = data.get("data", {}).get("item", [])
        
        log.info(f"[FALLBACK] get_shop_items raw items: {len(items)}")
        
        # Normaliza formato
        products = []
        for item in items:
            product = {
                "itemid": item.get("itemid"),
                "shopid": item.get("shopid"),
                "name": item.get("name", ""),
                "price": item.get("price", 0) / 100000 if item.get("price") else 0,  # Shopee usa preço * 100000
                "sold": item.get("sold", 0),
                "image": item.get("image", ""),
                "item_rating": item.get("item_rating", {}),
            }
            
            # Filtra produtos válidos
            if product["itemid"] and product["name"]:
                products.append(product)
        
        log.info(f"[FALLBACK] get_shop_items normalized: {len(products)} produtos")
        return products
        
    except Exception as e:
        log.error(f"[FALLBACK] Erro em get_shop_items: {e}")
        return []


def extract_shop_id_from_data(shop_data: dict) -> Optional[str]:
    """Extrai shopid dos dados da loja."""
    return shop_data.get("shopid") or shop_data.get("shop_id") or shop_data.get("userid")