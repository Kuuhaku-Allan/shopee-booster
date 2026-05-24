# Fase R7.2D — Timeout e fallback na etapa de extração

Esta documentação descreve as melhorias implementadas na Fase R7.2D para garantir a resiliência e a estabilidade da coleta do Radar Assistido de concorrentes.

## 1. Problema Observado
A Fase R7.2C adicionou timeouts para carregamento e rolagem da página. Contudo, em alguns cenários (especialmente em páginas de catálogo do Mercado Livre com a estrutura `/p/MLB...`), o coletor ficava preso indefinidamente na etapa **"Extraindo dados do produto concorrente"**. 

## 2. Causa Provável
O coletor tentava consultar seletores visuais que não existiam no layout de páginas de catálogo `/p/MLB...` e, na ausência de timeouts curtos/instantes ou de fallbacks robustos, o fluxo de execução ficava travado nos seletores ou nas rotinas internas de persistência e download de imagens (assets).

## 3. Soluções Implementadas

### A. Timeouts Estritos de Extração e Assets
Adicionamos timeouts específicos para cada subetapa da coleta:
1. **Timeout de Extração (25s):** Caso a extração de dados do produto na página dure mais de 25 segundos, o coletor gera uma exceção `TimeoutError("extract_timeout_after_25s")`.
2. **Timeout de Assets (30s):** Caso o download de imagens/vídeos pelo serviço `_persist_collected_assets` dure mais de 30 segundos, gera uma exceção `TimeoutError("assets_timeout_after_30s")`.
3. **Timeout Total por URL (90s):** Limite estrito de 90 segundos para todo o ciclo de vida de processamento de uma URL.

### B. Fallback para Páginas de Catálogo (/p/MLB...)
* **Slug Fallback:** Caso seletores e tags JSON-LD/meta falhem em obter o título do concorrente, o coletor extrai e limpa o slug da própria URL para usá-lo como título (`_extract_title_from_url`).
* **Novos Seletores de Preço:** Expandimos a lista de seletores visuais de preços no Mercado Livre para incluir classes comumente usadas em catálogos:
  * `.ui-search-price__second-line .andes-money-amount__fraction`
  * `.andes-price__fraction`
  * `.price-tag-fraction`

### C. Coleta Parcial e Regra de Salvamento
* Se **ambos** o título e preço falharem (ausência de dados mínimos após tentativa visual e fallback), a coleta é marcada como falha clara (`missing_title_and_price_after_extraction`).
* Se **apenas um** deles (título ou preço) for extraído com sucesso, o sistema aceita os dados parciais e salva o concorrente no banco de dados como `collected` (com qualidade baixa identificada no `raw_json`), evitando falhar a coleta inteira.
* Os erros de download de assets individuais viram warnings e **não abortam** o salvamento do produto concorrente.

### D. Subetapas em Tempo Real na UI
Quebramos a etapa genérica de extração em subetapas detalhadas em português, reportadas dinamicamente na interface Streamlit:
* **Abrindo página**
* **Fazendo scroll**
* **Extraindo título e preço**
* **Extraindo descrição**
* **Extraindo imagens**
* **Salvando no banco**
* **Finalizando URL**

## 4. Testes Automatizados
Adicionamos 6 novos testes unitários e de integração em [test_radar_workflow_ui_service.py](file:///c:/Users/Defal/Documents/Faculdade/Projeto%20Shopee/test_radar_workflow_ui_service.py) para cobrir todos os fluxos de sucesso parcial, falhas, fallbacks e timeouts. Todos os 29 testes do suite estão passando com sucesso.
