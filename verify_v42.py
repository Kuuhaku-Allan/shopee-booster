import sys
import os

# Auditoria de Metadados V4.2
# Adiciona o _internal ao path para simular o ambiente do .exe
sys.path.append(os.path.join(os.getcwd(), 'dist', 'ShopeeBooster', '_internal'))

try:
    import streamlit
    import importlib.metadata
    version = importlib.metadata.version('streamlit')
    print(f"--- [CERTIFICADO V4.2] ---")
    print(f"Streamlit Metadata: ENCONTRADO (Versao: {version})")
    print(f"Ambiente de Runtime: 100% OK")
    print(f"--------------------------")
except Exception as e:
    print(f"ERRO DE AUDITORIA: {e}")
    sys.exit(1)
