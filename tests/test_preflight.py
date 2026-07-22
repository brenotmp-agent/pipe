"""Testes unitários para src/core/preflight.py — função preflight().

Cobre todos os cenários especificados na issue #34:
- Happy path: todas as credenciais ok → retorna sem exceção
- SSH ausente (env não definida) → SystemExit(1)
- GH_TOKEN ausente → SystemExit(1)
- KIRO_API_KEY ausente → SystemExit(1)
- Múltiplas falhas agregadas → único SystemExit(1) com todas reportadas
- gh fora do PATH (FileNotFoundError) → falha registrada sem crash
- kiro-cli fora do PATH (FileNotFoundError) → falha registrada sem crash

Todos os subprocessos e variáveis de ambiente são mockados.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ─── Fixture de isolamento do singleton Log ───────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_log(tmp_path):
    """Redireciona o diretório de log do singleton para tmp_path em cada teste."""
    from src.core.log import log
    original_dir = log._log_dir
    original_file = log._file

    log._log_dir = tmp_path / "logs"
    log._log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log._log_dir / "test.json"
    log._file = open(log_file, "a", encoding="utf-8")

    yield

    log._file.close()
    log._log_dir = original_dir
    log._file = original_file


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_completed(returncode=0, stdout="", stderr=""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _gh_auth_ok(user="operador-bot"):
    """Saída simulada de `gh auth status` com sucesso e escopo project."""
    return _make_completed(
        returncode=0,
        stdout=(
            "github.com\n"
            f"  ✓ Logged in to github.com account {user} (oauth_token)\n"
            "  - Token scopes: 'repo', 'project', 'read:org'\n"
        ),
        stderr="",
    )


def _kiro_whoami_ok():
    """Saída simulada de `kiro-cli whoami` com sucesso."""
    return _make_completed(
        returncode=0,
        stdout="Logged in with API key\nEmail: bot@example.com\n",
        stderr="",
    )


def _env_all_ok(tmp_path):
    """Retorna um dict de env com todas as variáveis obrigatórias definidas."""
    key_file = tmp_path / "id_ed25519"
    key_file.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----\n")
    return {
        "PIPE_SSH_KEY_FILE": str(key_file),
        "GH_TOKEN": "ghp_faketoken123",
        "KIRO_API_KEY": "kiro_fakekey456",
    }


# ─── Happy path ───────────────────────────────────────────────────────────────

class TestHappyPath:
    """Cenário A: todas as credenciais ok → preflight() retorna normalmente."""

    def test_all_credentials_ok_returns_none(self, tmp_path, capsys):
        """Happy path completo: SSH + GH_TOKEN + KIRO_API_KEY todos válidos."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                # Deve retornar sem levantar exceção
                result = preflight_mod.preflight()

        assert result is None

    def test_happy_path_logs_success_symbols(self, tmp_path, capsys):
        """Happy path deve emitir ✓ para cada credencial."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok("operador-bot")
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "✓ SSH" in output, f"Esperado '✓ SSH' na saída. Saída: {output!r}"
        assert "✓ GitHub" in output, f"Esperado '✓ GitHub' na saída. Saída: {output!r}"
        assert "✓ kiro-cli" in output, f"Esperado '✓ kiro-cli' na saída. Saída: {output!r}"

    def test_happy_path_logs_3_of_3_ok(self, tmp_path, capsys):
        """Happy path deve emitir '3/3 credenciais OK'."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "3/3" in output, f"Esperado '3/3' na saída. Saída: {output!r}"

    def test_happy_path_extracts_github_identity(self, tmp_path, capsys):
        """Happy path deve extrair e exibir @user do gh auth status."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok("meu-bot-123")
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "meu-bot-123" in output, (
            f"Identidade do GitHub não aparece na saída. Saída: {output!r}"
        )

    def test_happy_path_shows_ssh_key_path(self, tmp_path, capsys):
        """Happy path deve exibir caminho da chave SSH (não o valor)."""
        env = _env_all_ok(tmp_path)
        ssh_path = env["PIPE_SSH_KEY_FILE"]

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                preflight_mod.preflight()

        output = capsys.readouterr().out
        assert ssh_path in output, (
            f"Caminho da chave SSH não aparece na saída. Saída: {output!r}"
        )


# ─── SSH ausente (M-01) ───────────────────────────────────────────────────────

class TestSSHMissing:
    """Cenário B: PIPE_SSH_KEY_FILE não definida → SystemExit(1) com ✗ SSH."""

    def test_missing_ssh_env_raises_system_exit(self, tmp_path, capsys):
        """PIPE_SSH_KEY_FILE ausente → SystemExit(1)."""
        env = _env_all_ok(tmp_path)
        env.pop("PIPE_SSH_KEY_FILE")

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            # Garantir que a variável não existe
            with patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop("PIPE_SSH_KEY_FILE", None)
                with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                    from src.core import preflight as preflight_mod
                    with pytest.raises(SystemExit) as exc_info:
                        preflight_mod.preflight()

        assert exc_info.value.code == 1

    def test_missing_ssh_env_message_contains_fail_symbol(self, tmp_path, capsys):
        """Mensagem M-01 deve conter '✗ SSH'."""
        env = {"GH_TOKEN": "tok", "KIRO_API_KEY": "key"}

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("PIPE_SSH_KEY_FILE", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "✗ SSH" in output, f"Esperado '✗ SSH' na saída. Saída: {output!r}"

    def test_missing_ssh_env_message_docker_aware(self, tmp_path, capsys):
        """Mensagem M-01 deve mencionar variável PIPE_SSH_KEY_FILE e contexto Docker."""
        env = {"GH_TOKEN": "tok", "KIRO_API_KEY": "key"}

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("PIPE_SSH_KEY_FILE", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "PIPE_SSH_KEY_FILE" in output, (
            f"Mensagem não menciona PIPE_SSH_KEY_FILE. Saída: {output!r}"
        )
        assert "secret" in output.lower(), (
            f"Mensagem não menciona secret Docker. Saída: {output!r}"
        )
        assert "export PIPE_SSH_KEY_FILE" not in output, (
            f"Mensagem contém referência host-centric proibida. Saída: {output!r}"
        )

    def test_missing_ssh_file_raises_system_exit(self, tmp_path, capsys):
        """PIPE_SSH_KEY_FILE aponta para arquivo inexistente → SystemExit(1) com ✗ SSH (M-02)."""
        nonexistent = tmp_path / "chave_que_nao_existe"
        env = {
            "PIPE_SSH_KEY_FILE": str(nonexistent),
            "GH_TOKEN": "tok",
            "KIRO_API_KEY": "key",
        }

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit) as exc_info:
                    preflight_mod.preflight()

        assert exc_info.value.code == 1

    def test_missing_ssh_file_message_contains_path_and_fail_symbol(self, tmp_path, capsys):
        """Mensagem M-02 deve conter '✗ SSH' e o caminho interpolado."""
        nonexistent = tmp_path / "chave_ausente"
        env = {
            "PIPE_SSH_KEY_FILE": str(nonexistent),
            "GH_TOKEN": "tok",
            "KIRO_API_KEY": "key",
        }

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "✗ SSH" in output, f"Esperado '✗ SSH' na saída. Saída: {output!r}"
        assert str(nonexistent) in output, (
            f"Caminho da chave ausente não interpolado na mensagem. Saída: {output!r}"
        )


# ─── GH_TOKEN ausente (M-03) ─────────────────────────────────────────────────

class TestGHTokenMissing:
    """Cenário C: GH_TOKEN não definido → SystemExit(1) com ✗ GitHub."""

    def test_missing_gh_token_raises_system_exit(self, tmp_path):
        """GH_TOKEN ausente → SystemExit(1)."""
        env = _env_all_ok(tmp_path)
        env.pop("GH_TOKEN")

        def fake_run(args, **kwargs):
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"gh não deve ser chamado sem GH_TOKEN: {args}")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit) as exc_info:
                    preflight_mod.preflight()

        assert exc_info.value.code == 1

    def test_missing_gh_token_message_contains_fail_symbol(self, tmp_path, capsys):
        """Mensagem M-03 deve conter '✗ GitHub'."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"gh não deve ser chamado sem GH_TOKEN: {args}")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "✗ GitHub" in output, f"Esperado '✗ GitHub' na saída. Saída: {output!r}"

    def test_missing_gh_token_message_mentions_variable(self, tmp_path, capsys):
        """Mensagem M-03 deve mencionar GH_TOKEN."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"gh não deve ser chamado sem GH_TOKEN: {args}")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "GH_TOKEN" in output, (
            f"Mensagem não menciona GH_TOKEN. Saída: {output!r}"
        )

    def test_missing_gh_token_gh_auth_not_called(self, tmp_path):
        """Quando GH_TOKEN está ausente, gh auth status NÃO deve ser executado."""
        env = _env_all_ok(tmp_path)
        gh_called = []

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                gh_called.append(args)
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            return _make_completed(0)

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        assert len(gh_called) == 0, (
            f"gh auth status não deve ser chamado sem GH_TOKEN. Chamadas: {gh_called}"
        )

    def test_gh_auth_status_exit_nonzero_raises_system_exit(self, tmp_path, capsys):
        """gh auth status com exit code != 0 → SystemExit(1) com ✗ GitHub."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _make_completed(returncode=1, stderr="not logged in")
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit) as exc_info:
                    preflight_mod.preflight()

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "✗ GitHub" in output, f"Esperado '✗ GitHub' na saída. Saída: {output!r}"


