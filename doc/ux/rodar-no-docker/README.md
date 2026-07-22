# UX — Rodar no Docker (US-05: Operação autônoma no runtime)

Status: draft
Owner: ux (Talita Souza)
Etapa: Prototipação
Last updated: 2026-07-07
Rastreabilidade: RF-07, RNF-04; ADR-05, ADR-06; R-4, R-5 · Issue #20

## Por que existe UX numa story headless?

A US-05 entrega a garantia de que o container **opera sozinho, sem intervenção
no runtime**. Isso muda o objeto de estudo da UX, mas não a elimina:

- Não há GUI. **A interface do produto são duas superfícies:**
  1. **O log do terminal** (`docker logs`) — é o único canal pelo qual o
     operador percebe o estado do sistema (está vivo? saudável? travou? por quê?).
  2. **O board do GitHub** — é a superfície de controle onde o humano atua nos
     gates `need_human`, **sem tocar no container**.
- O "usuário" é o **operador/analista**, não um usuário final de app.
- O momento de maior fricção é a **falha de setup** (credencial/config faltando):
  a qualidade da mensagem de erro decide se o operador resolve em 30 segundos ou
  abre um chamado.

Portanto, nesta etapa, "protótipo" = **mockups anotados da saída de terminal**
(a "tela" de um sistema headless) + **fluxo de interação humano↔board** +
**diretrizes de escrita (UX writing)** para status e erros.

## Restrição de escopo (importante)

RNF-04 / ADR-06 proíbem alteração da lógica de negócio da esteira nesta feature.
Logo, os artefatos aqui se dividem em:

- **Verificação (dentro da US-05):** confirmar que o comportamento atual já
  entrega uma boa experiência autônoma (fail-fast claro, sem prompts, logs em
  tempo real, gate `need_human` não trava).
- **Recomendações (backlog de UX):** melhorias de UX writing/observabilidade que
  exigiriam código. Ficam registradas como oportunidades priorizadas, **não** são
  implementadas nesta story.

## Artefatos desta etapa

| Arquivo | Conteúdo |
|---------|----------|
| [`us05-personas-e-jornada.md`](us05-personas-e-jornada.md) | Persona do operador, cenários e jornada de operação (primeiro `up` → regime permanente → falha → gate humano) |
| [`us05-prototipos-terminal.md`](us05-prototipos-terminal.md) | Protótipos anotados da saída de terminal (banner, arranque, regime, ociosidade, fail-fast, rate limit) e do fluxo no board |
| [`us05-diretrizes-e-avaliacao.md`](us05-diretrizes-e-avaliacao.md) | Diretrizes de UX writing para status/erros, avaliação heurística (Nielsen) da saída atual e backlog de recomendações |

## Referências de mercado (benchmark)

O produto é um **serviço autônomo de longa duração operado por logs** — a mesma
categoria de:

- **GitHub Actions self-hosted runner** — processo headless que faz *polling* de
  trabalho e loga "Listening for Jobs" quando ocioso; modelo de "espera visível".
- **Watchtower / cron / systemd services** — serviços de fundo cujo único feedback
  é o log; a boa prática é logar heartbeat/ciclo para provar que está vivo.
- **n8n / Apache Airflow (schedulers)** — orquestradores que rodam workers em
  loop; o operador confia no log de "tick"/"scheduler heartbeat" e resolve
  exceções numa **UI de board/DAG separada** — análogo ao nosso board do GitHub.
- **Docker logs / 12-Factor App (logs como stream de eventos)** — logs no stdout,
  não bufferizados, tratados como fluxo — exatamente o que `PYTHONUNBUFFERED=1`
  garante (AC-04).

O padrão comum a todos: **o operador não interage com o processo; ele lê o log e
age num plano de controle externo.** Nosso plano de controle é o board do GitHub.

## Fontes de boas práticas consultadas

- PatternFly — *Command-line interface handbook* (estrutura de mensagens de erro:
  o que aconteceu, por quê, como corrigir; linguagem simples; próximos passos;
  stack traces só atrás de flag de debug). Conteúdo reescrito para conformidade.
  <https://www.patternfly.org/content-design/writing-guides/cli-handbook/writing-guidelines>
- Shopify CLI — *UX guidelines for input, output and errors* (cores/estilos
  contextuais, símbolos ASCII-safe, modo não-interativo para automação).
  <https://github.com/Shopify/shopify-cli/wiki/UX-guidelines-for-input,-output-and-errors>
- Nielsen Norman Group — *10 Usability Heuristics* (visibilidade do estado do
  sistema; ajudar a reconhecer/diagnosticar/recuperar de erros; prevenção de erros).
- Boas práticas de logging/observabilidade em containers (logs no stdout, sem
  buffer, com contexto suficiente para reconstruir o estado).

> Nota: todo conteúdo de terceiros foi parafraseado e resumido para conformidade
> com as restrições de licenciamento das fontes.
