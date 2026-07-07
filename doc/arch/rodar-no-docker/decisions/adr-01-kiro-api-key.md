# ADR-01 — `KIRO_API_KEY` como autenticação headless do kiro-cli

Status: Aceito
Data: 2026-07-07
Story: US-02 (#17)
Contexto relacionado: D-01, RF-04, R-3

## Contexto

Em container não há browser nem sessão interativa. O `kiro-cli` (agente) precisa
autenticar sem qualquer toque humano. A decisão de como fazer isso era o único
risco potencialmente bloqueador da feature (D-01).

## Decisão

Usar a variável de ambiente `KIRO_API_KEY` como mecanismo de autenticação do
kiro-cli. Quando definida, o kiro-cli pula o fluxo de login por browser
inteiramente. O agente é invocado em modo headless com `kiro-cli chat
--no-interactive --trust-all-tools` (já implementado em
`kiro_cli_agent.py:_run`).

Disponível a partir do Kiro CLI 2.0. A precedência de autenticação é: sessão de
browser (ausente em container) → `KIRO_API_KEY` → nenhum. Em container,
`KIRO_API_KEY` é sempre o método ativo, confirmável por `kiro-cli whoami` (ou o
subcomando de status equivalente da versão instalada) sem imprimir a key.

## Alternativas consideradas

- **Login por browser (`kiro-cli login`)** — inviável sem GUI/interação; quebra
  a operação autônoma. Descartado.
- **Automação do login por browser (headless browser / expect)** — frágil,
  fora dos mecanismos oficiais, alto custo de manutenção. Descartado (viola a
  diretriz "mecanismos oficiais apenas").

## Consequências

- (+) Autenticação determinística, um único env var, sem estado interativo.
- (+) Continuidade de sessão preservada — o SQLite de sessões do kiro-cli
  independe do método de auth (detalhado em §5 do doc de arquitetura, R-1).
- (−) Exige assinatura Kiro Pro ou superior; em contas gerenciadas por admin, a
  geração de keys precisa estar habilitada (R-3). Pré-requisito operacional a
  documentar no runbook (US-06).
- A key entra em runtime (US-03), nunca na imagem (RNF-01).

## Fontes

[kiro.dev/docs/cli/headless](https://kiro.dev/docs/cli/headless/),
[kiro.dev/changelog/cli/2-0](https://kiro.dev/changelog/cli/2-0/).
Conteúdo reescrito para conformidade com licenciamento.
