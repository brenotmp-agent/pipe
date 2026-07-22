"""Testes de integração do boot da esteira — função startup().

Cobre os casos especificados na issue #35:
  1. Preflight ok: sequência _setup_ssh → preflight completa sem erro; startup()
     retorna normalmente.
  2. Preflight falha (GH_TOKEN ausente): startup() levanta SystemExit(1); a
     saída contém '✗ GitHub'.
  3. Preflight falha (KIRO_API_KEY ausente): startup() levanta SystemExit(1); a
     saída contém '✗ kiro-cli'.
  4. _setup_ssh falha antes do preflight: se _setup_ssh() levantar exceção,
     o preflight não chega a ser chamado.

Todos os subprocessos, variáveis de ambiente e operações de filesystem fora
de tmp_path são mockados. O singleton Log é redirecionado para tmp_path, assim
como em test_preflight.py.

NOTA: Os testes que patcham `src.__main__.preflight` verificam o contrato da
implementação esperada (issue #35). Eles falharão com AttributeError até que o
desenvolvedor adicione `from src.core.preflight import preflight` em
`src/__main__.py` e insira a chamada em `startup()`. Isso é intencional — os
testes documentam o comportamento esperado e funcionam como critério de aceite
da implementação.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.__main__ as _main_module


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


# ─── Fixture de isolamento de filesystem ─────────────────────────────────────

@pytest.fixture(autouse=True)
def _chdir_tmp(tmp_path, monkeypatch):
    """Isola diretório de trabalho em tmp_path para não criar repo/ real."""
    monkeypatch.chdir(tmp_path)
    yield


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


def _fake_run_all_ok(args, **kwargs):
    """subprocess.run fake que retorna sucesso para gh e kiro-cli."""
    if args[0] == "gh":
        return _gh_auth_ok()
    if args[0] == "kiro-cli":
        return _kiro_whoami_ok()
    return _make_completed(0)


def _env_all_ok(tmp_path):
    """Retorna um dict de env com todas as variáveis obrigatórias definidas."""
    key_file = tmp_path / "id_ed25519"
    key_file.write_text(
        "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----\n"
    )
    return {
        "PIPE_SSH_KEY_FILE": str(key_file),
        "GH_TOKEN": "ghp_faketoken123",
        "KIRO_API_KEY": "kiro_fakekey456",
    }


def _minimal_config(tmp_path):
    """Configuração mínima válida para startup()."""
    return {
        "sleep": 10,
        "git": {
            "repo": {},   # sem repos → startup não tenta clonar
        },
        "boards": {
            "platform": "github",
            "task": {
                "columns": {},
            },
        },
        "log": {
            "dir": str(tmp_path / "logs"),
            "ttl": 10,
            "level": "INFO",
        },
        "agents": {},
    }


# ─── Caso 1: Preflight ok ─────────────────────────────────────────────────────

class TestStartupPreflightOk:
    """Caso 1: sequência _setup_ssh → preflight completa sem erro.

    startup() deve retornar None sem levantar nenhuma exceção.
    """

    def test_startup_returns_normally_when_preflight_ok(self, tmp_path, capsys):
        """Happy path com preflight real: todas as credenciais ok → startup() retorna."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)

        with patch.dict("os.environ", env, clear=False):
            with patch("src.core.preflight.subprocess.run", side_effect=_fake_run_all_ok):
                with patch("src.__main__._setup_ssh"):
                    with patch("src.core.context_generator.generate_context"):
                        with patch("src.__main__.QUEUE_FILE") as mock_qf:
                            mock_qf.exists.return_value = False
                            from src.__main__ import startup
                            result = startup(config)

        assert result is None

    def test_preflight_called_after_setup_ssh(self, tmp_path, capsys):
        """preflight() deve ser chamado após _setup_ssh() e antes de qualquer clone.

        Este teste verifica o contrato da implementação esperada (issue #35):
        `src/__main__.py` deve importar `preflight` de `src.core.preflight` e
        chamá-la em `startup()` após `_setup_ssh()`.
        """
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)
        call_order = []

        def fake_setup_ssh():
            call_order.append("_setup_ssh")

        def fake_preflight():
            call_order.append("preflight")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.__main__._setup_ssh", side_effect=fake_setup_ssh):
                with patch.object(
                    _main_module, "preflight",
                    create=True,
                    side_effect=fake_preflight,
                ):
                    with patch("src.core.context_generator.generate_context"):
                        with patch("src.__main__.QUEUE_FILE") as mock_qf:
                            mock_qf.exists.return_value = False
                            from src.__main__ import startup
                            startup(config)

        assert "_setup_ssh" in call_order, "startup() deve chamar _setup_ssh()"
        assert "preflight" in call_order, "startup() deve chamar preflight()"
        assert call_order.index("_setup_ssh") < call_order.index("preflight"), (
            "_setup_ssh() deve ser chamado antes de preflight()"
        )

    def test_startup_happy_path_preflight_is_called(self, tmp_path):
        """startup() deve invocar preflight() exatamente uma vez no happy path."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)

        with patch.dict("os.environ", env, clear=False):
            with patch("src.__main__._setup_ssh"):
                with patch.object(
                    _main_module, "preflight", create=True
                ) as mock_preflight:
                    with patch("src.core.context_generator.generate_context"):
                        with patch("src.__main__.QUEUE_FILE") as mock_qf:
                            mock_qf.exists.return_value = False
                            from src.__main__ import startup
                            startup(config)

        mock_preflight.assert_called_once()

    def test_startup_happy_path_no_system_exit(self, tmp_path, capsys):
        """startup() não deve levantar SystemExit quando preflight passa."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)

        try:
            with patch.dict("os.environ", env, clear=False):
                with patch("src.__main__._setup_ssh"):
                    with patch.object(_main_module, "preflight", create=True):
                        with patch("src.core.context_generator.generate_context"):
                            with patch("src.__main__.QUEUE_FILE") as mock_qf:
                                mock_qf.exists.return_value = False
                                from src.__main__ import startup
                                startup(config)
        except SystemExit as e:
            pytest.fail(
                f"startup() não deve levantar SystemExit no happy path. "
                f"Saiu com código: {e.code}"
            )


