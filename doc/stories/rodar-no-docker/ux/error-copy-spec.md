# Catálogo de Copy — Mensagens de autenticação (US-02)

Status: aprovado
Owner: requisitos
Last updated: 2026-07-22

## Contexto

Documento canônico de copy para as mensagens que o operador lê no `docker logs`
quando a autenticação falha ou é confirmada. A versão anterior (M-01/M-02
apenas, gerada na issue #33) cobria somente SSH; este documento estende o
catálogo para cobrir também `gh` (M-03/M-04) e `kiro-cli` (M-05/M-06/M-07),
necessários para a implementação do `preflight()` (issue #34).

As mensagens M-01 e M-02 são as mesmas aprovadas em `#33` — mantidas aqui para
o catálogo ser o único ponto de verdade.

## Convenção de template

Toda mensagem de credencial segue a mesma estrutura:

```
✗ <credencial>  <resumo do estado numa linha>
    Causa:  por que isto impede a esteira de operar
    Ação:   o que fazer, no contexto Docker (.env / secret / compose)
    Onde:   URL ou referência para obter/corrigir a credencial
    Nota:   (opcional) pré-requisito ou ressalva
```

Regras de redação:
- **Uma linha de resumo**, sem jargão interno; enxuta.
- **Ação sempre Docker-aware**: fala em `.env`/secret/compose, nunca `export`
  no host.
- **Sem valor de segredo** em nenhuma hipótese — referência por nome da
  variável / identidade, nunca por conteúdo.
- Tom **neutro e cooperativo**: descreve o estado e o próximo passo; não culpa.
- Símbolo `✗` (U+2717) em falhas; `✓` (U+2713) em confirmações.

---

## M-01 — SSH: variável `PIPE_SSH_KEY_FILE` ausente ou vazia

**Trigger:** `os.environ.get("PIPE_SSH_KEY_FILE", "").strip()` retorna string
vazia.

**Mensagem:**
```
✗ SSH  variável PIPE_SSH_KEY_FILE não definida ou vazia
    Causa:  o clone via SSH no arranque precisa saber onde está a chave privada.
    Ação:   defina PIPE_SSH_KEY_FILE no serviço apontando para o secret montado.
            ex.: PIPE_SSH_KEY_FILE=/run/secrets/ssh_key
    Onde:   monte a chave como Docker secret (ver docker-compose / runbook).
```

**Implementação Python** (em `_validate_env()`, `src/core/config.py`):

```python
raise ConfigError(
    "✗ SSH  variável PIPE_SSH_KEY_FILE não definida ou vazia\n"
    "    Causa:  o clone via SSH no arranque precisa saber onde está a chave privada.\n"
    "    Ação:   defina PIPE_SSH_KEY_FILE no serviço apontando para o secret montado.\n"
    "            ex.: PIPE_SSH_KEY_FILE=/run/secrets/ssh_key\n"
    "    Onde:   monte a chave como Docker secret (ver docker-compose / runbook)."
)
```

---

## M-02 — SSH: arquivo de chave não encontrado

**Trigger:** `Path(key_path).expanduser().exists()` retorna `False`.

**Mensagem** (onde `<caminho>` é o valor de `PIPE_SSH_KEY_FILE`):

```
✗ SSH  arquivo de chave não encontrado em <caminho>
    Causa:  PIPE_SSH_KEY_FILE aponta para um caminho que não existe no container.
    Ação:   confira se o secret/volume da chave está montado nesse caminho.
    Onde:   seção 'secrets' do docker-compose (ver runbook).
```

**Implementação Python** (em `_validate_env()`, `src/core/config.py`):

```python
raise ConfigError(
    f"✗ SSH  arquivo de chave não encontrado em {key_path}\n"
    "    Causa:  PIPE_SSH_KEY_FILE aponta para um caminho que não existe no container.\n"
    "    Ação:   confira se o secret/volume da chave está montado nesse caminho.\n"
    "    Onde:   seção 'secrets' do docker-compose (ver runbook)."
)
```

---

## M-03 — GitHub: `GH_TOKEN` ausente

**Trigger:** `os.environ.get("GH_TOKEN")` retorna `None` ou string vazia.

**Mensagem:**
```
✗ GitHub  GH_TOKEN não definido — gh não autenticado
    Causa:  toda operação de board (GitHub Projects) exige um token.
    Ação:   defina GH_TOKEN no .env — PAT com escopos: repo, project.
    Onde:   github.com/settings/tokens
```

**Nota de implementação:** quando `GH_TOKEN` está ausente, não executar
`gh auth status` (não há credencial para testar). Registrar falha com esta
mensagem diretamente.

---

## M-04 — GitHub: escopo `project` faltante

**Trigger:** `GH_TOKEN` está definido, `gh auth status` retorna exit 0, mas
análise da saída indica ausência do escopo `project` (linha `Token scopes:`
não contém `'project'`).

**Mensagem:**
```
✗ GitHub  autenticado como @<user>, mas sem escopo de Projects
    Causa:  o PAT não inclui o escopo 'project' (necessário para mover cards).
    Ação:   regenere o PAT com 'repo' + 'project' e atualize GH_TOKEN no .env.
    Onde:   github.com/settings/tokens
```

**Nota:** a detecção de escopo é marcada como **opcional/recomendada** (ADR-04).
Exige análise da saída de `gh auth status` — a linha `Token scopes:` lista os
escopos ativos. A implementação pode optar por não detectar e deixar a falha
para o lazy, mas a detecção antecipada é o cenário preferido (cena D do
protótipo).

**Referência de saída do `gh auth status`:**
```
github.com
  ✓ Logged in to github.com account <user> (...)
  - Token scopes: 'repo', 'project', ...
```

---

## M-05 — kiro-cli: `KIRO_API_KEY` ausente

**Trigger:** `os.environ.get("KIRO_API_KEY")` retorna `None` ou string vazia.

**Mensagem:**
```
✗ kiro-cli  KIRO_API_KEY não definida — agente não autenticaria
    Causa:  sem sessão de browser no container, a API key é o único método
            headless do kiro-cli.
    Ação:   defina KIRO_API_KEY no .env (requer plano Kiro Pro ou superior).
    Onde:   app.kiro.dev → Settings → API keys
    Nota:   em conta gerenciada por admin, a geração de key precisa estar
            habilitada na governança (R-3).
```

**Nota de implementação:** quando `KIRO_API_KEY` está ausente, não executar
`kiro-cli whoami` (não há credencial para testar). Registrar falha com esta
mensagem diretamente.

---

## M-06 — kiro-cli: key rejeitada

**Trigger:** `KIRO_API_KEY` está definida, `kiro-cli whoami` retorna exit
code não-zero.

**Mensagem:**
```
✗ kiro-cli  KIRO_API_KEY presente, mas rejeitada
    Causa:  key inválida, revogada ou expirada.
    Ação:   gere uma nova em app.kiro.dev e atualize KIRO_API_KEY no .env.
    Onde:   app.kiro.dev → Settings → API keys
```

---

## M-07 — kiro-cli: binário não encontrado

**Trigger:** `subprocess.run(["kiro-cli", "whoami"], ...)` levanta
`FileNotFoundError`.

**Mensagem:**
```
✗ kiro-cli  binário 'kiro-cli' não encontrado no PATH
    Causa:  a imagem provavelmente não instalou o kiro-cli (ver US-01).
    Ação:   reconstrua a imagem; valide com 'kiro-cli --version' no build.
```

**Nota:** esta mensagem não deve ser confundida com falha de autenticação.
A causa é a ausência do binário na imagem, não da credencial.

---

## Confirmação positiva (happy path)

Em caso de sucesso em todas as três credenciais, o preflight emite:

```
✓ SSH       chave carregada de <caminho> → ~/.ssh/id_pipe
✓ GitHub    gh autenticado como @<user> (via GH_TOKEN)
✓ kiro-cli  método ativo: API key (via KIRO_API_KEY)
3/3 credenciais OK — modo headless pronto
```

Onde `<user>` é extraído da saída de `gh auth status` (linha `account <user>`).

---

## O que NÃO deve aparecer nas mensagens

- Referências a `export <VAR>=~/.ssh/...` (host-centric, não Docker-aware).
- Sugestões de editar `.bashrc`, `.profile` ou qualquer arquivo de perfil do host.
- Caminhos absolutos fixos de máquina host (ex.: `/home/user/.ssh/id_ed25519`).
- Valores de tokens, chaves ou segredos — nem mascarados.

## Critério negativo de aceitação

- A expressão `export PIPE_SSH_KEY_FILE` não aparece em nenhuma mensagem de erro.
- O valor de `GH_TOKEN`, `KIRO_API_KEY` ou qualquer chave SSH nunca aparece nos
  logs — apenas nome da variável, identidade (`@user`) ou método.
