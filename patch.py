import pathlib

path = pathlib.Path('backend_core.py')
content = path.read_text(encoding='utf-8')

# Signature
content = content.replace(
    '    segmento: str,\n    **kwargs,\n) -> dict:',
    '    segmento: str,\n    channel: str = \"desktop\",\n    **kwargs,\n) -> dict:'
)

# Optimize listing
old_opt = '''        else:
            result[\"text\"] = (
                \"⚡ Para gerar uma otimização completa, selecione um produto na aba \"
                \"**Auditoria Pro** clicando em '⚡ Otimizar'. Assim terei acesso ao \"
                \"preço, imagem e dados de concorrentes para gerar um listing preciso.\\n\\n\"
                \"Se quiser, posso analisar o mercado em geral — é só descrever o produto!\"
            )'''
new_opt = '''        else:
            if channel == \"whatsapp\":
                result[\"text\"] = (
                    \"⚡ Posso te ajudar de duas formas:\\n\\n\"
                    \"1. Se quiser uma *dica rápida* (títulos ou ideias), apenas me descreva o produto e o diferencial dele!\\n\"
                    \"2. Se quiser uma *otimização completa* (com dados de concorrentes e avaliações reais da Shopee), envie o comando /auditar.\"
                )
            else:
                result[\"text\"] = (
                    \"⚡ Para gerar uma otimização completa, selecione um produto na aba \"
                    \"**Auditoria Pro** clicando em '⚡ Otimizar'. Assim terei acesso ao \"
                    \"preço, imagem e dados de concorrentes para gerar um listing preciso.\\n\\n\"
                    \"Se quiser, posso analisar o mercado em geral — é só descrever o produto!\"
                )'''
content = content.replace(old_opt, new_opt)

# General chat
old_gen = '''    # ── Chat geral sem mídia ─────────────────────────────────
    if not has_media or intents == [\"general\"]:
        contents = [full_context + \"\\n\\n---\\nHistórico:\\n\"]'''
new_gen = '''    # ── Chat geral sem mídia ─────────────────────────────────
    if not has_media or intents == [\"general\"]:
        channel_instruction = \"\"
        if channel == \"whatsapp\":
            channel_instruction = (
                \"[INSTRUÇÕES DE SISTEMA - ORIGEM WHATSAPP]\\n\"
                \"Você está respondendo via WhatsApp.\\n\"
                \"1. NÃO mencione abas, botões, Streamlit, '.exe', interface desktop ou ferramentas visuais.\\n\"
                \"2. Para otimização de listing completa, oriente a usar o comando '/auditar'.\\n\"
                \"3. Responda de forma rápida e conversacional. Se faltar contexto, peça as características do produto (preço, benefícios).\\n\"
                \"4. Use formatação de WhatsApp (*negrito*, _itálico_).\\n\\n\"
            )
        contents = [channel_instruction + full_context + \"\\n\\n---\\nHistórico:\\n\"]'''
content = content.replace(old_gen, new_gen)

path.write_text(content, encoding='utf-8')
print("Patched backend_core.py")
