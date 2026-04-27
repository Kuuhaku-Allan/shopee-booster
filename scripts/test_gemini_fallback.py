"""
Test script para validar fallback robusto de modelos Gemini
"""
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()
load_dotenv(".shopee_config")

def test_gemini_fallback():
    """Testa o fallback robusto de modelos Gemini"""
    
    from backend_core import generate_text_with_model_fallback, MODELOS_TEXTO
    
    print("=" * 60)
    print("TESTE: Fallback Robusto de Modelos Gemini")
    print("=" * 60)
    
    # Verifica API key
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ GOOGLE_API_KEY não configurada")
        print("Configure no arquivo .env ou .shopee_config")
        return
    
    print(f"\n✅ API Key encontrada: {api_key[:10]}...{api_key[-4:]}")
    print(f"\nModelos a testar: {len(MODELOS_TEXTO)}")
    for i, model in enumerate(MODELOS_TEXTO, 1):
        print(f"  {i}. {model}")
    
    # Prompt simples para teste
    prompt = """Você é um assistente de e-commerce.

Responda em 2-3 linhas: Qual a importância de um bom título de produto na Shopee?"""
    
    print("\n" + "=" * 60)
    print("EXECUTANDO TESTE")
    print("=" * 60)
    print(f"\nPrompt: {prompt[:100]}...")
    print("\nIniciando fallback...\n")
    
    # Testa o fallback
    try:
        resultado = generate_text_with_model_fallback(
            prompt=prompt,
            api_key=api_key,
            models=MODELOS_TEXTO,
            task_name="test_fallback"
        )
        
        print("\n" + "=" * 60)
        print("RESULTADO")
        print("=" * 60)
        
        if resultado.startswith("⏳ Todos os modelos falharam"):
            print("❌ FALHA: Todos os modelos falharam")
            print("\nDetalhes dos erros:")
            print(resultado)
        else:
            print("✅ SUCESSO: Resposta gerada")
            print(f"\nTamanho: {len(resultado)} caracteres")
            print("\nResposta:")
            print("-" * 60)
            print(resultado)
            print("-" * 60)
        
    except Exception as e:
        print(f"\n❌ EXCEÇÃO: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)


def test_with_invalid_key():
    """Testa comportamento com API key inválida"""
    
    from backend_core import generate_text_with_model_fallback, MODELOS_TEXTO
    
    print("\n" + "=" * 60)
    print("TESTE: API Key Inválida")
    print("=" * 60)
    
    prompt = "Teste simples"
    
    resultado = generate_text_with_model_fallback(
        prompt=prompt,
        api_key="INVALID_KEY_12345",
        models=MODELOS_TEXTO,
        task_name="test_invalid_key"
    )
    
    print("\nResultado:")
    print(resultado)
    
    if "falharam" in resultado.lower():
        print("\n✅ Comportamento correto: Detectou falha e retornou mensagem de erro")
    else:
        print("\n⚠️ Comportamento inesperado")


def test_without_key():
    """Testa comportamento sem API key"""
    
    from backend_core import generate_text_with_model_fallback
    
    print("\n" + "=" * 60)
    print("TESTE: Sem API Key")
    print("=" * 60)
    
    # Remove temporariamente a variável de ambiente
    original_key = os.environ.get("GOOGLE_API_KEY")
    if original_key:
        del os.environ["GOOGLE_API_KEY"]
    
    prompt = "Teste simples"
    
    resultado = generate_text_with_model_fallback(
        prompt=prompt,
        api_key=None,
        task_name="test_no_key"
    )
    
    print("\nResultado:")
    print(resultado)
    
    if "não configurada" in resultado.lower():
        print("\n✅ Comportamento correto: Detectou ausência de API key")
    else:
        print("\n⚠️ Comportamento inesperado")
    
    # Restaura a variável de ambiente
    if original_key:
        os.environ["GOOGLE_API_KEY"] = original_key


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Testa fallback de modelos Gemini")
    parser.add_argument("--all", action="store_true", help="Executa todos os testes")
    parser.add_argument("--invalid", action="store_true", help="Testa com API key inválida")
    parser.add_argument("--no-key", action="store_true", help="Testa sem API key")
    
    args = parser.parse_args()
    
    if args.all:
        test_gemini_fallback()
        test_with_invalid_key()
        test_without_key()
    elif args.invalid:
        test_with_invalid_key()
    elif args.no_key:
        test_without_key()
    else:
        # Teste padrão
        test_gemini_fallback()
