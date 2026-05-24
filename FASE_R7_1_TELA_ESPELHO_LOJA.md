# Fase R7.1 — Tela do Espelho da Loja no .exe

## Objetivo
Expor os dados do Espelho da Loja (validados e estabilizados na R7.0 e R7.0A) através de uma interface gráfica nativa no app Streamlit (.exe). O objetivo é facilitar a inspeção, permitindo consultar métricas de cache e realizar "troubleshooting" diretamente pelo painel, substituindo os antigos scripts executados em terminal.

Esta fase cria a funcionalidade de *leitura e visualização* do espelho. Ela não altera o fluxo de coleta da Sentinela e não consome a API da Shopee.

## O que foi feito

1. **`shopee_core/radar_store_ui_service.py`**: Helper de UI que lê o arquivo `radar.db` (usando os serviços de espelho da R7.0) e formata os dados para o Streamlit, sem afetar as regras de negócio de back-end.
2. **`app.py`**:
   - Adicionada opção `🏪 Espelho da Loja` no menu lateral de partições.
   - Criada a nova tela de visualização (`render_espelho_loja`).
   - Implementado roteamento condicional para despachar a UI.
3. **`test_radar_store_ui_service.py`**: Suíte de testes (9 casos de teste) validando regras de consistência da interface para lojas desatualizadas, produtos ausentes, e banco vazio.
   
## Como Acessar a Tela
1. Inicie o aplicativo: `streamlit run app.py` (ou abra o executável compilado).
2. No menu lateral "Partições", selecione **"🏪 Espelho da Loja"**.

## Funcionalidades da Tela
* **Diagnóstico do Banco**: Mostra caminho absoluto, tamanho atual, total de lojas cacheadas, total de registros de produtos.
* **Métricas da Loja**: Exibe totais categorizados: Ativos, Alterados e Ausentes/Removidos, juntamente com o aviso visual de desatualização caso o último "snapshot" da loja tenha mais de 7 dias.
* **Tabela de Produtos**: Tabela com recursos de filtragem por status (`Todos`, `active`, `changed`, `missing`, `removed`, `unknown`), com exibição das fontes e links curtos.
* **Detalhes do Produto e JSON**: Visão ampla contendo a miniatura de imagem do produto, botões visuais para cópia de `store_product_uid`, `radar_product_uid` e URLs canônicas. Exibe também dados brutos guardados pela extração via expander.

## Guia do Smoke Test Manual

1. **Testando Banco Vazio / Loja Sem Cache**:
   - Abra a tela "Espelho da Loja" em um ambiente sem lojas cacheadas.
   - A tela exibirá um aviso azul "Nenhuma loja salva no espelho", sem disparar exceções no Streamlit.
2. **Testando Loja Existente (Ex: `totalmenteseu`)**:
   - Faça uma auditoria na loja e aguarde o salvamento do Espelho da R7.0.
   - Abra a tela "Espelho da Loja", selecione a loja no Selectbox.
   - Verifique se os *Cards de Métricas* trazem contagens consistentes (> 0).
   - Use a busca textual para isolar um produto.
   - Clique em inspecionar o detalhe do produto e copie o `radar_product_uid` caso precise debugar as associações no banco.
3. **Instruções de Fallback**:
   - Clique em "Ativar instrução de fallback" e valide se a instrução informa o passo-a-passo correto (`$env:SHOPEE_FORCE_RADAR_STORE_FALLBACK="true"`) para que o usuário saiba como realizar o bypass caso a Shopee bloqueie seu acesso momentaneamente.

## Limitações
* A R7.1 foca em **inspeção de leitura do espelho cacheado**.
* Botões como "Recarregar" atuam em escopo puramente visual (`st.rerun()`), sem disparar nova carga na Shopee.
* Bot do WhatsApp e geração do Gemini continuam agnósticos a essa tela, que funciona primariamente como painel de controle e monitoramento avançado.

## Próximos Passos
**R7.2 — Tela completa do Radar Assistido para cadastrar URLs de concorrentes**
Após o sucesso do Espelho da Loja, a interface do Radar começará a aceitar inputs de links externos de concorrentes e associá-los manualmente/automaticamente, fechando o ciclo do recurso "Radar de Concorrentes".
