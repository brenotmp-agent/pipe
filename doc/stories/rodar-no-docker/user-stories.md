# User Stories — Rodar no Docker

Status: draft
Owner: product
Last updated: 2026-07-07

## Inputs
- doc/product/rodar-no-docker/epicos.md
- doc/product/rodar-no-docker/vision.md
- doc/product/rodar-no-docker/problem-space.md
- README.md
- CONTEXT.md (ADR-04 referenciado nos requisitos de US-04)
- src/__main__.py (startup, REPO_DIR, QUEUE_FILE)
- src/core/config.py (CONTEXTS_DIR, SSH_KEY_ENV)
- src/core/change_queue.py (QUEUE_FILE)
- src/core/session.py (SessionIndex, .pipe/sessions.json)

---

## US-01 — Imagem Docker da esteira

**Como** operador,
**quero** uma imagem Docker com a esteira e todas as suas dependências (Python
3.12+, Git, GitHub CLI, kiro-cli),
**para** executar `python -m src` sem preparar o host manualmente.

### Critérios de aceitação

- A imagem contém Python 3.12+, Git, GitHub CLI (`gh`) e kiro-cli.
- `docker run <imagem>` executa `python -m src` como entrypoint.
- Nenhum segredo está embutido na imagem (chave SSH, token GitHub, credencial
  kiro-cli).
- A imagem é construída a partir do código-fonte do repositório.

### Fora de escopo
- Publicação em registries (Docker Hub, GHCR, ECR).
- Otimização de tamanho da imagem.

---

## US-02 — Injeção de configuração via compose

**Como** operador,
**quero** fornecer o `pipe.yml` e os `contexts/` montando arquivos/diretórios
no compose,
**para** não precisar reconstruir a imagem ao mudar configuração.

### Critérios de aceitação

- O `pipe.yml` é montado como bind mount read-only no container (ex.:
  `./pipe.yml:/app/pipe.yml:ro`).
- O diretório `contexts/` é montado como bind mount read-only (ex.:
  `./contexts:/app/contexts:ro`).
- A esteira lê `pipe.yml` e `contexts/` de dentro do container, não de dentro
  da imagem.

### Fora de escopo
- Geração automática de `pipe.yml` ou `contexts/`.

---

## US-03 — Injeção de segredos via compose

**Como** operador,
**quero** fornecer a chave SSH, a credencial do GitHub e a autenticação do
kiro-cli via compose (variáveis de ambiente e/ou bind mounts),
**para** não precisar acessar o container para autenticar manualmente.

### Critérios de aceitação

- A chave SSH privada é montada no container e apontada por
  `PIPE_SSH_KEY_FILE` (variável de ambiente lida por
  `src/core/config.py`:`SSH_KEY_ENV`).
- O `gh` CLI encontra sua credencial no container (ex.: token via variável
  `GH_TOKEN` ou bind mount do arquivo de configuração do `gh`).
- O kiro-cli encontra sua autenticação no container (ex.: bind mount de
  `~/.kiro` do host ou variável de ambiente equivalente).
- A esteira passa pelo `check_config()` e chega ao `startup()` sem erro de
  credencial.

### Fora de escopo
- Gestão de segredos por vault (HashiCorp Vault, AWS Secrets Manager, etc.).
- Rotação automática de credenciais.
- Definição de como o kiro-cli autentica em ambiente headless (a validar —
  issue separada).

---

## US-04 — Persistir estado de runtime entre reinícios

**Como** operador,
**quero** persistir `.pipe/`, `logs/` e `repo/` via volumes,
**para** preservar snapshots, fila, sessões e clones entre reinícios do
container.

### Contexto

A esteira acumula estado de runtime em três diretórios:

| Diretório | Conteúdo | Impacto se perdido |
|-----------|----------|--------------------|
| `.pipe/` | Snapshots de boards (`boards/<id>/snapshot.json`), fila de mudanças (`changeQueue.json`), índice de sessões (`sessions.json`), throttle | Re-sync completo no arranque; perda da continuidade de raciocínio do agente |
| `repo/` | Clones git dos repositórios configurados em `git.repo` | Re-clone de todos os repositórios no arranque |
| `logs/` | Logs diários (JSON) e logs de execução de agente (MD) | Perda de histórico de execução |

