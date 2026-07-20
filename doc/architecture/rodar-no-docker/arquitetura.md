# Arquitetura — Rodar a esteira em Docker

Status: draft
Owner: arquitetura
Last updated: 2026-07-20

> **Escopo deste documento.** Documentação **interna** da arquitetura da solução
> Docker: decisões técnicas (ADRs), visão de componentes, modelo de estado,
> segurança e sequência de arranque. Complementa o guia operacional em
> [`doc/runbook/docker.md`](../../runbook/docker.md) (voltado ao operador) e
> materializa as decisões levantadas em
> [`doc/stories/rodar-no-docker/user-stories.md`](../../stories/rodar-no-docker/user-stories.md).

## Inputs

- `doc/product/rodar-no-docker/{vision,problem-space,epicos}.md`
- `doc/stories/rodar-no-docker/user-stories.md` (RF/RNF/ADR, US-01…US-06)
- `doc/runbook/docker.md` (guia operacional)
- Código: `src/__main__.py` (`startup`, `_setup_ssh`, `check_config`),
  `src/core/config.py` (`_validate_env`, `check_config`, `SSH_KEY_ENV`),
  `src/adapters/kiro_cli_agent.py` (`_run`, sessões)

---

## 1. Princípio de projeto: o simples que funciona

A esteira é um **processo único, de longa duração, single-tenant**: um loop
sequencial (`while running`) que sincroniza boards e dispara agentes, um de cada
vez. Não há concorrência interna, não há servidor de rede, não há estado
compartilhado entre réplicas. A arquitetura Docker foi dimensionada para esse
perfil e **deliberadamente evita** soluções desproporcionais:

| Decisão | Por quê (e o que foi evitado) |
|---------|-------------------------------|
| Um único serviço no `docker compose` | Não há o que orquestrar entre containers. Evita Kubernetes, Swarm, sidecars. |
| Imagem single-stage sobre `python:3.12-slim` | App é Python + 3 binários (git, gh, kiro-cli). Build multi-stage traria pouco ganho de tamanho e mais complexidade. |
| Docker secrets `file:` + variáveis de ambiente | Injeção nativa do compose, sem servidor de segredos. Evita Vault/AWS Secrets Manager (fora de escopo, ver §7). |
| Volumes nomeados para estado | Persistência local trivial. Evita banco externo ou storage de rede. |
| Sem healthcheck HTTP | O processo não expõe porta; a saúde é observada pelos logs do loop. Um healthcheck sintético seria cerimônia sem valor. |

Regra prática para evoluções futuras: **só adicione uma peça de infraestrutura
quando um requisito concreto a exigir** (ex.: publicar em registry, rodar em
CI, múltiplos tenants). Até lá, o desenho abaixo é suficiente.

---

## 2. Visão de contexto (host × container)

