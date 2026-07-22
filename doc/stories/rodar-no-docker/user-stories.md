# User Stories — Rodar no Docker

Status: em andamento
Owner: produto + engenharia
Last updated: 2026-07-22

## Referências

- `doc/product/rodar-no-docker/vision.md` — visão e problema
- `doc/product/rodar-no-docker/epicos.md` — épicos
- `doc/product/rodar-no-docker/problem-space.md` — espaço do problema
- `doc/stories/rodar-no-docker/arquitetura.md` — decisões técnicas

---

## US-01 — Imagem Docker da esteira

**Como** operador da esteira,
**quero** uma imagem Docker que empacote a esteira e todas as suas dependências,
**para** poder rodar `python -m src` dentro do container sem preparação manual do host.

### Critérios de aceitação

- AC-01: A imagem contém Python 3.12+, Git, GitHub CLI (`gh`), `kiro-cli` e `pyyaml`.
- AC-02: `docker build .` constrói a imagem sem erros.
- AC-03: `docker run pipe python -m src --help` (ou equivalente de validação) não falha por dependência ausente.
- AC-04: A imagem não contém segredos embutidos (chave SSH, tokens).
- AC-05: `WORKDIR /app` declarado; código da esteira em `/app/src/`.

### Notas de implementação

- Dockerfile na raiz do repositório.
- Dependências: `python:3.12-slim` como base, `apt` para git/ssh/curl/jq, `gh` baixado como binário, `kiro-cli` copiado do host via `prepare-docker.sh`.
- Ver `doc/stories/rodar-no-docker/arquitetura.md` §2 para decisões de dependência.

---

## US-02 — Injeção de credenciais via docker-compose

**Como** operador da esteira,
**quero** injetar credenciais (token GitHub, chave SSH) via docker-compose sem reconstruir a imagem,
**para** poder trocar credenciais sem um `docker build`.

### Critérios de aceitação

- AC-01: `GH_TOKEN` lido de variável de ambiente (`.env` ou export).
- AC-02: Chave SSH do host montada como arquivo no container (path configurável).
- AC-03: `PIPE_SSH_KEY_FILE` aponta para o caminho interno da chave no container.
- AC-04: Nenhum segredo hardcoded no `docker-compose.yml`.
- AC-05: Configuração do `gh` CLI (`~/.config/gh`) montada como read-only.

---

## US-03 — Configuração via docker-compose sem rebuild

**Como** operador da esteira,
**quero** injetar `pipe.yml` e `contexts/` via volumes no docker-compose,
**para** poder alterar a configuração da esteira sem reconstruir a imagem.

### Critérios de aceitação

- AC-01: `pipe.yml` montado como volume read-only em `/app/pipe.yml`.
- AC-02: `contexts/` montado como volume em `/app/contexts`.
- AC-03: Trocar `pipe.yml` no host + `docker compose up -d` aplica a nova config sem `docker build`.
- AC-04: `docker compose config` valida sem erros.

---

## US-04 — Persistência de estado entre reinícios

**Como** operador da esteira,
**quero** que o estado de runtime (snapshots, sessões de agente, clones git, logs) seja preservado entre reinícios do container,
**para** não perder continuidade de raciocínio dos agentes nem precisar refazer clones a cada subida.

### Critérios de aceitação

- AC-01: `docker compose down && docker compose up` preserva arquivos em `.pipe/`, `repo/` e `logs/` no host.
- AC-02: Os três diretórios de estado são configuráveis por variável de ambiente (`PIPE_STATE_DIR`, `PIPE_REPO_DIR`, `PIPE_LOGS_DIR`).
- AC-03: Sem as variáveis definidas no `.env`, o compose usa defaults ao lado do compose (`./`, `./repo`, `./logs`).
- AC-04: Bind mounts usados para estado (não named volumes) — o operador pode inspecionar/auditar o estado no host.
- AC-05: `compose.ephemeral.yml` disponível para modo efêmero (CI, testes).
- AC-06: Nenhum bind mount aponta para `/app` inteiro (D-05 — preservaria o código da imagem).

### Tabela de estado de runtime

| Diretório container | Variável host | Default | Política | Impacto se perdido |
|---------------------|---------------|---------|----------|--------------------|
| `/app/.pipe` | `PIPE_STATE_DIR` | `./.pipe` | PRESERVAR | Re-sync completo; perde continuidade de raciocínio dos agentes |
| `/app/repo` | `PIPE_REPO_DIR` | `./repo` | REUSAR | Re-clone de todos os repositórios |
| `/app/logs` | `PIPE_LOGS_DIR` | `./logs` | ACUMULAR | Perda de histórico (operação segue normal) |

### Contrato D-05 (bind mounts de estado)

O contrato D-05 define que:
1. Bind mounts mapeiam **subdiretórios específicos** (`/app/.pipe`, `/app/repo`, `/app/logs`), **nunca** `/app` inteiro.
2. Defaults inline no compose (`${VAR:-./default}`) garantem funcionamento sem `.env`.
3. O modo persistente é o **default** — efêmero é opt-in explícito via `compose.ephemeral.yml`.

### Notas de implementação

- Ver `doc/stories/rodar-no-docker/arquitetura.md` §4 para decisão ADR-04 (bind mounts vs named volumes).
- Ver `doc/stories/rodar-no-docker/ux/prototipos/docker-compose.prototipo.yml` para modelo anotado.
- Ver `doc/stories/rodar-no-docker/ux/prototipos/.env.prototipo` para variáveis de estado.

---

## US-05 — Operação autônoma e restart automático

**Como** operador da esteira,
**quero** que o container reinicie automaticamente após crash ou reboot do host,
**para** que a esteira opere sem supervisão manual.

### Critérios de aceitação

- AC-01: `restart: unless-stopped` declarado no serviço `pipe`.
- AC-02: `docker compose stop` para o container sem restart automático.
- AC-03: Após reboot do host com Docker configurado para iniciar automaticamente, o container sobe sem intervenção.

---

## US-06 — Documentação de operação

**Como** novo operador da esteira,
**quero** um runbook claro com pré-requisitos, passos de subida e verificação,
**para** colocar a esteira para rodar em Docker sem conhecimento prévio do código.

### Critérios de aceitação

- AC-01: Runbook cobre pré-requisitos (Docker, `gh auth login`, chave SSH, token GitHub).
- AC-02: Passo a passo de subida com comandos copiáveis.
- AC-03: Seção de verificação (como confirmar que está rodando).
- AC-04: Distinção entre `docker compose down` e `docker compose down -v` com aviso de perda de estado.
- AC-05: Um usuário novo consegue colocar a esteira para rodar seguindo apenas o runbook.
