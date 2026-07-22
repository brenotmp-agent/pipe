# ADR-03 — Instalação do kiro-cli: download via URL + verificação SHA-256

Status: aprovado
Owner: arquitetura
Last updated: 2026-07-22
Autora: Rafael Martins — Analista de Requisitos

---

## Contexto

O kiro-cli é um binário proprietário sem repositório APT oficial e sem URL de
download com versão explícita na path. A tarefa de levantamento de versões
(issue #44) identificou que a URL pública disponível usa `/latest/` na path:

```
https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-x86_64-linux.zip
```

O risco R-2 exige que a versão instalada seja rastreável e que o build falhe
caso o artefato seja adulterado ou substituído.

Havia três alternativas sob consideração:

1. **COPY do host** — copiar o binário via `prepare-docker.sh` (abordagem da
   task #40).
2. **Download via URL + SHA-256** — baixar o zip durante o build e verificar
   o checksum.
3. **Instalador via `kiro.dev/install.sh --version`** — rejeitado: a flag
   `--version` não existe na documentação oficial (verificado em 2026-07-21).

## Decisão

Usar **download via URL + verificação SHA-256** durante o build.

O zip é baixado de
`https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-x86_64-linux.zip`
e o checksum do arquivo é verificado antes da extração:

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

## Justificativa

- **Sem dependência do host**: elimina a necessidade do `prepare-docker.sh` e
  do passo manual de cópia do binário antes de cada build.
- **Verificação de integridade**: o SHA-256 âncora a versão exata. Mesmo que a
  URL use `/latest/`, se o artefato mudar o build falha com erro explícito.
  Isso mitiga o risco R-2 de forma mais robusta que `COPY`.
- **Auditabilidade**: o SHA-256 e a versão ficam declarados explicitamente como
  `ARG` no Dockerfile, com valores padrão registrados em `docker/versions.env`.
- **Sem segredo no contexto de build**: ao contrário do `COPY`, não é preciso
  ter o binário disponível no diretório do host.
- A abordagem de `COPY do host` (task #40) foi válida como solução inicial, mas
  exige um passo manual (`prepare-docker.sh`) e o binário precisa existir no
  contexto de build — fragilidade operacional.

## Consequências

- O build requer conectividade de rede para `desktop-release.q.us-east-1.amazonaws.com`.
- Quando a AWS lançar uma nova versão do kiro-cli, o operador deve atualizar
  `KIRO_CLI_SHA256` e `KIRO_CLI_VERSION` em `docker/versions.env` e rebuild.
  O build **falhará** se apenas a URL for atualizada sem o SHA correspondente.
- O `prepare-docker.sh` e a instrução `COPY kiro-cli` no Dockerfile anterior
  são substituídos por esta abordagem.
- O smoke test `~/.local/bin/kiro-cli --version` na camada 6 usa o path
  completo (não depende do `PATH` da camada 7) — ver ADR-05 para detalhes
  sobre o usuário não-root e o PATH.
- Valores registrados em `docker/versions.env` (levantados em 2026-07-22):
  - `KIRO_CLI_VERSION=2.13.1`
  - `KIRO_CLI_SHA256=49d712558cc930d3570387ce468887ca0b510ba8b5f08e2f3c7a7a55d44e677f`
  - `KIRO_CLI_URL=https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-x86_64-linux.zip`
