#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# prepare-docker.sh — Prepara o contexto de build Docker
#
# O Dockerfile precisa do binário `kiro-cli` no contexto de build.
# Este script o copia do host para a raiz do projeto antes do docker-compose.
#
# Uso:
#   ./prepare-docker.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIRO_BIN="${SCRIPT_DIR}/kiro-cli"

# Localizar o binário no host
KIRO_HOST="$(command -v kiro-cli 2>/dev/null || echo "")"

if [[ -z "$KIRO_HOST" ]]; then
    echo "ERRO: kiro-cli não encontrado no PATH do host."
    echo "      Instale kiro-cli antes de executar este script."
    exit 1
fi

echo "kiro-cli encontrado em: $KIRO_HOST ($(du -sh "$KIRO_HOST" | cut -f1))"

if [[ -f "$KIRO_BIN" ]]; then
    echo "kiro-cli já presente no contexto de build. Pulando cópia."
else
    echo "Copiando kiro-cli para o contexto de build..."
    cp "$KIRO_HOST" "$KIRO_BIN"
    chmod +x "$KIRO_BIN"
    echo "Copiado: $KIRO_BIN ($(du -sh "$KIRO_BIN" | cut -f1))"
fi

echo ""
echo "Contexto de build pronto. Execute:"
echo "  docker compose build"
echo "  docker compose up"
