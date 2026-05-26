# Fase R7.3D - Ciclo automatico completo do Radar

## Problema observado

Depois da R7.3/R7.3C, o Radar Automatico passou a descobrir muitas URLs sozinho, mas ainda executava apenas uma rodada de coleta/classificacao/relatorio. Com isso, varios candidatos ficavam como `coleta_pendente`, o relatorio podia parar em `MEDIUM` mesmo com alvo `HIGH`, e a UI passava a impressao de que a classificacao falhou.

## Descobrir, coletar e classificar

- Descobrir: busca URLs no Mercado Livre e vincula candidatos ao produto proprio.
- Coletar: abre cada URL pendente e salva titulo, preco, vendedor e sinais do produto.
- Classificar: aplica regras sobre dados ja coletados.

`coleta_pendente` nao muda ao clicar em classificar porque ainda nao existe titulo/preco/dados suficientes. Esses candidatos precisam passar pela coleta antes.

## Logica de ciclos

`run_automatic_radar_cycle()` agora executa ciclos limitados:

1. valida Chrome/CDP;
2. gera queries;
3. descobre URLs no primeiro ciclo, quando habilitado;
4. prepara jobs;
5. coleta pendentes em lote (`max_collect_per_cycle`);
6. classifica candidatos coletados;
7. gera relatorio;
8. calcula confianca;
9. repete se a confianca alvo nao foi atingida e ainda ha pendentes.

O botao "Continuar ciclo automatico" chama o mesmo fluxo com descoberta desativada, reaproveitando pendentes ja existentes.

## Criterios de parada

- `success`: confianca alvo atingida.
- `limit_reached`: limite de ciclos, candidatos ou tempo atingido.
- `exhausted`: nao ha pendentes para continuar.
- `error`: falha tecnica antes de haver trabalho aproveitavel.

Quando o alvo e `HIGH`, pendentes restantes bloqueiam confianca alta e geram aviso, porque ainda podem alterar a base.

## Relevancia

Foram adicionadas penalidades para usos fora do nicho escolar infantil, incluindo natacao, esporte, academia, praia, hidratacao, trekking/trilha e urbano/corporativo. Caso observado: mochila Nabaiji/natacao nao pode virar `competitor_direct` para mochila escolar infantil princesa.

## UI

- Mostra ciclos executados, coletados, pendentes, confianca alvo, confianca atual e motivo de parada.
- Nao mostra `MEDIUM` com pendentes como sucesso final.
- Botao "Classificar Concorrentes" avisa quando ha pendentes.
- Tabela separada em Classificados, Fila pendente de coleta e Outros.

## Validacao

Testes automatizados executados:

```powershell
.\venv\Scripts\python.exe -m py_compile shopee_core\radar_discovery_service.py shopee_core\radar_workflow_ui_service.py shopee_core\radar_relevance_service.py app.py scripts\radar_discover_worker.py
.\venv\Scripts\python.exe -m pytest test_radar_discovery_service.py -q -p no:cacheprovider
.\venv\Scripts\python.exe -m pytest test_radar_relevance_service.py -q -p no:cacheprovider
.\venv\Scripts\python.exe -m pytest test_radar_workflow_ui_service.py -q -p no:cacheprovider
.\venv\Scripts\python.exe -m pytest test_radar_cdp_service.py -q --basetemp data\pytest-tmp-radar-cdp -p no:cacheprovider
```

Smoke manual recomendado:

1. Abrir `streamlit run app.py`.
2. Selecionar o produto atual.
3. Rodar Radar Automatico com `target_confidence=high`, `max_cycles=3`, `max_collect_per_cycle=5`.
4. Esperado: ciclo 1 coleta 5; se nao atingir `HIGH`, ciclo 2 coleta mais 5; depois ciclo 3. Ao final, mostra `success` ou `limit_reached` com pendentes restantes.
5. Clicar em "Continuar ciclo automatico".
6. Esperado: reaproveita pendentes existentes, nao duplica URLs, e melhora confianca ou informa o motivo real da parada.