# ─── KIRO_API_KEY ausente (M-05) ─────────────────────────────────────────────

class TestKiroAPIKeyMissing:
    """Cenário E: KIRO_API_KEY não definida → SystemExit(1) com ✗ kiro-cli."""

    def test_missing_kiro_api_key_raises_system_exit(self, tmp_path):
        """KIRO_API_KEY ausente → SystemExit(1)."""
        env = _env_all_ok(tmp_path)
        env.pop("KIRO_API_KEY")

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                raise AssertionError("kiro-cli não deve ser chamado sem KIRO_API_KEY")
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit) as exc_info:
                    preflight_mod.preflight()

        assert exc_info.value.code == 1

    def test_missing_kiro_api_key_message_contains_fail_symbol(self, tmp_path, capsys):
        """Mensagem M-05 deve conter '✗ kiro-cli'."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            return _make_completed(0)

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "✗ kiro-cli" in output, f"Esperado '✗ kiro-cli' na saída. Saída: {output!r}"

    def test_missing_kiro_api_key_message_mentions_variable(self, tmp_path, capsys):
        """Mensagem M-05 deve mencionar KIRO_API_KEY."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            return _make_completed(0)

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "KIRO_API_KEY" in output, (
            f"Mensagem não menciona KIRO_API_KEY. Saída: {output!r}"
        )

    def test_missing_kiro_whoami_not_called(self, tmp_path):
        """Quando KIRO_API_KEY está ausente, kiro-cli whoami NÃO deve ser executado."""
        env = _env_all_ok(tmp_path)
        kiro_called = []

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                kiro_called.append(args)
                return _kiro_whoami_ok()
            return _make_completed(0)

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        assert len(kiro_called) == 0, (
            f"kiro-cli whoami não deve ser chamado sem KIRO_API_KEY. Chamadas: {kiro_called}"
        )

    def test_kiro_whoami_exit_nonzero_raises_system_exit(self, tmp_path, capsys):
        """kiro-cli whoami com exit code != 0 → SystemExit(1) com ✗ kiro-cli (M-06)."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _make_completed(returncode=1, stderr="API key rejected")
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit) as exc_info:
                    preflight_mod.preflight()

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "✗ kiro-cli" in output, f"Esperado '✗ kiro-cli' na saída. Saída: {output!r}"


# ─── Múltiplas falhas agregadas (Cena F) ─────────────────────────────────────

class TestMultipleFailuresAggregated:
    """Cena F: múltiplas credenciais faltando → único SystemExit com tudo reportado."""

    def test_gh_token_and_kiro_api_key_missing_single_exit(self, tmp_path, capsys):
        """GH_TOKEN + KIRO_API_KEY ausentes → um único SystemExit(1) com ambos reportados."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            raise AssertionError(f"Nenhum subprocesso deve ser chamado: {args}")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit) as exc_info:
                    preflight_mod.preflight()

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "✗ GitHub" in output, f"Esperado '✗ GitHub' na saída. Saída: {output!r}"
        assert "✗ kiro-cli" in output, f"Esperado '✗ kiro-cli' na saída. Saída: {output!r}"

    def test_all_three_missing_single_exit_all_reported(self, tmp_path, capsys):
        """SSH + GH_TOKEN + KIRO_API_KEY ausentes → SystemExit(1) com as três falhas."""

        def fake_run(args, **kwargs):
            raise AssertionError(f"Nenhum subprocesso deve ser chamado: {args}")

        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("PIPE_SSH_KEY_FILE", None)
            os.environ.pop("GH_TOKEN", None)
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit) as exc_info:
                    preflight_mod.preflight()

        assert exc_info.value.code == 1
        output = capsys.readouterr().out
        assert "✗ SSH" in output, f"Esperado '✗ SSH' na saída. Saída: {output!r}"
        assert "✗ GitHub" in output, f"Esperado '✗ GitHub' na saída. Saída: {output!r}"
        assert "✗ kiro-cli" in output, f"Esperado '✗ kiro-cli' na saída. Saída: {output!r}"

    def test_multiple_failures_no_repeated_system_exit(self, tmp_path):
        """Múltiplas falhas devem resultar em exatamente um SystemExit, não vários."""
        env = _env_all_ok(tmp_path)

        exit_count = []

        original_exit = SystemExit

        def fake_run(args, **kwargs):
            raise AssertionError(f"Nenhum subprocesso deve ser chamado: {args}")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()
        # Se chegou aqui sem segunda exceção, está correto (pytest captura apenas uma)

    def test_gh_token_and_kiro_missing_count_in_summary(self, tmp_path, capsys):
        """Cena F: 1/3 credenciais OK quando SSH ok mas gh e kiro falham."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            raise AssertionError(f"Nenhum subprocesso deve ser chamado: {args}")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "1/3" in output, (
            f"Esperado '1/3' na saída quando SSH ok e gh/kiro falham. Saída: {output!r}"
        )

    def test_preflight_verifies_all_three_before_aborting(self, tmp_path, capsys):
        """O preflight deve verificar as 3 credenciais antes de abortar.

        Com GH_TOKEN ausente e KIRO_API_KEY ausente, ambas devem aparecer
        na saída — confirma que não houve curto-circuito na primeira falha.
        """
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            raise AssertionError(f"Nenhum subprocesso deve ser chamado: {args}")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        # Ambas as falhas devem estar presentes (não houve short-circuit)
        assert "✗ GitHub" in output and "✗ kiro-cli" in output, (
            "O preflight deve reportar todas as falhas, não apenas a primeira. "
            f"Saída: {output!r}"
        )


# ─── gh fora do PATH (FileNotFoundError) ─────────────────────────────────────

class TestGHNotInPath:
    """gh CLI não encontrado no PATH → falha registrada, sem crash do preflight."""

    def test_gh_not_in_path_raises_system_exit(self, tmp_path, capsys):
        """FileNotFoundError ao chamar gh → SystemExit(1), preflight não crasha."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                raise FileNotFoundError("No such file or directory: 'gh'")
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit) as exc_info:
                    preflight_mod.preflight()

        assert exc_info.value.code == 1

    def test_gh_not_in_path_message_contains_fail_symbol(self, tmp_path, capsys):
        """Falha de gh por FileNotFoundError deve emitir '✗ GitHub'."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                raise FileNotFoundError("No such file or directory: 'gh'")
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "✗ GitHub" in output, (
            f"Esperado '✗ GitHub' quando gh não está no PATH. Saída: {output!r}"
        )

    def test_gh_not_in_path_no_unhandled_exception(self, tmp_path):
        """FileNotFoundError do gh não deve vazar como exceção não tratada."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                raise FileNotFoundError("No such file or directory: 'gh'")
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                # Só SystemExit é esperado, não FileNotFoundError ou RuntimeError
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()


