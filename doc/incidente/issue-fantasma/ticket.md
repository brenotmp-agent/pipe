# Incidente — Issue Fantasma

## Registro

**Incidente ID:** 5
**Status:** Em Tratamento
**Owner:** product
**Data de Abertura:** 2026-07-04 12:40
**Last Updated:** 2026-07-06 11:41

Este incidente foi reportado por uma esteira que está usando a pipe em seu desenvolvimento interno.

### Descrição

A esteira agêntica v1.4.2 entra em loop infinito tentando fechar/atualizar a issue `#4` do board `story`, que **nunca existiu** no repositório GitHub. O erro se repete a cada ciclo de 10 minutos e não se resolve sozinho porque a fila de mudanças (`changeQueue.json`) retém o evento `delete-up` e o snapshot mantém o registro com `status: "delete-up"`.

**Erro GraphQL retornado:**
```
Could not resolve to an issue or pull request with the number of 4. (repository.issue)
```

### Evidências

| # | Evidência | Localização |
|---|-----------|-------------|
| 1 | Agente cria arquivo `4-login_e_logout-body.md` com ID fictício | `logs/1/2026-07-04_12-30-38.md` linha 830 |
| 2 | Agente sobrescreve `snapshot.json` com `"id": "4"`, `"status": "ok"` | `logs/1/2026-07-04_12-30-38.md` linhas 61-73 |
| 3 | Sync tenta `update_issue` para #4 e falha | `logs/2026-07-04.json` linhas 193-194 |
| 4 | Erro se repete na segunda execução do agente | `logs/2026-07-04.json` linhas 200-201 |
| 5 | Evento `delete-up` permanece no `changeQueue.json` | `.pipe/changeQueue.json` — entry com `"id": "4"` |
| 6 | Issues #1, #2, #3 fecham com sucesso (existem no GitHub como épicos) | `logs/2026-07-04.json` linhas 262-267 |
| 7 | Snapshot atual mantém issues #4, #5, #6 com `"status": "delete-up"` | `.pipe/boards/story/snapshot.json` |

**Trace do terminal mostrando o loop:**
```
13:16:22 [GitHub] [16s] #1 - Fechando issue
13:16:39 [Sync] [story] delete-up #1 - issue fechada
13:16:39 [GitHub] [16s] #2 - Fechando issue
13:16:56 [Sync] [story] delete-up #2 - issue fechada
13:16:56 [GitHub] [16s] #3 - Fechando issue
13:17:13 [Sync] [story] delete-up #3 - issue fechada
13:17:13 [GitHub] [16s] #4 - Fechando issue
13:17:29 [Pipe] Erro no ciclo (não fatal): GraphQL: Could not resolve to an issue or pull request with the number of 4. (repository.issue)
13:27:29 [GitHub] [16s] epic - Listando issues
...
13:28:03 [GitHub] [16s] #4 - Fechando issue
13:28:19 [Pipe] Erro no ciclo (não fatal): GraphQL: Could not resolve to an issue or pull request with the number of 4. (repository.issue)
13:38:19 [GitHub] [16s] epic - Listando issues
...
13:38:52 [GitHub] [16s] #4 - Fechando issue
13:39:09 [Pipe] Erro no ciclo (não fatal): GraphQL: Could not resolve to an issue or pull request with the number of 4. (repository.issue)
```

### Impacto

- **Esteira travada em loop**: A cada ciclo (10 min), a esteira retenta a operação impossível, consumindo rate limit da API do GitHub sem resultado.
- **Issues #5 e #6 também ficam pendentes**: Como o erro em #4 interrompe o ciclo, as issues #5 e #6 (igualmente fantasmas) nunca são processadas.
- **Épicos #1, #2, #3 receberam close indevido**: As issues reais do epic board foram fechadas erroneamente porque compartilhavam os IDs que o agente atribuiu às stories.
- **Rate limit desnecessário**: 3 chamadas GraphQL desperdiçadas por ciclo (1 close + 1 list_issues + throttle).

---

## Triagem

**Triagem realizada por:** Isabela Gomes - Tech Lead  
**Data:** 2026-07-06

### Confirmação do Problema

