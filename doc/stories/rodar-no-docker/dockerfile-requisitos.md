# Requisitos Técnicos — Dockerfile (US-01)

Status: aprovado
Owner: requisitos
Last updated: 2026-07-22
Autora: Rafael Martins — Analista de Requisitos

## Histórico de revisões

| Data | Alteração |
|------|-----------|
| 2026-07-21 | Versão inicial (task #40) — abordagem COPY src/ + COPY kiro-cli |
| 2026-07-22 | Revisão (task #45) — abordagem git clone (ADR-07) + download kiro-cli (ADR-03) |

---

## Escopo

Este documento especifica os requisitos técnicos para a criação do `Dockerfile`
e do `.dockerignore` na raiz do repositório. Cobre a US-01 (#16) completa.

---

## Evolução em relação à versão anterior (task #40)

A task #40 especificou uma abordagem baseada em `COPY src/` e `COPY kiro-cli`
do host. Esta revisão (task #45) altera duas decisões:

| Aspecto | Versão anterior (task #40) | Esta versão (task #45) |
|---------|----------------------------|------------------------|
| Código | `COPY src/` do contexto de build | `git clone` via BuildKit secret |
| kiro-cli | `COPY kiro-cli` do host | Download URL + SHA-256 |
| `.dockerignore` | Conteúdo detalhado (múltiplas exclusões) | Apenas `*` |
| `prepare-docker.sh` | Necessário | Desnecessário |

Motivação: ADR-03 (sem dependência do binário do host) e ADR-07 (código
declarativo, rastreável por ref git, chave SSH efêmera via BuildKit).

---

## Decisões de implementação

### GitHub CLI

O `gh` é instalado via **repositório APT oficial** do GitHub:

```dockerfile
ARG GH_VERSION=2.96.0
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
        https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh=${GH_VERSION} \
    && rm -rf /var/lib/apt/lists/*
```

O Método B (APT oficial) é preferido ao tarball por permitir pinagem via
`gh=2.96.0` no apt, que é verificado pelo mecanismo de integridade do APT
(GPG). Versão verificada: `2.96.0`.

### kiro-cli

Download via URL + verificação SHA-256, executado como usuário `pipe` (ADR-03):

```dockerfile
ARG KIRO_CLI_VERSION=2.13.1
ARG KIRO_CLI_URL=https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-x86_64-linux.zip
ARG KIRO_CLI_SHA256=49d712558cc930d3570387ce468887ca0b510ba8b5f08e2f3c7a7a55d44e677f

RUN curl --proto '=https' --tlsv1.2 -fsSL "$KIRO_CLI_URL" -o /tmp/kirocli.zip \
    && echo "${KIRO_CLI_SHA256}  /tmp/kirocli.zip" | sha256sum -c - \
    && unzip -q /tmp/kirocli.zip -d /tmp/kirocli_extract \
    && /tmp/kirocli_extract/kirocli/install.sh \
    && rm -rf /tmp/kirocli.zip /tmp/kirocli_extract \
    && ~/.local/bin/kiro-cli --version
```

**Nota sobre o smoke test**: O smoke test usa `~/.local/bin/kiro-cli --version`
(path absoluto) porque o `ENV PATH` é definido **na camada seguinte** (camada 7).
Na camada 6, o `PATH` do ambiente ainda não inclui `~/.local/bin`. O path
absoluto garante que o build falhe imediatamente se o binário não for
instalado corretamente.

### Código da esteira

Adquirido via `git clone` com chave SSH efêmera via BuildKit secret (ADR-07):

```dockerfile
ARG PIPE_REPO=git@github.com:brenotmp-agent/pipe.git
ARG PIPE_REF=main

RUN --mount=type=secret,id=ssh_key,uid=1000 \
    GIT_SSH_COMMAND="ssh -i /run/secrets/ssh_key \
        -o StrictHostKeyChecking=accept-new \
        -o UserKnownHostsFile=/dev/null" \
    git clone --depth 1 --branch "$PIPE_REF" "$PIPE_REPO" /tmp/esteira \
    && cp -r /tmp/esteira/src /app/src \
    && rm -rf /tmp/esteira
```

### Usuário não-root e PATH

A instalação do kiro-cli (camada 6) ocorre após `USER pipe` (camada 5).
O `install.sh` instala em `/home/pipe/.local/bin/kiro-cli`.

O `ENV PATH=/home/pipe/.local/bin:$PATH` é definido na camada 7 (após o
kiro-cli). Para que o smoke test na camada 6 funcione, o binário é referenciado
por `~/.local/bin/kiro-cli` (path absoluto, expandido pelo shell para
`/home/pipe/.local/bin/kiro-cli`).

Nas camadas seguintes e em runtime, `kiro-cli` funciona sem path completo.

### Versões de pacotes APT (git, openssh-client)

Pinadas explicitamente conforme `docker/versions.env`:

```dockerfile
git=1:2.47.3-0+deb13u1
openssh-client=1:10.0p1-7+deb13u4
```

`curl`, `ca-certificates` e `unzip` não são pinados (componentes de
infraestrutura de build, não de runtime da esteira — baixo risco de regressão).

---

## Especificação do Dockerfile

Ver `doc/arquitetura/rodar-no-docker/arquitetura.md` §4 para o Dockerfile de
referência anotado completo.

---

## Especificação do .dockerignore

```
*
```

Uma única linha. Garante contexto de build vazio — nenhum arquivo do host entra
no daemon Docker. Seguro por construção, não por listagem de exclusões.

---

## Critérios de verificação após implementação

```bash
# 1. Build deve concluir sem erro (BuildKit + secret)
DOCKER_BUILDKIT=1 docker build \
  --secret id=ssh_key,src="$PIPE_SSH_KEY_FILE" \
  --build-arg PIPE_REF=main \
  -t esteira .

# 2. Todos os binários acessíveis e com versões corretas
docker run --rm esteira sh -c \
  'git --version && gh --version && kiro-cli --version && \
   python -c "import yaml; print(yaml.__version__)"'
# Esperado: git 2.47.x, gh 2.96.0, kiro-cli 2.13.1, yaml 6.0.3

# 3. Usuário não-root
docker run --rm esteira id
# Esperado: uid=1000(pipe) gid=1000(pipe)

# 4. PYTHONUNBUFFERED definido
docker inspect esteira | grep PYTHONUNBUFFERED
# ou:
docker run --rm esteira env | grep PYTHONUNBUFFERED
# Esperado: PYTHONUNBUFFERED=1

# 5. Apenas src/ em /app — sem pipe.yml, contexts/, segredos
docker run --rm esteira ls /app
# Esperado: apenas 'src'

# 6. Chave SSH não presente em nenhuma camada
docker history --no-trunc esteira | grep -i ssh
# Esperado: nenhuma linha com valor de chave

# 7. .dockerignore contém apenas '*'
cat .dockerignore
# Esperado: *

# 8. Fail-fast sem credenciais (AC-07)
docker run --rm esteira; echo "Exit: $?"
# Esperado: Exit: 1
```

---

## Riscos identificados

| ID   | Risco | Mitigação |
|------|-------|-----------|
| R-2  | kiro-cli sem URL versionada (usa /latest/) | SHA-256 ancora a versão; build falha se hash divergir |
| R-3  | gh CLI versão desatualizada | Verificar releases antes de atualizar ARG |
| R-4  | Versão APT de git/openssh-client removida do repositório Debian | Reexecutar procedimento de levantamento (#44) e atualizar docker/versions.env |
| R-5  | Build offline inviável (git clone requer SSH ao GitHub) | Documentar pré-requisito de conectividade |

---

## Rastreabilidade

US-01 (#16) | RF-01, RNF-01, RNF-02, RNF-05 | ADR-01 a ADR-07
