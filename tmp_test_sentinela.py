"""
tmp_test_sentinela.py — Testa um ciclo completo da Sentinela sem esperar 4h.
Roda direto via: python tmp_test_sentinela.py
"""
import sys, os

# Garante que o projeto está no path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sentinela_db import init_db, listar_keywords, processar_mudancas_e_alertar, obter_config
from telegram_service import TelegramSentinela

print("=== Teste Rápido da Sentinela ===\n")

init_db()

token = obter_config("telegram_token")
chat_id = obter_config("telegram_chat_id")
keywords = listar_keywords()

print(f"Token: {'OK (' + token[:15] + '...)' if token else 'AUSENTE'}")
print(f"Chat ID: {'OK (' + str(chat_id) + ')' if chat_id else 'AUSENTE'}")
print(f"Keywords: {keywords}")

if not token or not chat_id:
    print("\n❌ Sem credenciais Telegram — configure na aba Sentinela > Bot Connection.")
    sys.exit(1)

if not keywords:
    print("\n❌ Sem keywords — cadastre na aba Sentinela > Nicho Monitorado.")
    sys.exit(1)

telegram = TelegramSentinela(token, chat_id)

print(f"\n📡 Testando envio ao Telegram...")
ok = telegram.enviar_alerta("🧪 *Teste do ciclo da Sentinela* — tudo funcionando!")
print(f"Envio: {'✅ OK' if ok else '❌ FALHOU'}")

# Busca real da primeira keyword (pode demorar ~30s)
kw = keywords[0]
print(f"\n🔍 Buscando concorrentes para '{kw}'...")
print("(isso pode levar até 60 segundos — aguarde)")

# Import do launcher headless fetch
from launcher import _fetch_competitors_headless
resultados = _fetch_competitors_headless(kw)

print(f"Resultados: {len(resultados)} concorrentes encontrados")
if resultados:
    for i, r in enumerate(resultados[:3], 1):
        print(f"  #{i} {r.get('nome','')[:40]} — R$ {r.get('preco',0):.2f}")
    processar_mudancas_e_alertar(kw, resultados, telegram)
    print("✅ processar_mudancas_e_alertar executado OK")
else:
    print("⚠️  Nenhum resultado — verifique a keyword e a conexão com a Shopee.")

print("\nTeste concluído.")
