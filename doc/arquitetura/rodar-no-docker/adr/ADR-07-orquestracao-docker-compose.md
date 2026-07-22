# ADR-07 — Orquestração via docker-compose (single service, sem rebuild)

Status: aceito
Data: 2026-07-07
Relacionado: RF-05, RNF-01, RNF-03, RNF-04; ADR-03, ADR-05, ADR-06
Escopo: US-03 (issue #18). Concretiza o princípio do ADR-06 no nível de orquestração.

## Contexto

O ADR-06 definiu o princípio "nada de ambiente ou segredo entra na imagem" e
delegou a concretização a US-02/US-03. US-03 precisa decidir **como** o
operador materializa esse princípio em um artefato único e reprodutível, de
forma que trocar configuração ou credencial **não exija `docker build`**
(RF-05).

A esteira é um único processo de vida longa (`python -m src`, ADR-01/ADR-02):
um loop que fala com GitHub (via `gh`/`git`) e com o backend do Kiro (via
`kiro-cli`). Não há serviço web, banco embarcado nem múltiplos processos
cooperando. As entradas externas são de três naturezas distintas:

1. **Configuração não sensível**: `pipe.yml` e `contexts/` — texto que o
   operador edita com frequência.
2. **Segredos**: chave SSH privada, `GH_TOKEN`, `KIRO_API_KEY`.
3. **Estado de runtime**: `repo/`, `logs/`, `.pipe/` e o estado do kiro-cli
   (`~/.kiro/` e o índice SQLite em `~/.local/share/kiro-cli/`).

Cada natureza pede um mecanismo de injeção diferente.

## Decisão

Um único `docker-compose.yml` versionado na raiz, com **um único serviço**
(`pipe`), que evolui incrementalmente ao longo de US-03/US-04/US-05. US-03
entrega a estrutura base. Compose V2 (`docker compose`, sem hífen); a
compatibilidade com o V1 (`docker-compose`) não é requisito (RNF-03/AC-01).

Mecanismo de injeção por natureza da entrada:

| Natureza | Mecanismo | Justificativa |
|----------|-----------|---------------|
| `pipe.yml`, `contexts/` | **bind mount somente-leitura** (`:ro`) | Editar no host e `docker compose up` aplica sem rebuild (RF-05). `:ro` impede que o container corrompa a fonte. |
| Chave SSH | **Docker secret** com origem em arquivo (`secrets.ssh_key.file`) | Montada em `/run/secrets/ssh_key` com `0400`; não vira variável de ambiente nem aparece no filesystem fora do mountpoint (RNF-01). Ver "SSH: secret vs bind mount". |
| `GH_TOKEN`, `KIRO_API_KEY` | **variável de ambiente via `.env`** do host | O `gh` e o `kiro-cli` leem essas variáveis nativamente (ADR-02/ADR-01 dos requisitos). `.env` fica no `.gitignore`. |
| Estado de runtime | **volumes nomeados** | Sobrevivem ao ciclo do container; a semântica de persistência é validada em US-04. |

Referências `${VAR}` no compose leem do `.env`; nenhum valor real é versionado
(RNF-01/AC-04/AC-05). Acompanha um `.env.example` versionado como contrato de
configuração.

## SSH: secret vs bind mount

Optou-se por **Docker secret** (origem em arquivo) em vez de bind mount `:ro`
direto da chave, porque o secret:

- é montado com `0400` (somente leitura do dono) em `/run/secrets/ssh_key`, sem
  expor o conteúdo como variável de ambiente;
- não deixa o arquivo visível no filesystem do container fora do mountpoint.

Em Compose V2 fora de Swarm, secrets com `file:` são suportados e montados como
bind read-only em `/run/secrets/<nome>` — não exigem Swarm. `_setup_ssh()`
copia essa chave para `~/.ssh/id_pipe` (0600) no arranque, coerente com ADR-03
e ADR-05. A chave nunca entra na imagem (RNF-01).

## `PIPE_SSH_KEY_FILE`: caminho fixo no compose, não no `.env`

`PIPE_SSH_KEY_FILE` aponta para o caminho **interno** do container
(`/run/secrets/ssh_key`), que é determinado pelo próprio compose (nome do
secret), não pelo operador. Portanto ela é declarada em `environment:` no
serviço, e **não** faz parte das variáveis que o operador preenche no `.env`.

Isso remove um _footgun_: `environment:` tem precedência sobre `env_file:`, de
modo que manter `PIPE_SSH_KEY_FILE` também no `.env` seria redundante e
enganoso (o valor do `.env` seria silenciosamente sobreposto). O operador só
fornece três valores no `.env`: `SSH_KEY_FILE_HOST` (caminho da chave **no
host**, usado na interpolação do secret em tempo de parse do compose),
`GH_TOKEN` e `KIRO_API_KEY`.

## Persistência do estado do kiro-cli: dois volumes

Para a continuidade de sessão do agente sobreviver a reinícios, persistem-se
**dois** caminhos, coerente com o comportamento verificado do kiro-cli neste
projeto (CONTEXT.md, "Sessão do agente") e com ADR-05:

- `~/.kiro/` (volume `kiro-home`) — sessões e config;
- `~/.local/share/kiro-cli/` (volume `kiro-local`) — o **índice SQLite keyed
  por cwd**, base de `--list-sessions` e, portanto, do `--resume-id`.

Sem o segundo volume, o índice de sessões se perde a cada reinício: mesmo com
`.pipe/sessions.json` preservado, os ids apontariam para sessões que
`--list-sessions` não enxerga, degradando para sessão nova a cada ciclo
(funcional, mas sem retomada de raciocínio). Ver o risco RA-1 no documento de
arquitetura de US-03.

> Divergência consciente com a matriz de US-02/US-03: os requisitos
> simplificaram para apenas `~/.kiro/` com base em leitura da documentação
> oficial. A arquitetura mantém os dois volumes por seguir o comportamento
> **empiricamente verificado** registrado em CONTEXT.md. Se a validação de
> runtime (US-04) confirmar que só `~/.kiro/` basta, remove-se `kiro-local`
> sem impacto — é a decisão conservadora e reversível.

## Consequências

- A imagem continua descartável e reprodutível; todo estado e segredo vive fora
  dela (mantém ADR-06). A mesma imagem roda em qualquer host trocando só o
  `.env` e os volumes (RNF-04, padrão 12-factor).
- Trocar `pipe.yml`, `contexts/` ou qualquer credencial é "editar e
  `docker compose up`" — sem rebuild. Rebuild só é necessário ao mudar `src/`
  ou o `Dockerfile` (RF-05/AC-06).
- `restart`, `healthcheck`, tratamento de `SIGTERM` e política de operação
  autônoma **não** entram aqui: pertencem a US-04/US-05, que evoluem o mesmo
  arquivo.
- O compose depende de uma imagem já construída (`image: pipe:latest`,
  entregue por US-01); US-03 não constrói imagem.
- Volumes nomeados assumem o uid 1000 (`pipe`) do container (ADR-05); permissões
  são responsabilidade do runtime, validadas em US-04.
