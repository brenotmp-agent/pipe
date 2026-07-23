# Descoberta UX — Rodar no Docker (US-01 Empacotar a esteira em imagem Docker)

Status: draft
Owner: ux (Talita Souza)
Last updated: 2026-07-07

## Enquadramento: quem é o "usuário" aqui

A esteira é uma aplicação **headless, autônoma e sem GUI**. Não existe tela,
botão nem fluxo clicável. Portanto a "experiência do usuário" desta feature é
**experiência do operador / DevX (Developer Experience)**: como um humano
coloca a esteira containerizada para rodar, entende que ela está saudável,
diagnostica quando algo falha e a opera no dia a dia.

Os pontos de contato reais (as "telas" deste produto) são:

1. **O arquivo de configuração** que o operador edita antes de subir (`.env`,
   `pipe.yml`, `contexts/`).
2. **O comando de subida** (`docker compose up` / `docker run`).
3. **A saída de log** no terminal e em `docker logs` — o único canal em que o
   produto "fala" com o operador durante a execução.
4. **As mensagens de erro** quando o arranque ou um ciclo falha.
5. **O board do GitHub** — onde o humano intervém nos gates `need_human` (fora
   da máquina, conforme `vision.md`).
6. **A documentação de operação** (runbook).

Esta descoberta cobre 1–5 na perspectiva de UX. O board (6) é experiência já
existente; apenas mapeamos onde ele entra na jornada.

## Inputs

- Issue #16 "Empacotar a esteira em imagem Docker" (`-body.md`)
- `doc/stories/rodar-no-docker/user-stories.md` (US-01 a US-06)
- `doc/product/rodar-no-docker/{vision,problem-space,epicos}.md`
- Código: `src/__main__.py` (`check_config`, `startup`, `_setup_ssh`),
  `src/core/config.py` (mensagens de erro reais), `src/core/log.py`
  (formato de saída atual)
- Referências de mercado e boas práticas (seção final)

---

## Entrevista com o usuário (roteiro + respostas derivadas)

A esteira roda de forma autônoma — não há um stakeholder disponível para
entrevista síncrona neste ciclo. Documentei abaixo o **roteiro de entrevista
que conduziria**, respondendo cada item com o que já está definido na
documentação de produto/requisitos e marcando explicitamente o que permanece
como **lacuna aberta** (a confirmar com Produto/Negócio).

### Bloco 1 — Contexto de uso e ambiente

**P1. Onde o operador vai rodar isto?** (notebook, servidor on-prem, VM em
nuvem, CI?)
→ Resposta (vision): "qualquer host com Docker" — servidor, nuvem ou máquina
local. **Assumo servidor/VM headless como cenário primário** (é o que justifica
a feature: remover o vínculo com a máquina física). Notebook local é secundário.

**P2. O operador tem acesso interativo ao host o tempo todo?**
→ Resposta (vision): não necessariamente. A operação autônoma pressupõe que,
após o `up`, ninguém precise voltar ao host. A intervenção humana acontece no
board do GitHub. **Implicação de UX: o log precisa ser autoexplicativo à
distância — o operador vai lê-lo via `docker logs` de outro lugar, muitas vezes
horas depois.**

**P3. Qual o nível técnico do operador?**
→ Resposta (vision/problem-space): "analista/desenvolvedor". Conhece Docker
básico e Git, mas **não necessariamente conhece o código da esteira**. A US-06
exige que ele suba tudo "sem conhecimento prévio do código". **Implicação: zero
jargão interno nas mensagens; termos devem referenciar conceitos do operador
(container, volume, variável), não conceitos internos (snapshot, fila).**

### Bloco 2 — Primeiro uso (onboarding)

**P4. Qual o "tempo até o primeiro ciclo" aceitável?**
→ Lacuna parcial. Não há meta numérica. **Proponho como meta de UX: um operador
novo sobe a esteira em ≤ 15 minutos** seguindo só o runbook (alinhado à métrica
de sucesso da vision: "usuário novo consegue... sem conhecimento prévio").

