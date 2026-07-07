# User Stories — Rodar no Docker

Status: draft
Owner: requisitos
Last updated: 2026-07-07

## Inputs

- Issue #1 "Rodar no Docker"
- Issue #16 "Empacotar a esteira em imagem Docker"
- Issue #17 "Autenticar dependências externas em modo headless"
- Issue #18 "Configurar a esteira via docker-compose sem rebuild"
- Issue #21 "Documentar a operação em Docker"
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
- kiro.dev/docs/cli/chat/session-management/ (documentação oficial sessões — confirma: SQLite em `~/.kiro/`, keyed por diretório)
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
  - O kiro-cli armazena sessões em `~/.kiro/` (banco SQLite, keyed por cwd —
    confirmado pela documentação oficial em kiro.dev/docs/cli/chat/session-management/).
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

O kiro-cli armazena sessões em SQLite dentro de `~/.kiro/`, keyed por cwd
(diretório de trabalho do `subprocess.run` — que é o clone do repositório em
`repo/<repo_id>`). Confirmado pela documentação oficial:
> "Storage: SQLite database in `~/.kiro/`; Scope: Sessions keyed by directory path"
> — kiro.dev/docs/cli/chat/session-management/ (Maio 2026)

Para que sessões sobrevivam entre reinícios do container, o volume `kiro-home`
(declarado em US-03) deve cobrir `~/.kiro/`.

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

## US-03 — Configurar a esteira via docker-compose sem rebuild

**Como** analista/operador,
**quero** declarar toda a configuração e todos os segredos no `docker-compose`,
**para** trocar a configuração sem reconstruir a imagem e sem nada sensível
fixado nela.

### Rastreabilidade

RF-05, RNF-01, RNF-03, RNF-04; ADR-01, ADR-02, ADR-03; ADR-06.
Épico: "Configuração e segredos por fora (docker-compose)".

**RF-05** — Toda configuração declarável no compose sem rebuild da imagem.
**RNF-01** — Nenhum segredo embutido na imagem.
**RNF-03** — Credenciais injetáveis via env/volume, nunca hardcoded no compose.
**RNF-04** — `docker compose up` como único comando necessário para subir a esteira.

### Critérios de aceitação

#### AC-01 — Arquivo docker-compose.yml versionado

- Existe um `docker-compose.yml` na raiz do repositório.
- O arquivo está versionado (commit); não contém valores de segredos hardcoded.
- O compose funciona com `docker compose` V2 (plugin — sem hífen). Compatibilidade
  com `docker-compose` V1 (deprecated) não é requisito.

#### AC-02 — Volumes de configuração (read-only)

| Caminho no container | Origem no host        | Permissão       |
|----------------------|-----------------------|-----------------|
| `/app/pipe.yml`      | `./pipe.yml` do host  | somente leitura |
| `/app/contexts/`     | `./contexts/` do host | somente leitura |

- Alterando `./pipe.yml` ou `./contexts/` no host e fazendo `docker compose up`
  (sem rebuild), a nova configuração entra em vigor — **sem** `docker build`.

#### AC-03 — Chave SSH como Docker secret (ADR-03)

- A chave SSH privada é declarada como Docker secret no `docker-compose.yml`.
- O secret é montado em `/run/secrets/ssh_key` (somente leitura) dentro do
  container.
- A variável de ambiente `PIPE_SSH_KEY_FILE=/run/secrets/ssh_key` aponta para
  esse caminho; `_setup_ssh()` faz a cópia interna para `~/.ssh/id_pipe`.
- O operador fornece o arquivo de chave SSH no host; o compose o injeta sem
  copiá-lo para a imagem.

#### AC-04 — Variáveis de ambiente obrigatórias

| Variável            | Fonte          | Descrição                                              |
|---------------------|----------------|--------------------------------------------------------|
| `PIPE_SSH_KEY_FILE` | `.env` do host | Caminho interno da chave SSH (`/run/secrets/ssh_key`)  |
| `GH_TOKEN`          | `.env` do host | PAT do GitHub (escopos: `repo`, `project`) — ADR-02    |
| `KIRO_API_KEY`      | `.env` do host | API key headless do kiro-cli (requer Pro+) — ADR-01    |

- O `docker-compose.yml` usa referências `${VARIAVEL}` lidas de `.env` do host.
- Nenhum valor real aparece no `docker-compose.yml` ou em arquivos versionados.

#### AC-05 — Arquivo .env.example

- Existe `.env.example` na raiz do repositório com todas as variáveis necessárias,
  descrição de cada uma e exemplos de valor (sem valores reais).
- O `.env` real está listado no `.gitignore`.
- O `.env.example` está versionado.

#### AC-06 — Sem rebuild ao trocar configuração (RF-05 — critério central)

- `docker compose up` com um `pipe.yml` diferente → a esteira inicia com a nova
  configuração **sem necessidade de `docker build`**.
- `docker compose up` com um `GH_TOKEN` diferente → a esteira usa o novo token
  **sem rebuild**.
