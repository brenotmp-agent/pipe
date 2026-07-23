# Arquitetura da Solução — Rodar no Docker

Status: draft (revisão 2)
Owner: arquitetura
Last updated: 2026-07-21
Escopo primário: US-01 (issue #16). Orientações para US-02..US-06.

> **Revisão 2 (2026-07-21):** a validação apontou que o `COPY src/` obrigava o
> operador a ter o código da esteira já baixado no host. A arquitetura foi
> ajustada: **o código passa a ser obtido por `git clone` do próprio repositório
> no build da imagem** (não mais copiado do host). Detalhes em ADR-07; o
> Dockerfile de referência (§4), a estrutura de camadas (§3.2), o `.dockerignore`
> (§4.1) e a verificação (§7) foram atualizados.

## 1. Princípio norteador

A esteira já é uma aplicação Python autocontida: um único módulo executável
(`python -m src`), uma única dependência de terceiros (`pyyaml`) e dois
binários externos que ela invoca por `subprocess` (`git`/`gh` e `kiro-cli`).

Portanto a arquitetura de containerização é deliberadamente **simples**: uma
única imagem, um único container de processo longo, build **single-stage**.
Não há serviço web, não há banco embarcado, não há necessidade de multi-stage
(nada é compilado). Qualquer estrutura além disso seria complexidade sem
retorno — evitamos "modinha" (distroless, multi-stage, orquestradores) onde o
custo de manutenção não se paga.

O que **não** muda: a lógica de negócio em `src/core` e `src/adapters`
permanece intacta (D-01). O container apenas empacota o runtime e move para
fora tudo que é ambiente e segredo. O **código** da esteira também não é mais um
insumo local: a imagem o busca por `git clone` no build (ADR-07), de modo que o
operador não precisa manter o repositório clonado no host.

## 2. Topologia alvo

```
 Host (qualquer máquina com Docker)
 ┌──────────────────────────────────────────────────────────────┐
 │  docker compose (US-03)                                        │
 │                                                                │
 │   env (runtime, US-02)          volumes                        │
 │   ┌───────────────────┐         ┌───────────────────────────┐ │
 │   │ PIPE_SSH_KEY_FILE │         │ ./pipe.yml      (ro)       │ │
 │   │ GH_TOKEN          │         │ ./contexts/     (ro)       │ │
 │   │ KIRO_API_KEY      │         │ pipe-repo   -> /app/repo   │ │
 │   │ (SSH key: secret) │         │ pipe-logs   -> /app/logs   │ │
 │   └─────────┬─────────┘         │ pipe-state  -> /app/.pipe  │ │
 │             │                   │ kiro-home   -> ~/.kiro      │ │
 │             ▼                   │ kiro-local  -> ~/.local/... │ │
 │   ┌─────────────────────────────┴───────────────────────────┐ │
 │   │  Container  (imagem US-01)                               │ │
 │   │  usuário não-root `pipe` (uid 1000), $HOME gravável      │ │
 │   │  CMD: python -m src                                      │ │
 │   │                                                          │ │
 │   │   main loop ── subprocess ──> git / gh  ── SSH+HTTPS ─┐  │ │
 │   │             └─ subprocess ──> kiro-cli chat --headless │  │ │
 │   └────────────────────────────────────────────────────────┘ │
 └──────────────────────────────────────────────────────┼───────┘
                                                          ▼
                              GitHub (Projects V2 + repos)  •  Kiro backend
```

O container é **stateful por volume**, não por camada de imagem: todo estado
(`repo/`, `logs/`, `.pipe/`, sessões do kiro-cli) vive em volumes nomeados. A
imagem em si é descartável e reprodutível.

## 3. Estrutura da imagem

### 3.1 Layout no container

```
/app                      WORKDIR
├── src/                  código da esteira (git clone no build — ADR-07)
├── pipe.yml              (volume ro — US-03, não copiado)
├── contexts/             (volume ro — US-03, não copiado)
├── repo/                 (volume nomeado — clones em runtime)
├── logs/                 (volume nomeado)
└── .pipe/                (volume nomeado — fila, snapshots, sessions.json)

/home/pipe                $HOME gravável (ADR-05)
├── .ssh/                 escrito por _setup_ssh() em runtime
├── .local/bin/kiro-cli   binário do agente (ADR-03)
├── .local/share/kiro-cli índice SQLite de sessões (volume — US-02)
└── .kiro/                sessões e config do kiro-cli (volume — US-02)
```

Todos os caminhos de código são relativos ao WORKDIR `/app`, coerente com o
código atual, que usa caminhos relativos (`Path("repo")`, `Path("pipe.yml")`,
`Path(".pipe/...")`).

### 3.2 Camadas de build (ordem = cache)

Da mais estável para a mais volátil, para maximizar cache de build:

1. Base `python:3.12-slim` (ADR-01).
2. Pacotes de sistema via `apt` pinados: `git`, `openssh-client`,
   `ca-certificates`, `curl`, `unzip` (D-02).
3. GitHub CLI (`gh`) via repositório APT oficial, versão pinada (ADR-04).
4. `pip install pyyaml==<versão>`.
5. Criação do usuário `pipe` e troca para não-root (ADR-05).
6. kiro-cli via zip installer para `~/.local/bin` + smoke test (ADR-03, R-2).
7. Variáveis de ambiente (`PYTHONUNBUFFERED`, `XDG_RUNTIME_DIR`, `PATH`).
8. `git clone` do `src/` a partir do repositório da esteira (camada mais
   volátil — muda a cada release; invalidada por `--build-arg PIPE_REF` ou pela
   opção `--no-cache` — ADR-07).

> O `git` (passo 2) já estava na imagem por ser dependência de runtime da
> esteira; ele também serve ao clone de build. O segredo SSH usado no clone é
> montado de forma **efêmera** via BuildKit e não persiste em nenhuma camada
> (ADR-07, RNF-01).

## 4. Dockerfile de referência

> Ilustrativo. A implementação do arquivo é a fase de codificação de US-01;
> aqui fica a decisão técnica concretizada. Versões marcadas `<...>` são
> definidas/validadas na implementação e registradas conforme ADR-04.

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim

# (2) Dependências de sistema — versões pinadas (D-02)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        ca-certificates \
        curl \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# (3) GitHub CLI via repositório oficial (DEB822), versão pinada (ADR-04)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh=<versao> \
    && rm -rf /var/lib/apt/lists/*

# (4) Dependência Python — pinada
RUN pip install --no-cache-dir pyyaml==<versao>

# (5) Usuário não-root (ADR-05)
RUN useradd --create-home --uid 1000 pipe
WORKDIR /app
RUN chown pipe:pipe /app
USER pipe

# (6) kiro-cli via zip installer -> ~/.local/bin, com smoke test (ADR-03, R-2)
ARG KIRO_CLI_VERSION=<versao-validada>
ARG KIRO_CLI_URL=https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-x86_64-linux.zip
ARG KIRO_CLI_SHA256=<checksum>
RUN curl --proto '=https' --tlsv1.2 -fsSL "$KIRO_CLI_URL" -o /tmp/kirocli.zip \
    && echo "${KIRO_CLI_SHA256}  /tmp/kirocli.zip" | sha256sum -c - \
    && unzip -q /tmp/kirocli.zip -d /tmp \
    && /tmp/kirocli/install.sh \
    && rm -rf /tmp/kirocli.zip /tmp/kirocli \
    && kiro-cli --version   # smoke test — falha o build se o binário não roda

# (7) Ambiente
ENV PYTHONUNBUFFERED=1 \
    XDG_RUNTIME_DIR=/tmp \
    PATH=/home/pipe/.local/bin:$PATH

# (8) Código da esteira — CLONADO do GitHub no build (não copiado do host) — ADR-07
#     Repo privado por SSH: a chave é montada como secret EFÊMERO do BuildKit
#     (nunca vira camada — RNF-01). Reusa a mesma PIPE_SSH_KEY_FILE do runtime.
ARG PIPE_REPO=git@github.com:brenotmp-agent/pipe.git
ARG PIPE_REF=main   # branch/tag; para pinagem forte, use um SHA (ver ADR-04)
RUN --mount=type=secret,id=ssh_key,uid=1000 \
    GIT_SSH_COMMAND='ssh -i /run/secrets/ssh_key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new' \
    git clone --depth 1 --branch "$PIPE_REF" "$PIPE_REPO" /tmp/esteira \
    && cp -r /tmp/esteira/src /app/src \
    && rm -rf /tmp/esteira

# Entrypoint em exec form: python vira PID 1 e recebe sinais diretamente
CMD ["python", "-m", "src"]
```

> **Comando de build** (BuildKit obrigatório para `--mount`/`--secret`):
>
> ```bash
> DOCKER_BUILDKIT=1 docker build \
>   --secret id=ssh_key,src="$PIPE_SSH_KEY_FILE" \
>   --build-arg PIPE_REF=main \
>   -t esteira .
> ```
>
> O operador não precisa clonar a esteira à mão: basta o `Dockerfile` e acesso
> de leitura ao repositório (a mesma chave SSH que a esteira já usa). Para uma
> versão específica, passe `--build-arg PIPE_REF=<tag|sha>`.

### 4.1 `.dockerignore`

Como o código passa a vir por `git clone` (ADR-07), **nada** do host precisa
entrar no contexto de build. O `.dockerignore` nega tudo — só o próprio
`Dockerfile` chega ao daemon:

```
*
```

Essa negação total é a garantia mais forte de RNF-01: `pipe.yml`, `contexts/`,
`repo/`, `logs/`, `.pipe/`, `.ssh`, `.env` e qualquer credencial ficam de fora
por construção, e o segredo SSH do clone é montado de forma efêmera (não vem do
contexto de build nem vira camada).

## 5. Fluxo de arranque no container

```
docker compose up
   └─ CMD python -m src  (PID 1, usuário pipe)
        ├─ check_config()          valida pipe.yml (volume ro) e PIPE_SSH_KEY_FILE
        │                          → falha rápida com SystemExit(1) se faltar (US-05)
        ├─ startup()
        │    └─ _setup_ssh()        copia a chave de PIPE_SSH_KEY_FILE p/ ~/.ssh/id_pipe
        │                          (exige $HOME gravável — ADR-05)
        │       clona repos em /app/repo (volume)
        └─ while running:          loop; agente via kiro-cli chat --no-interactive
```

`check_config()` → `_validate_env()` já garante a "falha clara no arranque"
(US-05): sem `PIPE_SSH_KEY_FILE` o processo termina com `SystemExit(1)` e
mensagem descritiva. Nenhuma mudança de código é necessária para US-01.

## 6. Orientações para gaps de UX (L1–L5) e stories seguintes

A prototipação (`doc/ux/rodar-no-docker/prototipos.md`) levantou lacunas para
a Arquitetura. Posição arquitetural:

- **L4 — shutdown em `docker compose down`.** O loop trata `KeyboardInterrupt`
  (SIGINT) mas **não** `SIGTERM`, que é o sinal enviado por `docker stop`/
  `compose down`. Hoje o container é encerrado por SIGKILL após o grace period.
  Impacto controlado: a fila (`.pipe/changeQueue.json`) é at-least-once e o
  startup re-enfileira itens pendentes, então o estado do board é consistente.
  O único trabalho perdível é uma execução de agente em andamento (subprocess
  de até 3600s). **Recomendação (US-04):** instalar handler de `SIGTERM` que
  seta `running = False` para encerrar ao fim do ciclo corrente; usar sempre
  `CMD` em exec form (já previsto) para o sinal chegar ao Python. Se necessário
  encerramento mais rápido, ajustar `stop_grace_period` no compose.
- **L5 — cores ANSI sem TTY.** O log da esteira pode emitir ANSI que poluem
  `docker logs`. Direção: detectar TTY / respeitar `NO_COLOR`. É ajuste de
  apresentação em `src/core/log.py`, fora do escopo de US-01 (não toca a
  imagem). O input do kiro-cli já é limpo de ANSI no adapter e `KIRO_LOG_NO_COLOR`
  já é setado.
- **L2 — `GH_TOKEN`/`KIRO_API_KEY` só falham em runtime.** Aceitável para
  US-01. Um preflight opcional (checar presença das variáveis no arranque) é
  candidato a US-05, sem impacto na imagem.
- **L1 (meta de onboarding) e L3 (heartbeat de ociosidade):** produto/US-04;
  sem impacto arquitetural na imagem.

## 7. Verificação (critérios de aceitação → como validar)

| AC (US-01) | Verificação |
|-----------|-------------|
| AC-01 base+conteúdo | `docker build` conclui; `docker run --rm img sh -c 'git --version && gh --version && kiro-cli --version && python -c "import yaml"'` |
| AC-02 código | `docker run --rm img ls /app` mostra só `src/` (obtido por `git clone` no build — ADR-07); `pipe.yml`/`contexts/` ausentes. Opcional: comparar `src/` com o `PIPE_REF` esperado |
| AC-03 segredos | `docker history --no-trunc img` e `docker inspect img` sem valores sensíveis |
| AC-04 não-root | `docker run --rm img id` → `uid=1000(pipe)`; `~/.ssh` gravável |
| AC-05 env | `docker inspect` mostra `PYTHONUNBUFFERED=1` |
| AC-06 entrypoint | `docker run` (com env mínimas) inicia `python -m src` sem instalação no host |

## 8. Decisões (ADRs)

Ver `adr/`:

- ADR-01 — Imagem base `python:3.12-slim`
- ADR-02 — Build single-stage
- ADR-03 — Instalação do kiro-cli via zip installer (não `.deb`)
- ADR-04 — Pinagem de versões e reprodutibilidade
- ADR-05 — Usuário não-root com `$HOME` gravável
- ADR-06 — Externalização de configuração e segredos
- ADR-07 — Aquisição do código via `git clone` no build (não `COPY`)