✅ **Problema confirmado.** As evidências de log (itens 1–7) são consistentes e demonstram o comportamento descrito. O loop é reproduzível e determinístico: enquanto `changeQueue.json` e `snapshot.json` contiverem as entradas fantasmas, a esteira retentará indefinidamente.

### Classificação

**Bug de design na interface agente ↔ esteira**, com dois vetores independentes que se combinam para produzir o incidente:

1. **Ausência de proteção de estado interno**: o agente tem acesso de escrita irrestrito ao `snapshot.json`, que é exclusivamente memória interna do módulo `sync.py`.
2. **Ausência de tratamento de erro irrecuperável**: quando a API retorna "issue não existe", a esteira trata como erro transitório e retenta indefinidamente em vez de descartar o evento.

Não é erro de configuração nem uso incorreto — o operador não fez nada de errado. O sistema criou as condições para o próprio travamento.

### Impacto

| Dimensão | Avaliação |
|----------|-----------|
| Usuários afetados | 1 operador (Breno) — uso interno |
| Perda financeira | Não — projeto interno, sem SLA externo |
| Disponibilidade | Board `story` inutilizado; demais boards operacionais |
| Dano colateral | Issues reais #1, #2, #3 (épicos) fechadas indevidamente no GitHub |
| Rate limit | ~3 chamadas GraphQL desperdiçadas a cada 10 min enquanto o loop persiste |

### Severidade

**P3 — Média**

Justificativa:
- A esteira **não crashou** — o erro é tratado como não-fatal e os demais boards continuam operando.
- Existe **workaround imediato** (edição manual dos arquivos de estado).
- O dano colateral (épicos fechados) é **reversível** — as issues podem ser reabertas manualmente no GitHub.
- Não há perda de dados permanente nem impacto financeiro.

Não elevo para P2 porque: (a) apenas 1 usuário afetado; (b) workaround funcional; (c) sem SLA externo.

### Workaround Imediato

Remover manualmente as entradas com IDs fantasmas do `snapshot.json` e do `changeQueue.json` e reabrir os épicos fechados indevidamente:

```bash
# 1. Remover eventos pendentes de #4, #5, #6 da fila
jq '[.[] | select(.id != "4" and .id != "5" and .id != "6")]' .pipe/changeQueue.json > /tmp/q.json && mv /tmp/q.json .pipe/changeQueue.json

# 2. Remover issues fantasmas do snapshot
jq '.issues = [.issues[] | select(.id != "4" and .id != "5" and .id != "6")]' .pipe/boards/story/snapshot.json > /tmp/s.json && mv /tmp/s.json .pipe/boards/story/snapshot.json

# 3. Reabrir os épicos fechados indevidamente (GitHub CLI)
gh issue reopen 1 && gh issue reopen 2 && gh issue reopen 3
```

---

## Análise Técnica

**Analista:** Bruno Ferreira - Engenheiro de Software SR  
**Data:** 2026-07-06

**Método:** investigação de código-fonte (AST + leitura direta), correlação de logs/traces do incidente e reconstrução do histórico de deploys via `git log`. Cada afirmação abaixo foi confirmada no código real do repositório.

### Sequência de eventos detalhada

1. **12:30:38** — Agente `Helena Costa - Product Manager` executa na coluna `criacao-stories` do épico #1. Cria 6 arquivos de story com nomes prefixados por números sequenciais arbitrários:
   - `1-cadastro_parcial-body.md`
   - `2-confirmacao_de_email-body.md`
   - `3-cadastro_completo-body.md`
   - `4-login_e_logout-body.md`
   - `5-bloqueio_tentativas_login-body.md`
   - `6-recuperacao_de_senha-body.md`

2. **12:30:38** — O mesmo agente **sobrescreve** o arquivo `.pipe/boards/story/snapshot.json`, registrando 6 issues com `"id": "1"` a `"id": "6"` e `"status": "ok"`. Esses IDs são números inventados — não são numbers reais de issues no GitHub.

3. **12:39:40** — O sync detecta as 6 issues como `change-up` (o snapshot registra IDs numéricos com status "ok", os arquivos existem com mtime diferente). Tenta atualizar no GitHub:
   - `#1`, `#2`, `#3` → Funcionam por **coincidência**: existem issues com esses numbers no repositório (são os 3 épicos criados anteriormente).
   - `#4` → **Falha**: `"Could not resolve to an issue or pull request with the number of 4"` — não existe issue #4 no repositório.