- Único caso que exige rebuild: alteração do código-fonte da esteira (`src/`) ou
  de dependências do Dockerfile (ex.: nova versão do kiro-cli). Configuração e
  segredos nunca exigem rebuild.

#### AC-07 — Volumes de estado (escopo desta US: declarar no compose)

Os volumes abaixo devem estar **declarados** no `docker-compose.yml`. A
semântica de persistência (comportamento ao down/up) é validada em US-04; esta
US garante apenas que o compose os declara corretamente.

| Caminho no container | Volume nomeado | Descrição                                         |
|----------------------|----------------|---------------------------------------------------|
| `/app/repo/`         | `pipe-repo`    | Clones de repositório git                         |
| `/app/logs/`         | `pipe-logs`    | Logs de execução                                  |
| `/app/.pipe/`        | `pipe-state`   | Estado da esteira (fila, snapshots, sessões)       |
| `~/.kiro/`           | `kiro-home`    | Banco SQLite de sessões do kiro-cli (keyed por cwd) |

**Nota sobre `~/.kiro/`:** a documentação oficial do kiro-cli confirma que todas
as sessões são armazenadas em SQLite em `~/.kiro/`, com escopo por diretório
(`cwd` do processo). O `~` é o HOME do usuário que executa o container (usuário
não-root definido em ADR-05). Sem este volume, cada reinício do container perde
o histórico de sessões e a continuidade de raciocínio do agente (`.pipe/sessions.json`
apontaria para IDs inexistentes, gerando novas sessões a cada reinício —
funcional, mas sem retomada de contexto).

**Esclarecimento de escopo:** a política de `restart: unless-stopped` e a
validação do comportamento de persistência ao `docker compose down && up`
pertencem a US-04 e US-05, que convivem no mesmo `docker-compose.yml` entregue
aqui.

### Fora de escopo desta US

- Persistência de estado validada (verificar que o estado sobrevive ao down/up) → US-04.
- Política de restart do container (`restart: unless-stopped`) → US-05.
- Validação do comportamento autônomo e fail-fast → US-05.
- Publicação da imagem em registry.
- Escolha de tecnologia avançada de gestão de segredos (Vault, AWS Secrets
  Manager etc.).

### Notas de implementação

#### Estrutura de referência do docker-compose.yml

```yaml
services:
  pipe:
    image: pipe:latest          # imagem construída por US-01
    env_file: .env              # GH_TOKEN, KIRO_API_KEY, PIPE_SSH_KEY_FILE
    environment:
      - PIPE_SSH_KEY_FILE=/run/secrets/ssh_key
    volumes:
      - ./pipe.yml:/app/pipe.yml:ro
      - ./contexts:/app/contexts:ro
      - pipe-repo:/app/repo
      - pipe-logs:/app/logs
      - pipe-state:/app/.pipe
      - kiro-home:/home/pipe/.kiro
    secrets:
      - ssh_key
    # restart, healthcheck etc. definidos em US-04/US-05

secrets:
  ssh_key:
    file: ${SSH_KEY_FILE_HOST}  # caminho do arquivo no host, via .env

volumes:
  pipe-repo:
  pipe-logs:
  pipe-state:
  kiro-home:
```

> **Nota:** este é um design de referência para orientar a implementação. Os
> valores de versão, usuário não-root e outras configurações de segurança são
> definidos no Dockerfile (US-01) e validados em US-04/US-05.

#### Por que Docker secrets para a chave SSH?

O Docker secrets monta o arquivo diretamente em `/run/secrets/<nome>` com
permissões `0400` (somente leitura do dono). Isso é preferível a um bind mount
`ro` porque: (1) o arquivo não aparece no filesystem do container fora do ponto
de montagem, e (2) o secret não é exposto em variável de ambiente (mais seguro
que injetar o conteúdo da chave como env var).

#### Mudança de configuração sem rebuild — mecanismo

A imagem (US-01) não contém `pipe.yml` nem `contexts/`. O container monta esses
arquivos em runtime via volumes bind-mount (AC-02). Basta editar os arquivos no
host e fazer `docker compose up` para a nova configuração entrar em vigor.
Credenciais (`GH_TOKEN`, `KIRO_API_KEY`) são variáveis de ambiente lidas do
`.env` em cada `docker compose up` — troca-se o `.env` e sobe novamente sem
rebuild.

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

RF-08, D-04; riscos R-3, R-4.
Épico "Documentação de operação".

### Critérios de aceitação

O guia `doc/runbook/docker.md`, versionado no repositório, cobre os seguintes
tópicos:

#### AC-01 — Pré-requisitos no host

