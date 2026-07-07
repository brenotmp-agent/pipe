# ADR-01 — Imagem base `python:3.12-slim`

Status: aceito
Data: 2026-07-07
Relacionado: RNF-02, RF-01

## Contexto

A esteira exige Python 3.12+ (README) e roda como um processo Python de longa
duração. Precisamos de uma base que traga o interpretador correto, seja enxuta
e tenha `apt` para instalar `git`, `gh` e utilitários.

## Decisão

Usar `python:3.12-slim` como imagem base.

## Justificativa

- Traz o Python 3.12 oficial já configurado — sem gerência manual de PPA/pyenv.
- Variante `slim` (Debian) é pequena, mas mantém `apt` e glibc completo.
- glibc do Debian bookworm/trixie (≥ 2.36) satisfaz o requisito do kiro-cli
  (glibc ≥ 2.34), permitindo a variante padrão (não-musl) do binário — ver
  ADR-03.

## Alternativas descartadas

- **`python:3.12` (full):** centenas de MB extras de toolchain que a esteira
  não usa (não compila nada).
- **`alpine` (musl):** exigiria a variante musl do kiro-cli e costuma dar
  atrito com wheels/binários que assumem glibc. Complexidade sem ganho real
  aqui.
- **`distroless`:** sem `apt`/shell, inviabiliza instalar `git`/`gh` e o smoke
  test; overhead de multi-stage sem retorno para este caso.

## Consequências

- Imagem final pequena e previsível.
- Atualizações de segurança da base vêm pelo ciclo oficial da tag `3.12-slim`.
