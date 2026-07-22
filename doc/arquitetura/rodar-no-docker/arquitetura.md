# Arquitetura — Rodar no Docker

Status: aprovado
Owner: arquitetura
Last updated: 2026-07-22
Autora: Rafael Martins — Analista de Requisitos

---

## §1 — Escopo

Este documento descreve a arquitetura de containerização da esteira agêntica:
decisões de design, estrutura da imagem, Dockerfile de referência anotado e
artefatos a produzir. É a referência técnica para as tasks de implementação do
épico "Rodar no Docker" (issue #1, stories #16–#21).

---

## §2 — Princípios

1. **Nenhum segredo na imagem** (RNF-01): chaves SSH, tokens e configurações
   sensíveis são injetados via `docker-compose` — nunca embutidos na imagem.
2. **Versões pinadas** (RNF-05): toda dependência tem versão explícita
   registrada em `docker/versions.env`.
3. **Imagem autocontida** (RF-01): `python -m src` inicia sem instalação
   adicional no host.
4. **Usuário não-root** (ADR-05): o container executa como `pipe` (uid 1000).
5. **Contexto de build vazio** (ADR-07): `.dockerignore: *` — nenhum arquivo
   do host entra no contexto de build.
6. **Código declarativo** (ADR-07): o código vem de `git clone` durante o
   build, com ref explícita via `--build-arg PIPE_REF`.

---

## §3 — Estrutura da imagem

### §3.1 — Componentes

| Componente | Versão | Localização na imagem |
|------------|--------|----------------------|
| Python | 3.12-slim (base) | `/usr/local/bin/python3` |
| git | 1:2.47.3-0+deb13u1 | `/usr/bin/git` |
| openssh-client | 1:10.0p1-7+deb13u4 | `/usr/bin/ssh` |
| curl | APT (sem pinagem) | `/usr/bin/curl` |
| ca-certificates | APT (sem pinagem) | `/etc/ssl/certs/` |
| unzip | APT (sem pinagem) | `/usr/bin/unzip` |
| GitHub CLI (`gh`) | 2.96.0 | `/usr/local/bin/gh` |
| pyyaml | 6.0.3 | site-packages Python |
| kiro-cli | 2.13.1 | `/home/pipe/.local/bin/kiro-cli` |
| Código da esteira | ref `PIPE_REF` | `/app/src/` |

### §3.2 — Camadas (ordem de build, da mais estável para a mais volátil)

```
Camada 1 — Base               FROM python:3.12-slim
Camada 2 — Sistema            RUN apt-get install (git, openssh, curl, ca-certs, unzip)
Camada 3 — GitHub CLI         RUN install gh via apt oficial
Camada 4 — PyYAML             RUN pip install pyyaml==6.0.3
Camada 5 — Usuário não-root   RUN useradd pipe + chown /app; USER pipe
Camada 6 — kiro-cli           RUN curl + sha256sum + unzip + install.sh
Camada 7 — Variáveis          ENV PYTHONUNBUFFERED=1 XDG_RUNTIME_DIR=/tmp PATH=...
Camada 8 — Código             RUN --mount=type=secret git clone + cp src/
Entrypoint                    CMD ["python", "-m", "src"]
```

A ordem camadas 1–4 (root) → camada 5 (switch para pipe) → camadas 6–8 (pipe)
é intencional: curl e unzip precisam estar disponíveis antes da instalação do
kiro-cli; o usuário pipe deve ser criado antes do kiro-cli para que o install.sh
instale em `/home/pipe/.local/bin/`.

### §3.3 — Volumes declarados no docker-compose

| Volume | Tipo | Caminho no container | Conteúdo |
|--------|------|---------------------|----------|
| `pipe.yml` | bind ro | `/app/pipe.yml` | Configuração da esteira |
| `contexts/` | bind rw | `/app/contexts/` | Contextos dos agentes |
| `~/.ssh/id_ed25519` | bind ro | `/home/pipe/.ssh/id_ed25519` | Chave SSH |
| `~/.config/gh/` | bind ro | `/home/pipe/.config/gh/` | Auth do gh CLI |
| `pipe_state` | named | `/app/.pipe/` | Estado interno |
| `pipe_repos` | named | `/app/repo/` | Clones dos repositórios |
| `pipe_logs` | named | `/app/logs/` | Logs de execução |

---

## §4 — Dockerfile de referência anotado

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Comando de build (BuildKit obrigatório para --secret):
#
#   DOCKER_BUILDKIT=1 docker build \
#     --secret id=ssh_key,src="$PIPE_SSH_KEY_FILE" \
#     --build-arg PIPE_REF=main \
#     -t esteira .
#
# Para uma versão específica: --build-arg PIPE_REF=<tag|sha>

# ── Camada 2: Dependências de sistema ────────────────────────────────────────
# Versões pinadas declaradas em docker/versions.env
# curl + ca-certificates: necessários para bootstrap do gh CLI e download do kiro-cli
# unzip: necessário para extrair o zip do kiro-cli
# openssh-client: necessário para _setup_ssh configurar ~/.ssh/
# git: necessário para clonar repositórios gerenciados pela esteira em runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git=1:2.47.3-0+deb13u1 \
        openssh-client=1:10.0p1-7+deb13u4 \
        ca-certificates \
        curl \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# ── Camada 3: GitHub CLI (versão pinada via APT oficial) ─────────────────────
# Repositório APT oficial do GitHub com chave GPG assinada
# Alternativa (tarball): ver doc/arquitetura/rodar-no-docker/adr/ADR-03
ARG GH_VERSION=2.96.0
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
        https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh=${GH_VERSION} \
    && rm -rf /var/lib/apt/lists/*

# ── Camada 4: PyYAML (única dependência Python da esteira) ───────────────────
ARG PYYAML_VERSION=6.0.3
RUN pip install --no-cache-dir pyyaml==${PYYAML_VERSION}

# ── Camada 5: Usuário não-root (ADR-05) ──────────────────────────────────────
# pipe (uid 1000): _setup_ssh escreve em ~/.ssh/; kiro-cli persiste sessões em ~/
RUN useradd --create-home --uid 1000 pipe
WORKDIR /app
RUN chown pipe:pipe /app
USER pipe

# ── Camada 6: kiro-cli (ADR-03) ──────────────────────────────────────────────
# Download via URL oficial + verificação SHA-256 para ancorar a versão
# install.sh instala em ~/.local/bin/kiro-cli (= /home/pipe/.local/bin/kiro-cli)
# Smoke test usa o path absoluto pois ENV PATH ainda não foi definido nesta camada
ARG KIRO_CLI_VERSION=2.13.1
ARG KIRO_CLI_URL=https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-x86_64-linux.zip
ARG KIRO_CLI_SHA256=49d712558cc930d3570387ce468887ca0b510ba8b5f08e2f3c7a7a55d44e677f
RUN curl --proto '=https' --tlsv1.2 -fsSL "$KIRO_CLI_URL" -o /tmp/kirocli.zip \
    && echo "${KIRO_CLI_SHA256}  /tmp/kirocli.zip" | sha256sum -c - \
    && unzip -q /tmp/kirocli.zip -d /tmp/kirocli_extract \
    && /tmp/kirocli_extract/kirocli/install.sh \
    && rm -rf /tmp/kirocli.zip /tmp/kirocli_extract \
    && ~/.local/bin/kiro-cli --version

# ── Camada 7: Variáveis de ambiente ─────────────────────────────────────────
# PYTHONUNBUFFERED=1: logs em tempo real em docker logs (12-Factor XI, AC-04 US-05)
# XDG_RUNTIME_DIR=/tmp: evita warning de runtime dir do kiro-cli
# PATH: adiciona ~/.local/bin para que kiro-cli seja acessível por nome simples
ENV PYTHONUNBUFFERED=1 \
    XDG_RUNTIME_DIR=/tmp \
    PATH=/home/pipe/.local/bin:$PATH

# ── Camada 8: Código da esteira via git clone (ADR-07) ──────────────────────
# --mount=type=secret: chave SSH efêmera — NÃO fica em nenhuma camada da imagem
# StrictHostKeyChecking=accept-new: aceita fingerprint do github.com automaticamente
# Apenas src/ é copiado para /app/src — pipe.yml e contexts/ entram por volume
ARG PIPE_REPO=git@github.com:brenotmp-agent/pipe.git
ARG PIPE_REF=main
RUN --mount=type=secret,id=ssh_key,uid=1000 \
    GIT_SSH_COMMAND="ssh -i /run/secrets/ssh_key \
        -o StrictHostKeyChecking=accept-new \
        -o UserKnownHostsFile=/dev/null" \
    git clone --depth 1 --branch "$PIPE_REF" "$PIPE_REPO" /tmp/esteira \
    && cp -r /tmp/esteira/src /app/src \
    && rm -rf /tmp/esteira

CMD ["python", "-m", "src"]
```

---

## §5 — .dockerignore

Com a abordagem de `git clone` (ADR-07), o contexto de build é intencionalmente
vazio. O `.dockerignore` deve conter apenas:

```
*
```

Isso garante que `pipe.yml`, `contexts/`, `.pipe/`, `.ssh`, `.env`, `kiro-cli`
(binário local) e qualquer credencial no diretório do host nunca entrem no
contexto de build — por construção, não por listagem.

---

## §6 — Artefatos a materializar

| Artefato | Responsável | Status |
|----------|-------------|--------|
| `docker/versions.env` | task #44 | ✅ concluído (2026-07-22) |
| `doc/arquitetura/rodar-no-docker/adr/ADR-01-imagem-base.md` | task #45 requisitos | ✅ |
| `doc/arquitetura/rodar-no-docker/adr/ADR-02-build-single-stage.md` | task #45 requisitos | ✅ |
| `doc/arquitetura/rodar-no-docker/adr/ADR-03-instalacao-kiro-cli.md` | task #45 requisitos | ✅ |
| `doc/arquitetura/rodar-no-docker/adr/ADR-04-pinagem-versoes.md` | task #45 requisitos | ✅ |
| `doc/arquitetura/rodar-no-docker/adr/ADR-05-usuario-nao-root.md` | task #45 requisitos | ✅ |
| `doc/arquitetura/rodar-no-docker/adr/ADR-06-externalizacao-config-segredos.md` | task #45 requisitos | ✅ |
| `doc/arquitetura/rodar-no-docker/adr/ADR-07-aquisicao-codigo-git-clone.md` | task #45 requisitos | ✅ |
| `doc/arquitetura/rodar-no-docker/arquitetura.md` | task #45 requisitos | ✅ |
| `Dockerfile` | task #45 implementação | ⏳ pendente |
| `.dockerignore` | task #45 implementação | ⏳ pendente |

---

## §7 — Rastreabilidade

| Requisito | ADR |
|-----------|-----|
| RNF-01 (sem segredos na imagem) | ADR-06, ADR-07 |
| RNF-02 (base python:3.12-slim) | ADR-01 |
| RNF-05 (versões pinadas) | ADR-04 |
| AC-05 US-01 (usuário não-root) | ADR-05 |
| R-2 (kiro-cli rastreável) | ADR-03, ADR-04 |
| RF-05 (config externa) | ADR-06 |