- Docker Engine instalado + plugin `docker compose` V2 (sem hífen).
- Conta GitHub com Personal Access Token (PAT) criado.
- Conta Kiro com plano Pro, Pro+, Pro Max ou Power; API key gerada em
  `app.kiro.dev`. Em contas gerenciadas por administrador, o admin precisa
  habilitar geração de API keys (R-3). Referência:
  [kiro.dev/docs/cli/enterprise/governance/api-keys](https://kiro.dev/docs/cli/enterprise/governance/api-keys/).
- Chave SSH privada configurada no GitHub (para clone via SSH).

#### AC-02 — Estrutura do docker-compose.yml

- O guia descreve o `docker-compose.yml` com todos os parâmetros: variáveis de
  ambiente (`PIPE_SSH_KEY_FILE`, `GH_TOKEN`, `KIRO_API_KEY`), volumes
  (`pipe-repo`, `pipe-logs`, `pipe-state`, `kiro-home`), e Docker secret
  (`ssh_key`).
- O guia referencia o `.env.example` e explica como criar o `.env` local (sem
  versioná-lo).
- O guia explica que alterações em `pipe.yml` ou `contexts/` não exigem
  rebuild da imagem — basta `docker compose up`.

#### AC-03 — Passo a passo de subida

O guia descreve, em ordem, os passos para colocar a esteira a rodar:

1. Clonar o repositório.
2. Copiar `.env.example` para `.env` e preencher as variáveis.
3. Criar/ajustar `pipe.yml` e `contexts/`.
4. Construir a imagem: `docker compose build`.
5. Subir a esteira: `docker compose up -d`.

Cada passo inclui o comando exato e o resultado esperado.

#### AC-04 — Como verificar que está rodando

- `docker compose ps` → container com estado `Up`.
- `docker logs pipe -f` (ou `docker compose logs -f`) → log output esperado do
  ciclo do loop:
  - Linha de startup: `[Config] pipe.yml válido`
  - Linha de startup: `[Startup] Verificando repositórios`
  - Ciclo de sync: `[Board] Sincronizando boards remotos`
  - Ciclo ocioso: `[Main] Dormindo N segundos`
- O guia indica que a ausência de erros nas primeiras linhas confirma que as
  credenciais foram aceitas.

#### AC-05 — Parar e reiniciar preservando estado

- Parar: `docker compose down` (não destrói volumes nomeados).
- Reiniciar: `docker compose up -d` → o estado anterior é retomado:
  - `pipe-state` preserva fila de mudanças, snapshots e índice de sessões
    (`.pipe/sessions.json`).
  - `kiro-home` preserva o banco SQLite de sessões do kiro-cli (`~/.kiro/`),
    mantendo a continuidade de raciocínio dos agentes.
  - `pipe-repo` preserva os clones dos repositórios (evita re-clone).
- **Destruir o estado** (reset completo): `docker compose down -v` remove
  todos os volumes nomeados. O guia avisa explicitamente sobre a diferença
  entre `down` e `down -v`.

#### AC-06 — Rotação da KIRO_API_KEY (R-4)

O guia descreve o procedimento de rotação da `KIRO_API_KEY` sem perda de
continuidade:

1. Gerar nova API key em `app.kiro.dev` (a chave anterior permanece válida
   durante a troca).
2. Atualizar o valor de `KIRO_API_KEY` no arquivo `.env` do host.
3. Reiniciar o container: `docker compose up -d` (não requer rebuild).
4. Revogar a chave antiga em `app.kiro.dev`.

O guia nota que: (a) os volumes de estado não são afetados pela rotação;
(b) a documentação oficial recomenda rotação periódica de API keys e revogação
das que não estão em uso — ver
[kiro.dev/docs/cli/headless/#best-practices](https://kiro.dev/docs/cli/headless/#best-practices).

#### Critério de sucesso

Um usuário novo, sem conhecimento prévio do código, consegue colocar a esteira
para rodar seguindo apenas o `doc/runbook/docker.md` (RF-08 e métrica de
sucesso da vision).

### Fora de escopo desta US

- Documentação interna da arquitetura Docker (pertence às etapas técnicas,
  em `doc/architecture/rodar-no-docker/arquitetura.md`).
- Publicação da imagem em registry.
- CI/CD de build da imagem.
- Escolha de tecnologia avançada de gestão de segredos (Vault, AWS Secrets
  Manager, etc.).

---

## Matriz de dependências entre stories

| Story  | Depende de          | Habilita                              |
|--------|---------------------|---------------------------------------|
| US-01  | —                   | US-02, US-03, US-04, US-05, US-06     |
| US-02  | US-01               | US-03                                 |
| US-03  | US-01, US-02        | US-04, US-05, US-06                   |
| US-04  | US-01, US-02, US-03 | —                                     |
| US-05  | US-01, US-03        | —                                     |
| US-06  | US-01, US-02, US-03 | —                                     |

US-01 é a story-base da feature. Todas as demais dependem dela.

**Nota sobre US-03 e US-04/US-05:** as três stories materializam-se no mesmo
`docker-compose.yml`. US-03 entrega a estrutura base (volumes, envs, secrets,
.env.example); US-04 valida a persistência de estado ao down/up; US-05 adiciona
a política de restart e fail-fast. O arquivo evolui incrementalmente ao longo
das três stories.
