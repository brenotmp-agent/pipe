# User Stories — Rodar no Docker

Status: draft
Owner: requisitos
Last updated: 2026-07-07

## Inputs

- Issue #1 "Rodar no Docker"
- Issue #16 "Empacotar a esteira em imagem Docker"
- Issue #17 "Autenticar dependências externas em modo headless"
- doc/product/rodar-no-docker/vision.md
- doc/product/rodar-no-docker/problem-space.md
- doc/product/rodar-no-docker/epicos.md
- src/__main__.py (`_setup_ssh`, `startup`)
- src/core/config.py (`check_config`, `SSH_KEY_ENV`, `_validate_env`)
- src/adapters/kiro_cli_agent.py (`_run`, `_session_exists`, `_list_session_ids`)
- CONTEXT.md (seções: Execução de Agentes, Sessão do agente)
- README.md (seções: Configuração, Uso)
- kiro.dev/docs/cli/headless/ (documentação oficial headless mode)
- kiro.dev/docs/cli/authentication/ (documentação oficial autenticação)
- kiro.dev/docs/cli/chat/session-management/ (documentação oficial sessões)
- cli.github.com/manual/gh_help_environment (GH_TOKEN — gh CLI)

---

## Matriz de requisitos não-funcionais e decisões de arquitetura

| ID     | Tipo     | Descrição                                                                 |
|--------|----------|---------------------------------------------------------------------------|
| RF-01  | Funcional | Container executa `python -m src` sem preparação manual do host           |
| RF-02  | Funcional | Chave SSH injetada por fora, `_setup_ssh` configura sem intervenção       |
| RF-03  | Funcional | `gh` CLI autenticado via `GH_TOKEN` sem `gh auth login`                   |
| RF-04  | Funcional | `kiro-cli` autenticado via `KIRO_API_KEY` sem browser                     |
| RNF-01 | Segurança | Nenhum segredo embutido na imagem                                         |
| RNF-02 | Infra     | Imagem base `python:3.12-slim`                                            |
| RNF-03 | Segurança | Credenciais injetáveis via env/volume, nunca hardcoded no compose         |
| RNF-04 | Operação  | `docker compose up` como único comando necessário para subir a esteira    |
| RNF-05 | Infra     | Dependências com versões pinadas no Dockerfile                            |
| D-01   | Decisão   | kiro-cli autentica via KIRO_API_KEY (headless oficial — ADR-01)           |
| D-02   | Decisão   | Dependências instaladas na imagem, não resolvidas em runtime              |
| D-03   | Decisão   | gh CLI usa GH_TOKEN; não executa `gh auth login` (ADR-02)                 |
| ADR-01 | Arq.      | KIRO_API_KEY como mecanismo de autenticação headless do kiro-cli           |
| ADR-02 | Arq.      | GH_TOKEN como mecanismo de autenticação headless do gh CLI                |
| ADR-03 | Arq.      | Chave SSH montada read-only; `_setup_ssh` copia para `~/.ssh/id_pipe`     |
| ADR-05 | Arq.      | Container roda como usuário não-root com HOME gravável                    |
| ADR-06 | Arq.      | Configurações externas via volumes/env; nada sensível fixo na imagem      |

---

## US-01 — Empacotar a esteira em imagem Docker

**Como** analista/operador,
**quero** uma imagem Docker que contenha a esteira e todas as suas dependências de runtime,
**para** executar `python -m src` em qualquer host com Docker sem preparar a máquina manualmente.

### Rastreabilidade

RF-01, RNF-02, RNF-05, D-02; ADR-05, ADR-06; risco R-2.
Épico: "Imagem containerizada da esteira".

### Critérios de aceitação

#### AC-01 — Imagem base e conteúdo

- `docker build` conclui sem erro e gera uma imagem baseada em `python:3.12-slim`.
- A imagem contém, acessíveis via PATH, os seguintes componentes com versões
  pinadas no Dockerfile (não "latest"):
  - `git` — instalado via apt (pacote `git` do Debian)
  - `openssh-client` — instalado via apt
  - `ca-certificates` — instalado via apt
  - `gh` (GitHub CLI) — instalado via repositório oficial APT do GitHub
    (`https://cli.github.com/packages`)
  - `kiro-cli` — instalado via `.deb` oficial baixado de
    `https://desktop-release.q.us-east-1.amazonaws.com/latest/kiro-cli.deb`
  - `pyyaml` — instalado via `pip install pyyaml==<versão>`

