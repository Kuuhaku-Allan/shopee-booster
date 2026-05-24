# Fase R7.2B — Auto-Start Radar Chrome para Coleta CDP

## Problema Anterior
Na fase R7.2A, a coleta escopada de concorrentes foi corrigida, porém ao executar sob o modo `cdp` (Chrome DevTools Protocol), se o navegador dedicado do Radar não estivesse aberto na porta `9222`, a coleta falhava imediatamente e registrava os jobs e candidatos como `failed` de forma definitiva no banco de dados.

Ademais, exigir que o usuário abra um console do PowerShell e execute o script `start-radar-chrome.ps1` é aceitável para desenvolvimento, mas inaceitável como UX final para a distribuição empacotada em `.exe` (PyInstaller).

## Solução com Auto-Start Automatizado

### 1. Inicialização Automática do Navegador
Implementamos o módulo `shopee_core/radar_cdp_service.py` que gerencia o ciclo de vida do Chrome CDP:
* **Detecção Automática**: O serviço varre os caminhos comuns de instalação do Google Chrome e do Microsoft Edge no Windows (incluindo caminhos sob `Program Files`, `Program Files (x86)` e `LocalAppData`).
* **Lançamento Desvinculado**: Se a porta `9222` estiver inativa, o app abre o navegador com as flags remotas via `subprocess.Popen` em background. No Windows, utiliza a flag `DETACHED_PROCESS` (`0x00000008`) para garantir que o Chrome continue aberto mesmo se o processo pai do Streamlit sofrer recarregamento.
* **Polling de Inicialização**: Aguarda até 15 segundos (fazendo requisições curtas a `http://127.0.0.1:9222/json/version`) até que a interface CDP esteja respondendo antes de ceder o controle à coleta.

### 2. Perfil de Dados Dedicado
Para não interferir nas sessões pessoais do usuário e manter a portabilidade sob o `.exe`, o navegador é disparado com a diretiva:
`--user-data-dir=data/radar_chrome_profile`

Isso cria um perfil persistente e isolado na pasta de dados da própria aplicação, onde os cookies de sessão de login do Mercado Livre ou Shopee ficam salvos para futuras consultas do Radar.

### 3. Tratamento de Erros de Ambiente e UX
* **Sem Consumo de Fila**: Se o Chrome não puder ser localizado ou falhar em responder dentro do timeout de 15 segundos, o app aborta o processamento imediatamente. Retorna um sinalizador de erro de ambiente (`environment_error=True`) sem incrementar as tentativas (`attempts`) das tarefas e sem alterar o status dos jobs ou candidatos para `failed`.
* **Feedbacks Visuais e Fallback Manual**:
  * Ao clicar em coletar, a UI exibe o spinner: *"Abrindo Chrome do Radar..."*
  * Se aberto automaticamente: *"Chrome do Radar foi aberto automaticamente. Iniciando a coleta..."*
  * Se já ativo: *"Chrome do Radar já estava ativo. Iniciando a coleta..."*
  * Se falhar: Exibe um warning descritivo de erro de ambiente e renderiza um cartão expansível `st.expander` contendo o comando de fallback manual do script `start-radar-chrome.ps1` para desenvolvimento e depuração.
* **Reconciliação e Recuperação**: Ao iniciar uma nova coleta ou reconciliar a fila, candidatos que tenham falhado por falhas passadas têm seu status redefinido para `pending`, permitindo uma retentativa limpa.

### 4. Limitações
O navegador é aberto visível e sem técnicas de ocultação furtiva (stealth). Caso o Mercado Livre ou a Shopee solicitem login, captcha ou verificação em duas etapas, **o usuário deve resolver a pendência de forma humana diretamente na janela do navegador que se abriu**. Após isso, a coleta prosseguirá automaticamente.