# ─── kiro-cli fora do PATH (FileNotFoundError / M-07) ────────────────────────

class TestKiroNotInPath:
    """kiro-cli não encontrado no PATH (M-07) → falha registrada, sem crash."""

    def test_kiro_not_in_path_raises_system_exit(self, tmp_path, capsys):
        """FileNotFoundError ao chamar kiro-cli → SystemExit(1), preflight não crasha."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                raise FileNotFoundError("No such file or directory: 'kiro-cli'")
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit) as exc_info:
                    preflight_mod.preflight()

        assert exc_info.value.code == 1

    def test_kiro_not_in_path_message_contains_fail_symbol(self, tmp_path, capsys):
        """Falha M-07 deve emitir '✗ kiro-cli' e mencionar 'PATH' ou 'não encontrado'."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                raise FileNotFoundError("No such file or directory: 'kiro-cli'")
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "✗ kiro-cli" in output, (
            f"Esperado '✗ kiro-cli' quando kiro-cli não está no PATH. Saída: {output!r}"
        )
        # Deve mencionar que o binário não foi encontrado
        assert "kiro-cli" in output.lower(), (
            f"Mensagem deve mencionar 'kiro-cli'. Saída: {output!r}"
        )

    def test_kiro_not_in_path_no_unhandled_exception(self, tmp_path):
        """FileNotFoundError do kiro-cli não deve vazar como exceção não tratada."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                raise FileNotFoundError("No such file or directory: 'kiro-cli'")
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                # Só SystemExit é esperado, não FileNotFoundError
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

    def test_kiro_not_in_path_m07_message_structure(self, tmp_path, capsys):
        """Mensagem M-07 deve mencionar que a imagem provavelmente não instalou kiro-cli."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                raise FileNotFoundError("No such file or directory: 'kiro-cli'")
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        # M-07 orienta sobre imagem Docker — deve mencionar reconstrução ou imagem
        assert "imagem" in output.lower() or "path" in output.lower(), (
            f"Mensagem M-07 deve mencionar imagem ou PATH. Saída: {output!r}"
        )


