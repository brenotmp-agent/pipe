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

## Decisão de tratamento

**Opção escolhida: Opção 2 — Tasks de correção no board Task.**

**Justificativa:**

O incidente é um bug de software com causa raiz clara, solução técnica bem definida e escopo de correção delimitado (~0,5 a 2 dias). Não há sistema fora do ar, não há perda de dados irreversível e não há necessidade de ação de emergência fora do fluxo normal de desenvolvimento. O problema é grave (P1) em termos de impacto funcional, mas tratável pelo processo padrão de engenharia sem necessidade de manter o fluxo de incidente produtivo ativo.

Serão criadas **duas tasks** no board `task`:
1. **Hotfix (Abordagem 1):** Preservar `/agent_level` no sync down — correção imediata de baixo risco.
2. **Refatoração estrutural (Abordagem 2):** Persistir `agent_level` via label `agent-level-<nível>` no GitHub — elimina a fragilidade na raiz, bloqueada pela conclusão do hotfix.

---

## Tarefas de correção

- [ ] Task: Hotfix — preservar `agent_level` no sync down (`_apply_change_down` em `sync.py`) — board `task`
- [ ] Task: Refatoração estrutural — persistir `agent_level` via label `agent-level-<nível>` no GitHub — board `task` (bloqueada pela task de hotfix)

---

## Ação proposta

**Decisão:** Opção 2 — problema intermediário resolvível por tasks de correção.

A análise técnica confirma que o bug tem causa raiz única e bem delimitada, solução técnica documentada e impacto controlável (sem risco de corrupção de dados ou indisponibilidade sistêmica). O fluxo de incidente produtivo não é necessário.

**Task 1 — Hotfix: Preservar `agent_level` no sync down**
- Board: `task`
- Objetivo: Corrigir imediatamente a perda do `agent_level` durante o sync down.
- Escopo: Alterar `_apply_change_down` em `src/core/sync.py` para ler o `agent_level` atual do `-body.md` local antes de sobrescrever e repassá-lo a `_compose_down_body`, que o reinjetará no `IssueCommands` derivado de `from_issue`. Adicionar 1-2 testes de round-trip cobrindo o caminho board → `from_issue` → `_compose_down_body` → arquivo.
- Esforço: low (~0,5 dia). Risco baixo.

**Task 2 — Refatoração estrutural: Persistir `agent_level` via label no GitHub**
- Board: `task`
- Objetivo: Eliminar a dependência de estado local volátil substituindo o armazenamento do `agent_level` por labels no board no formato `agent-level-<nível>`.
- Escopo: Ajustar planning-poker para gravar a label; adaptar `resolve_agent_id` (`agent.py`) para resolver o nível a partir das labels (match por prefixo); tratar a label como campo especial em `IssueCommands`/serialização (como já feito com `need_human`); migrar issues em aberto; atualizar `override-agent`/config e documentação.
- Esforço: medium (~1,5-2 dias). Risco médio.
- Bloqueada pela conclusão da Task 1.