#### AC-02 — Código da esteira

- O diretório `src/` é copiado para dentro da imagem.
- Os arquivos `pipe.yml`, `contexts/`, `repo/`, `logs/` e `.pipe/` **não** são
  copiados (entram por volume em US-03 ou são criados em runtime).

#### AC-03 — Segredos

- Nenhuma chave SSH, token de API, credencial do `gh`, `KIRO_API_KEY` ou qualquer
  outro segredo é copiado ou embutido na imagem.
- Verificação: `docker history <imagem>` e `docker inspect <imagem>` não revelam
  valores sensíveis.

#### AC-04 — Usuário não-root

- O container executa como um usuário não-root (ex.: `uid=1000`, chamado `pipe`).
- O `$HOME` deste usuário é gravável dentro do container, pois:
  - `_setup_ssh()` em `startup()` escreve `~/.ssh/id_pipe` e `~/.ssh/config`.
  - O kiro-cli armazena sessões e configurações em `~/.kiro/` (banco SQLite de
    sessões, keyed por cwd) e índice em `~/.local/share/kiro-cli/`.
- Referência: ADR-05.

#### AC-05 — Variáveis de ambiente obrigatórias na imagem

- `PYTHONUNBUFFERED=1` definido via `ENV` no Dockerfile (garante logs em tempo
  real no `docker logs`).

#### AC-06 — Entrypoint

- O comando padrão do container é `python -m src`.
- Ao executar o container com as variáveis de ambiente mínimas presentes
  (ver US-02 para lista completa), `python -m src` inicia sem nenhuma instalação
  adicional no host.

### Comportamento esperado na inicialização

Quando `python -m src` executa:

1. `check_config()` valida `pipe.yml` (montado em volume) e a variável de
   ambiente `PIPE_SSH_KEY_FILE` (que deve apontar para um arquivo existente no
   container — injetado como secret ou volume por US-02).
2. `startup()` chama `_setup_ssh()`: copia a chave do caminho indicado por
   `PIPE_SSH_KEY_FILE` para `~/.ssh/id_pipe` e configura `~/.ssh/config`.
3. O loop principal roda normalmente.

### Fora de escopo desta US

- Injeção de credenciais em runtime (US-02).
- Montagem de volumes para `pipe.yml`, `contexts/`, `repo/`, `logs/` (US-03).
- Publicação da imagem em registry.
- CI/CD de build da imagem.

### Notas de implementação

#### Instalação do kiro-cli (risco R-2)

O kiro-cli é um binário nativo (não um pacote npm). O método de instalação
documentado em `https://kiro.dev/docs/cli/installation/` para Debian/Ubuntu é:

```bash
wget https://desktop-release.q.us-east-1.amazonaws.com/latest/kiro-cli.deb
dpkg -i kiro-cli.deb
apt-get install -f   # resolve dependências
```

Para pinagem de versão no Dockerfile: o arquivo `.deb` disponibilizado em
`/latest/` é sempre a versão mais recente sem controle de versão na URL. Para
garantir reprodutibilidade, o Dockerfile deve registrar explicitamente qual
versão foi validada (comentário), ou fixar a versão via download de URL
versionada se a distribuição disponibilizar uma.

**Validação crítica (risco R-2):** após a instalação, o Dockerfile deve executar
`kiro-cli --version` para confirmar que o binário está funcional dentro da imagem.

#### Sessões do kiro-cli em container

O kiro-cli armazena sessões em SQLite dentro de `~/.kiro/` e o índice em
`~/.local/share/kiro-cli/`, keyed por cwd (diretório de trabalho do
`subprocess.run` — que é o clone do repositório em `repo/<repo_id>`). Para que
sessões sobrevivam entre reinícios do container, os volumes definidos em US-03
devem cobrir `~/.kiro/` e `~/.local/share/kiro-cli/`.

