# Protótipos de terminal — Saída do arranque (US-02)

Status: aprovado
Owner: ux
Story: #17 (US-02)
Last updated: 2026-07-22

Estes são os "wireframes" da story: como o operador percebe a autenticação num
produto sem tela. Cada cena é um estado que ele pode encontrar no `docker logs`.
Prefixos seguem o formato de log atual (`[Componente] mensagem`), visto em
`src/__main__.py` e `src/core/log.py`.

Convenções de fidelidade:
- `✓ / ✗` marcam resultado por credencial (sem cor obrigatória; degrada para
  texto puro — o adapter já roda com `KIRO_LOG_NO_COLOR=1`).
- Valores de segredo **nunca** aparecem: mostra-se origem/identidade, nunca o
  valor. Ex.: usuário do `gh`, método do kiro-cli, caminho da chave — jamais o
  token ou a chave privada.

---

## Cena A — Happy path com preflight (estado-alvo)

Consolida as verificações de credenciais num resumo único no arranque.

```
[Config]    Validando pipe.yml
[Config]    pipe.yml válido
[Startup]   Verificando repositórios
[Preflight] Verificando credenciais das dependências externas...
[Preflight] ✓ SSH       chave carregada de /run/secrets/ssh_key → ~/.ssh/id_pipe
[Preflight] ✓ GitHub    gh autenticado como @operador-bot (via GH_TOKEN)
[Preflight] ✓ kiro-cli  método ativo: API key (via KIRO_API_KEY)
[Preflight] 3/3 credenciais OK — modo headless pronto
[Startup]   Clonando main
[Loop]      Ciclo iniciado
```

O operador confirma em 3 linhas que o headless autenticou de fato, vendo a
**identidade** de cada credencial sem nenhum valor sensível.

---

## Cena B — Falta a chave SSH (comportamento existente, ajuste de copy)

`check_config()` → `_validate_env()` já falha rápido antes do preflight.

```
[Config]    Validando pipe.yml
[Config]    ERRO ✗ SSH  variável PIPE_SSH_KEY_FILE não definida ou vazia
                    Causa:  o clone via SSH no arranque precisa saber onde está a chave privada.
                    Ação:   defina PIPE_SSH_KEY_FILE no serviço apontando para o secret montado.
                            ex.: PIPE_SSH_KEY_FILE=/run/secrets/ssh_key
                    Onde:   monte a chave como Docker secret (ver docker-compose / runbook).
```
```
(container encerra com exit code 1)
```

---

## Cena C — Falta GH_TOKEN

**Atual (lazy) — pior ponto da jornada:**
```
[Config]    pipe.yml válido
[Startup]   Clonando main
[Loop]      Ciclo iniciado
[Board]     Sincronizando backlog
... (dezenas de linhas depois) ...
[Board]     ERRO gh: exit status 1
```

**Com preflight (estado-alvo):**
```
[Preflight] ✓ SSH       chave carregada de /run/secrets/ssh_key → ~/.ssh/id_pipe
[Preflight] ✗ GitHub    GH_TOKEN não definido — gh não autenticado
                Causa:  toda operação de board (GitHub Projects) exige um token.
                Ação:   defina GH_TOKEN no .env — PAT com escopos: repo, project.
                Onde:   github.com/settings/tokens
[Preflight] 2/3 credenciais OK — arranque abortado
```
```
(container encerra com exit code 1)
```

---

## Cena D — GH_TOKEN presente mas com escopo insuficiente

Falha previsível nº 1 da jornada. Causa diferente de "ausente" — merece mensagem
própria. Detecção via análise da saída de `gh auth status` (linha `Token scopes:`).

```
[Preflight] ✓ SSH       chave carregada
[Preflight] ✗ GitHub    autenticado como @operador-bot, mas sem escopo de Projects
                Causa:  o PAT não inclui o escopo 'project' (necessário para mover cards).
                Ação:   regenere o PAT com 'repo' + 'project' e atualize GH_TOKEN no .env.
                Onde:   github.com/settings/tokens
[Preflight] 2/3 credenciais OK — arranque abortado
```
```
(container encerra com exit code 1)
```

**Nota:** detecção de escopo é opcional/recomendada (ADR-04). Ver M-04 no
catálogo `error-copy-spec.md`.

