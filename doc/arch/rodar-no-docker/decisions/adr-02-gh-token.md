# ADR-02 — `GH_TOKEN` como autenticação headless do gh CLI

Status: Aceito
Data: 2026-07-07
Story: US-02 (#17)
Contexto relacionado: D-03, RF-03

## Contexto

Todas as operações de board (GitHub Projects V2, via `GitHubBoardAdapter`)
usam o `gh` CLI, que precisa estar autenticado. Em container não há como
executar `gh auth login` (interativo, exige browser/device flow).

## Decisão

Fornecer um Personal Access Token via variável de ambiente `GH_TOKEN`. O `gh`
consome o token automaticamente do ambiente; `gh auth status` retorna sucesso
sem que `gh auth login` seja executado. Este é o mecanismo oficial recomendado
para uso headless/automação do `gh`, e tem precedência sobre credenciais
armazenadas — comportamento adequado a um container efêmero.

O PAT exige os escopos `repo` (issues/PRs) e `project` (mover cards no Projects
V2). Sem `project`, o adapter falha nas operações de coluna.

## Alternativas consideradas

- **`gh auth login` no entrypoint** — interativo, requer browser/device code;
  incompatível com operação autônoma. Descartado.
- **`GITHUB_TOKEN` (token efêmero de Actions)** — específico de CI do GitHub,
  não se aplica ao container de longa duração da esteira. `GH_TOKEN` (PAT) é o
  ajuste correto para este contexto.

## Consequências

- (+) Um env var, zero estado interativo, precedência determinística.
- (−) Validação lazy hoje: sem o preflight (ADR-04), a ausência do token só
  falha na primeira chamada de board, no meio do loop.
- (−) Escopo insuficiente é uma falha previsível comum; o preflight (ADR-04) e
  a copy (M-04 do UX) tratam isso explicitamente.
- Token entra em runtime a partir do `.env` do host (US-03), nunca na imagem.

## Fontes

[cli.github.com/manual/gh_help_environment](https://cli.github.com/manual/gh_help_environment),
[cli.github.com/manual/gh_auth_login](https://cli.github.com/manual/gh_auth_login).
Conteúdo reescrito para conformidade com licenciamento.
