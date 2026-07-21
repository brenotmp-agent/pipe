FROM python:3.12-slim

# Dependências do sistema: git, ssh, curl, jq (utilitários de linha)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ssh \
    curl \
    jq \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (gh) — baixa o binário oficial
ARG GH_VERSION=2.94.0
RUN curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
    | tar -xz -C /usr/local/bin --strip-components=2 "gh_${GH_VERSION}_linux_amd64/bin/gh" \
    && gh --version

# kiro-cli — copiado do host (binário nativo, não distribuído via repositório público)
COPY kiro-cli /usr/local/bin/kiro-cli
RUN chmod +x /usr/local/bin/kiro-cli

# Dependências Python
RUN pip install --no-cache-dir pyyaml

# Diretório de trabalho da esteira
WORKDIR /app

# Copia o código-fonte da esteira
COPY src/ ./src/
COPY README.md CONTEXT.md ./

# Diretórios criados em runtime (montados via volumes)
# - /app/pipe.yml          → configuração
# - /app/contexts/         → contextos dos agentes
# - /app/repo/             → clones dos repositórios
# - /app/logs/             → logs de execução
# - /app/.pipe/            → estado interno (snapshots, fila, sessões)
# - /root/.ssh/            → chave SSH
# - /root/.config/gh/      → autenticação do gh CLI

CMD ["python", "-m", "src"]
