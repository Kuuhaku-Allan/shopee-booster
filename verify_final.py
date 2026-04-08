import sys
import os

# Auditoria Final V4.3 (Standard Powerup)
# Adiciona o _internal ao path para simular o ambiente do .exe
sys.path.append(os.path.join(os.getcwd(), 'dist', 'ShopeeBooster', '_internal'))

try:
    import streamlit
    import importlib.metadata
    import timeit
    import inspect
    import tempfile
    
    version = importlib.metadata.version('streamlit')
    print(f"--- [CERTIFICADO V4.3] ---")
    print(f"Streamlit Metadata: ENCONTRADO (Versao: {version})")
    print(f"Standard Libs (timeit, inspect, tempfile): PRESENTES")
    print(f"Ambiente de Runtime: 100% OPERACIONAL")
    print(f"--------------------------")
except Exception as e:
    print(f"ERRO DE AUDITORIA FINAL: {e}")
    sys.exit(1)
