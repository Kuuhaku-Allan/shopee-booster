import sqlite3
from datetime import datetime, timedelta
import os
import sys

# ══════════════════════════════════════════════════════════════
# RUNTIME_DIR — pasta persistente única para TODOS os módulos
# ══════════════════════════════════════════════════════════════
# Regra:
#   • .exe  → pasta onde o ShopeeBooster.exe está instalado
#   • dev   → pasta do projeto (onde este arquivo está)
#
# ATENÇÃO: launcher.py, sentinela_db.py e app.py devem usar
# este módulo para resolver caminhos — nunca calcular sozinhos.
# ══════════════════════════════════════════════════════════════

if getattr(sys, "frozen", False):
    RUNTIME_DIR = os.path.dirname(sys.executable)
else:
    RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH           = os.path.join(RUNTIME_DIR, "data", "sentinela.db")
SENTINELA_LOG_PATH = os.path.join(RUNTIME_DIR, "sentinela_log.txt")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    # Migration: se houver um DB legado na pasta antiga do projeto
    # e o DB atual estiver vazio ou não existir, copia.
    legacy_db_path = os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
        "data", "sentinela.db"
    )
    if getattr(sys, "frozen", False):
        try:
            if os.path.exists(legacy_db_path) and (not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0):
                import shutil
                shutil.copy2(legacy_db_path, DB_PATH)
        except Exception:
            pass

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS keywords_monitoradas (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE,
            ativa   INTEGER DEFAULT 1
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historico_precos (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id           TEXT,
            shop_id           TEXT,
            nome_produto      TEXT,
            preco             REAL,
            ranking           INTEGER,
            data_verificacao  DATETIME
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS config_sentinela (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')

    conn.commit()
    conn.close()


# ── CRUD configurações ────────────────────────────────────────

def salvar_config(chave, valor):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO config_sentinela (chave, valor) VALUES (?, ?)",
                 (chave, str(valor)))
    conn.commit()
    conn.close()


def obter_config(chave):
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute("SELECT valor FROM config_sentinela WHERE chave = ?", (chave,)).fetchone()
        conn.close()
        return res[0] if res else None
    except Exception:
        return None


def configurar_loja_mestre(url_loja: str):
    salvar_config("minha_loja_url", url_loja.strip())


def obter_loja_mestra() -> str | None:
    return obter_config("minha_loja_url")


# ── CRUD keywords ─────────────────────────────────────────────

def adicionar_keyword(keyword: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO keywords_monitoradas (keyword) VALUES (?)",
                 (keyword.strip().lower(),))
    conn.commit()
    conn.close()


def listar_keywords() -> list:
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT keyword FROM keywords_monitoradas WHERE ativa = 1").fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def remover_keyword(keyword: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM keywords_monitoradas WHERE keyword = ?",
                 (keyword.strip().lower(),))
    conn.commit()
    conn.close()


# ── CRUD histórico ────────────────────────────────────────────

def salvar_historico(item_id, shop_id, nome_produto, preco, ranking):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        INSERT INTO historico_precos
            (item_id, shop_id, nome_produto, preco, ranking, data_verificacao)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (str(item_id), str(shop_id), str(nome_produto),
          float(preco), int(ranking), datetime.now()))
    conn.commit()
    conn.close()