4. **12:40:41** — Erro capturado como "não fatal" pelo `except Exception` no loop principal. Ciclo dorme 10 minutos (`config.sleep`).

5. **12:50:41** — Retenta. Falha novamente com o mesmo erro.

6. **12:58:38** — Reinício manual da esteira. Na segunda execução do agente (13:07:28), o agente repete o padrão: lê os arquivos (agora sem prefixo numérico, pois foram renomeados entre as execuções), mas novamente **sobrescreve o snapshot** com IDs "1"-"6".

7. **13:16:22** — O sync detecta que os arquivos body anteriores com prefixo numérico foram removidos e enfileira `delete-up` para as 6 issues. #1, #2, #3 são fechadas com sucesso (issues reais do épico no GitHub). #4 falha novamente.

8. **13:17:29 em diante** — Loop infinito: a cada 10 minutos a esteira retenta `close_issue` para #4, falha, e o evento permanece na fila.

### Causa raiz (tripla) — confirmada no código-fonte

A falha não tem causa única: é a **combinação de três defeitos independentes** que, juntos, produzem o loop. Cada um foi localizado e verificado no código.

#### 1. O agente tem acesso de escrita irrestrito ao estado interno da esteira

O `snapshot.json` (e o `changeQueue.json`) são memória interna, de propriedade exclusiva do `sync.py` / `change_queue.py`. Não há qualquer proteção contra escrita pelo agente:

- `src/core/agent.py:97` — cada agente nativo é gerado com `"tools": ["*"]` (todas as ferramentas liberadas).
- `src/adapters/kiro_cli_agent.py:52` — a execução usa `--trust-all-tools` (nenhuma confirmação/gate).
- `src/core/agent.py` (`build_prompt`) entrega ao agente **caminhos absolutos** dentro de `.pipe/boards/<board>/<coluna>/`, que é exatamente a árvore onde vive o `snapshot.json` (`.pipe/boards/<board>/snapshot.json`). O agente descobre e escreve o arquivo sem nenhuma barreira.

**Observação:** o gate de permissões introduzido em `7fe845f` (`check_access`) valida apenas se o **token do GitHub** tem escrita no repositório; não protege os arquivos de estado local. A superfície continua aberta.

#### 2. O prefixo numérico do nome de arquivo é interpretado como ID de issue existente

`src/core/sync.py`, função `detect_local_changes`:

```python
for body_file in board_dir.rglob("*-body.md"):
    match = re.match(r"^(\d+)-", body_file.name)
    if match:
        local_bodies[match.group(1)] = body_file  # ← assume issue já rastreada
```

Ao criar `4-login_e_logout-body.md`, o sync casa `^(\d+)-` e trata o arquivo como pertencente à issue #4 já existente → dispara `change-up`/`delete-up` em vez de `create-up`. O fluxo correto (criar arquivo `<slug>-body.md` sem ID, deixar o sync fazer `create-up` e atribuir o number real) nunca é acionado.

#### 3. Ausência de tratamento de erro irrecuperável no apply de sync

Quando a issue não existe, a cadeia de exceções é:

- `src/adapters/github_board.py` `close_issue()` / `update_issue()` → `_gh()` → em retorno diferente de zero e que **não** é rate-limit nem offline, executa `raise Exception(...)` (`github_board.py:203`). "Could not resolve to an issue or pull request" não está nas listas de rate-limit/offline, então propaga.
- `src/core/sync.py` `_apply_delete_up()` chama `board_obj.close_issue(...)` **sem try/except** → propaga.
- `src/core/sync.py` `apply_changes()` só captura `PenaltyException` → o `Exception` genérico escapa.
- Como a fila é *at-least-once* (`change_queue.py`: `getNext()` só espia; `remove()` só após sucesso), o evento **nunca é removido** e retorna no próximo ciclo. Nada identifica "issue inexistente" para descartar o evento.

### Achado adicional: divergência de versão altera o modo de falha

O incidente ocorreu na **v1.4.2** (`b23a69d`, deploy de 2026-07-02, em operação no dia 04). O comportamento de *loop silencioso a cada 10 min* descrito no chamado depende de um handler que existia **apenas na v1.4.2**:

