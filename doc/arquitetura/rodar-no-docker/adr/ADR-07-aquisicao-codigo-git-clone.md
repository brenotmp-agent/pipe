# ADR-07 — Aquisição do código via `git clone` no build (não `COPY`)

Status: aceito (revisão 2 da arquitetura)
Data: 2026-07-21
Relacionado: RF-01, RNF-01, RNF-05, D-01, R-2, R-3, ADR-02, ADR-04, ADR-06
Refina: US-01 AC-02 (que dizia "`src/` é copiado")

## Contexto

A primeira versão da arquitetura usava `COPY src/ /app/src/`. Isso obriga o
operador a ter o repositório da esteira **já clonado no host** antes do build —
exatamente o passo manual que a feature "Rodar no Docker" quer eliminar. A
validação da arquitetura (issue #16) pediu que **o próprio processo de
containerização baixe o código da esteira do GitHub**, sem download manual.

Fatos relevantes do ambiente:

- O repositório da esteira é **privado** e acessado por **SSH**
  (`git@github.com:brenotmp-agent/pipe.git`).
- O operador já possui uma chave SSH com acesso ao GitHub — é a mesma
  `PIPE_SSH_KEY_FILE` que a esteira usa em runtime (`_setup_ssh()`).
- `git` já está na imagem por ser dependência de runtime (ADR anterior),
  então não há custo adicional de ferramenta para clonar.

## Decisão

Obter o código por **`git clone` no build da imagem** (build-time), no lugar do
`COPY`. O clone:

- Usa `ARG PIPE_REPO` (default o repo da esteira) e `ARG PIPE_REF` (default
  `main`) para escolher a versão.
- Autentica com a chave SSH **montada como secret efêmero do BuildKit**
  (`--mount=type=secret,id=ssh_key`), reusando a `PIPE_SSH_KEY_FILE` do
  operador. O segredo **não** entra em nenhuma camada da imagem (RNF-01).
- Faz `git clone --depth 1 --branch "$PIPE_REF"` e copia apenas `src/` para
  `/app/src`, descartando o resto do repositório (mantém a imagem enxuta e o
  layout de `/app` idêntico ao anterior).

Comando de build:

```bash
DOCKER_BUILDKIT=1 docker build \
  --secret id=ssh_key,src="$PIPE_SSH_KEY_FILE" \
  --build-arg PIPE_REF=main \
  -t esteira .
```

## Justificativa

- **Elimina o passo manual** (objetivo da validação): o operador precisa só do
  `Dockerfile` e de acesso de leitura ao repo; nunca clona a esteira à mão.
- **Mantém a imagem imutável e reprodutível** (12-factor, RNF-05): um build
  corresponde a uma versão conhecida do código. `PIPE_REF=main` traz "a última
  versão" no momento do build; para reprodutibilidade estrita, aponta-se
  `PIPE_REF` para uma **tag ou SHA** (ver ADR-04). Isso preserva as garantias
  que um `COPY` de árvore versionada dava, sem exigir a árvore no host.
- **Segurança (RNF-01):** secret de BuildKit é montado apenas durante o `RUN`
  do clone e não persiste — diferente de `ARG`/`ENV` com token, que vazariam em
  `docker history`. Combina com o `.dockerignore` que agora nega todo o contexto.
- **Reuso de credencial existente:** a mesma chave SSH do runtime serve ao
  build; não introduz um novo tipo de segredo (ex.: PAT) só para o build.
- **Continua single-stage** (ADR-02): o clone é mais um passo linear; nada é
  compilado, não há artefato a separar.

## Alternativas consideradas

- **Clone em runtime (entrypoint baixa/atualiza o código a cada start).**
  Atende à leitura literal de "o container baixa a última versão" e reusa as
  credenciais de runtime. **Descartada como padrão** porque: (a) quebra a
  imutabilidade — a versão em execução vira não-determinística e um push ruim na
  `main` derruba todos os containers no próximo restart; (b) cria dependência de
  rede/GitHub no arranque; (c) duplicaria a lógica de setup de SSH **fora** da
  aplicação (bootstrap não pode chamar `_setup_ssh()`, que faz parte do próprio
  código ainda não baixado) — um code smell. Fica registrada como opção caso o
  produto priorize "auto-update no restart" sobre reprodutibilidade (candidata a
  US-04/US-06), e é o **ponto explícito de validação** desta revisão.
- **`COPY src/` (versão anterior).** Simples, mas exige o repositório no host —
  o problema que esta ADR resolve.
- **`--ssh default` (agente SSH do BuildKit) em vez de `--secret`.** Válido e
  suportado; preferimos `--secret` com arquivo por ser consistente com o modelo
  de "chave em arquivo" (`PIPE_SSH_KEY_FILE`) que a esteira já adota, sem exigir
  `ssh-agent` carregado no host de build. Fica como alternativa equivalente.
- **Distribuir imagem pré-buildada via registry.** Resolveria o download de
  outra forma, mas registry/CI está **fora do escopo** de US-01.

## Consequências

- Build passa a exigir **BuildKit** (`DOCKER_BUILDKIT=1`, padrão no Docker atual)
  e a flag `--secret`/`--build-arg` — documentar no runbook e na orquestração
  (US-03).
- Surge o risco **R-3**: o build depende de acesso de leitura ao repo privado
  (chave SSH válida no host de build). Mitigação: reuso da `PIPE_SSH_KEY_FILE`,
  `StrictHostKeyChecking=accept-new` e mensagem clara de falha do clone.
- Atualizar a esteira na imagem = rebuild com o `PIPE_REF` desejado (mudança
  explícita e auditável).
- `.dockerignore` passa a negar todo o contexto (`*`), reforçando RNF-01.
- US-01 AC-02 fica refinado: "`src/` presente na imagem" continua verdadeiro,
  mas a origem é o `git clone`, não o `COPY`.
