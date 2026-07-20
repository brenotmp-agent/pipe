# Incidente — Avaliação de complexidade falhando

Status: Decisão de tratamento
Owner: engineering
Last updated: 2026-07-07

## Registro

### Descrição:
- Data: 2026-07-07
- Reportado por: Breno (autor da issue #23)

Todas as issues do board Task da própria esteira `pipe` ao passar pela coluna `planning-poker` recebem um perfil de agente via `/agent_level`, porém quando chegam à coluna `desenvolvimento` são atendidas pelo agente padrão da coluna em vez do agente mapeado pelo `override-agent`. O nível definido pelo planning-poker é perdido silenciosamente antes de ser consumido.

### Evidências

A hipótese inicial apontava para a forma de armazenamento das labels como causa. A triagem e a análise técnica confirmaram causa raiz diferente — perda de estado local no ciclo de sync down.

### Impacto:
100% das issues do board `task` que passam pela coluna `planning-poker` são afetadas. A funcionalidade de seleção de agente por complexidade (`override-agent`) fica completamente inoperante: tasks de alta complexidade chegam ao agente default (modelo menos capaz), gerando retrabalho e entregas de qualidade inferior; tasks de baixa complexidade podem ser executadas pelo modelo mais caro, desperdiçando tokens.

---

## Triagem

### Classificação:
Bug de software — perda de estado local por reescrita do sync down.

### Severidade:
**P1 — Alta**. Funcionalidade de seleção diferenciada de agentes por complexidade completamente inoperante. O investimento feito na etapa de planning-poker é perdido em 100% das issues. Degradação silenciosa (sem erro ou alarme).

### Prioridade:
Alta — corrigir com urgência.

### Workaround:
Nenhum automatizado viável no fluxo agêntico. Reeditar manualmente o `/agent_level` no `-body.md` após cada sync é impraticável; suprimir o sync down quebraria a sincronização do board.

---

## Análise Técnica

**Responsável:** Bruno Ferreira - Engenheiro de Software SR
**Data:** 2026-07-07

### Causa raiz

O `agent_level` é um campo de estado **puramente local** — o GitHub não armazena esse dado. O sync down reconstrói o arquivo `-body.md` exclusivamente a partir do estado do board via `from_issue()` (`src/core/commands.py`, linhas 86-103), que não popula o campo `agent_level`. A função `_compose_down_body()` (`src/core/sync.py`, linhas 66-77, chamada nas linhas 473 e 601) regrava o bloco `@---` sem `/agent_level`. No primeiro down sync que atinge a issue (full sync diário, mudança manual no board, ou gatilho de par recíproco), o nível é descartado. Quando a issue chega à coluna `desenvolvimento`, `agent_level()` retorna `None`, `override-agent` nunca é aplicado e a issue é atendida pelo agente default da coluna.

Observação: o parser/serializer e a resolução de agente funcionam corretamente (testes verdes em `tests/test_agent_level.py`). O defeito está na fronteira não testada do sync down — ausência de teste de round-trip (board → `from_issue` → `_compose_down_body` → arquivo) mascarou o bug.

### Abordagens de correção identificadas

**Abordagem 1 — Preservar `/agent_level` no sync down (hotfix imediato):**
Em `_apply_change_down` (`sync.py`), ler o `agent_level` atual do `-body.md` local antes de sobrescrever e repassá-lo a `_compose_down_body` para reinjeção no `IssueCommands` derivado de `from_issue`. Em `_apply_create_down` não há estado local prévio, nada a fazer.
- Escopo: ~15–30 linhas em `sync.py` + 1-2 testes de round-trip.
- Esforço: ~0,5 dia. Risco baixo.

**Abordagem 2 — Persistir via label `agent-level-<nível>` no GitHub (solução estrutural):**
Substituir o armazenamento local volátil por labels no board. O planning-poker passa a gravar a label; `resolve_agent_id` resolve o nível a partir das labels (match por prefixo). A label precisa ser tratada como campo especial (como `need_human`) para não ser sobrescrita pela semântica SET de `/labels`. Exige migração das issues em aberto e ajustes em `agent.py`, `commands.py`, possivelmente `config.py` e README.
- Esforço: ~1,5-2 dias. Risco médio.

As abordagens não são mutuamente exclusivas: a 1 estabiliza imediatamente, a 2 elimina a fragilidade estrutural na raiz.

---

## Decisão de tratamento (revisada)

**Opção escolhida: Opção 2 — Task de correção no board Task.**

**Responsável pela revisão:** Isabela Gomes - Tech Lead
**Data da revisão:** 2026-07-20

**Histórico de revisão:**
- Decisão original (2026-07-07): duas tasks — hotfix (Abordagem 1) + refatoração estrutural (Abordagem 2).
- Revisão solicitada por `brenodpm` (2026-07-20): a Abordagem 1 (hotfix — preservar no sync) foi rejeitada por criar complexidade desnecessária em `_apply_change_down` e estabelecer precedente para bugs futuros. Aprovada somente a Abordagem 2 (refatoração estrutural via labels).

**Decisão revisada:**

O incidente é um bug de software com causa raiz clara e solução técnica bem definida. O fluxo de incidente produtivo não é necessário. Será criada **uma única task** no board `task`, implementando diretamente a solução estrutural definitiva: persistir o `agent_level` como label no GitHub, eliminando por completo a dependência de estado local volátil que originou o problema.

A decisão de não criar o hotfix intermediário é deliberada: a Abordagem 1 corrigiria o sintoma (`_compose_down_body` descartando o campo) mas deixaria o design original intacto — um campo de estado que existe apenas no arquivo local e é destruído a cada sync down. A Abordagem 2 resolve o problema em sua raiz, tornando o hotfix desnecessário.

---

## Tarefas de correção

- [ ] Task: Refatoração estrutural — persistir `agent_level` via label `agent-level-<nível>` no GitHub — board `task`

---

## Ação proposta

**Decisão:** Opção 2 — problema intermediário resolvível por task de correção (solução estrutural única).

**Task — Refatoração estrutural: Persistir `agent_level` via label `agent-level-<nível>` no GitHub**
- Board: `task`
- Coluna: `backlog`
- Objetivo: Eliminar a dependência de estado local volátil. O `agent_level` passa a ser armazenado como label no board (`agent-level-low`, `agent-level-medium`, `agent-level-high`), persistido e sincronizado pelo mecanismo de labels já existente.
- Escopo técnico:
  - `src/core/agent.py`: adaptar `agent_level()` para resolver o nível a partir das labels da issue (match por prefixo `agent-level-`); adaptar `resolve_agent_id()` conforme necessário.
  - `src/core/commands.py`: tratar a label `agent-level-<nível>` como campo especial (semelhante a `need_human`) — não deve ser sobrescrita pela semântica SET de `/labels`; atualizar `from_issue()` para popular o campo a partir da label do board.
  - Planning-poker: garantir que o agente grave a label `agent-level-<nível>` correspondente ao nível definido (em vez de — ou além de — usar `/agent_level` no bloco `@---`).
  - Migração: converter issues em aberto que possuam `/agent_level` no bloco `@---` para a nova label.
  - Configuração e docs: verificar se `config.py` / `override-agent` precisam de ajuste; atualizar README com a nova semântica.
  - Testes: ampliar suíte para cobrir resolução de agente a partir de labels e o tratamento especial da label no ciclo de sync.
- Esforço: medium (~1,5–2 dias). Risco médio.
- Critério de aceite:
  - `agent_level` armazenado como label `agent-level-<nível>` no GitHub.
  - Sync down preserva o nível via label, sem dependência de estado local.
  - `resolve_agent_id` retorna o agente correto com base na label.
  - Label `agent-level-<nível>` não sobrescrita pelo `/labels` do usuário.
  - Issues em aberto migradas para o novo formato.
  - Testes passando; sem quebra de funcionalidades existentes.
