# Arquitetura — US-03: Configurar a esteira via docker-compose sem rebuild

Status: draft
Owner: arquitetura
Autor: Lucas Almeida — Arquiteto de Software
Last updated: 2026-07-07
Escopo: US-03 (issue #18). Base: US-01 (`arquitetura.md`, ADR-01..ADR-06).

> Este documento concretiza, no nível de orquestração, o princípio já decidido
> em [`../adr/ADR-06`](adr/ADR-06-externalizacao-config-segredos.md)
> ("nada de ambiente ou segredo entra na imagem"). A decisão de orquestração
> está formalizada em [`ADR-07`](adr/ADR-07-orquestracao-docker-compose.md). A
> visão geral da imagem e a topologia da feature vivem em
> [`arquitetura.md`](arquitetura.md) (entrega de US-01).

---

## 1. Inputs

- `doc/stories/rodar-no-docker/user-stories.md` (US-03; AC-01..AC-07)
- `doc/ux/rodar-no-docker/us-03-experiencia-do-operador.md` e os protótipos em
  `doc/ux/rodar-no-docker/prototipos/` (`docker-compose.example.yml`,
  `env.example`, `quickstart.md`)
- `doc/arquitetura/rodar-no-docker/arquitetura.md` e `adr/` (US-01)
- `CONTEXT.md` (seções "Sessão do agente", "Configuração (pipe.yml)")
- `src/__main__.py` (`_setup_ssh`, `startup`), `src/core/config.py`
  (`_validate_env`, `check_config`)

---

## 2. Princípio norteador

A solução é **deliberadamente simples**, coerente com a arquitetura da imagem
(US-01): um único `docker-compose.yml` versionado, com **um único serviço**
(`pipe`), consumindo uma imagem já pronta. Nada de orquestrador, profiles,
múltiplas instâncias ou tecnologia externa de segredos (Vault, AWS Secrets
Manager) — seriam complexidade sem retorno para o problema de "subir uma
esteira de processo único em um host". Evita-se a "modinha da vez".

O valor central da story é **trocar configuração sem rebuild**. Isso não é uma
feature nova a construir: é uma **consequência arquitetural** de separar o que é
imutável (a imagem = `src/` + binários) do que é mutável (configuração,
segredos, estado), injetando o mutável em runtime. O compose é apenas a
declaração dessa separação.

O arquivo evolui de forma incremental: US-03 entrega a estrutura base (serviço,
volumes, envs, secret, `.env.example`); US-04 valida a persistência ao
down/up; US-05 adiciona `restart` e fail-fast. Os três convivem no mesmo
arquivo.

---

## 3. Modelo de injeção por natureza da entrada

O ponto central do desenho é reconhecer que as entradas externas têm naturezas
diferentes e cada uma pede um mecanismo diferente (detalhado em
[`ADR-07`](adr/ADR-07-orquestracao-docker-compose.md)):

```
                       docker-compose.yml (serviço único: pipe)
                                    │
        ┌───────────────────┬───────┴────────────┬────────────────────┐
        ▼                   ▼                    ▼                     ▼
  CONFIG (edita muito)  SEGREDO (SSH)      SEGREDOS (tokens)     ESTADO (runtime)
  bind mount :ro        Docker secret       env via .env          volume nomeado
  ┌─────────────────┐   ┌───────────────┐   ┌───────────────┐    ┌───────────────┐
  │ ./pipe.yml   ─ro│   │ ssh_key       │   │ GH_TOKEN      │    │ pipe-repo     │
  │ ./contexts/  ─ro│   │ /run/secrets/ │   │ KIRO_API_KEY  │    │ pipe-logs     │
  └─────────────────┘   │  ssh_key 0400 │   └───────┬───────┘    │ pipe-state    │
        │               └───────┬───────┘           │            │ kiro-home     │
        │                       │                    │            │ kiro-local    │
        ▼                       ▼                    ▼            └───────────────┘
  editar + up            _setup_ssh() copia    lidos nativamente        │
  = nova config          p/ ~/.ssh/id_pipe     por gh / kiro-cli        ▼
  SEM rebuild            (0600) no arranque                       persiste entre
                                                                  reinícios (US-04)
```

- **Configuração** (`pipe.yml`, `contexts/`): bind mount `:ro`. Editar no host
  e `docker compose up` aplica a nova configuração **sem rebuild** — é o
  mecanismo que entrega RF-05/AC-06. O `:ro` protege a fonte no host.
- **Chave SSH**: Docker secret (origem em arquivo), montado `0400` em
  `/run/secrets/ssh_key`. Não vira env var nem aparece fora do mountpoint
  (RNF-01). `_setup_ssh()` copia para `~/.ssh/id_pipe` no arranque (ADR-03/05).
- **Tokens** (`GH_TOKEN`, `KIRO_API_KEY`): variáveis de ambiente via `.env` do
  host, lidas nativamente por `gh` e `kiro-cli`. `.env` no `.gitignore`.
- **Estado** (`repo/`, `logs/`, `.pipe/`, estado do kiro-cli): volumes nomeados
  (semântica de persistência validada em US-04).

### 3.1 Precedência de variáveis e o caminho fixo da chave SSH

`PIPE_SSH_KEY_FILE` aponta para o caminho **interno** do container
(`/run/secrets/ssh_key`), determinado pelo próprio compose — não é escolha do
operador. Por isso é declarada em `environment:` no serviço e **não** compõe o
`.env` que o operador preenche. Como `environment:` tem precedência sobre
`env_file:`, mantê-la também no `.env` seria redundante e enganoso.

O operador preenche apenas três valores no `.env`:

| Variável | Uso | Momento |
|----------|-----|---------|
| `SSH_KEY_FILE_HOST` | caminho da chave **no host**, interpolado em `secrets.ssh_key.file` | parse do compose |
| `GH_TOKEN` | injetado no container; lido pelo `gh` | runtime |
| `KIRO_API_KEY` | injetado no container; lido pelo `kiro-cli` | runtime |

> Ajuste de DX recomendado sobre o protótipo de UX: remover `PIPE_SSH_KEY_FILE`
> do `.env.example` (mantendo-a fixa em `environment:` no compose), para evitar
> a dupla definição. O protótipo a lista nos dois lugares; a implementação
> canônica deve consolidar no compose.

---

## 4. Estrutura de referência do `docker-compose.yml`

> Ilustrativa. A implementação do arquivo é a fase de codificação de US-03;
> aqui fica a decisão técnica concretizada. Alinhada ao protótipo de UX
> (`doc/ux/rodar-no-docker/prototipos/docker-compose.example.yml`) e à topologia
> de `arquitetura.md`.

```yaml
services:
  pipe:
    image: pipe:latest            # imagem construída por US-01 (não construída aqui)
    env_file:
      - .env                      # injeta GH_TOKEN, KIRO_API_KEY no container
    environment:
      # caminho INTERNO da chave (definido pelo compose, não pelo operador)
      - PIPE_SSH_KEY_FILE=/run/secrets/ssh_key
    volumes:
      # --- configuração: editar no host + `up` aplica SEM rebuild ---
      - ./pipe.yml:/app/pipe.yml:ro
      - ./contexts:/app/contexts:ro
      # --- estado de runtime (persistência validada em US-04) ---
      - pipe-repo:/app/repo
      - pipe-logs:/app/logs
      - pipe-state:/app/.pipe
      - kiro-home:/home/pipe/.kiro
      - kiro-local:/home/pipe/.local/share/kiro-cli
    secrets:
      - ssh_key
    # restart / healthcheck / stop_grace_period -> US-04/US-05

secrets:
  ssh_key:
    file: ${SSH_KEY_FILE_HOST}    # caminho no host, via .env (não versionado)

volumes:
  pipe-repo:
  pipe-logs:
  pipe-state:
  kiro-home:
  kiro-local:
```

`.env.example` (versionado) — contrato de configuração; o `.env` real fica no
`.gitignore`:

```dotenv
# Caminho, NO HOST, da chave SSH privada cadastrada no GitHub
SSH_KEY_FILE_HOST=/caminho/para/sua/chave/id_ed25519
# PAT do GitHub — escopos: repo, project
GH_TOKEN=
# API key headless do kiro-cli (requer plano Pro ou superior)
KIRO_API_KEY=
```

---

## 5. Mecanismo "sem rebuild" (RF-05, AC-06)

A imagem (US-01) contém **apenas** `src/` e binários de runtime; não contém
`pipe.yml`, `contexts/` nem segredo algum (garantido por `.dockerignore` com
allow-list de `src/` — ver `arquitetura.md` §4.1). Logo:

| Mudança | Ação | Rebuild? |
|---------|------|----------|
| `pipe.yml` | editar no host + `docker compose up -d` | Não |
| `contexts/` | editar no host + `docker compose up -d` | Não |
| `GH_TOKEN` / `KIRO_API_KEY` | editar `.env` + `docker compose up -d` | Não |
| Chave SSH | trocar arquivo apontado por `SSH_KEY_FILE_HOST` + `up` | Não |
| Código da esteira (`src/`) ou `Dockerfile` | `docker build` | **Sim** |

O "sem rebuild" é, portanto, uma propriedade estrutural: nada que o operador
troca no dia a dia está dentro da imagem.

---

## 6. Rastreabilidade (requisito → decisão)

| Requisito | Atendido por |
|-----------|--------------|
| RF-05 — configuração trocável sem rebuild | §5; bind mount `:ro` de `pipe.yml`/`contexts` + envs via `.env` (ADR-07) |
| RNF-01 — nenhum segredo na imagem | ADR-06; secret SSH `0400`, tokens via `.env`, `.env` no `.gitignore` |
| RNF-03 — credenciais injetáveis, nunca hardcoded; Compose V2 | ADR-07; `${VAR}` do `.env`, sem valores no compose; `docker compose` (sem hífen) |
| RNF-04 — um comando para subir | `docker compose up -d` (serviço único) |
| ADR-06 — externalização | concretizado por §3 e ADR-07 |
| AC-01 compose versionado | §4; arquivo na raiz, sem segredos |
| AC-02 volumes de config `:ro` | §3; `./pipe.yml`, `./contexts` |
| AC-03 chave SSH como secret | §3, ADR-07; `/run/secrets/ssh_key` |
| AC-04 envs obrigatórias | §3.1; `.env` (3 valores) + `PIPE_SSH_KEY_FILE` fixo |
| AC-05 `.env.example` | §4; versionado, `.env` no `.gitignore` |
| AC-06 sem rebuild | §5 |
| AC-07 volumes de estado declarados | §4; `pipe-repo/logs/state`, `kiro-home`, `kiro-local` |

---

## 7. Fronteiras de escopo

| Assunto | Story | Observação |
|---------|-------|-----------|
| Declarar volumes de estado no compose | **US-03** | entregue aqui |
| Validar persistência ao `down`/`up` | US-04 | semântica, não declaração |
| `restart: unless-stopped`, `healthcheck` | US-05 | política de operação |
| Tratamento de `SIGTERM` (shutdown limpo) | US-04 | ver `arquitetura.md` §6 (L4) |
| Construir a imagem (`Dockerfile`) | US-01 | US-03 só consome `image:` |
| Publicar imagem em registry | fora | não requisitado |
| Gestão avançada de segredos (Vault etc.) | fora | complexidade desnecessária |

---

## 8. Riscos arquiteturais

| ID | Risco | Mitigação |
|----|-------|-----------|
| RA-1 | Persistência de sessão do kiro-cli depende do índice SQLite em `~/.local/share/kiro-cli/`; se só `~/.kiro/` for montado, a retomada (`--resume-id`) degrada para sessão nova a cada reinício. | Montar **dois** volumes (`kiro-home` + `kiro-local`), conforme comportamento verificado (CONTEXT.md, ADR-05). Divergência consciente da matriz de US-02/US-03 (só `~/.kiro/`); reversível se US-04 provar que um basta. Ver [ADR-07](adr/ADR-07-orquestracao-docker-compose.md). |
| RA-2 | Permissões dos volumes nomeados podem não casar com o uid 1000 (`pipe`) do container, causando falha de escrita em `~/.ssh`, `.pipe/` ou estado do kiro-cli. | uid fixo 1000 (ADR-05); validar escrita nos volumes em US-04. |
| RA-3 | `secrets` com `file:` em Compose V2 fora de Swarm — confirmar suporte no engine alvo. | Compose V2 suporta secrets baseados em arquivo (bind read-only em `/run/secrets/<nome>`); validar no host de destino durante a codificação. |
| RA-4 | Dupla definição de `PIPE_SSH_KEY_FILE` (env_file + environment) pode confundir. | Consolidar no `environment:` do compose e remover do `.env.example` (§3.1). |

---

## 9. Verificação (AC → como validar)

| AC (US-03) | Verificação |
|-----------|-------------|
| AC-01 | `docker compose config` valida o arquivo; `git grep` não encontra valores de segredo no compose |
| AC-02 | trocar `pipe.yml` no host + `docker compose up -d` → nova config em vigor sem `docker build` |
| AC-03 | `docker compose exec pipe ls -l /run/secrets/ssh_key` → `0400`; chave não aparece em `env` do container |
| AC-04 | `docker compose exec pipe printenv PIPE_SSH_KEY_FILE GH_TOKEN KIRO_API_KEY` retorna os valores esperados |
| AC-05 | `.env.example` versionado e `.env` ignorado (`git check-ignore .env`) |
| AC-06 | trocar `GH_TOKEN` no `.env` + `up -d` → novo token em uso, sem rebuild (imagem inalterada em `docker images`) |
| AC-07 | `docker compose config --volumes` lista `pipe-repo`, `pipe-logs`, `pipe-state`, `kiro-home`, `kiro-local` |

---

## 10. Decisões (ADRs) relacionadas

- [ADR-06](adr/ADR-06-externalizacao-config-segredos.md) — Externalização de
  configuração e segredos (princípio; US-01).
- [ADR-07](adr/ADR-07-orquestracao-docker-compose.md) — Orquestração via
  docker-compose, single service, sem rebuild (US-03, este escopo).
- [ADR-03](adr/ADR-03-instalacao-kiro-cli.md) e
  [ADR-05](adr/ADR-05-usuario-nao-root.md) — instalação do kiro-cli e usuário
  não-root com `$HOME` gravável (US-01), pré-condições para SSH e estado do
  kiro-cli.