```python
# b23a69d:src/__main__.py:405-407 (v1.4.2)
except Exception as e:
    log.error("Pipe", f"Erro no ciclo (não fatal): {e}")
    time.sleep(config.get("sleep", 60))   # ← engole o erro e retenta no próximo ciclo
```

Esse `except Exception` amplo é a origem do "Erro no ciclo (não fatal)" visto no trace e do loop de 10 minutos.

**Porém, na base de código atual (branch `hotfix5-5-...`, divergente da v1.4.2 a partir de `5e0c4d5`) esse handler foi removido**, junto com o `try/except PenaltyException` que protegia o `apply_changes` dentro de `sync_board`. Consequência prática para quem for corrigir:

- As causas **#1, #2 e #3 continuam presentes** na base atual (verificado: regex em `sync.py`, `_apply_delete_up` sem tratamento, `tools:["*"]` + `--trust-all-tools`).
- Sem o `except Exception`, a mesma condição de issue-fantasma **não gera mais loop silencioso — gera crash duro** do processo (a exceção sobe até `main()`, que não tem guarda). Como o `board_full_sync` no startup recupera itens pendentes do snapshot para a fila, o efeito passa a ser um **crash-loop no restart** em vez de retry a cada 10 min.

Ou seja: remover o `except` amplo (feito em outra frente) não resolveu o incidente; apenas trocou "loop silencioso" por "queda do serviço". A correção real depende de tratar a causa (itens abaixo), não do handler genérico.

### Efeito colateral: close indevido de épicos

As issues reais #1, #2, #3 do repositório GitHub (os épicos) foram **fechadas erroneamente** pelo `delete-up` das stories fictícias, porque o agente atribuiu IDs "1", "2", "3" — que colidem com os numbers dos épicos no mesmo repositório. O espaço de numbers do GitHub é compartilhado entre todos os boards do repo (epic/story/task), então qualquer operação destrutiva (`close_issue`) por ID não valida a qual board o number pertence. Dano reversível via `gh issue reopen`.

### Respostas às perguntas da análise

**Qual a causa?**
Combinação de três defeitos de design na interface agente ↔ esteira: (1) agente com escrita irrestrita sobre o estado interno (`snapshot.json`/`changeQueue.json`); (2) sync interpreta prefixo numérico do nome de arquivo como ID de issue real (`re.match(r"^(\d+)-")`), pulando o `create-up`; (3) ausência de tratamento para erro irrecuperável "issue inexistente", combinada com fila *at-least-once* que retém o evento para sempre. O gatilho foi o agente inventar IDs "1"–"6" e reescrever o snapshot; a coincidência com os numbers dos épicos causou o dano colateral.

**Qual o risco?**
Severidade **P3** (confirmo a triagem). Board `story` inutilizado; demais boards operacionais. Na v1.4.2 o serviço permanece de pé em loop, gastando ~3 chamadas GraphQL a cada 10 min (desperdício de rate limit). **Alerta:** na base de código atual (pós-remoção do `except` amplo) o mesmo cenário derruba o processo em crash-loop — risco de indisponibilidade total da esteira até intervenção manual. Dano colateral (épicos fechados) é reversível; não há perda de dados permanente nem impacto financeiro/SLA externo.

**Existe workaround?**
Sim, imediato e já validado na triagem: remover as entradas fantasmas de `changeQueue.json` e do `snapshot.json` (via `jq`) e reabrir os épicos com `gh issue reopen 1 2 3`. É paliativo — sem as correções de código, o agente pode reincidir na próxima execução na coluna de criação.

**Quanto custa corrigir?**
Estimativa de esforço de engenharia (correções detalhadas na próxima etapa):

