# ADR-04 — Pinagem de versões de todas as dependências

Status: aprovado
Owner: arquitetura
Last updated: 2026-07-22
Autora: Rafael Martins — Analista de Requisitos

---

## Contexto

Builds Docker sem pinagem de versão sofrem de "drift": o mesmo Dockerfile pode
produzir imagens diferentes em datas distintas, dependendo do que o repositório
APT ou o PyPI fornecerem na hora do build. Isso viola RNF-05 (versões pinadas)
e dificulta rastreabilidade e resposta a incidentes.

## Decisão

**Todas** as dependências da imagem devem ter versão explicitamente pinada:

| Dependência | Pinagem | Onde declarado |
|-------------|---------|----------------|
| `git` | `=1:2.47.3-0+deb13u1` | Dockerfile (APT) |
| `openssh-client` | `=1:10.0p1-7+deb13u4` | Dockerfile (APT) |
| `gh` | `=2.96.0` via tarball ou APT | Dockerfile via `ARG GH_VERSION` |
| `pyyaml` | `==6.0.3` | Dockerfile via `ARG PYYAML_VERSION` |
| `kiro-cli` | SHA-256 do zip | Dockerfile via `ARG KIRO_CLI_SHA256` |
| Imagem base | digest fixado | `docker/versions.env` (recomendado) |

As versões são registradas em `docker/versions.env` como fonte canônica, e os
valores são referenciados no Dockerfile via `ARG` com defaults.

## Justificativa

- Reprodutibilidade: o mesmo `docker build` em datas diferentes deve produzir
  imagens funcionalmente idênticas.
- Segurança: pinagem impede que uma atualização silenciosa de upstream introduza
  uma regressão ou vulnerabilidade sem revisão.
- Rastreabilidade: cada componente tem uma versão documentada e verificável.
- O kiro-cli não oferece URL com versão explícita; o SHA-256 do zip é a âncora
  de reproducibilidade (ver ADR-03).

## Consequências

- Quando for necessário atualizar uma dependência, o operador deve:
  1. Levantar a nova versão usando os procedimentos da issue #44.
  2. Atualizar `docker/versions.env`.
  3. Fazer rebuild e validar os critérios de aceitação.
- Versões APT (git, openssh-client) podem quebrar o build se o repositório
  Debian remover versões antigas. Em caso de quebra, reexecutar o procedimento
  de levantamento de versões e atualizar o manifesto.
- Versão do `gh` via tarball: o tarball
  `gh_2.96.0_linux_amd64.tar.gz` está disponível permanentemente em
  `https://github.com/cli/cli/releases/` — não sofre remoção.

## Valores atuais (registrados em docker/versions.env)

```env
GH_VERSION=2.96.0
PYYAML_VERSION=6.0.3
KIRO_CLI_VERSION=2.13.1
KIRO_CLI_SHA256=49d712558cc930d3570387ce468887ca0b510ba8b5f08e2f3c7a7a55d44e677f
KIRO_CLI_URL=https://desktop-release.q.us-east-1.amazonaws.com/latest/kirocli-x86_64-linux.zip
GIT_APT_VERSION=1:2.47.3-0+deb13u1
OPENSSH_CLIENT_APT_VERSION=1:10.0p1-7+deb13u4
BASE_IMAGE=python:3.12-slim
```