```
┌───────────────────────────── HOST (qualquer máquina com Docker) ──────────────────────────────┐
│                                                                                                 │
│   .env  ──────────────┐   (GH_TOKEN, KIRO_API_KEY, PIPE_SSH_KEY_FILE, SSH_KEY_FILE_HOST)        │
│   pipe.yml ───────────┤                                                                         │
│   contexts/  ─────────┤   fornecidos pelo operador, lidos em runtime                            │
│   id_ed25519 (SSH) ───┘                                                                         │
│           │                                                                                     │
│           │  docker compose up                                                                  │
│           ▼                                                                                     │
│   ┌──────────────────────── Container  (usuário não-root `pipe`) ───────────────────────────┐  │
│   │                                                                                          │  │
│   │   python -m src   ──►  loop principal (check_config → startup → sync → agentes)          │  │
│   │        │                                                                                 │  │
│   │        ├── git / openssh-client ───────────►  GitHub (clone/push via SSH)                │  │
│   │        ├── gh CLI  (GH_TOKEN)      ────────►  GitHub Projects V2 (board, GraphQL/REST)   │  │
│   │        └── kiro-cli (KIRO_API_KEY) ────────►  Kiro (execução de agente, headless)        │  │
│   │                                                                                          │  │
│   │   Montagens:  /run/secrets/ssh_key (ro) · /app/pipe.yml (ro) · /app/contexts (ro)        │  │
│   │   Volumes:    /app/repo · /app/logs · /app/.pipe · /home/pipe/.kiro                      │  │
│   └──────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

A esteira depende de **três integrações externas**, cada uma autenticada por um
mecanismo headless distinto (ver §5). Nenhum segredo vive na imagem; tudo entra
pelo host em runtime.

---

## 3. Decisões de arquitetura (ADRs)

Os ADRs abaixo consolidam e formalizam as decisões referenciadas na matriz de
requisitos (`user-stories.md`). Formato enxuto: contexto → decisão →
consequência.

### ADR-01 — Autenticação do kiro-cli via `KIRO_API_KEY` (headless)

- **Contexto.** Em container não há browser para o login interativo do kiro-cli.
- **Decisão.** Autenticar exclusivamente por `KIRO_API_KEY` (suporte headless
  oficial, kiro-cli ≥ 2.0). Injetada como variável de ambiente em runtime.
- **Consequência.** Requer assinatura Kiro Pro ou superior (risco **R-3**;
  contas gerenciadas exigem o admin habilitar geração de API keys). A
  continuidade de sessão (`--list-sessions`/`--resume-id`) permanece funcional
  com API key (risco **R-1** fechado). Falha é *lazy*: só ocorre na primeira
  execução de agente, não no arranque.

### ADR-02 — Autenticação do gh CLI via `GH_TOKEN`

- **Contexto.** As operações de board usam o `gh` CLI, que normalmente exige
  `gh auth login` interativo.
- **Decisão.** Fornecer `GH_TOKEN` (PAT com escopos `repo` e `project`) como
  variável de ambiente. O `gh` a reconhece automaticamente, sem `gh auth login`.
- **Consequência.** Zero interação. Falha é *lazy*: só na primeira chamada de
  board. Escopos insuficientes bloqueiam o gate `board.check_access` no arranque.

### ADR-03 — Chave SSH como Docker secret, copiada por `_setup_ssh`

- **Contexto.** O clone/push dos repositórios é via SSH; a chave privada é um
  segredo que não pode ir para a imagem nem para variável de ambiente.
- **Decisão.** Montar a chave como **Docker secret** em `/run/secrets/ssh_key`
  (read-only, `0400`). `PIPE_SSH_KEY_FILE` aponta para esse caminho;
  `_setup_ssh()` copia para `~/.ssh/id_pipe` (`0600`) e escreve `~/.ssh/config`.
- **Consequência.** A chave nunca aparece no filesystem fora do ponto de
  montagem nem em `env`. O código atual **já** funciona sem alteração: ele
  apenas lê o caminho de `PIPE_SSH_KEY_FILE` e copia o arquivo.

### ADR-04 — Dependências instaladas na imagem, com versões pinadas

- **Contexto.** Reprodutibilidade e ausência de resolução de dependências em
  runtime.
- **Decisão.** Instalar git, openssh-client, ca-certificates, `gh`, `kiro-cli` e
  `pyyaml` **na imagem**, com versões fixadas (não `latest`). O `.deb` do
  kiro-cli vem do canal oficial; a versão validada é registrada no Dockerfile e
  confirmada com `kiro-cli --version` durante o build (mitiga risco **R-2**).
- **Consequência.** Trocar dependência ou versão do kiro-cli exige rebuild.
  Configuração e segredos **nunca** exigem rebuild (ver ADR-06).

### ADR-05 — Container roda como usuário não-root com HOME gravável

- **Contexto.** `_setup_ssh()` escreve em `~/.ssh/`; o kiro-cli grava sessões em
  `~/.kiro/` (SQLite, keyed por diretório).
- **Decisão.** Criar usuário `pipe` (uid 1000) com `$HOME=/home/pipe` gravável.
  O container executa como esse usuário.
- **Consequência.** Menor superfície de risco (sem root). O volume de sessões é
  montado em `/home/pipe/.kiro` (ver §4). `XDG_RUNTIME_DIR=/tmp` elimina warnings
  do kiro-cli em base slim sem systemd.

### ADR-06 — Configuração externa via volumes/env; nada sensível fixo na imagem

- **Contexto.** Trocar `pipe.yml`, `contexts/` ou credenciais não deve exigir
  rebuild (RF-05), e nenhum segredo pode ficar embutido (RNF-01).
- **Decisão.** `pipe.yml` e `contexts/` entram por **bind mount read-only**;
  credenciais entram por `.env`/secret. A imagem contém apenas `src/` e
  dependências.
- **Consequência.** Único caso que exige rebuild é mudança em `src/` ou nas
  dependências do Dockerfile. Todo o resto é `docker compose up`.

---

## 4. Modelo de estado e persistência

O estado de runtime é externalizado em **volumes nomeados**. A escolha entre
bind mount (read-only, para config) e volume nomeado (read-write, para estado)
é o eixo central do desenho:

| Caminho no container | Tipo | Recurso | Origem | Sobrevive a `down`? |
|----------------------|------|---------|--------|---------------------|
| `/app/pipe.yml` | bind `ro` | configuração | `./pipe.yml` (host) | n/a (arquivo do host) |
| `/app/contexts/` | bind `ro` | personas dos agentes | `./contexts/` (host) | n/a (arquivo do host) |
| `/run/secrets/ssh_key` | secret `ro` | chave SSH | `${SSH_KEY_FILE_HOST}` | n/a (secret do host) |
| `/app/repo/` | volume `pipe-repo` | clones git | volume | **sim** |
| `/app/logs/` | volume `pipe-logs` | logs de execução | volume | **sim** |
| `/app/.pipe/` | volume `pipe-state` | fila, snapshots, `sessions.json` | volume | **sim** |
| `/home/pipe/.kiro/` | volume `kiro-home` | SQLite de sessões do kiro-cli | volume | **sim** |

### Por que `kiro-home` é um volume de primeira classe

A continuidade de raciocínio dos agentes depende de **dois** artefatos
alinhados: o índice `.pipe/sessions.json` (mapeia board/issue/agente →
`session_id`) e o banco SQLite em `~/.kiro/` (onde a sessão de fato existe,
keyed pelo `cwd` do `subprocess.run`, que é `repo/<repo_id>`). Se apenas
`pipe-state` persistisse, o índice apontaria para IDs inexistentes após um
reinício: a esteira degradaria graciosamente para sessão nova (funcional, mas
sem retomada de contexto). Persistir **ambos** preserva a continuidade descrita
no README.

`down` preserva todos os volumes; `down -v` os destrói (reset completo) — a
distinção destrutiva está sinalizada no runbook.

---

## 5. Modelo de autenticação (headless)

Três integrações, três mecanismos, um princípio comum: **o segredo entra pelo
host, nunca pela imagem**.

| Integração | Mecanismo | Entrada | Validação | Falha se ausente |
|------------|-----------|---------|-----------|------------------|
| git/SSH | chave privada → `_setup_ssh` | Docker secret `ssh_key` | `check_config` valida `PIPE_SSH_KEY_FILE` (arquivo existe) | **fail-fast** no arranque (`SystemExit(1)`) |
| gh CLI | `GH_TOKEN` (PAT) | env via `.env` | `board.check_access` (gate de permissões) | *lazy* — primeira operação de board |
| kiro-cli | `KIRO_API_KEY` | env via `.env` | — | *lazy* — primeira execução de agente |

**Assimetria intencional.** `PIPE_SSH_KEY_FILE` é validada no arranque porque o
clone SSH acontece dentro de `startup()`. `GH_TOKEN` e `KIRO_API_KEY` só são
exigidos dentro do loop, portanto falham de forma *lazy* — com mensagem
identificável no log, nunca com travamento silencioso (US-05).

---

## 6. Sequência de arranque no container

```
docker compose up
   │
   ▼
