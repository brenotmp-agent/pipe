# Jornada do Operador — Rodar no Docker

Status: draft
Owner: ux (Talita Souza)
Last updated: 2026-07-07

Complementa `descoberta.md`. Mapeia a jornada ponta a ponta do operador que
sobe e opera a esteira containerizada, marcando emoções, pontos de fricção e
oportunidades de UX. Cada oportunidade referencia a US que a implementa.

## Personas

### Persona primária — "Ana, operadora de plantão"

- Analista/dev com Docker e Git no dia a dia; **não conhece o código** da
  esteira.
- Opera de um servidor/VM remoto, muitas vezes por SSH, às vezes acompanhando
  `docker logs` do próprio notebook.
- Objetivo: subir a esteira uma vez, confiar que roda sozinha, ser avisada
  quando algo exige ação (no board do GitHub).
- Dor: "está rodando ou travou?"; "por que não subiu e o que eu faço?".

### Persona secundária — "Léo, quem configura pela primeira vez"

- Faz o setup inicial (segredos, `pipe.yml`, `contexts/`).
- Objetivo: sair do zero ao primeiro ciclo rápido, sem ler o código.
- Dor: descobrir *quais* segredos precisa e em *qual formato*; erros que só
  aparecem depois de muita espera.

## Mapa da jornada (fases)

Legenda de emoção: 🙂 tranquilo · 😐 neutro/atento · 😟 fricção/risco

### Fase 0 — Descobrir pré-requisitos  😟

- **Faz:** lê o runbook, junta chave SSH, `GH_TOKEN`, `KIRO_API_KEY`, prepara
  `pipe.yml` e `contexts/`.
- **Pensa:** "será que tenho tudo? em que formato?"
- **Fricção:** é o maior gargalo do onboarding; segredos vêm de lugares
  diferentes (SSH, GitHub, Kiro).
- **Oportunidade UX:** checklist "tenha isto em mãos" no topo do runbook +
  `.env.example` anotado que serve de lista viva. → **US-03/US-06**
  (protótipos §2 e §6).

### Fase 1 — Configurar  😐

- **Faz:** copia `.env.example` → `.env`, preenche valores, monta volumes de
  `pipe.yml`/`contexts/`.
- **Pensa:** "isto aqui é caminho ou conteúdo? é obrigatório?"
- **Fricção:** confundir caminho da chave (dentro do container) com o arquivo
  do host; não saber o que é opcional.
- **Oportunidade UX:** cada variável no `.env.example` com uma linha de
  descrição, marcação obrigatório/opcional e exemplo. → **US-02/US-03**
  (protótipos §2).

### Fase 2 — Subir  😐→🙂

- **Faz:** `docker compose up` (ou `docker run`).
- **Pensa:** "subiu? está fazendo algo?"
- **Fricção:** silêncio inicial; hoje a primeira linha é só
  "Config: Validando pipe.yml", sem identificar versão/serviço.
- **Oportunidade UX:** **banner de arranque** (nome, versão, modo) + **resumo
  de preflight** do que foi validado. → **US-01 (ENV/versão) + US-05**
  (protótipos §1 e §3).

### Fase 3 — Confirmar saúde  😟→🙂

- **Faz:** observa `docker logs`, procura sinal de "está vivo e ocioso".
- **Pensa:** "está trabalhando, esperando ou travou?"
- **Fricção crítica (L3):** ociosidade (`sleep`) é indistinguível de
  travamento visto de fora.
- **Oportunidade UX:** **linha de heartbeat de ociosidade** ("nada a fazer,
  próximo ciclo em Ns") e estado explícito "aguardando ação humana no board".
  → **US-04** (protótipos §4).

### Fase 4 — Operação contínua / intervenção  🙂

- **Faz:** deixa rodando; quando uma issue cai em gate `need_human`, age **no
  board do GitHub** (não na máquina).
- **Pensa:** "onde eu preciso agir?"
- **Fricção:** saber que a esteira está bloqueada esperando o board e não com
  erro.
- **Oportunidade UX:** log distinguir claramente "aguardando humano no board"
  de "erro". → **US-04** (protótipos §4).

### Fase 5 — Diagnosticar falha  😟→🙂

- **Faz:** algo falhou no arranque ou num ciclo; lê o log para entender.
- **Pensa:** "o que quebrou e o que eu faço agora?"
- **Fricção:** mensagens cruas (stderr do git, exceções) sem próximo passo.
- **Oportunidade UX:** **catálogo de mensagens de erro padronizadas**
  (o quê / por quê / próximo passo) + exit code correto para o Docker reiniciar
  ou parar. → **US-05** (protótipos §5).

### Fase 6 — Parar / reiniciar  🙂

- **Faz:** `docker compose down`; depois `up` de novo, esperando continuidade.
- **Pensa:** "perco trabalho? a esteira lembra onde parou?"
- **Fricção (L4):** comportamento de shutdown e persistência de estado/sessões.
- **Oportunidade UX:** runbook documenta parada, persistência via volumes
  (`.pipe/`, sessões do kiro-cli) e o que é efêmero. → **US-03/US-06**
  (protótipos §6).

## Resumo de oportunidades × US

| Oportunidade UX | Fase | US que implementa |
|---|---|---|
| Checklist de pré-requisitos no runbook | 0 | US-06 |
| `.env.example` anotado (obrigatório/opcional + descrição) | 1 | US-02, US-03 |
| Banner de arranque (nome/versão/modo) | 2 | US-01 |
| Resumo de preflight (validado × testado em runtime) | 2 | US-05 |
| Heartbeat de ociosidade + estado "aguardando board" | 3, 4 | US-04 |
| Catálogo de erros (o quê/por quê/próximo passo) + exit codes | 5 | US-05 |
| Runbook de parada/persistência | 6 | US-03, US-06 |
| Log limpo sem ANSI fora de TTY (`NO_COLOR`) | 2–5 | US-01/US-04 |

Nenhuma dessas mudanças altera a lógica de negócio; são de apresentação/saída e
documentação, coerentes com o escopo da feature.