#### Autenticação headless do kiro-cli

O kiro-cli suporta autenticação headless via `KIRO_API_KEY` (disponível a partir
da versão 2.0). Requer assinatura Kiro Pro ou superior. Esta variável é injetada
em runtime (US-02), não embutida na imagem.

#### HOME gravável e XDG_RUNTIME_DIR

Em containers Debian slim sem systemd, `XDG_RUNTIME_DIR` não está definido. O
kiro-cli usa `$XDG_RUNTIME_DIR` para logs (`kiro-log/kiro-chat.log`); se ausente,
cai para `/tmp`. Isso não impede a execução. O Dockerfile pode definir
`XDG_RUNTIME_DIR=/tmp` como variável de ambiente para eliminar warnings.

---

## US-02 — Autenticar dependências externas em modo headless

**Como** operador,
**quero** fornecer as credenciais das três dependências externas (SSH, GitHub,
kiro-cli) por fora do container,
**para** que a esteira autentique e opere sem qualquer interação manual.

### Desambiguação: por que US-02 é diferente de US-01?

**US-01 (#16)** garante que a **imagem existe e está correta**: os binários
estão instalados, o código foi copiado, o usuário é não-root. Pergunta
respondida: *"a imagem tem o que precisa?"*

É perfeitamente possível concluir US-01 com um `docker build` bem-sucedido e
ainda não saber se `kiro-cli` aceita `KIRO_API_KEY` sem prompt interativo, se
`gh` dispensa `gh auth login` com apenas `GH_TOKEN`, ou se a cópia da chave
SSH pelo `_setup_ssh` é suficiente para o clone funcionar sem toque humano.

**US-02 (esta story)** garante que esses binários **autenticam sem interação
humana** quando as credenciais corretas são fornecidas por fora. Pergunta
respondida: *"uma vez que as credenciais são injetadas, funciona de fato em
headless?"*

Além disso, US-02 produz as especificações exatas de quais env vars declarar
e quais volumes montar — base formal sem a qual US-03 (compose) não tem como
saber o que injetar. As duas stories são ortogonais: a imagem pode estar perfeita
(US-01) e o compose ainda não saber o que declarar (US-02 pendente).

### Rastreabilidade

RF-02, RF-03, RF-04, D-01, D-03; ADR-01, ADR-02, ADR-03; RNF-01; riscos R-1, R-3.
Épico: "Configuração e segredos por fora (docker-compose)".

### Premissas confirmadas (pesquisa documental)

As três dependências possuem suporte headless oficial e documentado:

| Dependência | Mecanismo headless | Fonte |
|---|---|---|
| SSH / git | Variável `PIPE_SSH_KEY_FILE` + volume read-only; `_setup_ssh` copia para `~/.ssh/id_pipe` | `src/__main__.py`, ADR-03 |
| `gh` CLI | Variável `GH_TOKEN` — `gh auth status` retorna sucesso sem `gh auth login` | [cli.github.com/manual/gh_help_environment](https://cli.github.com/manual/gh_help_environment) |
| `kiro-cli` | Variável `KIRO_API_KEY` — skips browser login entirely, disponível a partir da v2.0 | [kiro.dev/docs/cli/headless](https://kiro.dev/docs/cli/headless/) |

### Critérios de aceitação

#### AC-01 — SSH (RF-02, ADR-03)

- A chave privada SSH é montada por volume **read-only** no container (ex.:
  `/run/secrets/ssh_key` ou `/secrets/ssh_key`).
- `PIPE_SSH_KEY_FILE` aponta para o caminho interno do arquivo montado.
- `startup()` → `_setup_ssh()` copia o arquivo para `~/.ssh/id_pipe` (modo
  `0600`) e configura `~/.ssh/config` com `IdentityFile ~/.ssh/id_pipe` para
  `github.com`.
- O clone via SSH (`git clone git@github.com:...`) conclui sem nenhuma
  preparação manual do host.
- A chave original permanece somente leitura no ponto de montagem; apenas a
  cópia em `~/.ssh/id_pipe` tem permissão de escrita.

#### AC-02 — gh CLI (RF-03, D-03, ADR-02)

- Com `GH_TOKEN` definido na env do container, `gh auth status` retorna
  sucesso **sem** que `gh auth login` tenha sido executado.
- O `GH_TOKEN` deve ser um Personal Access Token (PAT) com escopos `repo`
  e `project` (necessários para as operações do `GitHubBoardAdapter`).
- Verificação de ausência: se `GH_TOKEN` não estiver definido, a esteira
  falha na primeira chamada de board (comportamento lazy — não no startup,
  pois `check_config` não valida `GH_TOKEN`). Documentar como pré-requisito
  em US-06.

#### AC-03 — kiro-cli (RF-04, D-01, ADR-01)

- Com `KIRO_API_KEY` definido na env do container, `kiro-cli chat
  --no-interactive` executa sem prompt e sem necessidade de browser.
- `kiro-cli whoami` (ou equivalente, ex.: `kiro-cli auth status`) confirma
  que o método de autenticação ativo é API key, não sessão de browser.
- A variável `KIRO_API_KEY` substitui completamente o browser-login; não há
  interação com o usuário em nenhum momento do ciclo de execução.

**Precedência de autenticação do kiro-cli (confirmada via documentação oficial):**
1. Sessão de browser ativa (`kiro-cli login`) — ausente em container
2. `KIRO_API_KEY` — **será sempre o método ativo em container**
3. Nenhum — CLI solicita login interativo (não ocorre com KIRO_API_KEY definida)

#### AC-04 — Continuidade de sessão com KIRO_API_KEY (R-1)

- `kiro-cli chat --list-sessions` (executado com `KIRO_API_KEY` ativo) lista
  as sessões do cwd normalmente.
- `kiro-cli chat --resume-id <SESSION_ID>` retoma uma sessão anterior com
  `KIRO_API_KEY` ativo sem erro.
- **Conclusão:** não há degradação necessária. O mecanismo de continuidade de
  sessão da esteira (`SessionIndex`, `.pipe/sessions.json`) funciona
  integralmente em modo headless com API key.
- Sessões são armazenadas em SQLite local (`~/.kiro/`), com escopo por cwd
  (diretório de trabalho do `subprocess.run`), independentemente do método de
  autenticação.

**Condição de falha aceitável (registrar como débito se ocorrer):** se, após
testes reais, `--resume-id` sob `KIRO_API_KEY` apresentar comportamento
inesperado (ex.: sessão não encontrada, erro de autenticação na retomada),
a esteira deve degradar graciosamente: executar sem `--resume-id` (nova sessão),
atualizar o índice com o novo id, e registrar a limitação como débito técnico.
O loop **não deve ser interrompido** por falha de retomada de sessão.

#### AC-05 — Segredos (RNF-01)

- Nenhuma das três credenciais é embutida na imagem.
- `GH_TOKEN` e `KIRO_API_KEY` são variáveis de ambiente injetadas em runtime.
- A chave SSH é montada por volume, nunca copiada para a imagem.
- O `docker-compose.yml` usa referências `${VAR}` lidas de `.env` do host
  (`.env` está em `.gitignore`).

#### AC-06 — Validação no startup

| Credencial       | Validada no startup | Comportamento se ausente |
|------------------|---------------------|--------------------------|
| `PIPE_SSH_KEY_FILE` | Sim — `check_config()` → `_validate_env()` | `SystemExit(1)` com mensagem descritiva |
| `GH_TOKEN`       | Não — lazy | Falha na primeira chamada de board; log com erro identificável |
| `KIRO_API_KEY`   | Não — lazy | Falha na primeira execução de agente; log com erro identificável |

Esta assimetria é **comportamento intencionalmente documentado**: `PIPE_SSH_KEY_FILE`
é obrigatória para o startup funcionar (o clone SSH ocorre no `startup()`);
`GH_TOKEN` e `KIRO_API_KEY` só são necessários nas operações do loop. Documentar
todos os três como pré-requisitos no runbook (US-06).

### Fora de escopo desta US

- O `docker-compose.yml` que declara as credenciais (US-03).
- Escolha de tecnologia de gestão de segredos além do Docker secrets básico.
- Validação de permissões mínimas do PAT do GitHub (documentar no runbook US-06).

### Notas / riscos

**R-3 — KIRO_API_KEY requer plano pago:**
`KIRO_API_KEY` está disponível apenas para assinantes Kiro Pro, Pro+, Pro Max
ou Power. Em contas gerenciadas por administrador, o admin precisa habilitar
a geração de API keys (governança). Isso é um pré-requisito operacional que
deve ser documentado em US-06 como parte dos pré-requisitos do operador.
Ver: [kiro.dev/docs/cli/enterprise/governance/api-keys](https://kiro.dev/docs/cli/enterprise/governance/api-keys/).

**R-1 — Continuidade de sessão:**
Risco originalmente levantado como potencialmente bloqueador. **Fechado:** a
documentação oficial confirma que `--list-sessions` e `--resume-id` funcionam
normalmente com `KIRO_API_KEY`. O armazenamento SQLite local (`~/.kiro/`) é
independente do método de autenticação. A validação em AC-04 confirma e
documenta o plano de degradação caso testes reais evidenciem comportamento
diferente.

---

## US-03 — Orquestrar com docker-compose

**Como** analista/operador,
**quero** um `docker-compose.yml` que suba a esteira completa com um único
`docker compose up`,
**para** não precisar lembrar flags de `docker run` e ter toda a configuração
de volumes e variáveis documentada em código.

### Rastreabilidade

RNF-04; épico "Configuração e segredos por fora (docker-compose)".

### Critérios de aceitação

#### AC-01 — Volumes de configuração (read-only)

| Caminho no container | Origem no host        | Permissão     |
|----------------------|-----------------------|---------------|
| `/app/pipe.yml`      | `./pipe.yml` do host  | somente leitura |
| `/app/contexts/`     | `./contexts/` do host | somente leitura |

#### AC-02 — Volumes de estado (persistência entre reinícios)

| Caminho no container          | Volume nomeado   | Descrição                                   |
|-------------------------------|------------------|---------------------------------------------|
| `/app/repo/`                  | `pipe-repo`      | Clones de repositório                       |
| `/app/logs/`                  | `pipe-logs`      | Logs de execução                            |
| `/app/.pipe/`                 | `pipe-state`     | Estado da esteira (fila, snapshots, sessões) |
| `~/.kiro/`                    | `kiro-home`      | Sessões e configurações do kiro-cli (SQLite) |
| `~/.local/share/kiro-cli/`    | `kiro-local`     | Índice SQLite de sessões do kiro-cli         |

**Rationale dos volumes kiro:** o kiro-cli armazena o banco de sessões em
`~/.kiro/` e o índice SQLite em `~/.local/share/kiro-cli/`, ambos keyed por
cwd. Sem esses volumes, cada reinício do container perde o histórico de sessões
e a continuidade de raciocínio do agente (`.pipe/sessions.json` apontaria para
IDs inexistentes, gerando novas sessões a cada reinício — funcional, mas sem
retomada de contexto).

#### AC-03 — Variáveis de ambiente

| Variável         | Descrição                                                              |
|------------------|------------------------------------------------------------------------|
| `PIPE_SSH_KEY_FILE` | Caminho da chave SSH dentro do container (ex.: `/run/secrets/ssh_key`) |
| `GH_TOKEN`       | Personal Access Token do GitHub (escopos: `repo`, `project`)          |
| `KIRO_API_KEY`   | API key do kiro-cli para modo headless (requer plano Pro ou superior)  |

#### AC-04 — Chave SSH como Docker secret

- A chave SSH é declarada como Docker secret no `docker-compose.yml`.
- O secret é montado em `/run/secrets/ssh_key` (somente leitura) dentro do
  container.
- `PIPE_SSH_KEY_FILE=/run/secrets/ssh_key` aponta para esse caminho.

#### AC-05 — Arquivo .env

- `docker-compose.yml` usa referências `${GH_TOKEN}`, `${KIRO_API_KEY}` etc.,
  lidas de `.env` do host.
- Um arquivo `.env.example` documenta todas as variáveis necessárias com
  descrição e exemplo (sem valores reais).
- O `.env` real está listado no `.gitignore`.
- O `docker-compose.yml` está versionado no repositório.

---

## US-04 — Execução autônoma sem prompts interativos

**Como** analista/operador,
**quero** que o loop principal rode sem nenhuma interação humana durante a
execução,
**para** poder operar o container em servidor sem monitoramento constante.

### Rastreabilidade

Épico "Operação autônoma sem humano".

### Critérios de aceitação

- `python -m src` não exibe nenhum prompt interativo durante a execução normal.
- Em caso de configuração incorreta (ex.: `pipe.yml` inválido,
  `PIPE_SSH_KEY_FILE` não definido), o processo termina com código de saída
  não-zero e mensagem de erro clara nos logs — sem travar silenciosamente.
- O container permanece rodando o loop ininterruptamente enquanto aguarda
  `need_human`; a intervenção humana ocorre no board do GitHub (mover o card),
  não no container.
- O kiro-cli é invocado com `--no-interactive --trust-all-tools` (já
  implementado em `kiro_cli_agent.py:_run`); nenhum prompt de aprovação de
  ferramenta interrompe a execução.

---

## US-05 — Falha clara no arranque

**Como** analista/operador,
**quero** que o container falhe imediatamente com mensagem de erro descritiva
se a configuração mínima estiver ausente,
**para** detectar problemas no arranque e não desperdiçar tempo debugando um
container travado silenciosamente.

### Rastreabilidade

Épico "Operação autônoma sem humano".

### Critérios de aceitação

- Se `PIPE_SSH_KEY_FILE` não estiver definido → `SystemExit(1)` com mensagem
  `Variável de ambiente 'PIPE_SSH_KEY_FILE' não definida ou vazia`.
  *(Comportamento já implementado em `config.py:_validate_env`.)*
- Se `PIPE_SSH_KEY_FILE` apontar para arquivo inexistente → `SystemExit(1)`
  com mensagem `Arquivo SSH não encontrado: <caminho>`.
  *(Comportamento já implementado.)*
- Se `pipe.yml` não for encontrado ou for inválido → `SystemExit(1)` com
  mensagem descritiva.
  *(Comportamento já implementado.)*
- Se `GH_TOKEN` não estiver definido → falha na primeira chamada de board com
  mensagem de erro identificável no log (comportamento lazy, não no startup).
- Se `KIRO_API_KEY` não estiver definido → falha na primeira execução de
  agente com mensagem de erro identificável no log (comportamento lazy, não no
  startup).
- Em nenhum caso o processo trava silenciosamente aguardando input do
  operador.

---

## US-06 — Documentação de operação

**Como** analista/operador novo,
**quero** uma documentação enxuta com pré-requisitos, variáveis/segredos
necessários e passo a passo de subida,
**para** colocar a esteira para rodar em Docker sem conhecimento prévio do
código.

### Rastreabilidade

Épico "Documentação de operação".

### Critérios de aceitação

- Existe `doc/runbook/docker.md` cobrindo:
  - Pré-requisitos do host: Docker instalado, conta GitHub com PAT,
    conta Kiro com plano Pro ou superior e API key gerada.
  - Lista de variáveis/segredos com descrição, escopo de permissões necessário
    e onde obter:
    - `PIPE_SSH_KEY_FILE`: caminho do arquivo de chave SSH privada
    - `GH_TOKEN`: PAT com escopos `repo` e `project`
    - `KIRO_API_KEY`: gerada em app.kiro.dev (requer Pro+)
  - Passo a passo de subida (`docker compose up`).
  - Como verificar que está rodando (`docker logs`, `docker compose ps`).
  - Como parar (`docker compose down`).
  - Nota sobre governança de API key em contas administradas (R-3).

---

## Matriz de dependências entre stories

| Story  | Depende de       | Habilita                     |
|--------|------------------|------------------------------|
| US-01  | —                | US-02, US-03, US-04, US-05, US-06 |
| US-02  | US-01            | US-03                        |
| US-03  | US-01, US-02     | US-04, US-06                 |
| US-04  | US-01, US-02, US-03 | —                         |
| US-05  | US-01            | —                            |
| US-06  | US-01, US-02, US-03 | —                         |

US-01 é a story-base da feature. Todas as demais dependem dela.
