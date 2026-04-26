"""
scripts/prewarm_rembg.py — Pré-aquece o modelo rembg
====================================================
Baixa e carrega o modelo u2netp antes do primeiro uso no WhatsApp.
Isso evita que o primeiro processamento fique lento ou travado.

Execute uma vez:
    python scripts/prewarm_rembg.py
"""

from __future__ import annotations

import io
import time
from PIL import Image

print("=" * 60)
print("Pré-aquecendo rembg (modelo u2netp)...")
print("=" * 60)

start = time.time()

try:
    from rembg import new_session, remove

    print("\n[1/3] Importando rembg... OK")

    # Cria sessão com modelo leve u2netp
    print("[2/3] Carregando modelo u2netp...")
    session = new_session("u2netp")
    print("      Modelo carregado com sucesso!")

    # Cria imagem de teste 64x64
    print("[3/3] Rodando teste mínimo...")
    img = Image.new("RGB", (64, 64), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    # Processa imagem de teste
    result = remove(img_bytes, session=session)

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"✅ rembg pronto! Tempo total: {elapsed:.2f}s")
    print(f"{'=' * 60}")
    print(f"\nModelo salvo em: ~/.u2net/ ou models/.u2net/")
    print("Agora o primeiro processamento no WhatsApp será rápido.")

except Exception as e:
    import traceback
    print(f"\n❌ ERRO ao pré-aquecer rembg:")
    print(traceback.format_exc())
    print("\nPossíveis causas:")
    print("  1. onnxruntime não instalado: pip install onnxruntime")
    print("  2. Modelo não conseguiu baixar (verifique conexão)")
    print("  3. Falta de memória")
    exit(1)