# ─── Caso 2: Preflight falha — GH_TOKEN ausente ───────────────────────────────

class TestStartupPreflightFailGHToken:
    """Caso 2: GH_TOKEN ausente → startup() levanta SystemExit(1).

    A saída deve conter '✗ GitHub'.
    """

    def test_startup_raises_system_exit_when_gh_token_missing(self, tmp_path):
        """GH_TOKEN ausente → SystemExit(1) durante startup()."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            raise AssertionError(f"gh não deve ser chamado sem GH_TOKEN: {args}")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                with patch("src.__main__._setup_ssh"):
                    with patch("src.core.context_generator.generate_context"):
                        with patch("src.__main__.QUEUE_FILE") as mock_qf:
                            mock_qf.exists.return_value = False
                            from src.__main__ import startup
                            with pytest.raises(SystemExit) as exc_info:
                                startup(config)

        assert exc_info.value.code == 1

    def test_startup_gh_token_missing_output_contains_fail_symbol(
        self, tmp_path, capsys
    ):
        """Saída deve conter '✗ GitHub' quando GH_TOKEN está ausente."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            return _make_completed(0)

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                with patch("src.__main__._setup_ssh"):
                    with patch("src.core.context_generator.generate_context"):
                        with patch("src.__main__.QUEUE_FILE") as mock_qf:
                            mock_qf.exists.return_value = False
                            from src.__main__ import startup
                            with pytest.raises(SystemExit):
                                startup(config)

        output = capsys.readouterr().out
        assert "✗ GitHub" in output, (
            f"Saída deve conter '✗ GitHub' quando GH_TOKEN ausente. Saída: {output!r}"
        )

    def test_startup_gh_token_missing_loop_not_reached(self, tmp_path):
        """Loop principal não deve ser alcançado quando preflight falha por GH_TOKEN."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)
        loop_entered = []

        def fake_run(args, **kwargs):
            if args[0] == "kiro-cli":
                return _kiro_whoami_ok()
            return _make_completed(0)

        def fake_board_full_sync(*args, **kwargs):
            loop_entered.append("board_full_sync")

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("GH_TOKEN", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                with patch("src.__main__._setup_ssh"):
                    with patch(
                        "src.__main__.board_full_sync",
                        side_effect=fake_board_full_sync,
                    ):
                        with patch("src.core.context_generator.generate_context"):
                            with patch("src.__main__.QUEUE_FILE") as mock_qf:
                                mock_qf.exists.return_value = False
                                from src.__main__ import startup
                                with pytest.raises(SystemExit):
                                    startup(config)

        assert len(loop_entered) == 0, (
            "board_full_sync não deve ser chamado quando preflight aborta o boot. "
            f"Chamadas: {loop_entered}"
        )


# ─── Caso 3: Preflight falha — KIRO_API_KEY ausente ──────────────────────────

class TestStartupPreflightFailKiroAPIKey:
    """Caso 3: KIRO_API_KEY ausente → startup() levanta SystemExit(1).

    A saída deve conter '✗ kiro-cli'.
    """

    def test_startup_raises_system_exit_when_kiro_api_key_missing(self, tmp_path):
        """KIRO_API_KEY ausente → SystemExit(1) durante startup()."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            raise AssertionError(
                f"kiro-cli não deve ser chamado sem KIRO_API_KEY: {args}"
            )

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                with patch("src.__main__._setup_ssh"):
                    with patch("src.core.context_generator.generate_context"):
                        with patch("src.__main__.QUEUE_FILE") as mock_qf:
                            mock_qf.exists.return_value = False
                            from src.__main__ import startup
                            with pytest.raises(SystemExit) as exc_info:
                                startup(config)

        assert exc_info.value.code == 1

    def test_startup_kiro_api_key_missing_output_contains_fail_symbol(
        self, tmp_path, capsys
    ):
        """Saída deve conter '✗ kiro-cli' quando KIRO_API_KEY está ausente."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            return _make_completed(0)

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                with patch("src.__main__._setup_ssh"):
                    with patch("src.core.context_generator.generate_context"):
                        with patch("src.__main__.QUEUE_FILE") as mock_qf:
                            mock_qf.exists.return_value = False
                            from src.__main__ import startup
                            with pytest.raises(SystemExit):
                                startup(config)

        output = capsys.readouterr().out
        assert "✗ kiro-cli" in output, (
            f"Saída deve conter '✗ kiro-cli' quando KIRO_API_KEY ausente. "
            f"Saída: {output!r}"
        )

    def test_startup_kiro_api_key_missing_exit_code_is_1(self, tmp_path):
        """SystemExit levantado pelo preflight deve ter código 1."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)

        def fake_run(args, **kwargs):
            if args[0] == "gh":
                return _gh_auth_ok()
            return _make_completed(0)

        with patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("KIRO_API_KEY", None)
            with patch("src.core.preflight.subprocess.run", side_effect=fake_run):
                with patch("src.__main__._setup_ssh"):
                    with patch("src.core.context_generator.generate_context"):
                        with patch("src.__main__.QUEUE_FILE") as mock_qf:
                            mock_qf.exists.return_value = False
                            from src.__main__ import startup
                            with pytest.raises(SystemExit) as exc_info:
                                startup(config)

        assert exc_info.value.code == 1, (
            f"SystemExit deve ter código 1. Código: {exc_info.value.code}"
        )


