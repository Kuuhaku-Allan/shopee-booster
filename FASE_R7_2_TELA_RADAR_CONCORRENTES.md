# Fase R7.2 — Tela do Radar Assistido

## Objetivo
Criar uma interface semiautomática integrada ao app (.exe/Streamlit) para gerenciar o workflow completo do **Radar de Concorrentes**, vinculando URLs manuais a produtos base da própria loja, sem depender de linhas de comando ou intervenção no código.

## O que foi Feito

1. **Database Schema (`radar_db.py`)**:
   - Criação da tabela `radar_candidate_links` responsável por ligar `own_product_uid` -> `candidate_product_uid`, garantindo que candidatos não se misturem entre nichos diferentes.
2. **Serviço de Fluxo (`radar_workflow_ui_service.py`)**:
   - Rotinas de leitura (`list_own_products_for_radar`) para listar bases rastreáveis.
   - Rotina de Ingestão (`add_competitor_urls_for_product`) que suporta múltiplas URLs em batch, efetuando desduplicação e criando jobs automaticamente.
   - Rotina Analítica: Integração amigável (`classify_linked_candidates_for_product`, `run_pattern_analysis_for_product`).
3. **Tela de UI (`app.py`)**:
   - Aba **"🎯 Radar Assistido"** na barra lateral.
   - Mecanismo de sugestões automáticas baseadas em sub-tokens do título base para facilitar busca orgânica.
   - Área de input batch e botões assíncronos (com spinner) acionando a `queue` e atualizando a interface nativa (métricas e tabela de concorrentes rica e filtrável).
4. **Testes (`test_radar_workflow_ui_service.py`)**:
   - Cobertura total das validações, isolamento de escopo por `own_product` e inserção limpa.

## Como Usar o Fluxo (Smoke Manual)
1. Certifique-se de já possuir um "Produto Próprio" salvo através da Auditoria ou recarregado via Espelho da Loja.
2. Abra a nova aba `🎯 Radar Assistido`.
3. Escolha seu produto próprio no dropdown. O painel exibirá as estatísticas atuais.
4. Note as *Sugestões de Busca*. Copie um dos termos sugeridos e jogue no Mercado Livre (ou Shopee).
5. Copie algumas URLs reais (ex: Mercado Livre) e cole na grande caixa de texto da tela.
6. Clique em **Adicionar URLs ao Radar**. A métrica de "Jobs Pendentes" subirá.
7. Selecione `Modo do Navegador: cdp` e `Limite de Coleta: 3`.
8. *Nota Importante:* Se usar `cdp`, lembre-se de que o **Chrome local para automação precisa estar aberto**. Abra um PowerShell e rode o atalho: `powershell -ExecutionPolicy Bypass -File .\deploy\local\start-radar-chrome.ps1`
9. Clique em **Coletar URLs Pendentes**.
10. Com a coleta encerrada, clique em **Classificar Concorrentes** para ver as estatísticas (Diretos, Parciais, etc).
11. Pressione **Gerar Relatório de Padrões** e navegue até a Auditoria para ver os resultados do seu estudo em prática!

## Limitações e Próximos Passos
- **Fase Atual (R7.2)**: É dependente de input manual. O sistema auxilia na digestão, organização e coleta, mas o usuário deve ativamente buscar as URLs.
- **Próxima Fase (R7.3)**: Assistente de busca semiautomática. Em vez do usuário "ir ao Mercado Livre", a UI injetará as queries num buscador e mostrará grids de candidatos, requerendo do usuário apenas clicar nos selecionados para ingestão rápida.
