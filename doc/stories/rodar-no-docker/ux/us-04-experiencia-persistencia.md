# UX — US-04: Persistir estado de runtime entre reinícios

Status: draft
Owner: ux (Talita Souza)
Stage: Prototipação
Last updated: 2026-07-07

## Inputs

- doc/stories/rodar-no-docker/user-stories.md (US-04)
- doc/stories/rodar-no-docker/requisitos-decisoes.md (RF-06, D-04, ADR-04)
- doc/product/rodar-no-docker/{vision,problem-space,epicos}.md
- src/__main__.py → `startup()`, `main()` (comportamento e logs reais)
- src/core/log.py → formato de log de terminal (`HH:MM:SS [Módulo] mensagem`)
- .gitignore (`.pipe/`, `logs/`, `repo/`, `contexts/` fora do versionamento)
- Pesquisa de mercado e boas práticas (ver seção "Referências externas")

## Escopo desta entrega (UX / Prototipação)

Nesta feature **não há tela**. A "interface" que o operador manipula é o
`docker-compose.yml` (arquivo de configuração como interface) e o **feedback de
log no arranque**. Portanto os artefatos de UX aqui são:

1. Persona e contexto do operador.
2. Jornadas do operador (4 cenários).
3. Achados de usabilidade (avaliação heurística) sobre o comportamento atual.
4. Recomendações de experiência (copy, defaults, ergonomia do compose).
5. Protótipos de baixa fidelidade (em `./prototipos/`).
6. Entrevista de descoberta (perguntas + premissas adotadas).

Fora de escopo desta etapa: implementar o `docker-compose.yml`/`Dockerfile`
final e alterar código Python (etapas de engenharia). As recomendações que
exigem código estão marcadas como **→ Engenharia**.

---

## 1. Persona e contexto

**Persona primária — "Operador Diego"**
Analista/DevOps que sobe a esteira em um host qualquer (servidor, VM na nuvem,
máquina de CI). Conhece Docker e `docker compose`, mas **não conhece o código**
da esteira. Objetivo: subir e manter a esteira rodando com o mínimo de
cerimônia, e conseguir confiar que o estado (raciocínio dos agentes, snapshots,
clones) sobrevive a reinícios.

Dores relevantes para US-04:
- Não sabe, ao reiniciar, se o estado foi de fato preservado ou zerado.
- Tem medo de "perder o trabalho" dos agentes sem perceber.
- Não quer decorar quais diretórios internos importam (`.pipe/`, `logs/`,
  `repo/`) nem por quê.

**Persona secundária — "CI Bot / Camila QA"**
Roda a esteira de forma efêmera (teste isolado, demonstração). Quer estado
zerado a cada subida, sem configurar nada e sem erro.

### Momento-chave (o que o operador realmente decide)

O operador toma **uma única decisão de UX**: *"quero que o estado sobreviva a
reinícios — sim ou não?"*. Todo o resto (quais três diretórios, por que a fila
é apagada, etc.) deve ser cuidado pelo design, não empurrado como carga
cognitiva.

---

## 2. Jornadas do operador

Notação: 🟢 caminho feliz · 🟡 ponto de atrito · 🔴 risco de perda de estado.

### Jornada A — Primeira subida em modo persistente 🟢

1. Operador clona o repo, copia `.env.example` → `.env`, deixa os binds ativos
   (default).
2. `docker compose up`.
3. Esteira clona os repositórios, faz sync completo, começa a trabalhar.
4. **Expectativa de feedback:** o log deve dizer, logo no arranque, que está em
   **modo persistente** e onde o estado vive.

### Jornada B — Reinício em modo persistente 🟢 (valor central da US-04)

1. `docker compose down` → `docker compose up` (ou host reiniciou).
2. Esteira **reaproveita** `repo/<id>` (sem re-clone), usa o snapshot como
   baseline (sem re-sync completo), e retoma sessões de agente
   (`sessions.json`).
3. 🟡 **Atrito atual:** o operador só *infere* que houve reaproveitamento pela
   **ausência** das mensagens "Clonando…". Não há confirmação positiva. Ver
   Achado H-1.
4. Nota de design (transparência): `.pipe/changeQueue.json` é sempre apagada no
   arranque — isso é **intencional** e não é perda de estado; precisa ser
   comunicado como rotina, não como alerta.

### Jornada C — Subida efêmera (sem volumes) 🟢

1. Camila comenta/remove os binds no compose (ou usa o override efêmero).
2. `docker compose up` → estado zerado, sem erro (D-04).
3. **Expectativa de feedback:** o log deve dizer explicitamente que está em
   **modo efêmero** — para que ninguém rode "efêmero por engano" achando que
   está persistindo.

### Jornada D — Perda de estado por engano 🔴 (a evitar)

1. Operador *acha* que configurou persistência, mas o caminho do bind aponta
   para lugar errado / não montou.