python -m src  (usuário `pipe`, cwd=/app)
   │
   ├─ check_config()
   │     ├─ _validate_env(): PIPE_SSH_KEY_FILE definido e arquivo existe  ──► ausente ⇒ SystemExit(1)
   │     └─ valida pipe.yml (montado ro) + contexts não vazios            ──► inválido ⇒ SystemExit(1)
   │
   ├─ startup()
   │     ├─ _setup_ssh(): copia /run/secrets/ssh_key → ~/.ssh/id_pipe (0600) + ~/.ssh/config
   │     ├─ limpa fila de mudanças anterior (.pipe/change_queue)
   │     └─ clona repos ausentes em /app/repo/ (git+SSH)                   ──► SSH inválido ⇒ erro claro
   │
   ├─ board.connect() + board.check_access()                              ──► GH_TOKEN/escopo ruim ⇒ SystemExit(1)
   │
   ├─ board_full_sync()  (estrutura local + sync remoto + mudanças)
   │
   └─ while running:  sync_board → process_queue → keep_task → call_agent → sleep_time
                                                        │
                                                        └─ kiro-cli chat --no-interactive --trust-all-tools
                                                           (cwd=repo/<repo_id>, KIRO_API_KEY, sem prompt)
```

O ponto de observabilidade do operador são os logs (`docker compose logs -f`): a
sequência `[Pipe] → [Config] → [Startup] → [Board]`, seguida de `[Sleep]
Nenhuma atividade - dormindo Ns` no ciclo ocioso, confirma arranque saudável.
Os rótulos de log são fixos (`log.info(<origem>, …)` em `__main__.py`): `Pipe`,
`Config`, `Startup`, `Board`, `KeepTask`, `Sleep`. Detalhes e tabela de erros no
runbook.

### Operação autônoma

- `PYTHONUNBUFFERED=1` garante logs em tempo real no `docker logs`.
- O kiro-cli é sempre invocado com `--no-interactive --trust-all-tools`
  (`kiro_cli_agent._run`): nenhum prompt de aprovação interrompe o loop.
- Os gates humanos do fluxo (`need_human`) **não** exigem acesso ao container: o
  humano move o card no board do GitHub e o próximo ciclo de sync retoma. O
  container roda ininterruptamente enquanto aguarda.
- `restart: unless-stopped` (US-05) mantém o container de pé após reinício do
  host/daemon, respeitando parada manual.

---

## 7. Segurança

- **Sem segredos na imagem (RNF-01).** Verificável por `docker history` e
  `docker inspect`. Só `src/` e dependências são copiados.
- **Chave SSH nunca em env.** Docker secret montado `0400`; a cópia gravável fica
  restrita a `~/.ssh/id_pipe` (`0600`). Ver ADR-03.
- **`.env` fora do versionamento.** Listado no `.gitignore`; apenas
  `.env.example` (sem valores reais) é versionado.
- **Usuário não-root (ADR-05).** Reduz o impacto de uma eventual escapada de
  processo do agente.
- **PAT de menor privilégio.** `GH_TOKEN` com apenas `repo` + `project`.
- **Rotação de `KIRO_API_KEY` (R-4).** Procedimento sem downtime documentado no
  runbook; não afeta volumes de estado.

**Fora de escopo (consciente).** Gestão avançada de segredos (Vault, AWS Secrets
Manager), publicação em registry e CI/CD de build. São evoluções que só se
justificam com um requisito de produção/multiusuário — coerente com o princípio
da §1.

---

## 8. Artefatos a materializar (implementação)

Esta arquitetura orienta três artefatos versionados na raiz do repositório,
entregues pelas stories US-01…US-03:

1. **`Dockerfile`** — single-stage sobre `python:3.12-slim`; instala deps
   pinadas; cria usuário `pipe`; `ENV PYTHONUNBUFFERED=1 XDG_RUNTIME_DIR=/tmp`;
   `COPY src/`; `CMD ["python", "-m", "src"]`; valida `kiro-cli --version` no
   build.
2. **`docker-compose.yml`** — serviço único `pipe`; `env_file: .env`;
   `environment: PIPE_SSH_KEY_FILE=/run/secrets/ssh_key`; volumes de config
   (`ro`) e de estado (nomeados); `secrets.ssh_key.file: ${SSH_KEY_FILE_HOST}`;
   `restart: unless-stopped`. Estrutura de referência em `user-stories.md` §US-03.
3. **`.env.example`** — `PIPE_SSH_KEY_FILE`, `GH_TOKEN`, `KIRO_API_KEY`,
   `SSH_KEY_FILE_HOST`, com descrição e sem valores reais. `.dockerignore`
   acompanha para não copiar `repo/`, `logs/`, `.pipe/`, `.env`.

> **Aderência do código atual.** O runtime **não precisa de alterações** para
> containerizar: `_setup_ssh` já lê `PIPE_SSH_KEY_FILE` de um caminho arbitrário,
> `check_config` já faz fail-fast, e o adapter kiro-cli já roda `--no-interactive
> --trust-all-tools`. A containerização é aditiva (Dockerfile + compose + env),
> não invasiva.

---

## 9. Rastreabilidade

| Requisito | Onde é atendido nesta arquitetura |
|-----------|-----------------------------------|
| RF-01 (`python -m src` sem preparar host) | §8 Dockerfile + §6 arranque |
| RF-02 / ADR-03 (SSH injetado) | §3 ADR-03, §5 |
| RF-03 / ADR-02 (gh headless) | §3 ADR-02, §5 |
| RF-04 / ADR-01 (kiro-cli headless) | §3 ADR-01, §5 |
| RF-05 (config sem rebuild) | §3 ADR-06, §4 |
| RNF-01/03 (sem segredo na imagem) | §7 |
| RNF-02 (base slim) / RNF-05 (deps pinadas) | §3 ADR-04, §8 |
| RNF-04 (`docker compose up` único comando) | §2, §6 |
| ADR-05 (não-root, HOME gravável) | §3 ADR-05, §4 (`kiro-home`) |
| R-1 (continuidade de sessão) | §4 (`kiro-home` + `.pipe/sessions.json`) |
| R-2 (instalação kiro-cli) | §3 ADR-04 (validação no build) |
| R-3 (KIRO_API_KEY plano pago) | §3 ADR-01, §7 |
| R-4 (rotação de key) | §7 + runbook |
