# Arquitetura — Rodar no Docker

Status: draft (revisão 2)
Owner: arquitetura
Last updated: 2026-07-21

Documentação arquitetural da feature "Rodar no Docker" (issue #1), com foco na
story-base **US-01 — Empacotar a esteira em imagem Docker** (issue #16).

> **Revisão 2 (2026-07-21):** o código da esteira passa a ser obtido por
> `git clone` no build (ADR-07), no lugar do `COPY src/`, atendendo à validação
> que pedia que o container baixasse o código do GitHub sem download manual.

## Índice

- [`arquitetura.md`](arquitetura.md) — visão da solução, estrutura da imagem,
  Dockerfile de referência, rastreabilidade e orientações para as demais
  stories.
- [`adr/`](adr/) — Architecture Decision Records (ADR-01 a ADR-07).

## Catálogo de requisitos (formalização)

Os identificadores abaixo são referenciados por Produto, Requisitos e UX
(`doc/product/`, `doc/stories/`, `doc/ux/`). Esta seção os consolida para dar
rastreabilidade única à feature.

### Requisitos funcionais (RF)

| ID | Requisito |
|----|-----------|
| RF-01 | A esteira executa `python -m src` dentro de um container e inicia o loop principal sem nenhuma instalação adicional no host. |

### Requisitos não-funcionais (RNF)

| ID | Categoria | Requisito |
|----|-----------|-----------|
| RNF-01 | Segurança | Nenhum segredo (chave SSH, `GH_TOKEN`, `KIRO_API_KEY`, credencial do `gh`) é copiado ou embutido na imagem. |
| RNF-02 | Portabilidade / Tamanho | A imagem é baseada em `python:3.12-slim`. |
| RNF-03 | Operabilidade | Credenciais e configuração são trocáveis sem rebuild da imagem (injeção em runtime). |
| RNF-04 | Usabilidade | A esteira sobe com um único comando de orquestração (`docker compose up`). |
| RNF-05 | Reprodutibilidade | Todas as dependências de runtime têm versão explicitamente pinada. |

### Restrições e decisões de contexto (D)

| ID | Restrição |
|----|-----------|
| D-01 | O empacotamento **não** altera a lógica de negócio da esteira; apenas embala e parametriza o runtime. |
| D-02 | Toda dependência de runtime (`git`, `gh`, `kiro-cli`, `openssh-client`, `ca-certificates`, `pyyaml`) é instalada com versão pinada no Dockerfile. |

## Riscos

| ID | Risco | Mitigação |
|----|-------|-----------|
| R-1 | Autenticação headless do kiro-cli depende de `KIRO_API_KEY` (plano Kiro Pro+) e só é verificável em runtime. | Smoke test de build valida apenas o binário (`kiro-cli --version`); a autenticação é validada no primeiro ciclo (US-05). |
| R-2 | O kiro-cli **não tem URL versionada** — o download aponta sempre para `/latest/`. | ADR-04: registrar a versão validada em `ARG` + comentário e verificar o checksum do artefato no build. |
| R-3 | O build depende de acesso de leitura ao repo **privado** da esteira (SSH) para o `git clone` (ADR-07). | Reuso da `PIPE_SSH_KEY_FILE` como secret efêmero de BuildKit; `StrictHostKeyChecking=accept-new`; falha clara do clone se a chave não tiver acesso. |

## Rastreabilidade rápida

| Requisito | Atendido por |
|-----------|--------------|
| RF-01 | ADR-01, ADR-02, ADR-05, ADR-07; Dockerfile de referência (CMD `python -m src`) |
| RNF-01 | ADR-06; ADR-07 (`.dockerignore` nega todo o contexto + secret efêmero no clone) |
| RNF-02 | ADR-01 |
| RNF-03 | ADR-06 |
| RNF-04 | ADR-06 (orquestração — US-03) |
| RNF-05 | ADR-03, ADR-04, ADR-07 (pin de `PIPE_REF` por tag/SHA) |
| D-01 | Todas as ADRs (nenhuma toca o domínio `src/core`) |
| D-02 | ADR-04 |
