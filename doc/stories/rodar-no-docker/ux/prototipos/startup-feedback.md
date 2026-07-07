# Protótipo — Feedback de arranque (visibilidade do modo de persistência)

Status: draft (protótipo de UX de baixa fidelidade)
Endereça: H-1 (visibilidade do estado) e H-3 (copy da limpeza da fila)
Formato base: log de terminal real da esteira → `HH:MM:SS [Módulo] mensagem`
(ver `src/core/log.py`).

> Wireframe textual. Não é código. As linhas marcadas **[NOVO]** são a proposta
> de UX; as demais já existem hoje em `startup()`. A copy definitiva e a
> implementação são da etapa de engenharia (recomendações R-1/R-2 do doc de UX).

---

## Princípio

No arranque, o operador precisa responder três perguntas em 1 olhada:

1. **Em que modo estou?** persistente ou efêmero
2. **Meu estado veio de antes?** herdado ou primeira vez
3. **Onde o estado vive?** (implícito nos binds; reforçado quando herdado)

O "modo" é **observável**, não uma flag nova (coerente com ADR-04: o código não
distingue os modos). Detecção sugerida: havia snapshot em `.pipe/boards/`?
existia `sessions.json`? havia clones em `repo/`? → daí se deriva a mensagem.

---

## Cenário 1 — Persistente, com estado herdado (Jornada B, valor central)

```
12:00:01 [Pipe] Iniciando esteira agêntica v1.x
12:00:01 [Startup] Verificando repositórios
12:00:01 [Startup] Modo persistente: estado anterior encontrado          # [NOVO]
12:00:01 [Startup]   • snapshot de boards preservado (sem re-sync completo) # [NOVO]
12:00:01 [Startup]   • sessões de agente preservadas (raciocínio retomado)  # [NOVO]
12:00:01 [Startup]   • 2 repositório(s) reaproveitado(s) (sem re-clone)      # [NOVO]
12:00:01 [Startup] Higienizando fila de sync do ciclo anterior            # [NOVO copy, ver H-3]
                    (rotina segura; a fila é reconstruída pelo full sync)
12:00:02 [Board] Sincronizando estrutura local
...
```

Antes (hoje) o operador via só: "Verificando repositórios" seguido de silêncio
sobre repos (porque não reclona) e "Removendo fila de mudanças anterior". Ele
tinha de *adivinhar* que a persistência funcionou.

---

## Cenário 2 — Persistente, primeira execução (volume vazio) (Jornada A)

```
12:00:01 [Startup] Verificando repositórios
12:00:01 [Startup] Modo persistente: nenhum estado anterior — primeira    # [NOVO]
                    execução neste volume
12:00:01 [Startup] Clonando main
12:00:05 [Startup] Clonando docs
12:00:09 [Board] Sincronizando estrutura local
...
```

Aqui as mensagens "Clonando" são esperadas (é a primeira vez). O rótulo de modo
evita que o operador confunda "primeira vez" com "perdi meu estado".

---

## Cenário 3 — Efêmero (sem volumes) (Jornada C)

```
12:00:01 [Startup] Verificando repositórios
12:00:01 [Startup] Modo efêmero: sem estado persistido — tudo será         # [NOVO]
                    reconstruído a cada subida
12:00:01 [Startup] Clonando main
12:00:05 [Startup] Clonando docs
...
```

Deixa explícito para a Camila (QA) que está tudo certo, e alerta o Diego que
rodou efêmero **por engano** (Jornada D vira visível já aqui).

---

## Cenário 4 — Persistente esperado, mas bind quebrado (Jornada D, risco) 🔴

Não há uma flag dizendo "eu queria persistir", então a esteira não consegue
saber que o operador *pretendia* persistir. O que o design entrega é: o
operador que esperava ver o Cenário 1 vê o Cenário 3 ("Modo efêmero…") e percebe
o problema no primeiro reinício, em vez de descobrir depois que perdeu o
raciocínio dos agentes.

Essa é a razão de a mensagem de modo ser **sempre** impressa: transforma uma
falha silenciosa em um sinal perceptível.

---

## Notas de copy (vocabulário — H-5)

- Usar sempre "modo persistente" / "modo efêmero" (não "stateful", "volátil").
- "Higienizando fila" em vez de "Removendo fila" para não parecer perda de
  estado (H-3).
- Mensagens de modo em nível INFO (não WARNING): modo efêmero é legítimo, não é
  erro (D-04).
