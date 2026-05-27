# Fase R7.3 — Radar Automatico de Concorrentes

**Status:** Em desenvolvimento  
**Precedencia:** R7.2L.1 ✓

## O que faz

Permite que o usuario clique em "Rodar Radar Automatico" na UI e o sistema:
1. Gera queries de busca baseadas no titulo do produto (filtros: tipo, publico, uso, tema, cor)
2. Busca URLs de concorrentes no Mercado Livre via Playwright/CDP
3. Normaliza e insere candidatos no banco
4. Dispara coleta de dados dos candidatos
5. Classifica os candidatos (direct / partial / rejected)
6. Gera relatorio de padroes com analise ponderada
7. Calcula confianca do radar

Sem chamadas de IA — tudo baseado em regras deterministicas.

## Arquivos criados/modificados

- `shopee_core/radar_discovery_service.py` — novo: geracao de queries, descoberta de URLs, calculo de confianca, ciclo automatico
- `shopee_core/radar_workflow_ui_service.py` — wrappers para `generate_search_queries_for_product()` e `run_automatic_radar_cycle()` (lazy imports para evitar circular)
- `app.py` — secao "Radar Automatico" na tela Radar Assistido com parametros, progresso e resultados
- `test_radar_discovery_service.py` — 11 testes

## Testes

```bash
python -m pytest test_radar_discovery_service.py -v
python -m pytest test_radar_relevance_service.py test_radar_patterns_service.py -v
```

## Smoke (manual)

Requer Chrome com CDP em `http://127.0.0.1:9222`:

1. Abrir app: `python app.py`
2. Navegar para Radar Assistido
3. Selecionar produto "Mochila Infantil Princesa Rosa Escolar Feminina Grande"
4. Clicar "Rodar Radar Automatico" com: max_queries=3, max_urls_per_query=5, max_collect=5
5. Verificar: progresso na UI, resultado com metricas, relatorio gerado

## Proximas fases

- R7.4: Renovação semanal automática (cron job ou scheduler)
- R7.5: Auditoria Pro usa dados do Radar
- R7.6: Chatbot usa dados do Radar
- R7.7: Sentinela usa dados do Radar
- R8.0: Build .exe
