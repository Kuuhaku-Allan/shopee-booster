"""
shopee_core/catalog_service.py — Serviço de Catálogo de Produtos
=================================================================
Gerencia importação, cache e recuperação de catálogos de produtos.

Fontes suportadas:
- Exportação XLSX/CSV da Shopee Seller Center
- Cache local de produtos
- Scraping público (fallback)

Fluxo:
1. Tenta scraping público
2. Se falhar, usa catálogo cacheado
3. Se não houver cache, solicita importação
4. Salva catálogo importado para uso futuro
"""

from __future__ import annotations

import logging
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import pandas as pd

log = logging.getLogger("catalog_service")

# Mapeamento de colunas possíveis da exportação da Shopee
COLUMN_MAPPINGS = {
    "name": [
        "Product Name", "Nome do Produto", "Nome", "name", 
        "product_name", "titulo", "título", "title"
    ],
    "price": [
        "Price", "Preço", "price", "valor", "preco"
    ],
    "stock": [
        "Stock", "Estoque", "stock", "quantity", "quantidade"
    ],
    "sku": [
        "SKU", "sku", "Código", "codigo", "code"
    ],
    "itemid": [
        "Item ID", "ID do Produto", "itemid", "item_id", 
        "product_id", "id"
    ],
    "image": [
        "Image", "Imagem", "image", "foto", "photo", "img"
    ],
    "status": [
        "Status", "status", "Estado", "state"
    ],
}