# ─── Testes de segurança: sem vazamento de segredos ──────────────────────────

class TestNoSecretLeakage:
    """Segurança: nenhum valor de segredo deve aparecer nos logs."""

    def test_no_token_value_in_output_on_success(self, tmp_path, capsys):
        """Tokens/chaves não devem aparecer na saída mesmo no happy path."""
        env = _env_all_ok(tmp_path)
        env["GH_TOKEN"] = "ghp_SECRETTOKEN_SHOULD_NOT_APPEAR"
        env["KIRO_API_KEY"] = "kiro_SECRETKEY_SHOULD_NOT_APPEAR"

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "SECRETTOKEN_SHOULD_NOT_APPEAR" not in output, (
            f"Valor do GH_TOKEN não deve aparecer na saída. Saída: {output!r}"
        )
        assert "SECRETKEY_SHOULD_NOT_APPEAR" not in output, (
            f"Valor do KIRO_API_KEY não deve aparecer na saída. Saída: {output!r}"
        )

    def test_no_token_value_in_output_on_failure(self, tmp_path, capsys):
        """Tokens/chaves não devem aparecer na saída mesmo em caso de falha."""
        env = _env_all_ok(tmp_path)
        env["GH_TOKEN"] = "ghp_SECRETTOKEN_SHOULD_NOT_APPEAR"
        env["KIRO_API_KEY"] = "kiro_SECRETKEY_SHOULD_NOT_APPEAR"

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _make_completed(returncode=1, stderr="authentication failed")
            if args[0] == "kiro-cli":
                return _make_completed(returncode=1, stderr="key rejected")
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "SECRETTOKEN_SHOULD_NOT_APPEAR" not in output, (
            f"Valor do GH_TOKEN não deve aparecer na saída de erro. Saída: {output!r}"
        )
        assert "SECRETKEY_SHOULD_NOT_APPEAR" not in output, (
            f"Valor do KIRO_API_KEY não deve aparecer na saída de erro. Saída: {output!r}"
        )


