# ADR-07 — Aquisição do código via git clone (BuildKit secret)

Status: aprovado
Owner: arquitetura
Last updated: 2026-07-22
Autora: Rafael Martins — Analista de Requisitos

---

## Contexto

O código da esteira (`src/`) precisa estar presente na imagem para que
`python -m src` funcione. Há três mecanismos possíveis:

1. **COPY**: copiar `src/` do contexto de build (`COPY src/ /app/src/`).
2. **git clone durante o build**: usar `RUN git clone` com a chave SSH
   fornecida via `--mount=type=secret`.
3. **git clone em entrypoint**: clonar quando o container inicializa (não
   é uma imagem autocontida).

A abordagem de `COPY` foi usada nas versões anteriores do Dockerfile (tasks
#40 e #43). A task #45 introduz a abordagem de `git clone` com BuildKit secret.

## Decisão

Usar **git clone com BuildKit secret** durante o build para adquirir o código
da esteira:

```dockerfile
ARG PIPE_REPO=git@github.com:brenotmp-agent/pipe.git
ARG PIPE_REF=main

RUN --mount=type=secret,id=ssh_key,uid=1000 \
    GIT_SSH_COMMAND="ssh -i /run/secrets/ssh_key \
        -o StrictHostKeyChecking=accept-new \
        -o UserKnownHostsFile=/dev/null" \
    git clone --depth 1 --branch "$PIPE_REF" "$PIPE_REPO" /tmp/esteira \
    && cp -r /tmp/esteira/src /app/src \
    && rm -rf /tmp/esteira
```

O build é invocado com:

```bash
DOCKER_BUILDKIT=1 docker build \
  --secret id=ssh_key,src="$PIPE_SSH_KEY_FILE" \
  --build-arg PIPE_REF=main \
  -t esteira .
```

## Justificativa

- **Segurança (RNF-01)**: o `--mount=type=secret` injeta a chave SSH como
  arquivo efêmero em `/run/secrets/ssh_key`. Ela **nunca** é salva em nenhuma
  camada da imagem — não aparece em `docker history`, não vaza em registries.
  Com `COPY`, o contexto de build incluiria `src/` e qualquer arquivo
  esquecido no `.gitignore` que também esteja no diretório.
- **Imagem declarativa**: a imagem declara explicitamente qual repositório
  (`PIPE_REPO`) e qual ref (`PIPE_REF`) contém o código — rastreável.
- **Implantação de uma versão específica**: `--build-arg PIPE_REF=v1.2.3`
  permite construir imagens de versões específicas sem modificar o Dockerfile.
- **Contexto de build vazio**: com `.dockerignore: *`, o contexto enviado ao
  daemon Docker é mínimo — apenas o Dockerfile. Build mais rápido e sem risco
  de vazar arquivos locais.
- **Alternativa COPY rejeitada**: com `COPY`, o contexto de build precisa
  conter `src/` — qualquer arquivo no diretório que não esteja listado no
  `.dockerignore` pode entrar na imagem acidentalmente.

## Requisito de BuildKit

O `--mount=type=secret` requer BuildKit:
- Docker ≥ 23.0: BuildKit é o padrão. O build funciona sem configuração extra.
- Docker < 23.0: definir `DOCKER_BUILDKIT=1` antes do `docker build`.
- Docker Compose v2: usa BuildKit por padrão.

## Consequências

- O build requer conectividade SSH para `github.com` e acesso ao repositório
  `brenotmp-agent/pipe` (privado).
- A chave SSH é provida pelo operador via `--secret id=ssh_key,src=<caminho>`.
  O valor de `PIPE_SSH_KEY_FILE` do host é o caminho natural.
- `StrictHostKeyChecking=accept-new` aceita o fingerprint do github.com
  automaticamente na primeira conexão — sem interação humana.
- `UserKnownHostsFile=/dev/null` impede que o fingerprint seja persistido na
  imagem (não há camada `/root/.ssh/known_hosts` residual).
- O `.dockerignore` deve conter apenas `*` — o contexto de build é
  intencionalmente vazio (nenhum arquivo do host entra).
- O `prepare-docker.sh` torna-se desnecessário com esta abordagem.

## Migração em relação à abordagem COPY

| Aspecto | COPY (anterior) | git clone (esta ADR) |
|---------|-----------------|----------------------|
| Código na imagem | do diretório do host | do repositório git |
| Chave SSH no build | não necessária | necessária via --secret |
| .dockerignore | detalhado | apenas `*` |
| Rastreabilidade da versão | implícita (estado do diretório) | explícita (ref git) |
| Build offline | possível | não (requer acesso SSH ao GitHub) |
| Segurança da chave SSH | n/a | chave efêmera, nunca em camada |