---

## Cena E — Falta KIRO_API_KEY

```
[Preflight] ✓ SSH       chave carregada
[Preflight] ✓ GitHub    gh autenticado como @operador-bot (via GH_TOKEN)
[Preflight] ✗ kiro-cli  KIRO_API_KEY não definida — agente não autenticaria
                Causa:  sem sessão de browser no container, a API key é o único método
                        headless do kiro-cli.
                Ação:   defina KIRO_API_KEY no .env (requer plano Kiro Pro ou superior).
                Onde:   app.kiro.dev → Settings → API keys
                Nota:   em conta gerenciada por admin, a geração de key precisa estar
                        habilitada na governança (R-3).
[Preflight] 2/3 credenciais OK — arranque abortado
```
```
(container encerra com exit code 1)
```

Variante — key presente mas rejeitada (`kiro-cli whoami` falha com exit non-zero):
```
[Preflight] ✗ kiro-cli  KIRO_API_KEY presente, mas rejeitada
                Causa:  key inválida, revogada ou expirada.
                Ação:   gere uma nova em app.kiro.dev e atualize KIRO_API_KEY no .env.
```

---

## Cena F — Múltiplas credenciais faltando (resumo agregado)

O preflight verifica tudo e reporta **todas** as pendências de uma vez — evita o
ciclo frustrante de corrigir uma, subir, descobrir a próxima.

```
[Preflight] ✓ SSH       chave carregada
[Preflight] ✗ GitHub    GH_TOKEN não definido — gh não autenticado
                Causa:  toda operação de board (GitHub Projects) exige um token.
                Ação:   defina GH_TOKEN no .env — PAT com escopos: repo, project.
                Onde:   github.com/settings/tokens
[Preflight] ✗ kiro-cli  KIRO_API_KEY não definida — agente não autenticaria
                Causa:  sem sessão de browser no container, a API key é o único método
                        headless do kiro-cli.
                Ação:   defina KIRO_API_KEY no .env (requer plano Kiro Pro ou superior).
                Onde:   app.kiro.dev → Settings → API keys
[Preflight] 1/3 credenciais OK — arranque abortado
```
```
(container encerra com exit code 1)
```

---

## Cena G — kiro-cli não encontrado no PATH

Não deveria ocorrer se US-01 (imagem) estiver correta, mas o preflight trata.

```
[Preflight] ✗ kiro-cli  binário 'kiro-cli' não encontrado no PATH
                Causa:  a imagem provavelmente não instalou o kiro-cli (ver US-01).
                Ação:   reconstrua a imagem; valide com 'kiro-cli --version' no build.
[Preflight] 2/3 credenciais OK — arranque abortado
```

---

## Notas de implementação

### Subcomando de status do kiro-cli

`kiro-cli whoami` é o subcomando correto e confirmado na versão instalada:

```
$ kiro-cli whoami
Logged in with GitHub
Email: <email>
```

Em modo headless com `KIRO_API_KEY`, a saída indicará o método API key.
Exit code 0 = autenticado; exit code não-zero = falha.

**Atenção:** em ambiente de desenvolvimento com sessão de browser ativa,
`kiro-cli whoami` pode retornar exit 0 mesmo com `KIRO_API_KEY` inválida (a
sessão de browser tem precedência). Em container Docker, onde não há sessão de
browser, a `KIRO_API_KEY` é o único método — um valor inválido resultará em
exit code não-zero.

### Extração de identidade de `gh auth status`

A saída de `gh auth status` contém a linha:
```
  ✓ Logged in to github.com account <user> (...)
```

Para extrair `<user>`: regex `account\s+(\S+)` na saída (stdout ou stderr
combinados), capturando o grupo 1.

### Sequência de verificação no preflight

O preflight deve verificar as três credenciais em ordem (SSH → gh → kiro-cli),
mas **não** interromper na primeira falha — verificar todas e agregar resultados.
Só após verificar as três é que decide se emite `SystemExit(1)`.

### Relação com `_validate_env()`

`_validate_env()` em `check_config()` continua sendo a primeira barreira para
SSH. O preflight replica a verificação SSH de forma autônoma (não chama
`_validate_env()` diretamente) para manter o módulo isolado e testável.
