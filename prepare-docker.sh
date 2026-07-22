#!/usr/bin/env bash
# prepare-docker.sh — prepara o contexto de build antes de `docker build`
#
# Uso:
#   ./prepare-docker.sh
#   docker build -t pipe-esteira .
#
# O que faz:
#   Copia o binário kiro-cli instalado localmente para a raiz do repositório,
#   tornando-o disponível no contexto de build do Dockerfile.
#
# Pré-requisito: kiro-cli deve estar instalado (ex.: ~/.local/bin/kiro-cli).
# A versão utilizada na imagem é a versão instalada localmente — o operador
# controla qual versão empacotar atualizando o kiro-cli no host antes de rodar
# este script.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$SCRIPT_DIR/kiro-cli"

# Localizar o binário kiro-cli
KIRO_BIN="$(command -v kiro-cli 2>/dev/null || echo "")"

if [[ -z "$KIRO_BIN" ]]; then
    echo "ERRO: kiro-cli não encontrado no PATH." >&2
    echo "Instale o kiro-cli e certifique-se de que está no PATH." >&2
    exit 1
fi

echo "Copiando $KIRO_BIN → $DEST"
cp "$KIRO_BIN" "$DEST"
chmod 755 "$DEST"

echo "Pronto. Execute: docker build -t pipe-esteira ."