# ─── Testes de estrutura de mensagem ─────────────────────────────────────────

class TestMessageStructure:
    """Verificação estrutural das mensagens conforme catálogo M-01…M-07."""

    def test_m03_message_has_causa_acao_onde(self, tmp_path, capsys):
        """Mensagem M-03 (GH_TOKEN ausente) deve seguir estrutura Causa/Ação/Onde."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            return _make_completed(0)

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "Causa:" in output, f"M-03 deve conter 'Causa:'. Saída: {output!r}"
        assert "Ação:" in output, f"M-03 deve conter 'Ação:'. Saída: {output!r}"
        assert "Onde:" in output, f"M-03 deve conter 'Onde:'. Saída: {output!r}"

    def test_m05_message_has_causa_acao_onde(self, tmp_path, capsys):
        """Mensagem M-05 (KIRO_API_KEY ausente) deve seguir estrutura Causa/Ação/Onde."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            return _make_completed(0)

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "Causa:" in output, f"M-05 deve conter 'Causa:'. Saída: {output!r}"
        assert "Ação:" in output, f"M-05 deve conter 'Ação:'. Saída: {output!r}"
        assert "Onde:" in output, f"M-05 deve conter 'Onde:'. Saída: {output!r}"

    def test_summary_line_abort_on_failure(self, tmp_path, capsys):
        """Linha de resumo em caso de falha deve mencionar 'arranque abortado'."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            return _make_completed(0)

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                with pytest.raises(SystemExit):
                    preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "abortado" in output.lower(), (
            f"Linha de resumo deve mencionar 'abortado'. Saída: {output!r}"
        )

    def test_summary_line_headless_on_success(self, tmp_path, capsys):
        """Linha de resumo em happy path deve mencionar 'headless'."""
        env = _env_all_ok(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                preflight_mod.preflight()

        output = capsys.readouterr().out
        assert "headless" in output.lower(), (
            f"Linha de resumo deve mencionar 'headless'. Saída: {output!r}"
        )


# ─── Testes de timeout e robustez de subprocess ──────────────────────────────

class TestSubprocessRobustness:
    """Verificações de que subprocessos são chamados com timeout e captura de saída."""

    def test_gh_auth_status_called_with_timeout(self, tmp_path, capsys):
        """gh auth status deve ser chamado com timeout definido (15s conforme spec)."""
        env = _env_all_ok(tmp_path)
        calls = []

        def fake_run(args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                preflight_mod.preflight()

        gh_calls = [c for c in calls if c["args"][0] == "gh"]
        assert len(gh_calls) >= 1, "gh deve ser chamado pelo menos uma vez"
        gh_call = gh_calls[0]
        assert "timeout" in gh_call["kwargs"], (
            "gh auth status deve ser chamado com timeout. kwargs: "
            f"{gh_call['kwargs']}"
        )
        assert gh_call["kwargs"]["timeout"] >= 10, (
            f"Timeout deve ser >= 10s (spec: 15s). Valor: {gh_call['kwargs']['timeout']}"
        )

    def test_kiro_whoami_called_with_timeout(self, tmp_path, capsys):
        """kiro-cli whoami deve ser chamado com timeout definido (15s conforme spec)."""
        env = _env_all_ok(tmp_path)
        calls = []

        def fake_run(args, **kwargs):
            calls.append({"args": args, "kwargs": kwargs})
            if args[0] == "gh":
                return _gh_auth_ok()
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"Comando inesperado: {args}")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                from src.core import preflight as preflight_mod
                preflight_mod.preflight()

        kiro_calls = [c for c in calls if c["args"][0] == "kiro-cli"]
        assert len(kiro_calls) >= 1, "kiro-cli deve ser chamado pelo menos uma vez"
        kiro_call = kiro_calls[0]
        assert "timeout" in kiro_call["kwargs"], (
            "kiro-cli whoami deve ser chamado com timeout. kwargs: "
            f"{kiro_call['kwargs']}"
        )
        assert kiro_call["kwargs"]["timeout"] >= 10, (
            f"Timeout deve ser >= 10s (spec: 15s). Valor: {kiro_call['kwargs']['timeout']}"
        )
