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
    ''', (str(item_id), str(shop_id), str(nome_produto), float(preco), int(ranking), datetime.now()))
    conn.commit()
    conn.close()

def _obter_preco_anterior(item_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT preco FROM historico_precos WHERE item_id = ? ORDER BY data_verificacao DESC LIMIT 1", (str(item_id),))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else None
    except Exception:
        return None

def processar_mudancas_e_alertar(keyword: str, resultados: list, telegram):
    # Percorre o top e processa mudancas
    from telegram_service import TelegramSentinela
    
    for i, p in enumerate(resultados):
        item_id = str(p.get("item_id", ""))
        nome = p.get("nome", "")
        preco_novo = float(p.get("preco", 0))
        ranking_atual = i + 1

        if not item_id: continue
        
        preco_antigo = _obter_preco_anterior(item_id)
        
        if preco_antigo is None:
            # Produto novo aparecendo pela primeira vez no nosso radar
            if ranking_atual <= 10:
                msg = TelegramSentinela.formatar_novo_concorrente(nome, preco_novo, ranking_atual)
                telegram.enviar_alerta(msg)
        else:
            # Produto existente, calcular mudanca
            diferenca = abs(preco_novo - preco_antigo)
            if preco_antigo > 0:
                porcentagem = (diferenca / preco_antigo) * 100
                if porcentagem >= 5.0: # SO AVISAR SE MUDOU MAIS DE 5% (Filtro Anti-Spam)
                    msg = TelegramSentinela.formatar_mudanca_preco(nome, preco_antigo, preco_novo)
                    telegram.enviar_alerta(msg)
        
        # Salva o novo snapshot (ou o repetido, para contabilizarmos ranking das lojas depois)
        salvar_historico(item_id, p.get("shop_id", ""), nome, preco_novo, ranking_atual)

def gerar_ranking_lojas_nicho():
    """Agrega os dados para criar o Rank das 100 melhores lojas do nicho."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT shop_id, COUNT(*) as forca_nicho, AVG(preco) as preco_medio
            FROM historico_precos
            GROUP BY shop_id
            ORDER BY forca_nicho DESC
            LIMIT 100
        ''')
        ranking = cursor.fetchall()
        conn.close()
        return ranking
    except Exception:
        return []

def obter_ultimo_preco(item_id):
    """Busca o preço da última verificação para comparar (o 'Diff')."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT preco FROM historico_precos WHERE item_id = ? ORDER BY data_verificacao DESC LIMIT 1", (str(item_id),))
        res = cursor.fetchone()
        conn.close()
        return res[0] if res else None
    except Exception:
        return None