def get_catalog_db_path() -> Path:
    """Retorna o caminho do banco de dados de catálogo"""
    db_path = Path("data/catalog_cache.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def init_catalog_db():
    """Inicializa o banco de dados de catálogo"""
    db_path = get_catalog_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_catalog_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            shop_url TEXT,
            username TEXT,
            source TEXT NOT NULL,
            products_json TEXT NOT NULL,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            UNIQUE(user_id, shop_url)
        )
    """)
    
    conn.commit()
    conn.close()
    log.info("[CATALOG] Banco de dados inicializado")


def normalize_column_name(df: pd.DataFrame, field: str) -> Optional[str]:
    """
    Encontra a coluna correspondente no DataFrame baseado em nomes possíveis.
    
    Args:
        df: DataFrame com os dados
        field: Campo a buscar (name, price, stock, etc.)
    
    Returns:
        Nome da coluna encontrada ou None
    """
    possible_names = COLUMN_MAPPINGS.get(field, [])
    
    for col in df.columns:
        col_lower = str(col).lower().strip()
        for possible in possible_names:
            if possible.lower() in col_lower or col_lower in possible.lower():
                return col
    
    return None


def load_products_from_file(file_path: str) -> list[dict]:
    """
    Carrega produtos de arquivo XLSX ou CSV.
    
    Args:
        file_path: Caminho do arquivo
    
    Returns:
        Lista de produtos normalizados
    """
    log.info(f"[CATALOG] Carregando arquivo: {file_path}")
    
    try:
        # Detecta tipo de arquivo
        if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
            df = pd.read_excel(file_path)
        elif file_path.endswith('.csv'):
            # Tenta diferentes encodings
            for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("Não foi possível detectar o encoding do CSV")
        else:
            raise ValueError(f"Formato de arquivo não suportado: {file_path}")
        
        log.info(f"[CATALOG] Arquivo carregado: {len(df)} linhas, {len(df.columns)} colunas")
        log.info(f"[CATALOG] Colunas encontradas: {list(df.columns)}")
        
        # Normaliza produtos
        products = []
        for idx, row in df.iterrows():
            product = normalize_product_row(df, row)
            if product and product.get("name"):  # Pelo menos o nome é obrigatório
                products.append(product)
        
        log.info(f"[CATALOG] {len(products)} produtos válidos extraídos")
        return products
        
    except Exception as e:
        log.error(f"[CATALOG] Erro ao carregar arquivo: {e}")
        raise


def normalize_product_row(df: pd.DataFrame, row: pd.Series) -> dict:
    """
    Normaliza uma linha do DataFrame para o formato padrão de produto.
    
    Args:
        df: DataFrame completo (para acessar nomes de colunas)
        row: Linha a normalizar
    
    Returns:
        Dicionário com produto normalizado
    """
    product = {
        "source": "import",
        "itemid": None,
        "shopid": None,
        "name": "",
        "price": 0.0,
        "stock": 0,
        "sku": "",
        "image": "",
        "status": "active",
    }
    
    # Mapeia cada campo
    for field, _ in COLUMN_MAPPINGS.items():
        col_name = normalize_column_name(df, field)
        if col_name and col_name in row.index:
            value = row[col_name]
            
            # Trata valores nulos
            if pd.isna(value):
                continue
            
            # Converte tipos
            if field == "price":
                try:
                    product[field] = float(str(value).replace(",", ".").replace("R$", "").strip())
                except:
                    product[field] = 0.0
            elif field == "stock":
                try:
                    product[field] = int(value)
                except:
                    product[field] = 0
            else:
                product[field] = str(value).strip()
    
    return product


def save_catalog(
    user_id: str,
    products: list[dict],
    shop_url: str = None,
    username: str = None,
    source: str = "import",
    expires_days: int = 30
) -> bool:
    """
    Salva catálogo de produtos no cache.
    
    Args:
        user_id: ID do usuário (telefone no WhatsApp, ou "desktop" no .exe)
        products: Lista de produtos
        shop_url: URL da loja (opcional)
        username: Username da loja (opcional)
        source: Fonte dos dados (import, scraping, etc.)
        expires_days: Dias até expiração do cache
    
    Returns:
        True se salvou com sucesso
    """
    init_catalog_db()
    
    try:
        db_path = get_catalog_db_path()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        products_json = json.dumps(products, ensure_ascii=False)
        now = datetime.now()
        expires_at = now + timedelta(days=expires_days)
        
        cursor.execute("""
            INSERT INTO shop_catalog_cache 
            (user_id, shop_url, username, source, products_json, imported_at, updated_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, shop_url) DO UPDATE SET
                username = excluded.username,
                source = excluded.source,
                products_json = excluded.products_json,
                updated_at = excluded.updated_at,
                expires_at = excluded.expires_at
        """, (user_id, shop_url, username, source, products_json, now, now, expires_at))
        
        conn.commit()
        conn.close()
        
        log.info(f"[CATALOG] Catálogo salvo: user={user_id}, products={len(products)}, source={source}")
        return True
        
    except Exception as e:
        log.error(f"[CATALOG] Erro ao salvar catálogo: {e}")
        return False


def get_catalog(user_id: str, shop_url: str = None) -> Optional[dict]:
    """
    Recupera catálogo do cache.
    
    Args:
        user_id: ID do usuário
        shop_url: URL da loja (opcional, se None busca qualquer catálogo do usuário)
    
    Returns:
        Dict com dados do catálogo ou None
    """
    init_catalog_db()
    
    try:
        db_path = get_catalog_db_path()
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        now = datetime.now()
        
        if shop_url:
            cursor.execute("""
                SELECT * FROM shop_catalog_cache
                WHERE user_id = ? AND shop_url = ?
                AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY updated_at DESC
                LIMIT 1
            """, (user_id, shop_url, now))
        else:
            cursor.execute("""
                SELECT * FROM shop_catalog_cache
                WHERE user_id = ?
                AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY updated_at DESC
                LIMIT 1
            """, (user_id, now))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            log.info(f"[CATALOG] Nenhum catálogo encontrado: user={user_id}, shop_url={shop_url}")
            return None
        
        products = json.loads(row["products_json"])
        
        result = {
            "user_id": row["user_id"],
            "shop_url": row["shop_url"],
            "username": row["username"],
            "source": row["source"],
            "products": products,
            "imported_at": row["imported_at"],
            "updated_at": row["updated_at"],
        }
        
        log.info(f"[CATALOG] Catálogo recuperado: user={user_id}, products={len(products)}")
        return result
        
    except Exception as e:
        log.error(f"[CATALOG] Erro ao recuperar catálogo: {e}")
        return None


def list_catalog_products(user_id: str, shop_url: str = None) -> list[dict]:
    """
    Lista produtos do catálogo.
    
    Args:
        user_id: ID do usuário
        shop_url: URL da loja (opcional)
    
    Returns:
        Lista de produtos
    """
    catalog = get_catalog(user_id, shop_url)
    return catalog["products"] if catalog else []


def delete_catalog(user_id: str, shop_url: str = None) -> bool:
    """
    Remove catálogo do cache.
    
    Args:
        user_id: ID do usuário
        shop_url: URL da loja (opcional, se None remove todos do usuário)
    
    Returns:
        True se removeu com sucesso
    """
    init_catalog_db()
    
    try:
        db_path = get_catalog_db_path()
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        if shop_url:
            cursor.execute("""
                DELETE FROM shop_catalog_cache
                WHERE user_id = ? AND shop_url = ?
            """, (user_id, shop_url))
        else:
            cursor.execute("""
                DELETE FROM shop_catalog_cache
                WHERE user_id = ?
            """, (user_id,))
        
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        
        log.info(f"[CATALOG] {deleted} catálogo(s) removido(s)")
        return deleted > 0
        
    except Exception as e:
        log.error(f"[CATALOG] Erro ao remover catálogo: {e}")
        return False


def import_shopee_export(file_path: str, user_id: str, shop_url: str = None, username: str = None) -> dict:
    """
    Importa exportação da Shopee e salva no cache.
    
    Args:
        file_path: Caminho do arquivo XLSX/CSV
        user_id: ID do usuário
        shop_url: URL da loja (opcional)
        username: Username da loja (opcional)
    
    Returns:
        Dict com resultado da importação
    """
    try:
        products = load_products_from_file(file_path)
        
        if not products:
            return {
                "ok": False,
                "message": "Nenhum produto válido encontrado no arquivo.",
                "products": []
            }
        
        # Salva no cache
        saved = save_catalog(
            user_id=user_id,
            products=products,
            shop_url=shop_url,
            username=username,
            source="import"
        )
        
        if not saved:
            return {
                "ok": False,
                "message": "Erro ao salvar catálogo no cache.",
                "products": products
            }
        
        return {
            "ok": True,
            "message": f"✓ {len(products)} produto(s) importado(s) com sucesso!",
            "products": products
        }
        
    except Exception as e:
        log.error(f"[CATALOG] Erro na importação: {e}")
        return {
            "ok": False,
            "message": f"Erro ao importar arquivo: {str(e)}",
            "products": []
        }
