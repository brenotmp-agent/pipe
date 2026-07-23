# Protótipos UX — Rodar no Docker

Status: draft
Owner: ux (Talita Souza)
Last updated: 2026-07-07

Protótipos de baixa fidelidade dos pontos de contato do operador. Como a esteira
é headless, os "protótipos de tela" são **mockups de saída de terminal**,
**artefatos de configuração anotados** e o **wireframe do runbook**.

Todos os mockups são coerentes com o formato de log real
(`src/core/log.py`: `HH:MM:SS [Módulo] mensagem`) e com as mensagens de erro
reais (`src/core/config.py`). São **propostas de UX**; a implementação técnica
fica com as US indicadas. Nenhum altera lógica de negócio.

---

## §1 — Banner de arranque (US-01)

**Problema (Fase 2 da jornada):** hoje a primeira linha do log é
`Config: Validando pipe.yml`, sem identificar o quê subiu nem a versão. Em
`docker logs` de um servidor remoto, o operador não confirma *o que* está
rodando.

**Proposta:** uma linha/bloco de identificação no início, usando a `VERSION` já
existente (`src/core/version.py`) e o modo de execução.

```
12:49:20 [Esteira] Esteira Agêntica v1.4.2 — iniciando (container)
12:49:20 [Config] Validando pipe.yml
```

Versão compacta (uma linha) preferida a ASCII-art: legível em `docker logs`,
sem ruído, sem depender de cores. Princípio: identificação clara + informação
mais importante primeiro (fonte: PatternFly writing guidelines).

---

## §2 — `.env.example` anotado (US-02, US-03)

**Problema (Fases 0–1):** o operador não sabe *quais* segredos precisa nem em
*qual formato*. Este é o principal artefato de onboarding de tooling headless
(padrão observado em Renovate, n8n, runners — ver `descoberta.md`).

**Proposta de conteúdo** (arquivo versionado; `.env` real fica no
`.gitignore`):

```dotenv
# ─────────────────────────────────────────────────────────────
#  Esteira Agêntica — configuração de runtime (Docker)
#  Copie para .env e preencha. NÃO versione o .env real.
# ─────────────────────────────────────────────────────────────

# [OBRIGATÓRIO] Caminho DA CHAVE SSH DENTRO DO CONTAINER.
# É um caminho, não o conteúdo da chave. A chave entra por volume/secret
# (ver docker-compose). Deve ter acesso de leitura aos repositórios do pipe.yml.
# Exemplo: /run/secrets/ssh_key
PIPE_SSH_KEY_FILE=

# [OBRIGATÓRIO] Token do GitHub usado pelo gh CLI (escopos: repo, project).
# Gere em https://github.com/settings/tokens
GH_TOKEN=

# [OBRIGATÓRIO] API key do kiro-cli (modo headless, requer plano Kiro Pro+).
KIRO_API_KEY=

# [OPCIONAL] Sobrescreve o intervalo de ociosidade do pipe.yml (segundos).
# PIPE_SLEEP=60
```

**Diretrizes de UX aplicadas:**
- Cabeçalho `[OBRIGATÓRIO]`/`[OPCIONAL]` em cada variável (reduz dúvida da
  Fase 1).
- Uma linha de descrição por variável, em linguagem do operador.
- Aviso explícito "caminho, não conteúdo" no `PIPE_SSH_KEY_FILE` — resolve a
  confusão de UX mapeada na Fase 1.
- Exemplo de valor em cada uma.

---

## §3 — Resumo de preflight no arranque (US-05)

**Problema (Fase 2, lacuna L2):** `check_config()` valida `pipe.yml`, SSH e
contexts, mas `GH_TOKEN`/`KIRO_API_KEY` só falham na primeira chamada real. O
operador fica no escuro sobre o que ainda pode dar errado.

**Proposta:** após validar, imprimir um resumo curto do que foi validado e do
que só será testado em runtime. Torna o estado do arranque legível.

```
12:49:20 [Config] Validando pipe.yml
12:49:20 [Config] pipe.yml válido
12:49:20 [Preflight] Verificado agora:
12:49:20 [Preflight]   ok  pipe.yml carregado (3 boards, 5 agentes)
12:49:20 [Preflight]   ok  chave SSH encontrada em /run/secrets/ssh_key
12:49:20 [Preflight]   ok  contexts preenchidos (5/5)
12:49:20 [Preflight] Será testado no primeiro uso:
12:49:20 [Preflight]   ..  GH_TOKEN (acesso ao GitHub)
12:49:20 [Preflight]   ..  KIRO_API_KEY (execução do agente)
12:49:20 [Preflight]   ..  acesso SSH aos repositórios (git clone)
```

Padrão inspirado no "config summary" de bots de automação (ver
`descoberta.md`). **A decidir com Arquitetura** se esta é a superfície certa
(pode ser um preflight ativo que testa `GH_TOKEN`/`KIRO_API_KEY` de fato — mais
caro, porém falha cedo). Registrado como recomendação, não requisito de US-01.

---

## §4 — Heartbeat de ociosidade e estado (US-04)

**Problema (Fases 3–4, lacuna L3 — crítico):** quando ociosa, a esteira dorme
`sleep` segundos. Em `docker logs`, "ociosa" e "travada" são idênticas. E o
operador não distingue "aguardando humano no board" de "trabalhando".

**Proposta — estado ocioso explícito:**

```
12:50:05 [Loop] Nada a fazer neste ciclo — ocioso
12:50:05 [Loop] Próximo ciclo em 60s (aguardando mudanças no board)
```

**Proposta — estado aguardando humano:**

```
12:51:10 [Loop] #42 aguardando ação humana no board (gate: Validação Negocial)
12:51:10 [Loop] Nenhuma ação no container é necessária — aja no board do GitHub
```

