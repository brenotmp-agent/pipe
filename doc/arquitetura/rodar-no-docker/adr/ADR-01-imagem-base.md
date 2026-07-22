# ADR-01 — Imagem base: python:3.12-slim

Status: aprovado
Owner: arquitetura
Last updated: 2026-07-22
Autora: Rafael Martins — Analista de Requisitos

---

## Contexto

A esteira agêntica é uma aplicação Python 3.12+. A imagem base precisa fornecer
o interpretador Python correto e ser suficientemente enxuta para reduzir
superfície de ataque e tempo de build.

## Decisão

Usar `python:3.12-slim` como imagem base.

## Justificativa

- `python:3.12-slim` é a variante oficial do Python sem pacotes de
  desenvolvimento desnecessários — inclui o runtime mas não cabeçalhos, man
  pages nem compiladores.
- Baseada em Debian, compatível com o repositório APT do GitHub CLI e com a
  libc glibc necessária para o binário do kiro-cli (validado em 2026-07-22:
  kiro-cli 2.13.1 executa sem erros em `python:3.12-slim`).
- Alternativas rejeitadas:
  - `python:3.12-alpine` — usa musl libc; o binário kiro-cli
    (`x86_64-unknown-linux-gnu`) falha com erro de glibc.
  - `python:3.12` (full) — 1 GB+; pesado demais sem ganho funcional.
  - `ubuntu:24.04` — não inclui Python por padrão; exigiria instalação manual.

## Consequências

- A imagem produzida tem base Debian Bookworm (slim).
- Pacotes APT disponíveis são os do repositório Debian Bookworm.
- Versões de `git` e `openssh-client` disponíveis em 2026-07-22:
  `1:2.47.3-0+deb13u1` e `1:10.0p1-7+deb13u4` respectivamente.
- O digest fixado da imagem base é
  `sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de`
  (registrado em `docker/versions.env`).