- **Correção 3 — tratamento de erro irrecuperável** (`_apply_delete_up`/`_apply_change_up` tratam "Could not resolve..." descartando o evento e limpando o snapshot): **~2–4 h** (baixo risco, alto retorno — estanca o loop/crash imediatamente). *Menor mudança possível; prioridade máxima.*
- **Correção 2 — `CONTEXT.md` gerado no startup** a partir do `pipe.yml`, proibindo manipulação de estado e ensinando nomeação sem ID: **~4–8 h** (previne reincidência).
- **Correção 1 — snapshot/estado como read-only para o agente** (não expor path, lista de arquivos protegidos, restringir `tools`): **~4–8 h**.
- **Correção 4 — validação pós-agente** (comparar mtime do snapshot, restaurar se alterado, renomear arquivos com prefixo numérico indevido): **~1 dia**.
- **Correção 5 — isolamento de IDs entre boards** (validar que o number pertence ao board antes de operação destrutiva): **~1–2 dias** (requer consulta ao projeto associado; maior custo).

**Total aproximado:** ~3–5 dias de dev para o pacote completo. O loop/crash em produção pode ser estancado em **menos de meio dia** aplicando somente a Correção 3.

---

## Decisão de Tratamento

**Decisão tomada por:** Isabela Gomes - Tech Lead  
**Data:** 2026-07-06

**Opção escolhida:** Opção 1 — Continuar como incidente produtivo. A issue segue o fluxo do board de incidente.

### Motivos

1. **Bug de design confirmado e de escopo não trivial.** A análise técnica identificou causa raiz tripla com cinco correções de código interdependentes, estimativa de 3–5 dias de esforço e necessidade de validação em profundidade. Não se trata de uma correção pontual e isolada.

2. **Risco ativo na base atual.** A remoção do `except Exception` amplo trocou "loop silencioso" por "crash-loop do processo". Sem as correções, qualquer nova execução do agente na coluna `criacao-stories` pode reinstaurar a condição de travamento com queda total da esteira — risco que justifica acompanhamento estruturado.

