# Esteira Agêntica — imagem de container
# Arquitetura: doc/architecture/rodar-no-docker/arquitetura.md
# Requisitos: doc/requirements/rodar-no-docker/requisitos.md

FROM python:3.12-slim

# ---------------------------------------------------------------------------
# Metadados
# ---------------------------------------------------------------------------
LABEL org.opencontainers.image.title="esteira-agentica" \
      org.opencontainers.image.description="Esteira automatizada de agentes de IA" \
      org.opencontainers.image.source="https://github.com/user/repo" \
      org.opencontainers.image.version="1.0.0"

# ---------------------------------------------------------------------------
# Dependências de sistema
# git, openssh-client: operações de repositório
# ca-certificates, curl, gnupg: instalação do gh CLI
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        openssh-client \
        ca-certificates \
        curl \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# GitHub CLI (versão pinada: 2.96.0)
# Repositório apt oficial do GitHub
# ADR-02: autenticação via GH_TOKEN, sem gh auth login
# ---------------------------------------------------------------------------
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh=2.96.0 \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Usuário não-root com HOME gravável (ADR-05)
# Necessário para _setup_ssh escrever ~/.ssh e kiro-cli gravar estado de sessão
# ---------------------------------------------------------------------------
RUN useradd --create-home --uid 1000 --shell /bin/bash pipe

# ---------------------------------------------------------------------------
# kiro-cli — binário ELF copiado do host via prepare-docker.sh
# ADR-01: autenticação por KIRO_API_KEY (modo headless oficial)
# A versão é controlada pelo operador: prepare-docker.sh copia o binário
# instalado localmente (ex.: ~/.local/bin/kiro-cli) para kiro-cli no contexto
# de build. Não existe instalador oficial com versão pinada por URL.
# ---------------------------------------------------------------------------
COPY --chown=root:root kiro-cli /usr/local/bin/kiro-cli
RUN chmod 755 /usr/local/bin/kiro-cli

# ---------------------------------------------------------------------------
# Dependência Python
# ---------------------------------------------------------------------------
RUN pip install --no-cache-dir pyyaml==6.0.2

# ---------------------------------------------------------------------------
# Logs em tempo real (RF-07, sugestão de arquitetura §5)
# AC-04 da US-05: sem buffer, saída visível em `docker logs`
# ---------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1

# ---------------------------------------------------------------------------
# Código-fonte da esteira (RF-01)
# pipe.yml e contexts/ NÃO são copiados — entram por volume em runtime (RF-05)
# AC-05 de US-01 / ADR-05: execução como usuário não-root
# ---------------------------------------------------------------------------
USER pipe
WORKDIR /app

COPY --chown=pipe:pipe src/ /app/src/

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
ENTRYPOINT ["python", "-m", "src"]
