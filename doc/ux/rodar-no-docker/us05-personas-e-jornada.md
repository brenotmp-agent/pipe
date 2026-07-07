# US-05 — Persona e Jornada de Operação

Status: draft
Owner: ux (Talita Souza)
Last updated: 2026-07-07

## 1. Persona primária

### Otávio — Operador/Analista da esteira

| Atributo | Descrição |
|----------|-----------|
| **Papel** | Analista que opera a esteira; sobe o container num host (VPS/nuvem/servidor interno) e o deixa rodando. |
| **Contexto** | Não fica "sentado" olhando o terminal. Sobe uma vez, confere que está de pé e volta a olhar só quando desconfia de algo ou recebe um sinal (issue parada no board). |
| **Nível técnico** | Confortável com Docker, `.env`, SSH e board do GitHub. **Não** conhece o código-fonte da esteira. |
| **Onde trabalha** | SSH no host para operar o container; navegador no board do GitHub para acompanhar/destravar issues. |
| **Objetivo** | "Subir e esquecer": que a esteira rode sozinha e só exija minha atenção quando um gate de negócio pede decisão humana — e essa decisão eu tomo no board, não na máquina. |

**Dores (o que dá medo num sistema autônomo):**
1. *"Está travado ou só ocioso?"* — silêncio no log é ambíguo.
2. *"Subiu errado e eu não percebi."* — falha silenciosa de credencial.
3. *"Preciso entrar na máquina para destravar cada aprovação?"* — não deveria.
4. *"Caiu de madrugada e ficou fora do ar até eu ver."* — quer recuperação sozinha.

**Ganhos esperados (o que gera confiança):**
- Feedback rítmico de que está vivo (heartbeat de ciclo/sleep).
- Falha de setup **imediata e explicada**, com exit-code != 0.
- Gates humanos resolvidos **no board**, com o container seguindo em frente.
- Recuperação automática após crash (`restart: unless-stopped`).

### Persona secundária

**Renata — quem aprova nos gates de negócio.** Só interage com o **board do
GitHub** (Aprovação de Negócio, Validações, Homologação). Não sabe que existe um
container. Para ela, a UX é 100% o board: mover o card retoma o trabalho no
ciclo seguinte. Isso reforça a decisão de produto: **o container nunca é ponto
de intervenção humana.**

## 2. Mapa mental: onde o usuário "vê" e "age"

```
                    PERCEPÇÃO                          AÇÃO
        ┌──────────────────────────────┐   ┌──────────────────────────────┐
        │  docker logs <container>      │   │  Board do GitHub (navegador)  │
        │  - banner + versão            │   │  - mover card no gate humano  │
Otávio  │  - arranque / validação       │   │  - preencher body / labels    │
        │  - ciclo (sync/keep/agent)    │   │                               │
        │  - ociosidade (sleep)         │   │  Host (SSH) — só operação:    │
        │  - erros / rate limit         │   │  - up / down / restart / .env │
        └──────────────────────────────┘   └──────────────────────────────┘
              "está vivo e saudável?"           "decido e destravo aqui"
```

Insight de design: **percepção e ação estão em superfícies separadas.** O log é
somente-leitura (diagnóstico); toda ação de negócio acontece no board. O container
não tem superfície de entrada — e isso é uma *feature* (AC-01, AC-05), não uma
limitação.

## 3. Jornada de operação (end-to-end)

Fases, o que o usuário faz, o que o sistema mostra e a emoção associada.

### Fase 1 — Primeiro `up` (onboarding)
- **Faz:** preenche `.env` (`GH_TOKEN`, `KIRO_API_KEY`, `SSH_KEY_PATH`), roda
  `docker compose up -d`, depois `docker logs -f`.
- **Vê:** banner ASCII → `Iniciando esteira agêntica vX` → validação de config →
  clone dos repos → sync inicial → `Esteira agêntica iniciada`.
- **Emoção:** 😟 ansioso ("configurei certo?") → 🙂 aliviado ao ver o banner e o
  ciclo começar.
- **Momento crítico:** se faltar credencial, precisa falhar **agora**, explicado.

### Fase 2 — Regime permanente (o dia a dia)
- **Faz:** nada. Ocasionalmente `docker logs --tail` para conferir.
- **Vê:** ciclos de sync, seleção de tarefa, execução de agente e, quando não há
  trabalho, `Nenhuma atividade - dormindo 60s (retorna às HH:MM:SS)`.
- **Emoção:** 😌 confiante — o heartbeat do sleep prova que está vivo, não travado.
- **Momento crítico:** distinguir "ocioso saudável" de "travado". O log de sleep
  com horário de retorno resolve isso hoje.

### Fase 3 — Gate humano (`need_human`)
- **Faz:** vê no board uma issue parada num gate; **no board**, revisa e move o
  card / ajusta o body. Não acessa a máquina.
- **Vê no log:** a esteira **não** para — segue varrendo outros boards e dorme se
  não houver mais nada. No ciclo seguinte ao movimento no board, sincroniza e
  retoma a issue.
- **Emoção:** 🙂 no controle — decide no board, o runtime não exige sua presença.
- **Momento crítico:** o operador precisa entender que "issue parada" ≠ "container
  travado". (Ver recomendação R-UX-03 sobre tornar isso explícito no log.)

### Fase 4 — Falha / recuperação
- **Faz:** idealmente nada. Se necessário, `docker logs` para diagnosticar.
- **Vê:** erro não-fatal logado e o loop seguindo; em crash duro, o
  `restart: unless-stopped` sobe de novo e o estado persistido (`.pipe/`) evita
  recomeçar do zero.
- **Emoção:** 😰 → 😌 quando percebe que voltou sozinho.
- **Momento crítico:** rate limit e rotação de `KIRO_API_KEY` (R-4) precisam
  aparecer no log de forma inteligível.

### Resumo da curva emocional

```
😟  😀        😌 ─────────────── 😌        😰→😌        😌
up  banner    regime permanente   gate humano  falha/restart  volta ao regime
    +ciclo    (heartbeat sleep)   (age no board)
```

O vale de ansiedade está no **primeiro up** (config) e na **falha**. São
exatamente os dois pontos onde a qualidade da mensagem (fail-fast e erro de
runtime) mais importa — foco das diretrizes de UX writing.

## 4. Cenários de referência (para validar os protótipos)

1. **Feliz:** tudo configurado → sobe, roda, dorme, retoma. (Fases 1→2)
2. **Config incompleta:** falta `PIPE_SSH_KEY_FILE` → fail-fast no arranque.
3. **Contexto de agente vazio:** arquivo em `contexts/...md` vazio → fail-fast.
4. **Credencial lazy inválida:** `GH_TOKEN`/`KIRO_API_KEY` errados → falha na
   primeira operação, logada, loop continua (não trava).
5. **Gate humano:** issue com `/need_human` → ignorada, container segue.
6. **Rate limit:** GitHub retorna 403/429 → throttle/penalty visível no log.
7. **Crash duro:** processo morre → `restart` sobe de novo, estado preservado.

Cada cenário tem um protótipo de saída correspondente em
[`us05-prototipos-terminal.md`](us05-prototipos-terminal.md).