**P5. O que o operador precisa ter em mãos antes de começar?**
→ Derivado de US-02: uma chave SSH com acesso ao(s) repositório(s), um token do
GitHub (`GH_TOKEN`), uma `KIRO_API_KEY`, um `pipe.yml` e os `contexts/`
preenchidos. **Implicação: precisamos de uma checklist de pré-requisitos "tenha
isto em mãos" no topo do runbook — é o maior ponto de fricção do onboarding.**

**P6. Como o operador sabe se acertou a configuração antes de gastar chamadas
de API?**
→ Lacuna. Hoje `check_config()` valida `pipe.yml`, SSH e contexts, mas a
validação de `GH_TOKEN` e `KIRO_API_KEY` só falha tarde (na primeira chamada
real). **Recomendação de UX (ver prototipos.md): um resumo de arranque
("preflight") que lista o que foi validado e o que será testado só em runtime,
para o operador não ficar no escuro.** A confirmar com Arquitetura se cabe em
US-01/US-05.

### Bloco 3 — Operação contínua

**P7. Como o operador sabe que "está funcionando" e não travou?**
→ Lacuna importante. A esteira dorme `sleep` segundos quando ociosa. Do lado de
fora, "dormindo" e "travado" parecem idênticos em `docker logs`. **Recomendação:
uma linha de heartbeat/estado ("ocioso, próximo ciclo em Ns") que torne a
ociosidade visível.** (ver prototipos.md §4)

**P8. O operador precisa distinguir "esperando humano" de "trabalhando"?**
→ Sim (vision, epicos): os gates `need_human` mantêm o container rodando
enquanto o humano age no board. **Implicação: o log deve deixar claro quando a
esteira está aguardando ação humana no board vs. executando um agente.**

**P9. Como o operador para com segurança?**
→ Derivado US-06: `docker compose down`. **Implicação: documentar o
comportamento de parada e se há trabalho em andamento que se perde.** Lacuna: o
container faz shutdown gracioso? (a confirmar com Arquitetura — impacta a
mensagem de UX no `down`).

### Bloco 4 — Erros e recuperação

**P10. Quais são os erros mais prováveis no primeiro uso?**
→ Derivado do código e de US-05: (a) `PIPE_SSH_KEY_FILE` não definido/arquivo
ausente; (b) `pipe.yml` inválido ou não montado; (c) contexts vazios; (d)
`GH_TOKEN` inválido/sem permissão; (e) `KIRO_API_KEY` ausente/sem plano; (f)
chave SSH sem acesso ao repositório (falha no `git clone`). **Estes 6 viram o
catálogo de mensagens de erro (ver prototipos.md §5).**

**P11. Quando falha, o operador consegue agir sem abrir o código?**
→ Objetivo de UX: sim. Toda mensagem de erro deve dizer **o quê, por quê e o
próximo passo**. Hoje algumas mensagens já fazem isso bem (ex.:
`_validate_env` sugere o `export`), outras não (ex.: falha de `git clone`
propaga stderr cru do git). **Oportunidade de padronização.**

### Lacunas abertas consolidadas (para Produto/Arquitetura)

| # | Lacuna | Impacto UX | Encaminhamento |
|---|--------|-----------|----------------|
| L1 | Sem meta de "tempo até primeiro ciclo" | Dificulta medir sucesso do onboarding | Propor 15 min como meta (Produto) |
| L2 | `GH_TOKEN`/`KIRO_API_KEY` só falham em runtime | Operador descobre erro tarde | Avaliar preflight check (Arquitetura, US-05) |
| L3 | Ociosidade indistinguível de travamento em `docker logs` | Operador não confia no estado | Heartbeat de estado (Arquitetura) |
| L4 | Comportamento de `docker compose down` (shutdown gracioso?) | Mensagem de parada e perda de trabalho | Confirmar (Arquitetura) |
| L5 | Cores ANSI no log em `docker logs` (sem TTY) | Códigos `\033[...]` podem poluir logs | Detectar TTY / respeitar `NO_COLOR` (ver §referências) |

Estas lacunas **não bloqueiam** a US-01 (o Dockerfile em si), mas informam o
design do restante da feature (US-04/05/06). Registradas aqui para rastreio.

---

## Referências de mercado (aplicações parecidas)

Busquei tooling **headless, autônomo, operado por container e que "conversa"
com o usuário só por log** — o mesmo perfil da esteira. Padrões observados:

