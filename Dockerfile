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

# ---------------------------------------------------------------------------
# Camada 2 — Dependências de sistema
# Pacotes em único RUN para minimizar camadas (ADR-02)
# Versões pinadas conforme docker/versions.env (ADR-04)
# gnupg não necessário: repositório APT do gh usa keyring binário via curl
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        git=1:2.47.3-0+deb13u1 \
        openssh-client=1:10.0p1-7+deb13u4 \
        ca-certificates \
        curl \
        unzip \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Camada 3 — GitHub CLI (gh)
# Repositório APT oficial do GitHub com chave GPG assinada
# Versão pinada conforme docker/versions.env (ADR-04)
# ---------------------------------------------------------------------------
RUN curl --proto '=https' --tlsv1.2 -fsSL \
        https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh=2.96.0 \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Camada 4 — PyYAML
# Versão pinada conforme docker/versions.env (ADR-04)
# ---------------------------------------------------------------------------
RUN pip install --no-cache-dir pyyaml==6.0.2

# ---------------------------------------------------------------------------
# Camada 5 — Usuário não-root (ADR-05)
# uid determinístico 1000; HOME gravável para ~/.ssh e sessões do kiro-cli
# ---------------------------------------------------------------------------
RUN useradd --create-home --uid 1000 pipe
WORKDIR /app
RUN chown pipe:pipe /app
USER pipe

# ---------------------------------------------------------------------------
# Camada 6 — kiro-cli (ADR-03)
# Instalado como usuário pipe → ~/.local/bin (PATH ainda não inclui esse dir)
# Smoke test usa path absoluto: ENV PATH só é definido na camada seguinte
# ---------------------------------------------------------------------------
ARG KIRO_CLI_VERSION=2.13.1
ARG KIRO_CLI_URL=https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-x86_64-linux.zip
ARG KIRO_CLI_SHA256=49d712558cc930d3570387ce468887ca0b510ba8b5f08e2f3c7a7a55d44e677f

RUN curl --proto '=https' --tlsv1.2 -fsSL "$KIRO_CLI_URL" -o /tmp/kirocli.zip \
    && echo "${KIRO_CLI_SHA256}  /tmp/kirocli.zip" | sha256sum -c - \
    && unzip -q /tmp/kirocli.zip -d /tmp/kirocli_extract \
    && /tmp/kirocli_extract/kirocli/install.sh \
    && rm -rf /tmp/kirocli.zip /tmp/kirocli_extract \
    && ~/.local/bin/kiro-cli --version

# ---------------------------------------------------------------------------
# Camada 7 — Variáveis de ambiente
# PATH inclui ~/.local/bin onde kiro-cli foi instalado
# XDG_RUNTIME_DIR=/tmp necessário para kiro-cli em container
# ---------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    XDG_RUNTIME_DIR=/tmp \
    PATH=/home/pipe/.local/bin:$PATH

# ---------------------------------------------------------------------------
# Camada 8 — Código da esteira via git clone (ADR-07)
# Camada mais volátil — última para preservar cache das anteriores
# Chave SSH efêmera via BuildKit secret (ADR-06): nunca persiste na imagem
# ---------------------------------------------------------------------------
ARG PIPE_REPO=git@github.com:brenotmp-agent/pipe.git
ARG PIPE_REF=main

RUN --mount=type=secret,id=ssh_key,uid=1000 \
    GIT_SSH_COMMAND="ssh -i /run/secrets/ssh_key -o StrictHostKeyChecking=accept-new" \
    git clone --depth 1 --branch "$PIPE_REF" "$PIPE_REPO" /tmp/esteira \
    && cp -r /tmp/esteira/src /app/src \
    && rm -rf /tmp/esteira

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
CMD ["python", "-m", "src"]