# ─── Caso 4: _setup_ssh falha antes do preflight ─────────────────────────────

class TestStartupSetupSSHFailsBeforePreflight:
    """Caso 4: _setup_ssh() levanta exceção → preflight não é chamado.

    Se a chave SSH não estiver acessível, _setup_ssh() deve falhar e o
    preflight não deve ser acionado.
    """

    def test_setup_ssh_failure_prevents_preflight_call(self, tmp_path):
        """_setup_ssh() levantando exceção → preflight() NÃO é chamado."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)
        preflight_called = []

        def fake_setup_ssh_error():
            raise FileNotFoundError("Arquivo de chave SSH não encontrado")

        def fake_preflight():
            preflight_called.append("called")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.__main__._setup_ssh", side_effect=fake_setup_ssh_error):
                with patch.object(
                    _main_module, "preflight",
                    create=True,
                    side_effect=fake_preflight,
                ):
                    with patch("src.core.context_generator.generate_context"):
                        with patch("src.__main__.QUEUE_FILE") as mock_qf:
                            mock_qf.exists.return_value = False
                            from src.__main__ import startup
                            with pytest.raises(FileNotFoundError):
                                startup(config)

        assert len(preflight_called) == 0, (
            "preflight() não deve ser chamado quando _setup_ssh() falha. "
            f"Chamadas: {preflight_called}"
        )

    def test_setup_ssh_failure_propagates_exception(self, tmp_path):
        """A exceção de _setup_ssh() deve propagar — não ser engolida por startup()."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)

        def fake_setup_ssh_error():
            raise FileNotFoundError("Chave SSH inválida: /caminho/inexistente")

        with patch.dict("os.environ", env, clear=False):
            with patch("src.__main__._setup_ssh", side_effect=fake_setup_ssh_error):
                with patch.object(_main_module, "preflight", create=True):
                    with patch("src.core.context_generator.generate_context"):
                        with patch("src.__main__.QUEUE_FILE") as mock_qf:
                            mock_qf.exists.return_value = False
                            from src.__main__ import startup
                            with pytest.raises(FileNotFoundError):
                                startup(config)

    def test_setup_ssh_exception_stops_before_clone(self, tmp_path):
        """Exceção em _setup_ssh() impede qualquer clone de repositório."""
        env = _env_all_ok(tmp_path)
        config = {
            **_minimal_config(tmp_path),
            "git": {
                "repo": {"main": "git@github.com:user/repo.git"},
            },
        }
        clone_called = []

        def fake_setup_ssh_error():
            raise OSError("Erro ao configurar SSH")

        def fake_subprocess_run(args, **kwargs):
            if args[0] == "git" and "clone" in args:
                clone_called.append(args)
            return _make_completed(0)

        with patch.dict("os.environ", env, clear=False):
            with patch("src.__main__._setup_ssh", side_effect=fake_setup_ssh_error):
                with patch("src.__main__.subprocess.run",
                           side_effect=fake_subprocess_run):
                    with patch.object(_main_module, "preflight", create=True):
                        with patch("src.core.context_generator.generate_context"):
                            with patch("src.__main__.QUEUE_FILE") as mock_qf:
                                mock_qf.exists.return_value = False
                                from src.__main__ import startup
                                with pytest.raises(OSError):
                                    startup(config)

        assert len(clone_called) == 0, (
            "git clone não deve ser executado quando _setup_ssh() falha. "
            f"Chamadas de clone: {clone_called}"
        )