def _obter_preco_anterior(item_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute(
            "SELECT preco FROM historico_precos WHERE item_id = ? ORDER BY data_verificacao DESC LIMIT 1",
            (str(item_id),)
        ).fetchone()
        conn.close()
        return res[0] if res else None
    except Exception:
        return None


def obter_ultimo_preco(item_id):
    return _obter_preco_anterior(item_id)


# ── Processamento de alertas ──────────────────────────────────

def processar_mudancas_e_alertar(keyword: str, resultados: list, telegram):
    from telegram_service import TelegramSentinela

    for i, p in enumerate(resultados):
        item_id       = str(p.get("item_id", ""))
        nome          = p.get("nome", "")
        preco_novo    = float(p.get("preco", 0))
        ranking_atual = i + 1

        if not item_id:
            continue

        preco_antigo = _obter_preco_anterior(item_id)

        if preco_antigo is None:
            if ranking_atual <= 10:
                msg = TelegramSentinela.formatar_novo_concorrente(nome, preco_novo, ranking_atual)
                telegram.enviar_alerta(msg)
        else:
            diferenca = abs(preco_novo - preco_antigo)
            if preco_antigo > 0:
                porcentagem = (diferenca / preco_antigo) * 100
                if porcentagem >= 5.0:
                    msg = TelegramSentinela.formatar_mudanca_preco(nome, preco_antigo, preco_novo)
                    telegram.enviar_alerta(msg)

        salvar_historico(item_id, p.get("shop_id", ""), nome, preco_novo, ranking_atual)


# ── Ranking e tendência ───────────────────────────────────────

def gerar_ranking_lojas_nicho():
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT shop_id,
                   COUNT(*)    AS presencas,
                   AVG(preco)  AS preco_medio,
                   MIN(ranking) AS melhor_posicao,
                   MAX(ranking) AS pior_posicao
            FROM historico_precos
            GROUP BY shop_id
            ORDER BY presencas DESC, melhor_posicao ASC
            LIMIT 100
        ''')
        ranking = cursor.fetchall()

        agora         = datetime.now()
        vinte_quatroh = agora - timedelta(hours=24)

        resultado = []
        for shop_id, presencas, preco_medio, melhor_pos, pior_pos in ranking:
            cursor.execute('''
                SELECT AVG(preco) FROM historico_precos
                WHERE shop_id = ? AND data_verificacao >= ?
            ''', (str(shop_id), vinte_quatroh.isoformat()))
            res_rec      = cursor.fetchone()
            preco_recente = res_rec[0] if (res_rec and res_rec[0] is not None) else None

            if preco_recente is not None and preco_medio > 0:
                diff_pct = ((preco_recente - preco_medio) / preco_medio) * 100
                tendencia = "SUBINDO" if diff_pct > 2 else ("Caindo" if diff_pct < -2 else "ESTÁVEL")
            else:
                tendencia = "— dados insuficientes —"

            resultado.append({
                "shop_id":        shop_id,
                "presencas":      presencas,
                "preco_medio":    round(preco_medio, 2),
                "melhor_posicao": melhor_pos,
                "pior_posicao":   pior_pos,
                "preco_recente":  round(preco_recente, 2) if preco_recente is not None else None,
                "tendencia":      tendencia,
            })

        conn.close()
        return resultado
    except Exception:
        return []


def gerar_tendencia_precos_nicho(dias: int = 7):
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        limite = datetime.now() - timedelta(days=dias)
        cursor.execute('''
            SELECT DATE(data_verificacao) AS dia, AVG(preco) AS preco_medio
            FROM historico_precos
            WHERE data_verificacao >= ?
            GROUP BY DATE(data_verificacao)
            ORDER BY dia ASC
        ''', (limite.isoformat(),))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception:
        return []


# ── Diagnóstico ───────────────────────────────────────────────

def get_diagnostics() -> dict:
    """
    Retorna informações de diagnóstico para o painel da UI.
    Nunca levanta exceção — retorna valores de fallback em caso de erro.
    """
    diag = {
        "db_path":        DB_PATH,
        "log_path":       SENTINELA_LOG_PATH,
        "runtime_dir":    RUNTIME_DIR,
        "db_existe":      os.path.exists(DB_PATH),
        "db_tamanho_kb":  0,
        "n_keywords":     0,
        "n_historico":    0,
        "n_configs":      0,
        "ultima_coleta":  None,
        "ultimas_linhas_log": [],
        "telegram_token": False,
        "telegram_token_len": 0,
        "telegram_chat_id": False,
        "telegram_chat_id_masked": "",
    }

    try:
        if diag["db_existe"]:
            diag["db_tamanho_kb"] = round(os.path.getsize(DB_PATH) / 1024, 1)
            conn = sqlite3.connect(DB_PATH)
            diag["n_keywords"] = conn.execute(
                "SELECT COUNT(*) FROM keywords_monitoradas WHERE ativa=1"
            ).fetchone()[0]
            diag["n_historico"] = conn.execute(
                "SELECT COUNT(*) FROM historico_precos"
            ).fetchone()[0]
            diag["n_configs"] = conn.execute(
                "SELECT COUNT(*) FROM config_sentinela"
            ).fetchone()[0]
            res = conn.execute(
                "SELECT MAX(data_verificacao) FROM historico_precos"
            ).fetchone()
            diag["ultima_coleta"] = res[0] if res else None

            # Credenciais Telegram
            tok_row = conn.execute(
                "SELECT valor FROM config_sentinela WHERE chave='telegram_token'"
            ).fetchone()
            cid_row = conn.execute(
                "SELECT valor FROM config_sentinela WHERE chave='telegram_chat_id'"
            ).fetchone()
            conn.close()

            tok_val = (tok_row[0] or "").strip() if tok_row else ""
            cid_val = (cid_row[0] or "").strip() if cid_row else ""

            diag["telegram_token"]       = bool(tok_val)
            diag["telegram_token_len"]   = len(tok_val)
            diag["telegram_chat_id"]     = bool(cid_val)
            diag["telegram_chat_id_masked"] = (
                cid_val[:4] + "****" + cid_val[-2:] if len(cid_val) > 6 else cid_val
            )
    except Exception as e:
        diag["db_error"] = str(e)

    try:
        if os.path.exists(SENTINELA_LOG_PATH):
            with open(SENTINELA_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
                linhas = f.readlines()
            diag["ultimas_linhas_log"] = [l.rstrip() for l in linhas[-40:]]
    except Exception as e:
        diag["log_error"] = str(e)

    return diag
