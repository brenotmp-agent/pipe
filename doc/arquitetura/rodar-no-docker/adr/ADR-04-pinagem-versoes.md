# ADR-04 — Pinagem de versões e reprodutibilidade

Status: aceito
Data: 2026-07-07
Relacionado: RNF-05, D-02, R-2

## Contexto

RNF-05/D-02 exigem builds reprodutíveis: nenhuma dependência em "latest"
implícito. Os componentes têm mecanismos de pinagem diferentes.

## Decisão

Pinar cada dependência pelo mecanismo apropriado:

| Componente | Mecanismo de pinagem |
|------------|----------------------|
| Base | Tag `python:3.12-slim` (opcionalmente `@sha256:<digest>` para pinagem forte). |
| `pyyaml` | `pip install pyyaml==<versao>`. |
| `gh` (GitHub CLI) | Repositório APT oficial + `apt-get install gh=<versao>`. |
| `git`, `openssh-client`, `ca-certificates`, `curl`, `unzip` | Versões do Debian da base (pin explícito `pkg=<versao>` quando a estabilidade exigir). |
| `kiro-cli` | URL `/latest/` (sem versão) → `ARG KIRO_CLI_VERSION` documentando a versão validada + verificação `sha256sum` do zip (ver ADR-03, R-2). |
| Código da esteira (`src/`) | `ARG PIPE_REF` no `git clone` (ADR-07). `main` = "última versão" no momento do build; para reprodutibilidade estrita, apontar `PIPE_REF` para uma **tag ou SHA**. |

## Justificativa

- Pinar por `==`/`=<versao>` garante que dois builds em datas diferentes
  produzam o mesmo conteúdo funcional.
- Para o kiro-cli, como não há URL versionada, o **checksum** é a única âncora
  real de reprodutibilidade; o `ARG` de versão serve de registro auditável do
  que foi validado.
- Digest da imagem base (`@sha256:`) é opcional: recomendado para produção,
  dispensável em iteração inicial. Fica como recomendação, não obrigação, para
  não travar o desenvolvimento.

## Consequências

- Atualizar uma dependência é uma mudança explícita e versionada no Dockerfile
  (segue a regra de bump de versão do projeto — ver `CONTEXT.md`).
- O checksum do kiro-cli precisa ser atualizado deliberadamente quando a versão
  validada mudar; se o `/latest/` mudar sozinho, o build falha — comportamento
  desejado (detecta a mudança em vez de silenciá-la).