# ─── Propagação de SystemExit — não engolido pelo loop ───────────────────────

class TestSystemExitPropagation:
    """Verifica que SystemExit(1) do preflight não é engolido pelo loop principal.

    O loop `while running` em main() usa `except Exception`. Como SystemExit
    herda de BaseException (não de Exception), ele deve propagar até o topo.
    """

    def test_system_exit_not_caught_by_except_exception(self, tmp_path):
        """SystemExit deve escapar de blocos `except Exception`."""
        raised_system_exit = False
        caught_by_exception_block = False

        def fake_startup_that_raises():
            raise SystemExit(1)

        try:
            fake_startup_that_raises()
        except Exception:
            caught_by_exception_block = True
        except SystemExit:
            raised_system_exit = True

        assert raised_system_exit, (
            "SystemExit deve ser capturado por 'except SystemExit', não por "
            "'except Exception'"
        )
        assert not caught_by_exception_block, (
            "SystemExit não deve ser engolido por 'except Exception'"
        )

    def test_system_exit_is_base_exception_not_exception(self):
        """Confirma que SystemExit herda de BaseException, não de Exception."""
        assert issubclass(SystemExit, BaseException), (
            "SystemExit deve ser subclasse de BaseException"
        )
        assert not issubclass(SystemExit, Exception), (
            "SystemExit NÃO deve ser subclasse de Exception"
        )

    def test_no_bare_except_in_main_loop(self):
        """O loop principal de main() não deve usar except BaseException nem bare except.

        Lê o código-fonte de __main__.py e verifica que não há bare except
        (except:) nem except BaseException que engoliriam o SystemExit do preflight.
        """
        main_source = Path(ROOT / "src" / "__main__.py").read_text(encoding="utf-8")
        lines = main_source.splitlines()

        bare_except_lines = [
            (i + 1, line.strip())
            for i, line in enumerate(lines)
            if line.strip() in ("except:", "except :") or
            line.strip().startswith("except BaseException")
        ]

        assert len(bare_except_lines) == 0, (
            "O loop principal não deve ter bare except nem except BaseException. "
            f"Encontrado em: {bare_except_lines}"
        )

    def test_preflight_system_exit_propagates_through_startup(self, tmp_path):
        """SystemExit levantado pelo preflight deve propagar através de startup()."""
        env = _env_all_ok(tmp_path)
        config = _minimal_config(tmp_path)

        def fake_preflight_raises():
            raise SystemExit(1)

        with patch.dict("os.environ", env, clear=False):
            with patch("src.__main__._setup_ssh"):
                with patch.object(
                    _main_module, "preflight",
                    create=True,
                    side_effect=fake_preflight_raises,
                ):
                    with patch("src.core.context_generator.generate_context"):
                        with patch("src.__main__.QUEUE_FILE") as mock_qf:
                            mock_qf.exists.return_value = False
                            from src.__main__ import startup
                            with pytest.raises(SystemExit) as exc_info:
                                startup(config)

        assert exc_info.value.code == 1, (
            "SystemExit propagado pelo preflight deve manter código 1"
        )