2. A cada `up`, tudo é reclonado e re-sincronizado; a continuidade de raciocínio
   dos agentes se perde silenciosamente.
3. **Mitigação de UX:** feedback explícito de modo no arranque (H-1) + defaults
   seguros (H-2) transformam esse 🔴 em algo perceptível já no primeiro reinício.

---

## 3. Achados de usabilidade (avaliação heurística)

Método: avaliação heurística de Nielsen aplicada ao comportamento de `startup()`
e `main()` observado em `src/__main__.py`, mais o formato de log de
`src/core/log.py`.

### H-1 — Falta visibilidade do modo de persistência (Heurística #1) — **Alta**

Hoje o `startup()` emite: "Verificando repositórios", "Removendo fila de
mudanças anterior", "Clonando <id>", "Removendo <id>". **Não existe** nenhuma
mensagem que declare "modo persistente" vs "modo efêmero", nem onde o estado
está montado. O operador precisa deduzir o modo pela ausência de mensagens — o
oposto de "manter o usuário informado sobre o que está acontecendo"
([NN/g, Heurística #1](https://www.nngroup.com/articles/visibility-system-status/)).

Impacto: alimenta diretamente a Jornada D (perda silenciosa). É o achado mais
importante desta feature.

**Recomendação → Engenharia:** ao final do `startup()`, emitir um resumo de
estado (ver protótipo `prototipos/startup-feedback.md` e Recomendação R-1).

### H-2 — A decisão persistir/efêmero deve ter default seguro (Heurística #5, prevenção de erro) — **Média**

O modo mais custoso de errar é "achar que persiste e não persistir" (Jornada D).
O design deve tornar a **persistência o default** no artefato entregue ao
operador, e o efêmero uma escolha explícita (comentar/override). Assim o erro
por omissão é o menos danoso.

**Recomendação → Compose (protótipo):** binds ativos por default; efêmero via
arquivo de override `compose.ephemeral.yml` **ou** comentário claro.

### H-3 — "Apagar a fila no arranque" parece perda de estado (Heurística #1/#9) — **Média**

A mensagem atual "Removendo fila de mudanças anterior" pode assustar um operador
que acabou de configurar persistência ("por que está removendo algo do meu
estado?"). É comportamento correto (a fila é reconstruída pelo
`board_full_sync`), mas a **copy** não explica que é rotina segura.

**Recomendação → Engenharia (copy):** reescrever para deixar claro que é
higienização esperada e que o snapshot foi preservado. Ver R-2.

### H-4 — Carga cognitiva dos três diretórios (Heurística #6, reconhecer > lembrar) — **Média**

Exigir que o operador saiba de cor que `.pipe/`, `logs/` e `repo/` precisam de
bind é lembrar, não reconhecer. O compose e o `.env.example` devem **listar e
comentar** os três, com uma frase de "o que se perde se eu tirar isto",
espelhando a tabela de impacto da US-04.

**Recomendação → Protótipos:** compose e `.env.example` anotados (feito).

### H-5 — Consistência de nomenclatura de "modo" (Heurística #4) — **Baixa**

Padronizar dois termos em toda a documentação e nos logs: **"modo persistente"**
e **"modo efêmero"**. Evitar sinônimos soltos ("stateful", "volátil",
"temporário") que fragmentam o modelo mental.

---

## 4. Recomendações de experiência

### R-1 — Resumo de estado no arranque (copy + gatilho) → Engenharia

Ao final de `startup()` (e/ou início de `main()`), emitir um bloco curto que
responda três perguntas do operador: *em que modo estou? o estado veio de antes?
onde ele vive?*

Detecção sugerida (sem novas dependências): para cada diretório de runtime,
verificar se já continha estado antes do arranque (ex.: `repo/` tinha clones,
`.pipe/boards/` tinha snapshot, `sessions.json` existia). O modo é uma
consequência observável, não uma flag nova de config — coerente com a ADR-04
(código não distingue os modos).

Copy proposta (PT-BR, mesmo estilo dos logs atuais) — ver wireframe completo em
`prototipos/startup-feedback.md`:

- Persistente com estado herdado:
  `[Startup] Modo persistente: estado anterior encontrado (snapshot, sessões e N repo(s) reaproveitados)`
- Persistente, primeira vez (vazio):
  `[Startup] Modo persistente: nenhum estado anterior — primeira execução neste volume`
- Efêmero:
  `[Startup] Modo efêmero: sem estado persistido — tudo será reconstruído a cada subida`

### R-2 — Copy da limpeza da fila → Engenharia

Trocar:
`Removendo fila de mudanças anterior`
por algo que sinalize rotina segura, ex.:
`Higienizando fila de sync do ciclo anterior (snapshot preservado; fila será reconstruída)`

### R-3 — Defaults seguros no artefato de operador → Compose (protótipo)

Persistência ligada por default; efêmero como escolha consciente. Caminhos
parametrizados por `.env` para o operador não editar YAML.

### R-4 — Espelhar a tabela de impacto onde o operador decide → Docs/Protótipo

O compose e o `.env.example` trazem, em comentário, a frase de impacto de cada
diretório (o que se perde ao remover o bind), para a decisão acontecer no ponto
de ação, não num doc separado.

### R-5 — Vocabulário único → Toda a doc + logs

"modo persistente" / "modo efêmero" (ver H-5).

---

## 5. Protótipos (baixa fidelidade)

Entregues em `doc/stories/rodar-no-docker/ux/prototipos/`:

- `docker-compose.prototipo.yml` — mockup anotado do compose (a "interface"),
  demonstrando defaults seguros (R-3), diretórios comentados com impacto (R-4) e
  parametrização por `.env`.
- `compose.ephemeral.prototipo.yml` — override que desliga a persistência de
  forma explícita (H-2).
- `.env.prototipo` — variáveis de caminho com comentários de impacto (R-4).
- `startup-feedback.md` — wireframe textual do log de arranque nos 4 cenários,
  com a copy proposta em R-1/R-2 (endereça H-1/H-3).

> ⚠️ São protótipos de UX para guiar a engenharia. Os nomes de arquivo usam o
> sufixo `.prototipo` de propósito para **não** serem confundidos com o artefato
> final de deploy.

---

## 6. Entrevista de descoberta

Como a execução é autônoma (sem humano ao vivo nesta etapa), registro as
perguntas que faria e a **premissa adotada** para cada uma, com justificativa.
O humano pode corrigir qualquer premissa no board.

| # | Pergunta ao usuário | Premissa adotada | Justificativa |
|---|---------------------|------------------|---------------|
| P1 | O operador prefere inspecionar o estado direto no host (bind mount) ou delegar ao Docker (named volume)? | **Bind mount**, como já define a US-04. | Bind expõe o estado ao operador (auditar `.pipe/`, ler logs, ver clones) sem ferramenta extra; `.gitignore` já trata esses paths como locais. |
| P2 | Persistência deve vir ligada ou desligada por padrão no artefato entregue? | **Ligada** (efêmero é opt-out explícito). | Prevenção de erro (H-2): o erro por omissão deve ser o menos danoso. |
| P3 | O operador quer confirmação explícita do modo no arranque? | **Sim** (R-1). | Heurística #1; mitiga a Jornada D (perda silenciosa). |
| P4 | Faz sentido persistir `logs/` por padrão? | **Sim, mas como conveniência** (pode ser removido sem impacto operacional). | US-04 classifica `logs/` como conveniência; refletido na copy de impacto. |
| P5 | O operador entende por que a fila (`changeQueue.json`) é apagada? | **Não sem ajuda** → melhorar copy (R-2) e documentar. | H-3: comportamento correto, comunicação insuficiente. |
| P6 | Qual o nível de familiaridade com Docker? | **Intermediário** (usa compose, não conhece o código). | Vision/problem-space: público é analista/DevOps que quer subir sem ler código. |

### Lacunas remanescentes (não bloqueiam esta etapa)

- **Nenhuma lacuna bloqueante.** A documentação de requisitos (US-04, RF-06,
  D-04, ADR-04) está completa e consistente com o código lido.
- A recomendação R-1/R-2 depende de uma **decisão de engenharia** (emitir os
  logs de modo/estado). Não é bloqueio de UX: os protótipos já entregam a copy e
  o gatilho sugeridos; a validação/implementação ocorre nas etapas seguintes.

---

## 7. Referências externas (pesquisa)

Boas práticas de UX/usabilidade:
- [NN/g — Visibility of System Status (Heurística #1)](https://www.nngroup.com/articles/visibility-system-status/)
- [NN/g — 10 Usability Heuristics for UI Design](https://www.nngroup.com/articles/ten-usability-heuristics/)

Referências de mercado (persistência em Docker para apps self-hosted):
- [Docker Compose Bind Mounts vs Named Volumes — serversideup](https://serversideup.net/blog/docker-compose-bind-mounts-vs-named-volumes/)
- [Docker Volumes vs Bind Mounts — sumguy](https://sumguy.com/docker-volumes-vs-bind-mounts/)

Padrão observado no mercado (ferramentas como bancos de dados e apps
self-hosted): bind mounts quando o operador quer **ver e versionar/backupear o
estado no host**; named volumes quando prioriza portabilidade/performance e não
precisa inspecionar. Para a esteira, cujo estado é justamente algo que o
operador quer auditar (snapshots, logs, clones), o bind mount da US-04 é a
escolha coerente com a experiência desejada.

> Conteúdo das fontes externas foi parafraseado/resumido para conformidade com
> restrições de licenciamento.
