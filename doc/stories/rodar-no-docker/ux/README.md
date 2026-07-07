# UX / DX — US-02 Autenticar dependências externas em modo headless

Status: prototype
Owner: ux (Talita Souza)
Last updated: 2026-07-07
Story: #17 (US-02) — épico "Rodar no Docker"

## Por que existe UX numa story headless?

US-02 não tem tela. Mesmo assim tem **usuário**: o operador que sobe a esteira
em um host com Docker. Como não há GUI, a experiência dele acontece em três
superfícies — e cada uma é um artefato desenhável:

| Superfície | O que é | Onde o operador a encontra |
|---|---|---|
| **Setup** (entrada) | Como ele declara as três credenciais | `.env` / `docker-compose.yml` |
| **Feedback** (saída) | Como o sistema diz "deu certo" ou "faltou X" | `docker logs` (terminal) |
| **Guia** (apoio) | Onde obter cada credencial e como corrigir | runbook (US-06) |

Este é um trabalho de **Developer/Operator Experience (DX)**. O "protótipo" aqui
são mockups de saída de terminal, especificação de copy de mensagens e o desenho
do arquivo de setup — os equivalentes headless de wireframes e telas.

## Deliverables desta pasta

| Arquivo | O que é |
|---|---|
| `operator-journey.md` | Mapa da jornada do operador no primeiro `up`, com dores, emoções e oportunidades |
| `terminal-prototypes.md` | "Wireframes" da saída de terminal: happy path + cada cenário de falha |
| `error-copy-spec.md` | Especificação de copy das mensagens (atual × proposto) + template reutilizável |
| `env-example.prototype` | Protótipo do arquivo de setup (`.env.example`) com copy inline — insumo para US-03 |

## Resumo das descobertas de UX

Três achados, em ordem de impacto na experiência do operador:

### 1. Validação assimétrica quebra o modelo mental (impacto alto)

`PIPE_SSH_KEY_FILE` falha no arranque com mensagem clara; `GH_TOKEN` e
`KIRO_API_KEY` falham **lazy**, no meio do loop (AC-06). Para um container
autônomo, isso significa: o operador dá `up`, vê o log correr como se estivesse
tudo bem, e só minutos depois — enterrado entre linhas de sync — descobre que
esqueceu um token. Ele não consegue correlacionar o erro tardio com a causa
("faltou a variável"). A pesquisa de mercado é consistente: validação de
configuração deve **falhar rápido no arranque** ([Reaktor — Little server
patterns](https://www.reaktor.com/blog/little-server-patterns-failing-quickly/)).

**Recomendação (para Engenharia validar no próximo estágio):** um **preflight
de credenciais** no `startup()` que verifica as três de uma vez e falha rápido
com um resumo único. Prototipado em `terminal-prototypes.md` (cena A e F).

### 2. Falta confirmação positiva de sucesso (impacto médio)

Os critérios AC-02/AC-03 já pedem `gh auth status` e `kiro-cli whoami` como
verificação — mas hoje nada disso aparece para o operador. Sem um "as três
credenciais estão OK", ele fica na dúvida se o headless realmente autenticou ou
se vai quebrar no primeiro card. O padrão de mercado para isso é o
**doctor/preflight** (`flutter doctor`, `gh auth status`): um resumo verde que
dá confiança antes do trabalho começar. Prototipado como o bloco de arranque na
cena A.

### 3. Copy das mensagens não é Docker-aware (impacto médio)

A mensagem atual de SSH sugere `export PIPE_SSH_KEY_FILE=...` — uma correção de
**host**, não de **container**. Quem roda em Docker corrige no `.env`/compose. A
copy precisa falar a língua do contexto de execução. Detalhado em
`error-copy-spec.md`.

## Boas práticas aplicadas (referências de mercado)

- **Toda mensagem de erro responde "o que / por quê / como corrigir"** e aponta
  onde obter a credencial — em vez de só reportar a falha
  ([bomberbot](https://www.bomberbot.com/javascript/how-to-write-error-messages-that-dont-suck/),
  [skillsmp — cli-messaging](https://skillsmp.com/skills/creatifcoding-gbg-packages-tmnl-claude-skills-cli-messaging-skill-md)).
- **Concisão**: tirar palavras desnecessárias, uma linha de causa + uma de ação
  ([Stack Overflow Design System](https://stackoverflow.design/content/examples/error-messages)).
- **Fail-fast no arranque** para configuração ausente, com saída não-zero clara
  ([Reaktor](https://www.reaktor.com/blog/little-server-patterns-failing-quickly/)).
- **Padrão doctor/preflight** para dar confiança antes de operar
  (`flutter doctor`, `gh auth status`).
- **Segredos nunca em log nem na imagem**: confirmar presença/validade sem
  jamais ecoar o valor ([Wiz — Docker Secrets](https://www.wiz.io/academy/container-security/docker-secrets)).

Conteúdo das fontes foi reescrito para conformidade com licenciamento.

## Fronteira de escopo

Este pacote é de **prototipação/especificação**. Não altera código em `src/`
nem cria o `docker-compose.yml`/`.env` reais (US-03). As recomendações de
preflight e de copy são insumos para a Engenharia implementar no estágio
seguinte; o `env-example.prototype` é referência de copy para US-03.
