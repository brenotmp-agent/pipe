# ADR-02 — Build single-stage

Status: aceito
Data: 2026-07-07
Relacionado: RF-01, D-01

## Contexto

Há uma tendência de usar builds multi-stage por padrão. Precisamos decidir se
isso se justifica para esta imagem.

## Decisão

Usar um **único stage** de build.

## Justificativa

- Nada é compilado: não há artefato de build a descartar entre stages. A única
  dependência Python (`pyyaml`) instala via wheel; `git`/`gh`/`kiro-cli` são
  binários prontos.
- Multi-stage só reduziria tamanho se houvesse toolchain de compilação a
  separar — não é o caso. Traria complexidade (cópia entre stages, PATH de
  usuário) sem redução relevante.
- Mantém o Dockerfile legível e auditável, alinhado ao princípio "o simples que
  funciona".

## Alternativas descartadas

- **Multi-stage** (builder + runtime): complexidade extra sem ganho de tamanho
  mensurável neste caso.

## Consequências

- Um Dockerfile linear, fácil de manter.
- A redução de tamanho vem de `--no-install-recommends`, limpeza de
  `/var/lib/apt/lists` e `pip --no-cache-dir`, não de stages.
