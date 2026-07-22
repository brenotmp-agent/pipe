"""Preflight de credenciais — verificação agregada no arranque.

Verifica em ordem: SSH, gh CLI (GH_TOKEN), kiro-cli (KIRO_API_KEY).
Agrega todos os resultados e levanta SystemExit(1) com resumo completo
se qualquer credencial falhar. No caminho feliz, emite confirmação positiva
e retorna normalmente.
Nunca imprime valor de segredo — apenas identidade/método/caminho.
"""

import os
import re
import subprocess
from pathlib import Path

from src.core.log import log

_MODULE = "Preflight"

# ─── Mensagens do catálogo M-01 … M-07 ───────────────────────────────────────

_M01 = (
    "✗ SSH  variável PIPE_SSH_KEY_FILE não definida ou vazia\n"
    "    Causa: o clone via SSH no arranque precisa saber onde está a chave privada.\n"
    "    Ação:  defina PIPE_SSH_KEY_FILE no serviço apontando para o secret montado.\n"
    "           ex.: PIPE_SSH_KEY_FILE=/run/secrets/ssh_key\n"
    "    Onde:  monte a chave como Docker secret (ver docker-compose / runbook)."
)

_M02_TMPL = (
    "✗ SSH  arquivo de chave não encontrado em {path}\n"
    "    Causa: PIPE_SSH_KEY_FILE aponta para um caminho que não existe no container.\n"
    "    Ação:  confira se o secret/volume da chave está montado nesse caminho.\n"
    "    Onde:  seção 'secrets' do docker-compose (ver runbook)."
)

_M03 = (
    "✗ GitHub  variável GH_TOKEN não definida ou vazia\n"
    "    Causa: o acesso à API do GitHub requer um token pessoal de acesso.\n"
    "    Ação:  defina GH_TOKEN no serviço apontando para o secret montado.\n"
    "           ex.: GH_TOKEN=/run/secrets/gh_token  (ou via env secret)\n"
    "    Onde:  monte o token como Docker secret (ver docker-compose / runbook)."
)

_M04 = (
    "✗ GitHub  GH_TOKEN presente mas escopo 'project' faltante\n"
    "    Causa: o token não tem permissão para ler/gravar GitHub Projects V2.\n"
    "    Ação:  regenere o token incluindo o escopo 'project' (ou 'read:project').\n"
    "    Onde:  GitHub → Settings → Developer settings → Personal access tokens."
)

_M05 = (
    "✗ kiro-cli  variável KIRO_API_KEY não definida ou vazia\n"
    "    Causa: o kiro-cli requer uma API key para operar em modo headless.\n"
    "    Ação:  defina KIRO_API_KEY no serviço apontando para o secret montado.\n"
    "           ex.: KIRO_API_KEY=/run/secrets/kiro_api_key\n"
    "    Onde:  monte a key como Docker secret (ver docker-compose / runbook)."
)

_M06 = (
    "✗ kiro-cli  KIRO_API_KEY presente mas rejeitada pelo serviço\n"
    "    Causa: a key pode estar expirada, revogada ou incorreta.\n"
    "    Ação:  verifique e atualize KIRO_API_KEY com uma key válida.\n"
    "    Onde:  painel de API keys do serviço kiro-cli."
)

_M07 = (
    "✗ kiro-cli  binário 'kiro-cli' não encontrado no PATH\n"
    "    Causa: kiro-cli não está instalado ou não está acessível no PATH do container.\n"
    "    Ação:  reconstrua a imagem garantindo que kiro-cli seja instalado corretamente.\n"
    "    Onde:  Dockerfile — camada de instalação do kiro-cli."
)

_GH_NOT_FOUND = (
    "✗ GitHub  binário 'gh' não encontrado no PATH\n"
    "    Causa: gh CLI não está instalado ou não está acessível no PATH do container.\n"
    "    Ação:  reconstrua a imagem garantindo que gh seja instalado corretamente.\n"
    "    Onde:  Dockerfile — camada de instalação do gh CLI."
)