Assim o operador remoto, olhando `docker logs` horas depois, entende em uma
linha que o sistema está vivo. Padrão observado em containers de loop
(Watchtower — ver `descoberta.md`).

---

## §5 — Catálogo de mensagens de erro (US-05)

**Problema (Fase 5):** algumas mensagens já são boas (ex.: `_validate_env`
sugere o `export`); outras propagam stderr cru (ex.: falha de `git clone`).
Objetivo: toda falha diz **o quê / por quê / próximo passo** e sai com exit code
correto para o Docker reagir (fonte: clig.dev, Calmops).

**Padrão de mensagem proposto:**

```
[Módulo] ✗ <o que falhou>
         Causa: <por quê, em linguagem do operador>
         Ação:  <próximo passo concreto>
```

**Catálogo dos 6 erros mais prováveis (mapeados na entrevista P10):**

| Cód. | Gatilho | Mensagem proposta (resumo) | Exit |
|---|---|---|---|
| E1 | `PIPE_SSH_KEY_FILE` ausente | ✗ Chave SSH não configurada · Causa: variável não definida · Ação: defina `PIPE_SSH_KEY_FILE` no `.env` apontando para o secret montado | 1 |
| E2 | Arquivo da chave não existe | ✗ Chave SSH não encontrada em `<path>` · Causa: caminho não existe no container · Ação: confira o volume/secret no docker-compose | 1 |
| E3 | `pipe.yml` ausente/inválido | ✗ `pipe.yml` não encontrado ou inválido · Causa: não montado ou YAML malformado · Ação: monte `./pipe.yml` como volume (somente leitura) | 1 |
| E4 | contexts vazios | ✗ Contextos de agente vazios · Causa: `contexts/<plat>/<agente>.md` sem conteúdo · Ação: preencha antes de subir · lista os arquivos | 1 |
| E5 | `GH_TOKEN` inválido/sem escopo | ✗ Acesso ao GitHub negado · Causa: token ausente, expirado ou sem escopo `repo`/`project` · Ação: gere um token novo e atualize `GH_TOKEN` | 1 |
| E6 | `git clone` sem acesso SSH | ✗ Falha ao clonar `<repo>` · Causa: a chave SSH não tem acesso ao repositório · Ação: adicione a chave pública como deploy key do repo | 1 |

E1–E4 já ocorrem no `check_config()` (arranque). E5–E6 ocorrem no `startup`/
primeiro uso — a proposta é **capturar e reformatar** antes de propagar o
stderr cru. Mensagens curtas no terminal; detalhe/trace vai só para o arquivo
de log (comportamento dual já existente em `log.py`).

**Nota de acessibilidade/portabilidade (lacuna L5):** os glifos `✗`/`ok`/`..` e
as cores ANSI devem cair para texto simples quando a saída não for um TTY
(`docker logs`, arquivo) ou quando `NO_COLOR` estiver definido. Alternativa sem
símbolo: prefixo textual `ERRO:` / `OK:` / `PENDENTE:`.

---

## §6 — Wireframe do runbook `doc/runbook/docker.md` (US-06)

Estrutura proposta (ordem = ordem da jornada; cada seção resolve uma fase):

```
# Rodar a esteira no Docker

## 1. Antes de começar — tenha isto em mãos   ← Fase 0
   [ ] Docker + Docker Compose instalados
   [ ] Chave SSH com acesso aos repositórios do pipe.yml
   [ ] Token do GitHub (GH_TOKEN) com escopos repo + project
   [ ] KIRO_API_KEY (plano Kiro Pro ou superior)
   [ ] pipe.yml e contexts/ preenchidos

## 2. Configurar                               ← Fase 1
   - copie .env.example para .env e preencha (tabela de variáveis)
   - monte pipe.yml e contexts/ como volumes

## 3. Subir                                    ← Fase 2
   docker compose up -d
   (o que esperar no log: banner + preflight)

## 4. Confirmar que está rodando               ← Fase 3
   docker compose ps
   docker compose logs -f    (como ler: ocioso / trabalhando / aguardando board)

## 5. Operação e intervenção humana            ← Fase 4
   - gates need_human são resolvidos NO BOARD do GitHub, não no container

## 6. Parar e reiniciar                         ← Fase 6
   docker compose down
   - o que persiste (volumes: .pipe/, logs/, repo/, sessões kiro-cli)
   - o que é efêmero

## 7. Solução de problemas                       ← Fase 5
   tabela: sintoma no log → causa → ação   (deriva do catálogo §5)
```

Diretrizes: começar pela checklist (maior fricção), linguagem sem jargão
interno, cada comando com "o que esperar", e uma tabela de troubleshooting
sintoma→ação (fonte: PatternFly, clig.dev).

---

## Prioridade e handoff

| Protótipo | Prioridade UX | Bloqueia US-01? | Entrega em |
|---|---|---|---|
| §1 Banner de arranque | Média | Não | US-01 |
| §2 `.env.example` anotado | Alta | Não | US-02/US-03 |
| §3 Preflight | Média (validar c/ Arq.) | Não | US-05 |
| §4 Heartbeat/estado | Alta | Não | US-04 |
| §5 Catálogo de erros | Alta | Não | US-05 |
| §6 Runbook | Alta | Não | US-06 |

**US-01 (o Dockerfile) não depende destes protótipos** — apenas o §1 (banner) e
a diretriz de log sem ANSI fora de TTY tocam a imagem. Os demais orientam
US-02/03/04/05/06. Isso mantém a story-base desbloqueada.

Próximo passo sugerido: validar as lacunas L1–L5 (`descoberta.md`) com Produto/
Arquitetura na etapa de validação do protótipo.
