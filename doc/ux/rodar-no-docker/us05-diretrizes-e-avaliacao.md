# US-05 — Diretrizes de UX writing, avaliação heurística e backlog de recomendações

Status: draft
Owner: ux (Talita Souza)
Last updated: 2026-07-07
Rastreabilidade: RF-07, RNF-04; ADR-05, ADR-06; R-4, R-5 · Issue #20

> Este documento fecha a etapa de Prototipação da US-05 com três entregas:
> (1) **diretrizes de UX writing** para status e erros num sistema headless;
> (2) **avaliação heurística** (Nielsen) da saída atual do terminal;
> (3) **backlog priorizado de recomendações** `R-UX-*`, que exigiriam código e
> por isso ficam **fora do escopo** desta story (RNF-04 / ADR-06).

---

## 1. Diretrizes de UX writing (para logs de status e erro)

Base: boas práticas de CLI parafraseadas do *PatternFly CLI handbook* e das *UX
guidelines* do Shopify CLI, adaptadas ao contexto de um serviço headless de
longa duração. Conteúdo reescrito para conformidade com as licenças das fontes.

### D1 — Toda mensagem de erro responde 3 perguntas
O que aconteceu · por que · como corrigir. Exemplo já presente no código e que
serve de modelo:

> `Variável de ambiente 'PIPE_SSH_KEY_FILE' não definida ou vazia. Defina com:
> export PIPE_SSH_KEY_FILE=~/.ssh/id_ed25519`

Faz o "o quê" (não definida) e o "como" (comando de correção). É o padrão-ouro a
replicar nas demais mensagens de erro.

### D2 — Linguagem simples, orientada ao operador
O leitor é o operador (persona Otávio), que **não conhece o código**. Evitar
nomes internos de função/variável na mensagem de terminal; usar termos do mundo
dele (credencial, board, container). Detalhe técnico e stack trace vão para o
**arquivo de log** (JSON), não para o stdout.

### D3 — Espera sempre visível, nunca silêncio
Operação longa (sleep, penalty, execução de agente) deve emitir sinal com
**horário de retorno previsível**. Já aplicado no `Sleep` e no `Rate limit`
(`retorna às HH:MM:SS`). É o principal antídoto contra a dor "travado ou
ocioso?". Onde ainda há silêncio longo (execução do agente, P3), fica a
recomendação R-UX-03.

### D4 — Severidade legível sem depender de cor
As cores ANSI (`log.py`) somem em agregadores de log e em `docker logs` sem TTY.
Mensagens de erro devem ser reconhecíveis **pelo texto** (o módulo `[Config]`,
`[Pipe]`, ou um prefixo textual de severidade), não só pela cor. Ver R-UX-05.

### D5 — Consistência de vocabulário e formato
Manter o padrão `[Módulo] mensagem` e um léxico estável (sempre "board", nunca
alternar com "quadro"; sempre "ciclo", "sessão", "tarefa"). Consistência reduz a
carga cognitiva de quem lê o log corrido por horas.

### D6 — Modo não-interativo é contrato, não opção
Nenhuma mensagem pode terminar esperando resposta (`[y/N]`, "pressione Enter").
Em automação, um prompt = travamento. Já garantido por
`kiro-cli chat --no-interactive` (AC-01) e pela validação síncrona de
`check_config`. Qualquer código novo deve preservar esse contrato.

### D7 — Ligar as duas superfícies (log ↔ board)
Sempre que o estado exigir ação humana **no board**, o log deveria dizê-lo
(hoje não diz — gate `need_human` é silencioso). Diretriz para futuras
mensagens: quando o runtime "empurra" uma decisão para o board, tornar isso
explícito no log. Ver R-UX-07.

---

## 2. Avaliação heurística da saída atual (10 heurísticas de Nielsen)

Escopo: a superfície de terminal (`docker logs`) + o fluxo no board. Escala:
✅ atende · 🟡 parcial · ❌ falha. Nenhuma heurística resultou em ❌.

| # | Heurística | Nota | Evidência / observação |
|---|-----------|------|------------------------|
| 1 | **Visibilidade do estado** | 🟡 | Banner, fases, heartbeat de sleep e rate limit são ótimos. Lacunas: silêncio durante execução do agente (P3) e gate `need_human` invisível (P6). |
| 2 | **Correspondência com o mundo real** | ✅ | Vocabulário do operador (board, sync, tarefa, sessão). Sem jargão de implementação nas linhas de INFO. |
| 3 | **Controle e liberdade do usuário** | ✅ | Controle vive no board (arrastar card) e no host (`up`/`down`/`restart`). O container é read-only por design — coerente com a persona. |
| 4 | **Consistência e padrões** | ✅ | Formato `HH:MM:SS [Módulo] msg` uniforme; segue a categoria de mercado (runner/scheduler observado por log). |
| 5 | **Prevenção de erros** | ✅ | `check_config` valida SSH e contexts **antes** do loop (fail-fast); gate de permissões (`check_access`) impede iniciar sem poder operar o repo. |
| 6 | **Reconhecer em vez de lembrar** | 🟡 | A linha do agente mostra `log=...` (onde achar o detalhe) — excelente. Mas o operador precisa "lembrar" que uma issue pulada pode estar em `need_human` no board (P6). |
| 7 | **Flexibilidade e eficiência** | 🟡 | Bom para o caso comum. Falta um nível DEBUG por board varrido (R-UX-02) para o operador avançado diagnosticar sem ruído no INFO. |
| 8 | **Estético e minimalista** | ✅ | Log enxuto, uma linha por evento relevante; detalhe volumoso segregado no arquivo JSON. |
| 9 | **Ajudar a reconhecer/diagnosticar/recuperar de erros** | 🟡 | Erros de setup são exemplares (D1). Já erros de runtime caem em `Erro no ciclo (não fatal): {e}` genérico (P5) — dificulta diagnóstico da causa raiz. |
| 10 | **Ajuda e documentação** | 🟡 | Depende do guia de operação (US-06/RF-08). O log aponta o arquivo de detalhe, mas não há "como agir" para throttle/penalty sem doc externa. |