# ─── Verificações individuais ─────────────────────────────────────────────────


def _check_ssh() -> tuple[bool, str]:
    """Verifica PIPE_SSH_KEY_FILE (presença + existência do arquivo).

    Returns:
        (ok, detalhe) — detalhe é o caminho da chave em sucesso ou a mensagem
        de erro M-01/M-02 em falha.
    """
    key_path = os.environ.get("PIPE_SSH_KEY_FILE", "").strip()
    if not key_path:
        return False, _M01
    if not Path(key_path).expanduser().exists():
        return False, _M02_TMPL.format(path=key_path)
    return True, key_path


def _check_gh() -> tuple[bool, str]:
    """Verifica GH_TOKEN e executa `gh auth status`.

    Returns:
        (ok, detalhe) — detalhe é identidade extraída em sucesso ou mensagem
        de erro M-03/M-04/M-GH-NOT-FOUND em falha.
    """
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        return False, _M03

    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        return False, _GH_NOT_FOUND

    if result.returncode != 0:
        # Detectar ausência de escopo project na saída de erro
        combined = (result.stdout or "") + (result.stderr or "")
        if "project" in combined.lower() and "scope" in combined.lower():
            return False, _M04
        return False, _M03

    # Extrair identidade @user da saída
    combined = (result.stdout or "") + (result.stderr or "")
    match = re.search(r"account\s+(\S+)", combined)
    if match:
        identity = match.group(1)
    else:
        identity = "gh autenticado (via GH_TOKEN)"

    # Verificar escopo project (opcional mas recomendado — cena D)
    if "project" not in combined.lower():
        return False, _M04

    return True, identity


def _check_kiro() -> tuple[bool, str]:
    """Verifica KIRO_API_KEY e executa `kiro-cli whoami`.

    Returns:
        (ok, detalhe) — detalhe é método ativo em sucesso ou mensagem
        de erro M-05/M-06/M-07 em falha.
    """
    api_key = os.environ.get("KIRO_API_KEY", "").strip()
    if not api_key:
        return False, _M05

    try:
        result = subprocess.run(
            ["kiro-cli", "whoami"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        return False, _M07

    if result.returncode != 0:
        return False, _M06

    return True, "método ativo: API key (via KIRO_API_KEY)"


# ─── Função pública ───────────────────────────────────────────────────────────


def preflight() -> None:
    """Verifica as três credenciais no arranque (fail-fast agregado).

    Verifica em ordem: SSH, gh (GH_TOKEN), kiro-cli (KIRO_API_KEY).
    Agrega todos os resultados e levanta SystemExit(1) com resumo completo
    se qualquer credencial falhar. No caminho feliz, emite a confirmação
    positiva e retorna normalmente.
    Nunca imprime valor de segredo — apenas identidade/método/caminho.
    """
    ssh_ok, ssh_detail = _check_ssh()
    gh_ok, gh_detail = _check_gh()
    kiro_ok, kiro_detail = _check_kiro()

    # Emitir resultado de cada credencial
    if ssh_ok:
        log.info(_MODULE, f"✓ SSH  {ssh_detail}")
    else:
        log.error(_MODULE, ssh_detail)

    if gh_ok:
        log.info(_MODULE, f"✓ GitHub  {gh_detail}")
    else:
        log.error(_MODULE, gh_detail)

    if kiro_ok:
        log.info(_MODULE, f"✓ kiro-cli  {kiro_detail}")
    else:
        log.error(_MODULE, kiro_detail)

    # Resumo agregado
    ok_count = sum([ssh_ok, gh_ok, kiro_ok])

    if ok_count == 3:
        log.info(_MODULE, "3/3 credenciais OK — modo headless pronto")
        return

    log.error(_MODULE, f"{ok_count}/3 credenciais OK — arranque abortado")
    raise SystemExit(1)
