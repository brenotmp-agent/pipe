# Error Copy Spec — Preflight de Credenciais

Status: definido
Owner: UX/produto
Last updated: 2026-07-22
Contexto: US-02, ADR-04, `src/core/preflight.py`

Catálogo de mensagens de erro para o preflight de credenciais. Cada mensagem
tem um código M-NN, componentes (Causa / Ação / Onde) e o símbolo de status.

---

## Formato geral

```
[Preflight] ✗ <credencial>  <resumo>
             Causa:          <descrição técnica do problema>
             Ação:           <o que o operador deve fazer>
             Onde:           <onde configurar>
```

O `<resumo>` é exibido na mesma linha do `✗`. As linhas Causa/Ação/Onde são
emitidas como log separado com recuo.

---

## Catálogo

### M-01 — SSH: variável ausente

Gatilho: `PIPE_SSH_KEY_FILE` não definida ou vazia.

```
✗ SSH       PIPE_SSH_KEY_FILE não definido
 Causa:     variável de ambiente PIPE_SSH_KEY_FILE ausente ou vazia
 Ação:      defina PIPE_SSH_KEY_FILE com o caminho da chave SSH
 Onde:      docker-compose.yml → environment → PIPE_SSH_KEY_FILE
```

### M-02 — SSH: arquivo não encontrado

Gatilho: `PIPE_SSH_KEY_FILE` definida mas o arquivo não existe.

```
✗ SSH       arquivo de chave não encontrado: <caminho>
 Causa:     PIPE_SSH_KEY_FILE aponta para arquivo inexistente
 Ação:      monte a chave SSH como volume e aponte PIPE_SSH_KEY_FILE para o
            caminho correto dentro do container
 Onde:      docker-compose.yml → volumes (chave SSH) + environment
```

### M-03 — GitHub: GH_TOKEN ausente

Gatilho: `GH_TOKEN` não definido no ambiente.

```
✗ GitHub    GH_TOKEN não definido
 Causa:     variável de ambiente GH_TOKEN ausente
 Ação:      defina GH_TOKEN com um token válido do GitHub (classic token ou
            fine-grained com escopo 'project')
 Onde:      docker-compose.yml → environment → GH_TOKEN
```

### M-04 — GitHub: token sem escopo `project`

Gatilho: `gh auth status` retorna exit 0 mas a saída indica escopo `project`
faltando.

```
✗ GitHub    token sem escopo 'project'
 Causa:     GH_TOKEN definido mas sem permissão para GitHub Projects
 Ação:      gere um novo Personal Access Token com o escopo 'project'
            habilitado em https://github.com/settings/tokens
 Onde:      docker-compose.yml → environment → GH_TOKEN
```

### M-05 — kiro-cli: KIRO_API_KEY ausente

Gatilho: `KIRO_API_KEY` não definido no ambiente.

```
✗ kiro-cli  KIRO_API_KEY não definido
 Causa:     variável de ambiente KIRO_API_KEY ausente
 Ação:      defina KIRO_API_KEY com uma API key válida do Kiro
            (requer plano Pro/Pro+/Pro Max/Power)
 Onde:      docker-compose.yml → environment → KIRO_API_KEY
```

### M-06 — kiro-cli: API key rejeitada

Gatilho: `KIRO_API_KEY` definida mas `kiro-cli whoami` retorna exit ≠ 0.

```
✗ kiro-cli  API key inválida ou expirada
 Causa:     kiro-cli whoami retornou erro com KIRO_API_KEY definido
 Ação:      verifique se KIRO_API_KEY está correta e não expirou;
            gere uma nova em https://kiro.dev/settings/api-keys
 Onde:      docker-compose.yml → environment → KIRO_API_KEY
```

### M-07 — kiro-cli: binário não encontrado

Gatilho: `subprocess.run(["kiro-cli", ...])` lança `FileNotFoundError`.

```
✗ kiro-cli  binário não encontrado
 Causa:     kiro-cli não está instalado ou não está no PATH
 Ação:      instale o kiro-cli na imagem Docker (ver Dockerfile) ou
            verifique que o binário está no PATH do container
 Onde:      Dockerfile / imagem base
```

---

## Mensagem de sucesso por credencial

| Credencial | Formato |
|-----------|---------|
| SSH | `✓ SSH       chave carregada de <caminho> → ~/.ssh/id_pipe` |
| GitHub | `✓ GitHub    gh autenticado como @<user> (via GH_TOKEN)` |
| kiro-cli | `✓ kiro-cli  método ativo: API key (via KIRO_API_KEY)` |

## Mensagens de resumo final

| Resultado | Mensagem |
|-----------|----------|
| Todas OK | `3/3 credenciais OK — modo headless pronto` |
| Alguma falha | `N/3 credenciais OK — arranque abortado` |

---

## Notas

- **Nunca** imprimir o valor de `GH_TOKEN`, `KIRO_API_KEY` ou conteúdo da
  chave SSH. Apenas nome da variável, identidade (`@user`) ou método.
- As mensagens seguem os protótipos em `terminal-prototypes.md`.
- M-04 (escopo `project`) é opcional/recomendado: detectado se a saída do
  `gh auth status` indicar ausência explícita do escopo.
