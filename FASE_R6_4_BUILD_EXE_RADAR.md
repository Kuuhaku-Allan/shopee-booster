# Fase R6.4 - Build EXE com Radar Assistido

Data: 2026-05-24

## Objetivo

Recompilar o `ShopeeBooster.exe` com a Auditoria Pro usando Radar Assistido e validar que o executavel encontra o `radar.db`, exibe preview, roda o modo debug sem IA e mantem o notebook como termo off-niche.

## Estado antes do build

- Branch: `feature/whatsapp-bot-core`
- R6.3D confirmada em `HEAD`: `2d972c1 Polish audit radar output formatting`
- A arvore continha arquivos nao relacionados ja modificados ou nao rastreados, como `.env.local`, `postgres_data/`, QR codes e artefatos/documentos de fases anteriores. Eles nao foram incluidos nesta validacao.

## Testes minimos

Comandos executados com o Python do ambiente virtual:

```powershell
.\venv\Scripts\python.exe test_audit_output_formatter.py
$env:PYTHONIOENCODING='utf-8'; .\venv\Scripts\python.exe test_audit_radar_integration.py
$env:PYTHONIOENCODING='utf-8'; .\venv\Scripts\python.exe test_radar_ui_service.py
.\venv\Scripts\python.exe -m compileall shopee_core scripts
.\venv\Scripts\python.exe -m py_compile app.py launcher.py
```

Resultado:

- `test_audit_output_formatter.py`: 30 testes OK.
- `test_audit_radar_integration.py`: 8 testes OK.
- `test_radar_ui_service.py`: 6 testes OK.
- `compileall shopee_core scripts`: OK.
- `py_compile app.py launcher.py`: OK.

Observacao: o Python global nao tinha `pandas`, entao os testes foram rodados pelo `venv`. O teste de UI do Radar tambem exigiu `PYTHONIOENCODING=utf-8` no console por causa de simbolos Unicode no output.

## Build

Metodo oficial usado:

```powershell
cmd /c build.bat
```

Local gerado:

```text
C:\Users\Defal\Documents\Faculdade\Projeto Shopee\dist\ShopeeBooster\ShopeeBooster.exe
```

O build terminou com sucesso. O PyInstaller emitiu avisos sobre dependencias opcionais ausentes, incluindo `langchain`, `android`, `filetype`, `onnx`, `pytest` e `tbb12.dll`, mas o executavel foi gerado e validado.

## Radar DB

Para o teste local do executavel foi usada a opcao B:

```powershell
New-Item -ItemType Directory -Force -Path dist\ShopeeBooster\data
Copy-Item -Force -Path data\radar.db -Destination dist\ShopeeBooster\data\radar.db
```

Tambem foi copiado `.shopee_config` para `dist\ShopeeBooster\.shopee_config` para evitar a tela de configuracao de chave durante o teste local.

Banco validado pelo executavel:

```text
C:\Users\Defal\Documents\Faculdade\Projeto Shopee\dist\ShopeeBooster\data\radar.db
```

## Diagnostico no EXE

Tela testada: `Auditoria Pro > Radar Assistido de Concorrentes`

Resultado do botao `Diagnosticar Radar`:

- `radar.db` encontrado.
- Tamanho aproximado: 1.52 MB.
- Produtos no banco: 84.
- Relatorios no banco: 6.
- Produtos proprios: 10.
- Produtos listaveis: 8.
- Produtos usaveis: 1.
- Produto `2777bd10...` encontrado.

## Preview do Radar

Produto selecionado:

```text
Mochila Infantil Princesa Rosa
```

Resultado observado:

- Preview exibido corretamente.
- 5 concorrentes diretos.
- Confianca: `medium`.
- Faixa de preco: `R$ 59,00 - R$ 302,53`.
- Media: `R$ 185,10`.
- Termos fortes: `mochila`, `infantil`, `escolar`, `feminina`, `rodinhas`.
- Features recomendadas: `escolar`, `infantil`, `rodinhas`, `feminina`, `personagem`, `reforcada`.
- Features a evitar/off-niche: `notebook`.
- `notebook` nao apareceu nas features recomendadas.

## Teste debug sem IA

Opcao ativada:

```text
Debug: mostrar contexto do Radar sem chamar IA
```

Acao:

```text
Gerar Otimizacao Completa
```

Resultado:

- Gemini nao foi chamado.
- Contexto do Radar foi construido com sucesso.
- Moeda saiu formatada como `R$ 59,00`, `R$ 185,10` e `R$ 302,53`.
- `notebook` permaneceu em off-niche/features a evitar.
- Nao houve erro no fluxo debug.

## Teste com IA real

Nao executado nesta validacao para preservar quota da Gemini. A validacao cobriu build, abertura do EXE, diagnostico do Radar, preview, contexto debug sem IA e testes automatizados da integracao/formatter.

## Problemas encontrados e corrigidos

1. O build oficial nao empacotava `shopee_core`, porque o entrypoint do PyInstaller e `launcher.py` e o `app.py` entra como data. O `build.bat` e o `ShopeeBooster.spec` foram ajustados para incluir `shopee_core`.
2. No executavel, o Playwright procurava browsers em `dist\ShopeeBooster\pw-browsers`, mas o bundle os colocava em `dist\ShopeeBooster\_internal\pw-browsers`. O `launcher.py` agora detecta os dois caminhos.
3. O Streamlit interpretava o `$` de `R$` como delimitador Markdown/math em alguns captions. O `app.py` agora escapa o simbolo de moeda nesses pontos da interface.
4. O modo debug sem IA ainda mostrava valores numericos crus no JSON. O `app.py` agora aplica `format_brl` tambem no resumo debug.

## Conclusao

A build R6.4 do `ShopeeBooster.exe` esta funcional para uso local com Auditoria Pro e Radar Assistido. O EXE abre, encontra o `radar.db`, mostra diagnostico e preview, mantem `notebook` como off-niche e preserva a moeda no formato `R$ XX,XX`. A parte de Radar Assistido esta fechada para uso no executavel atual; uma tela propria para cadastro/coleta/relatorio do Radar fica para uma fase futura, como R7.
