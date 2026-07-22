# ADR-02 — Build single-stage

Status: aprovado
Owner: arquitetura
Last updated: 2026-07-22
Autora: Rafael Martins — Analista de Requisitos

---

## Contexto

Builds multi-stage são úteis quando é necessário compilar artefatos em uma
imagem intermediária e copiar apenas os binários resultantes para a imagem
final. A esteira é uma aplicação Python interpretada, sem etapa de compilação.

## Decisão

Usar build **single-stage** — um único `FROM` no Dockerfile.

## Justificativa

- Não há etapa de compilação: Python não gera bytecode antecipado, e todas as
  dependências (`pyyaml`) são instaladas diretamente via pip.
- Os binários de sistema (`git`, `gh`, `openssh-client`) são instalados via
  APT/tarball e ficam na imagem final — não há artefatos intermediários a
  descartar.
- O kiro-cli é instalado via zip+install.sh e o executável fica em
  `~/.local/bin/kiro-cli` — também pertence à imagem final.
- Multi-stage adicionaria complexidade sem redução de tamanho: todos os
  componentes instalados no build são necessários em runtime.
- Alternativa rejeitada: multi-stage com imagem `builder` para instalar
  dependências e imagem `runtime` limpa. Rejeitada porque os binários de
  sistema (git, gh, openssh) são necessários em runtime, não apenas no build.

## Consequências

- O Dockerfile tem exatamente um `FROM`.
- A ordem das camadas deve ser planejada da mais estável para a mais volátil,
  para maximizar reuso de cache:
  1. Base
  2. Dependências de sistema (APT)
  3. GitHub CLI
  4. PyYAML
  5. Usuário não-root
  6. kiro-cli
  7. Variáveis de ambiente
  8. Código da esteira (mais volátil — muda a cada commit)