3. **Dano colateral presente.** Issues reais (#1, #2, #3) foram fechadas indevidamente. Embora reversível, o espaço de IDs compartilhado no GitHub exige correção (Correção 5) que vai além do problema imediato.

4. **Prevenção de reincidência requer múltiplas mudanças.** O workaround é paliativo. Sem as Correções 1, 2 e 4 (proteção de estado, CONTEXT.md, validação pós-agente), o padrão pode se repetir em outras execuções.

---

## Tarefas de Correção

**Planejamento realizado por:** Isabela Gomes - Tech Lead
**Data:** 2026-07-06

As 5 tasks foram criadas no board `task`, coluna `backlog`, todas com `/parent #5` (esta issue).

### Issues criadas

| Issue | Task | Prioridade | Estimativa | agent_level |
|-------|------|-----------|-----------|-------------|
| #6 | Correção 3 — Tratamento de erro irrecuperável no sync | 1 (máxima) | 2–4 h | low |
| #7 | Correção 2 — CONTEXT.md gerado no startup | 2 | 4–8 h | medium |
| #8 | Correção 1 — Snapshot como memória interna (read-only para agentes) | 3 | 4–8 h | medium |
| #9 | Correção 4 — Validação pós-agente | 4 | ~1 dia | medium |
| #10 | Correção 5 — Isolamento de IDs entre boards | 5 | 1–2 dias | high |

### Ordem de execução e dependências

As tasks foram criadas de forma independente (sem `/blocked_by` entre si), mas a ordem lógica de implementação deve respeitar a seguinte sequência:

```
T1 (Correção 3) → T2 (Correção 2) e T3 (Correção 1) [em paralelo] → T4 (Correção 4) → T5 (Correção 5)
```

**Justificativa:**
- **T1 primeiro**: estanca o crash-loop imediatamente. Base estável para o restante.
- **T2 e T3 em paralelo**: independentes entre si; T2 age no prompt/contexto, T3 age na lista de tools/paths — sem sobreposição.
- **T4 após T2+T3**: a validação pós-agente só faz sentido depois que a superfície de ataque e o contexto estão definidos; precisamos saber o que é "estado esperado" para comparar.
- **T5 por último**: maior custo, corrige dano colateral estrutural; as anteriores eliminam as condições que levam a este cenário.

### Estimativa total

| Cenário | Esforço |
|---------|---------|
| Somente T1 (estancar o crash) | ~½ dia |
| T1 + T2 + T3 (prevenir reincidência) | ~2–3 dias |
| Pacote completo (T1–T5) | ~4–6 dias |

### Detalhes de cada correção

#### Correção 1 — Snapshot como memória interna (read-only para agentes)

Tornar os snapshots auxiliares de memória exclusivamente internos:
- Durante o processamento, usar apenas a informação em memória.
- A cada alteração, salvar o novo estado no arquivo.
- Ler o arquivo apenas na inicialização da aplicação.
- **Proibir acesso ao snapshot pelo agente** — não informar o path no prompt e incluir na lista de arquivos protegidos.

#### Correção 2 — CONTEXT.md gerado no startup a partir do pipe.yml

No startup do serviço, gerar automaticamente o `CONTEXT.md` que:
- Traduz as configurações do `pipe.yml` em instruções claras para o agente.
- **Proíbe explicitamente** a manipulação dos arquivos `snapshot.json`, `changeQueue.json` e `throttle`.
- **Obriga** a criação de issues sem o ID numérico no nome: apenas `<slug>-body.md`, `<slug>-history.md`, `<slug>-addcomment.md`.
- **Ensina** o padrão correto de criação de branches.
- Elimina ambiguidade — o agente recebe instruções derivadas da configuração real em vez de inferir comportamento.

#### Correção 3 — Tratamento de erro irrecuperável no sync

Adicionar tratamento específico em `_apply_delete_up` e `_apply_change_up` para erros de "issue inexistente":

```python
def _apply_delete_up(board_id: str, item: ChangeItem, board_obj: Board):
    """Fecha issue no board (arquivo local já foi removido)."""
    try:
        board_obj.close_issue(board_id, item.id)
    except Exception as e:
        if "Could not resolve to an issue or pull request" in str(e):
            log.warning("Sync", f"[{board_id}] #{item.id} não existe no GitHub - "
                       "removendo do snapshot (issue fantasma)")
            # Issue não existe — limpar estado e seguir
            snap = Snapshot(board_id).load()
            snap.issues = [i for i in snap.issues if str(i.get("id")) != str(item.id)]
            snap.save()
            return
        raise

    snap = Snapshot(board_id).load()
    snap.issues = [i for i in snap.issues if str(i.get("id")) != str(item.id)]
    snap.save()
    log.info("Sync", f"[{board_id}] delete-up #{item.id} - issue fechada",
             issue_id=item.id)
```

#### Correção 4 — Validação pós-agente

Após a execução do agente, antes de devolver o controle ao loop:
- Comparar mtime do `snapshot.json` pré/pós execução.
- Se foi alterado pelo agente, **restaurar o snapshot anterior** e logar warning.
- Detectar arquivos com prefixo numérico criados em boards onde o ID não existia no snapshot pré-execução — logar warning e renomear removendo o prefixo numérico.

#### Correção 5 — Isolamento de IDs entre boards

O repositório GitHub compartilha o espaço de números de issues entre todos os boards (epic, story, task, etc.). Ao fazer operações como `close_issue`, validar que o ID pertence ao board correto consultando o projeto associado antes de executar a ação destrutiva.

---

## Ação Proposta

**Etapa:** Execução de Tratamento

**Executado por:** Diego Santos - Analista de Operações  
**Data:** 2026-07-06 11:41

**Ação executada:** Criação deste arquivo (`doc/incidente/issue-fantasma/ticket.md`) no repositório, consolidando o registro completo do incidente (descrição, triagem, análise técnica, decisão de tratamento, tarefas de correção e ação proposta), conforme decisão de Isabela Gomes (Tech Lead) de manter o incidente como produtivo no board de incidentes.

**Próximos passos:** O incidente segue para análise de relatório e formalização de tasks, conforme o fluxo do board de incidentes.

---

## Histórico de Atualizações

| Data | Responsável | Evento |
|------|-------------|--------|
| 2026-07-04 12:40 | Breno | Incidente reportado |
| 2026-07-06 13:04 | Isabela Gomes | Triagem concluída (P3 - Média) |
| 2026-07-06 13:59 | Bruno Ferreira | Análise técnica concluída |
| 2026-07-06 14:10 | Isabela Gomes | Decisão de tratamento (Incidente produtivo) |
| 2026-07-06 11:41 | Diego Santos | Execução de tratamento — Documentação criada |
| 2026-07-06 15:22 | Isabela Gomes | Planejamento técnico — 5 tasks criadas no board (issues #6–#10) |