A persistência é **opcional por design**: sem volumes, a esteira opera em modo
efêmero (estado zerado a cada `docker compose up`) sem erro — ideal para
ambientes de CI ou testes isolados.

### Comportamento do `startup()` com volumes

O `startup()` (`src/__main__.py`) já foi projetado para coexistir com estado
pré-existente:

- **`.pipe/changeQueue.json`**: **sempre apagada** no startup, mesmo com
  volume. Justificativa: a fila representa intenções de sync de uma execução
  anterior que pode ter ficado num estado inconsistente. O `board_full_sync()`
  subsequente detecta o estado real do board e repovoará a fila corretamente.
  O snapshot (`.pipe/boards/`) é preservado e usado como baseline para o
  `board_full_sync()`, evitando re-sync completo.
- **`.pipe/sessions.json`**: **preservado** entre reinícios. O startup não o
  apaga. Com o índice preservado, o agente retoma o raciocínio da sessão
  anterior ao continuar uma issue pausada.
- **`repo/<id>`**: se o diretório do repositório já existe, o `startup()` não
  reclona (apenas clona o que está faltando, remove o que não está na config).
  Não faz `git pull` automático — o código clonado é usado como está.
- **`logs/`**: acumulados entre reinícios. A limpeza segue o TTL configurado
  em `log.ttl` (dias).

### Critérios de aceitação

- O compose declara bind mounts opcionais para `.pipe/`, `logs/` e `repo/`.
- Com os volumes configurados e presentes no host, executar
  `docker compose down && docker compose up` preserva o estado anterior:
  - `.pipe/boards/` (snapshots) sobrevive → não há re-sync completo.
  - `.pipe/sessions.json` sobrevive → continuidade de raciocínio do agente.
  - `repo/<id>` sobrevive → não há re-clone.
  - `logs/` sobrevive → histórico de execução preservado.
- Sem os volumes configurados (bind mounts ausentes ou comentados), a esteira
  sobe em modo efêmero sem erro: faz sync completo, reclona repos, inicia
  sessões novas.
- A remoção dos bind mounts não requer alteração na imagem ou no código.

### Fora de escopo

- Estratégia de backup dos volumes (snapshots, repos, logs).
- Operação multi-instância da esteira (dois containers compartilhando os
  mesmos volumes).
- Sincronização do `repo/` com o remoto no arranque (ex.: `git pull`
  automático) — responsabilidade do agente via gitevents.

### Referências técnicas

- RF-06: preservação de estado entre reinícios.
- D-04: modo efêmero sem volumes deve funcionar sem erro.
- ADR-04: decisão de tornar a persistência opcional (volumes como opt-in).
- `src/__main__.py` → `startup()`: comportamento com estado pré-existente.
- `src/core/change_queue.py` → `QUEUE_FILE`: fila apagada no startup.
- `src/core/session.py` → `SessionIndex`: sessions.json preservado.

---

## US-05 — Documentação de operação

**Como** operador novo,
**quero** uma documentação clara de pré-requisitos, variáveis/segredos e
passo a passo de subida,
**para** colocar a esteira para rodar sem conhecimento prévio do código.

### Critérios de aceitação

- A documentação lista todos os pré-requisitos do host (Docker, Docker Compose,
  chave SSH, token GitHub, credencial kiro-cli).
- A documentação descreve todas as variáveis de ambiente e bind mounts
  necessários.
- A documentação inclui o passo a passo completo: clonar o repositório,
  preparar credenciais, configurar `pipe.yml`, executar `docker compose up`.
- A documentação descreve como verificar que a esteira está rodando
  corretamente (logs, comportamento esperado no arranque).
- Um usuário novo consegue colocar a esteira para rodar seguindo apenas a
  documentação, sem consultar o código.

### Fora de escopo
- Documentação interna de arquitetura da solução Docker.
- Guias específicos por plataforma de nuvem (AWS, GCP, Azure).
