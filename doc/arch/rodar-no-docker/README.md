# Arquitetura — Rodar no Docker

Status: draft
Owner: arquitetura (Lucas Almeida)
Last updated: 2026-07-07

Documentação arquitetural da feature "Rodar no Docker". Esta pasta formaliza as
decisões (ADRs) que até aqui só existiam como referências (`ADR-01`, `ADR-02`…)
na matriz de requisitos, e descreve o desenho técnico por story.

## Princípio norteador

Simples que funciona. A esteira já roda hoje numa máquina preparada à mão; o
objetivo do Docker é **portar o setup manual para dentro da imagem/compose**,
não reinventar a autenticação. Nenhuma tecnologia nova de gestão de segredos,
nenhum sidecar, nenhum orquestrador. Env vars + um volume read-only para a chave
SSH — os mecanismos headless **oficiais** de cada dependência.

## Índice

| Documento | Escopo |
|---|---|
| [`us-02-autenticacao-headless.md`](us-02-autenticacao-headless.md) | Arquitetura da US-02 (#17): autenticar SSH, gh e kiro-cli sem interação |
| [`decisions/adr-01-kiro-api-key.md`](decisions/adr-01-kiro-api-key.md) | kiro-cli autentica via `KIRO_API_KEY` |
| [`decisions/adr-02-gh-token.md`](decisions/adr-02-gh-token.md) | gh CLI autentica via `GH_TOKEN` |
| [`decisions/adr-03-ssh-key-readonly.md`](decisions/adr-03-ssh-key-readonly.md) | Chave SSH montada read-only, copiada para `~/.ssh/id_pipe` |
| [`decisions/adr-04-preflight-credenciais.md`](decisions/adr-04-preflight-credenciais.md) | Preflight de credenciais no arranque (fail-fast) + lazy como salvaguarda |

## Índice de ADRs (feature completa)

| ADR | Título | Status | Story dona |
|-----|--------|--------|-----------|
| ADR-01 | `KIRO_API_KEY` para kiro-cli headless | Aceito | US-02 (#17) |
| ADR-02 | `GH_TOKEN` para gh headless | Aceito | US-02 (#17) |
| ADR-03 | Chave SSH read-only → `~/.ssh/id_pipe` | Aceito | US-02 (#17) |
| ADR-04 | Preflight de credenciais no `startup()` | Proposto | US-02 (#17) |
| ADR-05 | Container roda como usuário não-root com HOME gravável | Referenciado | US-01 (#16) |
| ADR-06 | Config/segredos externos via volume/env; nada fixo na imagem | Referenciado | US-01 (#16) |

ADR-05 e ADR-06 são decisões de infraestrutura da imagem (US-01) e são
formalizadas na arquitetura daquela story. Aqui são apenas referenciadas por
serem pré-condições da autenticação headless (HOME gravável para `_setup_ssh`
e para as sessões do kiro-cli; nenhum segredo na imagem).

## Insumos

- Requisitos: [`../../stories/rodar-no-docker/user-stories.md`](../../stories/rodar-no-docker/user-stories.md)
- Prototipação (UX/DX): [`../../stories/rodar-no-docker/ux/`](../../stories/rodar-no-docker/ux/)
- Produto: [`../../product/rodar-no-docker/`](../../product/rodar-no-docker/)
- Código: `src/__main__.py` (`_setup_ssh`, `startup`), `src/core/config.py`
  (`check_config`, `_validate_env`), `src/adapters/kiro_cli_agent.py` (`_run`)
