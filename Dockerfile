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
        git=1:2.39.5-0+deb12u2 \
        openssh-client=1:9.2p1-2+deb12u5 \
        ca-certificates=20230311 \
        curl=7.88.1-10+deb12u12 \
        gnupg=2.2.40-1.1 \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# GitHub CLI (versão pinada: 2.94.0)
# Repositório apt oficial do GitHub
# ADR-02: autenticação via GH_TOKEN, sem gh auth login
# ---------------------------------------------------------------------------
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh=2.94.0 \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Usuário não-root com HOME gravável (ADR-05)
# Necessário para _setup_ssh escrever ~/.ssh e kiro-cli gravar estado de sessão
# ---------------------------------------------------------------------------
RUN useradd --create-home --uid 1000 --shell /bin/bash pipe

# ---------------------------------------------------------------------------
# kiro-cli (versão pinada: 2.4.2) — instalado como binário ELF standalone
# ADR-01: autenticação por KIRO_API_KEY (modo headless oficial)
# O binário é copiado de uma camada temporária para controle de versão preciso.
# Dependências mínimas: libgcc_s, libm, libc (já presentes no python:3.12-slim)
# ---------------------------------------------------------------------------
# Copia o binário para a imagem usando um placeholder — na prática o binário
# pode ser obtido via instalador oficial ou download direto.
# NOTA: substituir pela forma de distribuição oficial quando disponível.
# Por ora usamos COPY para injetar o binário do host (ver .dockerignore).
COPY --chown=root:root kiro-cli-bin /usr/local/bin/kiro-cli
RUN chmod 755 /usr/local/bin/kiro-cli

# ---------------------------------------------------------------------------
# Dependência Python
# ---------------------------------------------------------------------------
RUN pip install --no-cache-dir pyyaml==6.0.2

# ---------------------------------------------------------------------------
# Logs em tempo real (RF-07, sugestão de arquitetura §5)
# ---------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1

# ---------------------------------------------------------------------------
# Código-fonte da esteira (RF-01)
# pipe.yml e contexts/ NÃO são copiados — entram por volume em runtime (RF-05)
# ---------------------------------------------------------------------------
USER pipe
WORKDIR /app

COPY --chown=pipe:pipe src/ /app/src/

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
ENTRYPOINT ["python", "-m", "src"]
