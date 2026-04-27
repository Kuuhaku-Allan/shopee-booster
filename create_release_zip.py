#!/usr/bin/env python3
"""
Cria o arquivo ZIP de release do ShopeeBooster.
"""

import zipfile
import os
from pathlib import Path

def create_release_zip():
    """Cria ZIP com todos os arquivos do build."""
    source_dir = Path("dist/ShopeeBooster")
    zip_path = Path("dist/ShopeeBooster_v4.1.0.zip")
    
    print(f"\n📦 Criando ZIP de release...")
    print(f"📁 Origem: {source_dir}")
    print(f"💾 Destino: {zip_path}\n")
    
    # Remove ZIP antigo se existir
    if zip_path.exists():
        print(f"🗑️  Removendo ZIP antigo...")
        zip_path.unlink()
    
    # Cria novo ZIP
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=5) as zipf:
        total_files = 0
        total_size = 0
        
        # Adiciona todos os arquivos
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(source_dir.parent)
                
                file_size = file_path.stat().st_size
                total_size += file_size
                total_files += 1
                
                print(f"  ✅ {arcname} ({file_size:,} bytes)")
                zipf.write(file_path, arcname)
    
    zip_size = zip_path.stat().st_size
    compression_ratio = (1 - zip_size / total_size) * 100 if total_size > 0 else 0
    
    print(f"\n{'='*60}")
    print(f"✅ ZIP CRIADO COM SUCESSO!")
    print(f"{'='*60}")
    print(f"📊 Estatísticas:")
    print(f"   Arquivos: {total_files}")
    print(f"   Tamanho original: {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")
    print(f"   Tamanho comprimido: {zip_size:,} bytes ({zip_size/1024/1024:.1f} MB)")
    print(f"   Compressão: {compression_ratio:.1f}%")
    print(f"\n💾 Arquivo: {zip_path.absolute()}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    create_release_zip()
