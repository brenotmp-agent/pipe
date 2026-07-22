# UX — US-03 Configurar a esteira via docker-compose sem rebuild

Status: prototype (para validação)
Owner: ux
Autora: Talita Souza — User Experience
Last updated: 2026-07-07

> Esta é uma story de produto **sem interface gráfica**. A "experiência do
> usuário" aqui é a **experiência do operador (DX — developer/operator
> experience)**: a ergonomia dos arquivos que o operador edita
> (`docker-compose.yml`, `.env`), a jornada da primeira subida ("do zero ao loop
> rodando"), a clareza das mensagens de feedback e o esforço para **trocar a
> configuração sem rebuild**. Os artefatos desta etapa são: esta documentação,
> os protótipos anotados em `prototipos/` e a especificação de microtexto das
> mensagens.

---

## 1. Inputs

- `doc/stories/rodar-no-docker/user-stories.md` (US-01 a US-06; foco em US-03)
- `doc/product/rodar-no-docker/{vision,problem-space,epicos}.md`
- Issue #18 "Configurar a esteira via docker-compose sem rebuild"
- Referências de mercado e de UX (ver seção 4)

---

## 2. A pessoa e o contexto de uso

**Persona: "Operador da esteira"** (analista/desenvolvedor que quer rodar a
esteira sem depender de uma máquina física preparada à mão — em servidor, nuvem
ou qualquer host com Docker). Vem de `vision.md` (Público-alvo) e
`problem-space.md`.

| Dimensão | Descrição |
|---|---|
| Objetivo principal | Subir a esteira funcionando com o mínimo de passos e **trocar a configuração sem rebuild**. |
| Nível de familiaridade | Confortável com terminal e Docker; **não** conhece o código-fonte da esteira. |
| Ambiente | Host remoto (servidor/nuvem), muitas vezes via SSH, **sem GUI e sem browser** — daí o modo headless. |
| Frequência de uso | Setup inicial (uma vez) + trocas de configuração recorrentes (várias vezes). |
| Maior dor | Fricção de setup manual de 3 credenciais (SSH, GitHub, kiro-cli) e medo de "quebrar" ao mexer na config. |
| Critério de sucesso emocional | "Funcionou de primeira e eu não precisei entender o código." (métrica de sucesso da `vision.md`) |

**Momento de uso desta story:** o operador já tem a imagem (US-01) e entendeu
o mecanismo de credenciais (US-02). US-03 é onde ele **materializa tudo num
único arquivo** e ganha o superpoder de "editar e subir de novo, sem rebuild".

---

## 3. Entrevista com o usuário — lacunas e premissas

Não há usuário disponível para entrevista síncrona nesta etapa. Segui a
prática de UX de **extrair o máximo da documentação existente** e registrar,
de forma transparente, o que já está respondido e o que permanece como
premissa a validar. As premissas abaixo foram assumidas para destravar a
prototipação; nenhuma é bloqueante, mas todas devem ser confirmadas na etapa de
Validação de Protótipo.

### 3.1 Perguntas que eu faria — e o que a documentação já responde

| # | Pergunta ao operador | Resposta inferida da documentação |
|---|---|---|
| P1 | Você prefere um `docker-compose.yml` que já funciona, ou um `.example` para copiar? | AC-01 pede o arquivo versionado na raiz **funcional**; segredos vêm de `.env` (AC-04/05). Decisão: **compose versionado + `.env.example` para copiar**. |
| P2 | Onde você guarda os segredos hoje? | `.env` do host (AC-04). Nada sensível versionado (AC-05, RNF-01). |
| P3 | Quantas vezes por semana você troca configuração? | Não quantificado, mas é o **valor central** da story ("sem rebuild"). Otimizamos a jornada de troca (seção 5, passo 6). |
| P4 | Você roda em máquina com Docker Desktop ou só engine? | Assumido: **engine em servidor headless** (vision). Compose V2 plugin (`docker compose`, sem hífen) — AC-01/RNF-03. |
| P5 | Quer subir em foreground (ver logs) ou em background? | Ambos documentados na jornada; recomendação: `up -d` + `logs -f` (seção 5). |
| P6 | O que te deixa mais inseguro ao mexer na config? | Medo de precisar rebuild e de vazar segredo. Mitigado por microtexto e por `.env` no `.gitignore`. |

### 3.2 Premissas assumidas (a validar)

- **PR-1** — A raiz do repositório é o diretório de trabalho do operador (onde
  ficam `pipe.yml`, `contexts/`, `.env`). Alinha com a estrutura de referência
  da US-03.
- **PR-2** — O operador tem, ou consegue gerar, os 3 segredos (chave SSH, PAT
  GitHub com escopos `repo`+`project`, `KIRO_API_KEY` com plano Pro+). O
  onboarding **aponta onde obter cada um**, mas não os provisiona.
- **PR-3** — `docker compose up -d` em background é o modo preferido em
  servidor; foreground é para o primeiro diagnóstico.
- **PR-4** — Uma única esteira por host nesta story (sem múltiplas instâncias /
  profiles). Multi-instância fica fora de escopo.

### 3.3 Lacunas remanescentes para o humano (não bloqueantes)

- **G-1** — Confirmar se o compose deve ser `docker-compose.yml` (funcional) ou
  `docker-compose.example.yml` (a issue aceita ambos em "Critérios de
  aceitação"). Protótipo assume **`docker-compose.yml` funcional** + `.env`
  como fonte de segredos, por ser a melhor DX (um comando, zero renomeação de
  arquivo).
- **G-2** — Confirmar o caminho do HOME do usuário não-root para o volume
  `kiro-home` (`/home/pipe/.kiro` assumido de ADR-05). Depende do usuário
  definido no Dockerfile (US-01).

---

## 4. Referências de mercado e boas práticas

### 4.1 Benchmark — produtos self-hosted com onboarding via compose + `.env`

Ferramentas de referência que resolvem o mesmo problema de "suba em qualquer
host com um comando, configurando por fora": projetos self-hosted populares
distribuem um `docker-compose.yml` versionado acompanhado de um `.env.example`
que o operador copia para `.env` e preenche. O padrão recorrente observado
(ex.: n8n, Metabase, Plausible Analytics, Gitea, Sentry self-hosted) é:

- **Um comando para subir** (`docker compose up -d`) — reduz a barreira de
  adoção (Regra 8: defaults sensatos / zero-config quando possível). [4]
- **`.env.example` como contrato de configuração** — todas as variáveis
  documentadas, com descrição e onde obter, e o `.env` real no `.gitignore`. [3][5]
- **Comentários no compose como documentação embutida** — cada bloco explica o
  que faz e o que é seguro trocar.
- **Separação clara entre "config que troca" e "imagem que é fixa"** — o que
  materializa o valor "sem rebuild".

### 4.2 Boas práticas aplicadas (com fonte)

| Princípio | Como aplicamos | Fonte |
|---|---|---|
| Trate segredos com segurança; nunca versione | Segredos só no `.env` (gitignored) e chave SSH via Docker secret `0400`; nada no compose. | Docker Compose — Best practices for env vars [1] |
| Entenda a precedência de variáveis | Documentamos a ordem `.env` → shell → compose para evitar surpresas. | Docker Compose — Env var precedence [1] |
| Valide na entrada; defaults explícitos | `check_config()` falha rápido no arranque; `.env.example` lista todas as vars. | Common Docker Compose Mistakes [5] |
| Falhe rápido com mensagem útil (o quê / onde / como corrigir) | Microtexto das mensagens de erro na seção 6. | 12 Rules of CLI UX, Regra 1 [4] |
| Mensagens humanas, precisas, sem culpar o usuário, com ação construtiva | Reescrita das mensagens de erro na seção 6. | NN/g — Error-Message Guidelines [2] |
| Escreva status em stderr, dados em stdout | Recomendação para logs do loop (aplicável à US-04). | 12 Rules of CLI UX, Regra 11 [4] |

> Conteúdo das fontes foi reescrito e resumido para conformidade com
> restrições de licenciamento.

---

## 5. Jornada do operador — "do zero ao loop rodando"

Fluxo principal (happy path) com pontos de dor e mitigação de UX. Este é o
"protótipo de fluxo" a validar.

```
[1] Descoberta        →  lê o Quickstart no README/runbook
        │                 (dor: não saber por onde começar)
        ▼                 mitigação: 1 bloco "Quickstart" com 4 comandos
[2] Pré-requisitos    →  Docker + 3 credenciais (SSH, PAT, KIRO_API_KEY)
        │                 (dor: descobrir tarde que falta plano Pro+)
        ▼                 mitigação: checklist de pré-requisitos ANTES do up
[3] Configurar        →  cp .env.example .env  →  preenche 3 segredos
        │                 edita pipe.yml e contexts/ conforme necessidade
        │                 (dor: medo de vazar segredo / não saber o escopo do PAT)
        ▼                 mitigação: .env comentado + .gitignore + "onde obter"
[4] Subir             →  docker compose up -d
        │                 (dor: "travou?" / erro críptico)
        ▼                 mitigação: fail-fast claro (seção 6) + logs -f
[5] Verificar         →  docker compose logs -f  →  vê "loop iniciado"
        │                 docker compose ps  →  estado do serviço
        ▼
[6] TROCAR CONFIG     →  edita pipe.yml OU .env  →  docker compose up -d
    (SEM REBUILD)         (coração da US-03: nenhum docker build)
        │                 mitigação: callout explícito "não precisa rebuild"
        ▼
[7] Parar             →  docker compose down (estado persiste em volumes)
```

### Momento-chave (o valor da story): passo 6

O diferencial de UX desta story é **remover o medo e o custo de trocar a
configuração**. A jornada deve deixar explícito, em três lugares, que trocar
`pipe.yml` ou credenciais **não** exige `docker build`:

1. No cabeçalho comentado do `docker-compose.yml` (protótipo).
2. No `.env.example` (protótipo).
3. No Quickstart do runbook (US-06), como uma nota destacada.

Único caso que exige rebuild: mudança em `src/` ou no `Dockerfile` (AC-06).
Isso precisa estar dito com todas as letras para o operador não hesitar.

---

## 6. Design de microtexto — mensagens de feedback

As mensagens de erro são a principal "interface" de um produto headless. Cada
mensagem segue a estrutura **o quê aconteceu → onde → como corrigir** [4] e as
diretrizes de comunicação da NN/g (linguagem humana, precisa, construtiva, sem
culpar o usuário) [2].

> Nota: o comportamento de falha (fail-fast) é implementado em `config.py`
> (US-05). Esta seção é a **especificação de UX do texto** dessas mensagens,
> para orientar a implementação e a validação. As mensagens são exibidas no
> `docker logs` / stderr.

| Situação | Antes (só técnico) | Depois (UX — o quê / onde / como corrigir) |
|---|---|---|
| `PIPE_SSH_KEY_FILE` ausente | `Variável de ambiente 'PIPE_SSH_KEY_FILE' não definida ou vazia` | `Erro: a variável PIPE_SSH_KEY_FILE não está definida.`<br>`Ela deve apontar para o caminho da chave SSH dentro do container (ex.: /run/secrets/ssh_key).`<br>`Como corrigir: defina SSH_KEY_FILE_HOST no seu .env e confira o bloco 'secrets' do docker-compose.yml. Veja doc/runbook/docker.md.` |
| Arquivo SSH inexistente | `Arquivo SSH não encontrado: <caminho>` | `Erro: a chave SSH não foi encontrada em <caminho>.`<br>`Como corrigir: confirme que SSH_KEY_FILE_HOST no .env aponta para um arquivo existente no host e que o secret 'ssh_key' está declarado no compose.` |
| `pipe.yml` inválido/ausente | `pipe.yml inválido` | `Erro: não foi possível ler o pipe.yml em /app/pipe.yml.`<br>`Detalhe: <mensagem do parser>.`<br>`Como corrigir: valide o YAML no host (o arquivo é montado por volume, então basta corrigir e rodar 'docker compose up -d' — sem rebuild).` |
| `GH_TOKEN` ausente (lazy) | erro genérico na 1ª chamada de board | `Erro: falha ao acessar o board do GitHub — GH_TOKEN não definido ou sem permissão.`<br>`Como corrigir: gere um PAT com escopos 'repo' e 'project' e defina GH_TOKEN no .env. Veja doc/runbook/docker.md.` |
| `KIRO_API_KEY` ausente (lazy) | erro genérico na 1ª execução de agente | `Erro: falha ao executar o agente — KIRO_API_KEY não definida.`<br>`Como corrigir: gere uma API key em app.kiro.dev (requer plano Pro ou superior) e defina KIRO_API_KEY no .env.` |

Princípios do microtexto:
- **Nunca culpar o operador** ("você errou") — descrever o estado e o caminho. [2]
- **Sempre dar o próximo passo acionável** e, quando fizer sentido, lembrar que
  a correção **não exige rebuild** (reforça o valor da story).
- **Apontar para o runbook** (US-06) como fonte única de verdade.

---

## 7. Checklist heurístico (para a Validação de Protótipo)

Baseado nas heurísticas de usabilidade adaptadas para DX. Usar como roteiro de
avaliação do protótipo:

- [ ] **Visibilidade do estado** — `docker compose ps` e `logs -f` deixam claro
      se a esteira está rodando, ociosa ou falhou?
- [ ] **Correspondência com o mundo real** — nomes de variáveis e volumes são
      autoexplicativos (`PIPE_SSH_KEY_FILE`, `pipe-logs`, `kiro-home`)?
- [ ] **Controle e liberdade** — o operador troca config e reverte facilmente
      (editar `.env`/`pipe.yml` e subir de novo) sem rebuild?
- [ ] **Consistência e padrões** — segue o padrão de mercado (compose + `.env`
      copiado do `.example`)?
- [ ] **Prevenção de erros** — `.env` no `.gitignore`; secret SSH `ro`; defaults
      explícitos evitam config faltante?
- [ ] **Reconhecer em vez de lembrar** — comentários no compose e no `.env`
      explicam cada campo no ponto de uso?
- [ ] **Flexibilidade** — `up`, `up -d`, `logs -f`, `down` cobrem os modos de
      uso (foreground/background)?
- [ ] **Estética e minimalismo** — o compose tem só o necessário para US-03,
      sem ruído?
- [ ] **Ajuda a reconhecer/recuperar de erros** — mensagens no formato o quê /
      onde / como corrigir (seção 6)?
- [ ] **Ajuda e documentação** — Quickstart de 4 comandos + runbook (US-06)?

---

## 8. Artefatos entregues nesta etapa

- `doc/ux/rodar-no-docker/us-03-experiencia-do-operador.md` (este documento).
- `doc/ux/rodar-no-docker/prototipos/docker-compose.example.yml` — protótipo
  anotado do compose, com foco na DX e no "sem rebuild".
- `doc/ux/rodar-no-docker/prototipos/env.example` — protótipo anotado do arquivo
  de variáveis, com descrição, onde obter e escopos de cada credencial.
- `doc/ux/rodar-no-docker/prototipos/quickstart.md` — protótipo do microtexto de
  onboarding (4 passos) para alimentar o runbook (US-06).

> Os protótipos vivem em `doc/ux/.../prototipos/` de propósito: são material de
> **validação**, não os arquivos finais de produção. A implementação canônica
> do `docker-compose.yml`, `.env.example` e do runbook na raiz/`doc/runbook`
> pertence às stories de engenharia (US-03 impl., US-06), que devem usar estes
> protótipos como referência de DX.

---

## 9. Referências

- [1] Docker — Best practices for working with environment variables in Docker
  Compose. https://docs.docker.com/compose/how-tos/environment-variables/best-practices/
- [2] Nielsen Norman Group — Error-Message Guidelines.
  https://www.nngroup.com/articles/error-message-guidelines/
- [3] Docker — Secrets in Compose.
  https://docs.docker.com/compose/how-tos/use-secrets/
- [4] Wilson Xu — The 12 Rules of Great CLI UX (Regras 1, 8, 11).
  https://wilsonxudev.hashnode.dev/the-12-rules-of-great-cli-ux-lessons-from-building-30-develo
- [5] MoldStud — Common Docker Compose Mistakes and How to Avoid Them.
  https://moldstud.com/articles/p-avoid-these-common-docker-compose-pitfalls-tips-and-best-practices

> Conteúdo das fontes acima foi parafraseado e resumido para conformidade com
> restrições de licenciamento.
