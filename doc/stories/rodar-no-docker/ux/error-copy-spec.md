# Catálogo de Copy — Mensagens de Erro de SSH

Status: aprovado
Owner: requisitos
Last updated: 2026-07-22

## Contexto

Documento canônico de copy para mensagens de erro relacionadas à chave SSH
exibidas por `src/core/config.py` (`_validate_env()`). As mensagens anteriores
orientavam o operador a fazer `export` no host, o que é inadequado quando a
esteira roda em container Docker. Este catálogo substitui essas mensagens por
versões Docker-aware.

## Convenção de template

Cada mensagem segue a estrutura:

```
✗ SSH  <descrição curta do erro>
    Causa:  <o que causou o erro>
    Ação:   <o que o operador deve fazer>
            <continuação da ação, se necessário>
    Onde:   <onde aplicar a correção>
```

- `✗ SSH` é o prefixo fixo (símbolo Unicode U+2717 + espaço + "SSH").
- As linhas de detalhe são indentadas com 4 espaços.
- `Causa:`, `Ação:` e `Onde:` são alinhados com dois espaços após o rótulo
  (padding para alinhar os valores).

## M-01 — Variável `PIPE_SSH_KEY_FILE` ausente ou vazia

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

## M-02 — Arquivo de chave SSH não encontrado

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

## O que NÃO deve aparecer nas mensagens

- Referências a `export <VAR>=~/.ssh/...` (host-centric, não Docker-aware).
- Sugestões de editar `.bashrc`, `.profile` ou qualquer arquivo de perfil do host.
- Caminhos absolutos fixos de máquina host (ex.: `/home/user/.ssh/id_ed25519`).

## Critérios de aceitação desta spec

- As strings exatas de M-01 e M-02 estão implementadas em `_validate_env()`.
- A expressão `export PIPE_SSH_KEY_FILE` não aparece em nenhuma mensagem de
  erro de SSH.
- O símbolo `✗ SSH` está presente em ambas as mensagens.
- A estrutura Causa / Ação / Onde está presente em ambas as mensagens.
