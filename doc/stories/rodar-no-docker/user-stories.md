# User Stories — Rodar no Docker

Status: draft
Owner: requisitos
Last updated: 2026-07-07

## Inputs

- Issue #1 "Rodar no Docker"
- Issue #16 "Empacotar a esteira em imagem Docker"
- doc/product/rodar-no-docker/vision.md
- doc/product/rodar-no-docker/problem-space.md
- doc/product/rodar-no-docker/epicos.md
- src/__main__.py (`_setup_ssh`, `startup`)
- src/core/config.py (`check_config`, `SSH_KEY_ENV`)
- src/adapters/kiro_cli_agent.py (`_run`, `_session_exists`, `_list_session_ids`)
- CONTEXT.md (seções: Execução de Agentes, Sessão do agente)
- README.md (seções: Configuração, Uso)

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
  - O kiro-cli armazena sessões e configurações em `~/.kiro/` e
    `~/.local/share/kiro-cli/` (SQLite de sessões, keyed por cwd).
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

O kiro-cli armazena sessões em SQLite dentro de `~/.kiro/` (KIRO_HOME) e o
índice em `~/.local/share/kiro-cli/`, keyed por cwd (diretório de trabalho do
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

## US-02 — Injetar credenciais e configuração pelo docker-compose

**Como** analista/operador,
**quero** fornecer todos os segredos e configurações por fora da imagem,
**para** não embutir nenhum valor sensível no container e poder trocar credenciais
sem rebuild.

### Rastreabilidade

RNF-01, RNF-03; ADR-05, ADR-06.
Épico: "Configuração e segredos por fora (docker-compose)".

### Critérios de aceitação

#### AC-01 — Variáveis de ambiente obrigatórias (injetadas em runtime)

| Variável | Descrição |
|---|---|
| `PIPE_SSH_KEY_FILE` | Caminho da chave SSH dentro do container (ex.: `/run/secrets/ssh_key`) |
| `GH_TOKEN` | Token do GitHub (usado pelo `gh` CLI) |
| `KIRO_API_KEY` | API key do kiro-cli para modo headless |

#### AC-02 — Arquivos montados via volume

| Caminho no container | Origem no host | Permissão |
|---|---|---|
| `/app/pipe.yml` | `./pipe.yml` do host | somente leitura |
| `/app/contexts/` | `./contexts/` do host | somente leitura |

#### AC-03 — Volumes de estado (persistência entre reinícios)

| Caminho no container | Volume nomeado | Descrição |
|---|---|---|
| `/app/repo/` | `pipe-repo` | Clones de repositório |
| `/app/logs/` | `pipe-logs` | Logs de execução |
| `/app/.pipe/` | `pipe-state` | Estado da esteira (fila, snapshots, sessões) |
| `~/.kiro/` | `kiro-home` | Configurações e sessões do kiro-cli |
| `~/.local/share/kiro-cli/` | `kiro-local` | Índice SQLite de sessões do kiro-cli |

#### AC-04 — Segredos

- A chave SSH deve ser passada como Docker secret ou arquivo montado em modo
  somente leitura; não deve aparecer em variável de ambiente legível em
  `docker inspect`.
- Nenhuma variável de ambiente sensível é hardcoded no `docker-compose.yml`
  (usa referências `${VAR}` lidas do `.env` do host, que está em `.gitignore`).

### Fora de escopo desta US

- Implementação do `docker-compose.yml` (pertence à US de orquestração).
- Escolha de tecnologia de gestão de segredos além do Docker secrets básico.

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

- `docker compose up` sobe o container com todos os volumes e variáveis de
  US-02 declarados.
- O arquivo `docker-compose.yml` está versionado no repositório.
- Um arquivo `.env.example` documenta todas as variáveis necessárias com
  descrição; o `.env` real está no `.gitignore`.

---

## US-04 — Execução autônoma sem prompts interativos

**Como** analista/operador,
**quero** que o loop principal rode sem nenhuma interação humana durante a
execução,
**para** poder operar o container em servidor sem monitoramento constante.

### Rastreabilidade

Épico "Operação autônoma sem humano".

### Critérios de aceitação

- `python -m src` não exibe nenhum prompt interativo (nenhuma pergunta ao
  operador) durante a execução normal.
- Em caso de configuração incorreta (ex.: `pipe.yml` inválido, `PIPE_SSH_KEY_FILE`
  não definido), o processo termina com código de saída não-zero e mensagem de
  erro clara nos logs — sem travar silenciosamente.
- O container permanece rodando o loop ininterruptamente enquanto aguarda
  `need_human`; a intervenção humana ocorre no board do GitHub, não no container.

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

- Se `PIPE_SSH_KEY_FILE` não estiver definido, o processo termina com `SystemExit(1)`
  e mensagem `Variável de ambiente 'PIPE_SSH_KEY_FILE' não definida ou vazia`.
  (Comportamento já implementado em `config.py:_validate_env`.)
- Se `KIRO_API_KEY` não estiver definido e o kiro-cli não tiver sessão
  autenticada persistida, o processo falha na primeira tentativa de executar um
  agente com mensagem de erro identificável no log.
- Se `pipe.yml` não for encontrado ou for inválido, o processo termina com
  `SystemExit(1)` e mensagem descritiva.

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

- Existe um arquivo `doc/runbook/docker.md` (ou equivalente no README) cobrindo:
  - Pré-requisitos do host (Docker, credenciais).
  - Lista de variáveis/segredos com descrição.
  - Passo a passo de subida (`docker compose up`).
  - Como verificar que está rodando (`docker logs`, `docker compose ps`).
  - Como parar (`docker compose down`).

---

## Matriz de dependências

| Story | Depende de | Habilita |
|---|---|---|
| US-01 | — | US-02, US-03, US-04, US-05, US-06 |
| US-02 | US-01 | US-03 |
| US-03 | US-01, US-02 | US-04, US-06 |
| US-04 | US-01, US-02, US-03 | — |
| US-05 | US-01 | — |
| US-06 | US-01, US-02, US-03 | — |

US-01 é a story-base da feature. Todas as demais dependem dela.