- **Renovate / Dependabot (bots de automação de repositório em container):**
  toda a operação é dirigida por um arquivo de configuração versionado + um
  token via variável de ambiente; o feedback ao operador é o log estruturado.
  Padrão relevante: **um "config summary" no início do log** listando o que foi
  lido e validado antes de agir. Aplico isso no preflight (prototipos.md §3).
- **GitHub Actions self-hosted runner (container):** onboarding centrado em
  um punhado de variáveis/segredos obrigatórios + um passo único de subida;
  documentação com checklist de pré-requisitos. Reforça a **checklist "tenha em
  mãos"** do runbook.
- **Watchtower (container que age sozinho em loop):** loga explicitamente cada
  ciclo e o intervalo até o próximo — resolve o problema "está vivo ou
  travou?". Base para o **heartbeat de ociosidade** (§4).
- **n8n / Airflow (workers em Docker Compose):** convenção de `.env` +
  `.env.example` versionado, `docker compose up`, estado em volumes nomeados.
  Alinha com o desenho de configuração de US-02/US-03.

Padrão comum a todos: **o `.env.example` anotado é a principal peça de UX de
onboarding** de tooling headless. Por isso ele é um protótipo de primeira classe
aqui (prototipos.md §2).

Conteúdo reescrito para conformidade com licenciamento.

## Boas práticas de UX de linha de comando (fontes especializadas)

Sintetizei diretrizes de fontes de referência em UX de CLI. Princípios adotados
nos protótipos:

- **Erros devem dizer o quê, por quê e o próximo passo** — não despejar
  stack trace cru. Um stack trace não é mensagem de erro.
  ([clig.dev](https://clig.dev/),
  [PatternFly CLI handbook](https://www.patternfly.org/developer-resources/cli-handbook),
  [Grizzly Peak — CLI error handling](https://grizzlypeaksoftware.com/library/cli-error-handling-and-user-friendly-messages-qgugu9kg))
- **Linguagem simples, sem jargão interno; conclua com a informação mais
  importante e um próximo passo acionável.**
  ([PatternFly writing guidelines](https://www.patternfly.org/developer-resources/cli-handbook/writing-guidelines))
- **Exit codes corretos:** 0 sucesso, 1 erro geral, 2 mau uso, 130 Ctrl+C —
  para que operador e orquestrador (Docker/CI) reajam certo.
  ([Calmops — building CLI tools](https://calmops.com/software-engineering/cli-tools-command-line-applications/))
- **Respeitar `NO_COLOR` e ausência de TTY:** cores ANSI só quando a saída é um
  terminal interativo; em `docker logs`/arquivo, texto limpo.
  ([clig.dev](https://clig.dev/),
  [Best practices for inclusive CLIs](https://seirdy.one/posts/2022/06/10/cli-best-practices/))
- **Docker: pinar versões, rodar como não-root, segredos fora de env quando
  possível, logs não-bufferizados para visibilidade em tempo real.**
  ([Docker best practices 2026](https://thinksys.com/devops/docker-best-practices/),
  [Docker Compose env vars](https://docs.docker.com/compose/how-tos/environment-variables/best-practices/))

Conteúdo reescrito para conformidade com licenciamento.

---

## Referências

- [1] Command Line Interface Guidelines — https://clig.dev/
- [2] PatternFly • Command-line interface handbook — https://www.patternfly.org/developer-resources/cli-handbook
- [3] PatternFly • CLI writing guidelines — https://www.patternfly.org/developer-resources/cli-handbook/writing-guidelines
- [4] CLI Error Handling and User-Friendly Messages — https://grizzlypeaksoftware.com/library/cli-error-handling-and-user-friendly-messages-qgugu9kg
- [5] Building CLI Tools (Calmops) — https://calmops.com/software-engineering/cli-tools-command-line-applications/
- [6] Best practices for inclusive CLIs — https://seirdy.one/posts/2022/06/10/cli-best-practices/
- [7] Docker Best Practices 2026 — https://thinksys.com/devops/docker-best-practices/
- [8] Environment variables in Docker Compose — https://docs.docker.com/compose/how-tos/environment-variables/best-practices/
