# Fase R2.2 - Validacao Shopee com Perfil Persistente Logado

Data de preparacao: 2026-05-23

## Objetivo

Validar se o coletor R2 consegue extrair dados da Shopee quando o usuario esta logado
manualmente no perfil persistente do navegador:

```text
data/browser_profile/
```

Esta fase nao implementa bypass de login, bypass de captcha, automacao de senha,
stealth agressivo, download profundo de midias, IA, Bot WhatsApp, Auditoria ou Sentinela.

## Scripts Criados/Ajustados

### Abrir perfil persistente

Arquivo:

```text
scripts/radar_open_browser_profile.py
```

Uso principal:

```powershell
python scripts/radar_open_browser_profile.py --marketplace shopee
```

Comportamento:

- abre Chromium visivel;
- usa o mesmo perfil persistente do coletor;
- abre `https://shopee.com.br/`;
- imprime instrucao para login/verificacao manual;
- mantem o navegador aberto ate o usuario fechar o navegador ou pressionar ENTER no terminal.

Opcional para teste tecnico rapido:

```powershell
python scripts/radar_open_browser_profile.py --marketplace shopee --auto-close-seconds 5
```

### Coletor interativo

Arquivo ajustado:

```text
scripts/radar_collect_url.py
```

Uso:

```powershell
python scripts/radar_collect_url.py "https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331" --save --interactive
```

Opcional para ambientes onde o terminal nao recebe ENTER facilmente:

```powershell
python scripts/radar_collect_url.py "https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331" --save --interactive --interactive-wait-seconds 90
```

Comportamento:

- abre a URL no navegador visivel;
- se detectar login/verificacao, pausa para intervencao manual;
- se campos essenciais vierem vazios, pausa e tenta extrair novamente;
- salva produto, `raw_json`, assets e marca o job como `done` quando `--save` e usado.

## URL de Smoke Shopee

```text
https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331
```

## Procedimento de Validacao

1. Abrir o navegador persistente:

```powershell
python scripts/radar_open_browser_profile.py --marketplace shopee
```

2. Fazer login/verificacao manualmente na Shopee.

3. Fechar o navegador ou pressionar ENTER no terminal.

4. Rodar coleta interativa com save:

```powershell
python scripts/radar_collect_url.py "https://shopee.com.br/Mochila-Notebook-Grande-15-6-I-Connect-Sestini--i.833275000.58209898331" --save --interactive --interactive-wait-seconds 90
```

5. Inspecionar o banco:

```powershell
python scripts/radar_inspect_db.py
```

## Status Nesta Sessao

O codigo da R2.2 foi preparado e testado, mas a validacao autenticada completa da Shopee
nao foi concluida nesta sessao porque exige login/verificacao manual com credenciais do
usuario.

Validacao tecnica executada:

```powershell
python scripts/radar_open_browser_profile.py --marketplace shopee --auto-close-seconds 5
```

Resultado: o Chromium abriu usando `data/browser_profile/` e fechou automaticamente apos o
tempo configurado.

Resultado conhecido ate agora, herdado da R2.1:

- o perfil persistente existe e e usado pelo coletor;
- a Shopee abre em navegador visivel;
- sem login/verificacao concluido, a Shopee retorna pagina de bloqueio/login;
- o coletor salva a tentativa em `radar.db` sem tentar bypass;
- Mercado Livre ja foi aprovado com coleta real completa.

## Campos a Conferir Apos Login

Obrigatorios para considerar Shopee aprovado:

- `status=collected`
- `marketplace=shopee`
- `title` do produto preenchido
- `raw_json` preenchido

Desejaveis:

- `price`
- `shop_name`
- `description`
- `image_urls`
- registros em `radar_assets`

## Conclusao Provisoria

Conclusao atual: **C) Shopee ainda bloqueado no perfil atual sem login manual concluido.**

Proxima acao necessaria:

Executar o procedimento acima com login manual no navegador persistente. Se, depois do login,
o produto retornar titulo/preco/imagens, a conclusao muda para **A) Shopee aprovado com perfil
logado**. Se apenas parte dos campos vier preenchida, a conclusao muda para **B) Shopee
parcialmente aprovado**.
