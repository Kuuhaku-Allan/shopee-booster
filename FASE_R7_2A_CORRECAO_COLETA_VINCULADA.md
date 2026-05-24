# Fase R7.2A — Correção de Coleta de Candidatos Vinculados no Radar Assistido

## Contexto e Problema
Na fase R7.2, a interface do Radar Assistido foi criada permitindo ao usuário vincular URLs de concorrentes a produtos próprios. Entretanto, o botão "Coletar" na interface realizava o processamento por meio de uma fila global (`rc.get_pending_jobs`), o que frequentemente resultava em 0 jobs processados para o produto selecionado.

Outros problemas identificados:
- O ciclo de chamada para os scrapers em `run_linked_collection_for_product` estava incorreto e causaria quebras na execução real por tentar chamar diretamente as funções de coleta do Playwright sem passar uma instância válida de página.
- Havia uma mistura de status em português (`coleta_pendente`, `falha_coleta`) com inglês na base de dados e nos retornos de serviço.
- Erros de coleta ocorridos em background eram difíceis de inspecionar na interface pois sumiam com o `st.rerun()` necessário para atualizar a tabela.

## Soluções Implementadas

### 1. Coleta Escopada e Reconciliação
Implementamos uma rotina cirúrgica em `shopee_core/radar_workflow_ui_service.py` que:
* **Filtra estritamente** os jobs de coleta que pertencem aos candidatos vinculados ao `own_product_uid` selecionado.
* **Garante a integridade da fila** recriando jobs pendentes ausentes de candidatos cujo status seja `pending` ou `failed` e que ainda não possuam dados coletados.
* **Corrige o ciclo do Playwright** chamando a função principal do coletor (`rc.collect_product_page`), de modo a abrir o navegador sob demanda (via CDP ou Persistent Context), validar a qualidade da extração e persistir os assets em disco usando as funções core estáveis da aplicação.

### 2. Padronização de Status
* Padronizamos a base de dados e o serviço do backend para utilizar estritamente o padrão inglês (`pending`, `failed`, `collected`, `competitor_direct`, `competitor_partial`, `rejected`).
* Realizamos a tradução desses status de forma transparente e isolada na camada de renderização do `app.py`, preservando as cores da interface e o dropdown de filtragem do usuário sem poluir o banco de dados.

### 3. Persistência de Logs de Erros na UI
* Integramos o `st.session_state` para reter o resultado da última coleta. Desta forma, se ocorrerem falhas durante a coleta, os logs específicos das exceções e as URLs problemáticas correspondentes são exibidos de forma clara em um cartão expansível `st.expander` na UI, mesmo após recarregar a tela para atualizar a tabela.
* Limpamos esse estado sempre que o usuário altera a seleção do produto base para evitar confusões visuais.

### 4. Cobertura de Testes Exaustiva
* Adicionamos **10 novos casos de teste** automatizados em `test_radar_workflow_ui_service.py`, testando com mocks toda a lógica do fluxo sem abrir navegador.
* Cobertura dos testes:
  1. Mapeamento de status no retorno da tabela (`get_competitor_table_status_mappings`).
  2. Criação de jobs ausentes pela reconciliação (`ensure_collection_jobs_creates_missing_jobs`).
  3. Ignorar jobs ativos/existentes para evitar duplicações (`ensure_collection_jobs_skips_existing_active_jobs`).
  4. Ignorar produtos já coletados com sucesso (`ensure_collection_jobs_skips_completed_products`).
  5. Fluxo completo de sucesso mockado (`run_linked_collection_for_product` via mock).
  6. Comportamento sob bloqueio/captcha mockado (`run_linked_collection_with_blocked_mock`).
  7. Comportamento sob baixa qualidade mockada (`run_linked_collection_with_low_quality_mock`).
  8. Comportamento com marketplaces desconhecidos/não suportados (`run_linked_collection_with_unsupported_marketplace`).
  9. Tratamento robusto de exceções em tempo de execução (`run_linked_collection_exception_handling`).
  10. Respeito estrito ao limite de concorrência (`run_linked_collection_limits_concurrency`).

## Verificação e Regressão
* Todos os 18 testes de `test_radar_workflow_ui_service.py` passam com absoluto sucesso em **1.10s**.