**Placar:** 5 ✅ · 5 🟡 · 0 ❌.

**Leitura de UX:** a base de observabilidade é **sólida e suficiente para a
US-05** — nada precisa mudar para o container operar sozinho e satisfazer os AC.
As notas 🟡 são oportunidades de refinamento, não bloqueios. Todas viram
recomendação `R-UX-*` abaixo.

---

## 3. Backlog de recomendações de UX (fora do escopo da US-05)

Cada item exige alteração de código e, portanto, respeita RNF-04/ADR-06 ficando
**fora** desta story. Prioridade: **Alta** (fecha lacuna real de percepção) ·
**Média** (melhora diagnóstico) · **Baixa** (refinamento).

| ID | Recomendação | Origem | Prioridade | Custo estimado | Vira issue? |
|----|-------------|--------|------------|----------------|-------------|
| **R-UX-07** | Logar, 1×/ciclo, resumo de issues aguardando humano no board (ex.: `2 issue(s) aguardando humano: #18, #20`). Liga log↔board. | P6, P9, D7, Heur.1/6 | **Alta** | Baixo (só leitura de snapshot + log) | **Sim** |
| **R-UX-03** | Heartbeat durante execução do agente (`agente #N em execução há Xmin`) ou encaminhar marcos do agente ao stdout, eliminando o silêncio longo. | P3, D3, Heur.1 | **Alta** | Médio | **Sim** |
| **R-UX-04** | Tratar interação `restart` × erro de config: evitar crash-loop cego (documentar + avaliar `on-failure`/exit-code de config). | P4, ADR-05 | **Alta** | Médio (decisão com US-03/Arq.) | **Sim** |
| **R-UX-06** | Categorizar falhas de credencial no runtime (`credencial do GitHub rejeitada — verifique GH_TOKEN`) em vez de `Erro no ciclo (não fatal)` genérico. | P5, D1, Heur.9 | Média | Médio | Sim |
| **R-UX-05** | Prefixo textual de severidade nas mensagens de erro (não depender só da cor ANSI), robusto para agregadores de log. | P4, D4, Heur.9 | Média | Baixo | Sim |
| **R-UX-02** | Nível DEBUG por board varrido sem tarefa (`board 'story' sem tarefa elegível`), rastreabilidade sem poluir INFO. | P2, Heur.7 | Baixa | Baixo | Talvez |
| **R-UX-08** | Documentar throttle/penalty no guia de operação (US-06) para não confundir com travamento. **(Doc, não código.)** | P7, Heur.10 | Média | Baixo | Sim (em US-06) |
| **R-UX-01** | Contexto de progresso no arranque (duração esperada de clone/sync). | P1 | Baixa | Médio | Talvez |
| **R-UX-09** | Linha de boot com uptime/contagem de reinícios para contextualizar restart no histórico de log. | P8 | Baixa | Médio | Talvez |

### Recomendação de sequência (se/quando o backlog for priorizado)
1. **R-UX-07** e **R-UX-04** primeiro — são as que mais afetam a confiança do
   operador num sistema *autônomo* (gate invisível e crash-loop de config).
2. **R-UX-03** e **R-UX-06** — encurtam diagnóstico nos dois pontos de maior
   ansiedade da jornada (execução longa e falha de credencial).
3. **R-UX-08** cabe já em US-06 (é documentação, custo baixo, alto retorno).
4. Demais (R-UX-01/02/05/09) — refinamentos oportunos.

---

## 4. Fechamento da etapa de Prototipação

- **Verificação (dentro da US-05):** os protótipos P1–P9 e a avaliação heurística
  confirmam que o comportamento atual entrega uma experiência autônoma adequada
  e satisfaz AC-01 a AC-06 **sem alterar a lógica de negócio** (RNF-04). Não há
  artefato de UX que precise de implementação para a story ser concluída.
- **Recomendações (backlog):** 9 itens `R-UX-*` registrados como oportunidades de
  observabilidade/UX writing, priorizados, para tratamento em stories futuras —
  **não** nesta.
- **Sem lacunas abertas de UX.** A entrevista com o usuário foi substituída, na
  ausência de intervenção no runtime, pela leitura da documentação de produto
  (vision/problem-space/épicos), requisitos e arquitetura já aprovados, e pela
  inspeção do código real que produz cada mensagem — garantindo que os
  protótipos refletem o sistema, não suposições.

Artefatos da etapa: [`README.md`](README.md) ·
[`us05-personas-e-jornada.md`](us05-personas-e-jornada.md) ·
[`us05-prototipos-terminal.md`](us05-prototipos-terminal.md) · este documento.
