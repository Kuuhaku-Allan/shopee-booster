import sqlite3
from datetime import datetime
import os

DB_PATH = "data/sentinela.db"

def init_db():
    if not os.path.exists("data"):
        os.makedirs("data")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabela para as keywords do seu nicho
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keywords_monitoradas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE,
            ativa INTEGER DEFAULT 1
        )
    ''')
    
    # Tabela de histórico (Onde o "sentinela" vê as mudanças)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico_precos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT,
            shop_id TEXT,
            nome_produto TEXT,
            preco REAL,
            ranking INTEGER,
            data_verificacao DATETIME
        )
    ''')

    # Configurações do Telegram e da Sentinela
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config_sentinela (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def salvar_config(chave, valor):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO config_sentinela (chave, valor) VALUES (?, ?)", (chave, str(valor)))
    conn.commit()
    conn.close()

def obter_config(chave):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM config_sentinela WHERE chave = ?", (chave,))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else None
    except Exception:
        return None

def adicionar_keyword(keyword: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO keywords_monitoradas (keyword) VALUES (?)", (keyword.strip().lower(),))
    conn.commit()
    conn.close()

def listar_keywords() -> list:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT keyword FROM keywords_monitoradas WHERE ativa = 1")
        res = cursor.fetchall()
        conn.close()
        return [r[0] for r in res]
    except Exception:
        return []

def remover_keyword(keyword: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM keywords_monitoradas WHERE keyword = ?", (keyword.strip().lower(),))
    conn.commit()
    conn.close()

def salvar_historico(item_id, shop_id, nome_produto, preco, ranking):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO historico_precos (item_id, shop_id, nome_produto, preco, ranking, data_verificacao)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (item_id, shop_id, nome_produto, preco, ranking, datetime.now()))
    conn.commit()
    conn.close()
