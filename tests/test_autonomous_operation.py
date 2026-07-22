"""Testes de operação autônoma — US-05: Operar sem intervenção no runtime.

AC-02: Falta de credencial ou configuração inválida gera SystemExit(1) com
mensagem clara, sem travamento silencioso.

Cobre:
    - src/core/config.py :: _validate_env(), _validate_agents()
    - src/__main__.py    :: check_config() (wrapper com SystemExit)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import patch

# ─── helpers ──────────────────────────────────────────────────────────────────

_MINIMAL_PIPE_YML = """\
sleep: 60
git:
  repo:
    main: git@github.com:x/y.git
  flow:
    base: main
agents: {}
boards:
  platform: github
"""

_PIPE_YML_WITH_AGENT = """\
sleep: 60
git:
  repo:
    main: git@github.com:x/y.git
  flow:
    base: main
agents:
  kiro-cli:
    dev:
      name: engineering
boards:
  platform: github
"""


def _write_valid_ssh_key(tmp_path: Path) -> Path:
    """Cria um arquivo de chave SSH simulado (conteúdo arbitrário)."""
    key_file = tmp_path / "id_test_ed25519"
    key_file.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----\n")
    return key_file


# ─── classe de testes ─────────────────────────────────────────────────────────

class TestFailFastCheckConfig:
    """Cobertura do fail-fast em check_config — AC-02 da US-05."""

    # Isola o log singleton: redireciona log_dir para tmp_path para evitar
    # efeitos colaterais entre testes (o Log é singleton global).
    @pytest.fixture(autouse=True)
    def _isolate_log(self, tmp_path):
        """Redireciona o diretório de log do singleton para tmp_path."""
        from src.core.log import log
        original_dir = log._log_dir
        original_file = log._file

        # Redireciona para diretório isolado
        log._log_dir = tmp_path / "logs"
        log._log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log._log_dir / "test.json"
        log._file = open(log_file, "a", encoding="utf-8")

        yield

        # Restaura estado original
        log._file.close()
        log._log_dir = original_dir
        log._file = original_file

    # ── Teste 1 ───────────────────────────────────────────────────────────────

    def test_missing_ssh_key_env_raises_system_exit(self, tmp_path, monkeypatch):
        """Ausência de PIPE_SSH_KEY_FILE gera SystemExit(1) com mensagem clara."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PIPE_SSH_KEY_FILE", raising=False)
        (tmp_path / "pipe.yml").write_text(_MINIMAL_PIPE_YML)

        from src.__main__ import check_config
        with pytest.raises(SystemExit) as exc_info:
            check_config()

        assert exc_info.value.code == 1

    # ── Teste 2 ───────────────────────────────────────────────────────────────

    def test_missing_ssh_key_file_raises_system_exit(self, tmp_path, monkeypatch):
        """PIPE_SSH_KEY_FILE apontando para arquivo inexistente gera SystemExit(1)."""
        monkeypatch.chdir(tmp_path)
        nonexistent = tmp_path / "chave_que_nao_existe"
        monkeypatch.setenv("PIPE_SSH_KEY_FILE", str(nonexistent))
        (tmp_path / "pipe.yml").write_text(_MINIMAL_PIPE_YML)

        from src.__main__ import check_config
        with pytest.raises(SystemExit) as exc_info:
            check_config()

        assert exc_info.value.code == 1

    # ── Teste 3 ───────────────────────────────────────────────────────────────

    def test_empty_agent_context_raises_system_exit(self, tmp_path, monkeypatch):
        """Contexto de agente vazio gera SystemExit(1) em check_config."""
        monkeypatch.chdir(tmp_path)

        # Chave SSH válida (arquivo existe)
        key_file = _write_valid_ssh_key(tmp_path)
        monkeypatch.setenv("PIPE_SSH_KEY_FILE", str(key_file))

        # pipe.yml com um agente definido
        (tmp_path / "pipe.yml").write_text(_PIPE_YML_WITH_AGENT)

        # Criar o arquivo de contexto explicitamente vazio
        ctx_dir = tmp_path / "contexts" / "kiro-cli"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "dev.md").write_text("   \n   ", encoding="utf-8")  # apenas espaços

        from src.__main__ import check_config
        with pytest.raises(SystemExit) as exc_info:
            check_config()

        assert exc_info.value.code == 1

    # ── Teste 4 ───────────────────────────────────────────────────────────────

    def test_error_message_is_actionable(self, tmp_path, monkeypatch, capsys):
        """Mensagem de fail-fast deve ser clara e acionável (não um traceback silencioso).

        Verifica que a saída de terminal contém o nome da variável de ambiente
        faltante e uma instrução de como corrigi-la, conforme definido em
        _validate_env() → ConfigError.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PIPE_SSH_KEY_FILE", raising=False)
        (tmp_path / "pipe.yml").write_text(_MINIMAL_PIPE_YML)

        from src.__main__ import check_config
        with pytest.raises(SystemExit):
            check_config()

        captured = capsys.readouterr()
        output = captured.out

        # A mensagem deve mencionar a variável de ambiente pelo nome
        assert "PIPE_SSH_KEY_FILE" in output, (
            f"Mensagem não menciona a variável faltante. Saída: {output!r}"
        )

        # A mensagem deve conter instrução de como corrigir (export ...)
        assert "export" in output.lower(), (
            f"Mensagem não contém instrução de correção. Saída: {output!r}"
        )

    # ── Testes complementares de robustez ─────────────────────────────────────

    def test_missing_pipe_yml_raises_system_exit(self, tmp_path, monkeypatch):
        """Ausência de pipe.yml gera SystemExit(1) — complementa cobertura do fail-fast."""
        monkeypatch.chdir(tmp_path)
        key_file = _write_valid_ssh_key(tmp_path)
        monkeypatch.setenv("PIPE_SSH_KEY_FILE", str(key_file))
        # Não cria pipe.yml

        from src.__main__ import check_config
        with pytest.raises(SystemExit) as exc_info:
            check_config()

        assert exc_info.value.code == 1

    def test_valid_config_does_not_raise(self, tmp_path, monkeypatch):
        """Configuração válida (SSH + pipe.yml + context preenchido) não levanta exceção."""
        monkeypatch.chdir(tmp_path)

        key_file = _write_valid_ssh_key(tmp_path)
        monkeypatch.setenv("PIPE_SSH_KEY_FILE", str(key_file))

        (tmp_path / "pipe.yml").write_text(_PIPE_YML_WITH_AGENT)

        # Contexto de agente preenchido
        ctx_dir = tmp_path / "contexts" / "kiro-cli"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / "dev.md").write_text("Você é um agente de engenharia.", encoding="utf-8")

        from src.__main__ import check_config
        # Deve retornar a config sem levantar exceção
        result = check_config()
        assert isinstance(result, dict)
        assert "sleep" in result
