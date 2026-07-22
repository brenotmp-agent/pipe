"""Testes de operação autônoma — US-05: Operar sem intervenção no runtime.

AC-02: Falta de credencial ou configuração inválida gera SystemExit(1) com
mensagem clara, sem travamento silencioso.

AC-05: O gate need_human NÃO interrompe o container. Issues marcadas com
/need_human (ou /blocked_by) são ignoradas por keep_task; o loop continua
sem exceção e sem SystemExit.

Cobre:
    - src/core/config.py :: _validate_env(), _validate_agents()
    - src/__main__.py    :: check_config() (wrapper com SystemExit)
    - src/__main__.py    :: _is_blocked(issue), keep_task(board_id, config)
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
        """Mensagem de fail-fast (M-01) deve ser Docker-aware e acionável.

        Verifica que a saída de terminal contém o símbolo canônico '✗ SSH',
        o nome da variável faltante e a instrução Docker correta (sem sugerir
        'export' no host), conforme catálogo de copy M-01 aprovado em
        doc/stories/rodar-no-docker/ux/error-copy-spec.md.
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

        # A mensagem deve conter o símbolo canônico de erro SSH (M-01)
        assert "✗ SSH" in output, (
            f"Mensagem não contém o símbolo '✗ SSH'. Saída: {output!r}"
        )

        # A mensagem deve orientar para contexto Docker (secret montado)
        assert "secret" in output.lower(), (
            f"Mensagem não menciona configuração de secret Docker. Saída: {output!r}"
        )

        # A mensagem NÃO deve sugerir export no host — inadequado para containers
        assert "export PIPE_SSH_KEY_FILE" not in output, (
            f"Mensagem ainda contém 'export PIPE_SSH_KEY_FILE' (linguagem de host, não Docker). "
            f"Saída: {output!r}"
        )

    # ── Teste 4b ──────────────────────────────────────────────────────────────

    def test_missing_key_file_message_is_docker_aware(self, tmp_path, monkeypatch, capsys):
        """Mensagem M-02 (arquivo não encontrado) deve ser Docker-aware.

        Verifica que a saída contém o símbolo '✗ SSH', o caminho interpolado
        e orientação sobre secret/volume Docker — sem referência a host.
        """
        monkeypatch.chdir(tmp_path)
        nonexistent = tmp_path / "chave_que_nao_existe"
        monkeypatch.setenv("PIPE_SSH_KEY_FILE", str(nonexistent))
        (tmp_path / "pipe.yml").write_text(_MINIMAL_PIPE_YML)

        from src.__main__ import check_config
        with pytest.raises(SystemExit):
            check_config()

        captured = capsys.readouterr()
        output = captured.out

        # A mensagem deve conter o símbolo canônico de erro SSH (M-02)
        assert "✗ SSH" in output, (
            f"Mensagem M-02 não contém o símbolo '✗ SSH'. Saída: {output!r}"
        )

        # O caminho deve aparecer na mensagem
        assert str(nonexistent) in output, (
            f"Mensagem M-02 não interpolou o caminho da chave. Saída: {output!r}"
        )

        # Deve orientar para secret/volume Docker
        assert "secret" in output.lower() or "volume" in output.lower(), (
            f"Mensagem M-02 não menciona secret/volume Docker. Saída: {output!r}"
        )

    # ── Teste 4c ──────────────────────────────────────────────────────────────

    def test_m01_message_structure_has_causa_acao_onde(self, tmp_path, monkeypatch, capsys):
        """Mensagem M-01 deve seguir estrutura completa: Causa / Ação / Onde.

        A estrutura padronizada facilita triagem operacional em ambiente Docker.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PIPE_SSH_KEY_FILE", raising=False)
        (tmp_path / "pipe.yml").write_text(_MINIMAL_PIPE_YML)

        from src.__main__ import check_config
        with pytest.raises(SystemExit):
            check_config()

        captured = capsys.readouterr()
        output = captured.out

        assert "Causa:" in output, (
            f"Mensagem M-01 não contém campo 'Causa:'. Saída: {output!r}"
        )
        assert "Ação:" in output, (
            f"Mensagem M-01 não contém campo 'Ação:'. Saída: {output!r}"
        )
        assert "Onde:" in output, (
            f"Mensagem M-01 não contém campo 'Onde:'. Saída: {output!r}"
        )

    # ── Teste 4d ──────────────────────────────────────────────────────────────

    def test_m02_message_structure_has_causa_acao_onde(self, tmp_path, monkeypatch, capsys):
        """Mensagem M-02 deve seguir estrutura completa: Causa / Ação / Onde.

        Mesmo padrão de M-01 para consistência de triagem operacional.
        """
        monkeypatch.chdir(tmp_path)
        nonexistent = tmp_path / "chave_ausente"
        monkeypatch.setenv("PIPE_SSH_KEY_FILE", str(nonexistent))
        (tmp_path / "pipe.yml").write_text(_MINIMAL_PIPE_YML)

        from src.__main__ import check_config
        with pytest.raises(SystemExit):
            check_config()

        captured = capsys.readouterr()
        output = captured.out

        assert "Causa:" in output, (
            f"Mensagem M-02 não contém campo 'Causa:'. Saída: {output!r}"
        )
        assert "Ação:" in output, (
            f"Mensagem M-02 não contém campo 'Ação:'. Saída: {output!r}"
        )
        assert "Onde:" in output, (
            f"Mensagem M-02 não contém campo 'Onde:'. Saída: {output!r}"
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


# ─── helpers de need_human ────────────────────────────────────────────────────

def _minimal_config(board_id: str = "task", col_id: str = "doing") -> dict:
    """Config mínima para keep_task funcionar sem dependências externas."""
    return {
        "boards": {
            board_id: {
                "name": "Task",
                "priority": 0,
                "flow": "feature",
                "columns": {
                    col_id: {
                        "name": "Doing",
                        "agent": "dev",
                        "gitevents": "no-branch",
                        "change": {"advance": "done"},
                    }
                },
            }
        },
        "git": {
            "repo": {"main": "git@github.com:x/y.git"},
            "flow": {"base": "main"},
        },
    }


def _write_body(directory: "Path", issue_id: str, slug: str, content: str) -> "Path":
    """Cria o arquivo -body.md de uma issue no diretório de coluna fornecido.

    O nome segue o padrão `<id>-<slug>-body.md`. Retorna o Path do arquivo.
    """
    body_file = directory / f"{issue_id}-{slug}-body.md"
    body_file.write_text(content, encoding="utf-8")
    return body_file


def _write_snapshot(tmp_path: "Path", board_id: str, issues: list) -> None:
    """Persiste um snapshot.json mínimo para o board indicado em tmp_path.

    Cada item de `issues` deve ser um dict com ao menos 'id', 'column' e
    'body_path'. Os campos opcionais seguem o formato do Snapshot real.
    """
    import json

    snap_dir = tmp_path / ".pipe" / "boards" / board_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "snapshot.json").write_text(
        json.dumps({"board": {}, "issues": issues, "last_sync": None}, indent=2),
        encoding="utf-8",
    )


# ─── TestNeedHumanGate ────────────────────────────────────────────────────────

class TestNeedHumanGate:
    """AC-05 da US-05: /need_human não interrompe o loop.

    O gate de bloqueio apenas pula a issue — nunca levanta exceção, nunca
    chama SystemExit. O loop principal continua para a próxima issue/board.
    """

    # ── Teste 1 ───────────────────────────────────────────────────────────────

    def test_need_human_issue_is_skipped_in_keep_task(self, tmp_path, monkeypatch):
        """Issue com /need_human no body deve ser ignorada; a seguinte é retornada.

        Cria dois arquivos de issue na coluna 'doing':
        - Issue #10: body contém /need_human — deve ser pulada.
        - Issue #11: body limpo — deve ser retornada por keep_task.

        O snapshot registra as duas issues com body_path apontando para os
        arquivos reais em disco (padrão de produção de _is_blocked).
        """
        monkeypatch.chdir(tmp_path)

        board_id = "task"
        col_id = "doing"
        col_dir = tmp_path / ".pipe" / "boards" / board_id / col_id
        col_dir.mkdir(parents=True, exist_ok=True)

        # Issue 10: bloqueada por need_human
        body_10 = _write_body(col_dir, "10", "issue-bloqueada",
                               "# Issue bloqueada\n\nTexto.\n\n@---\n/need_human\n")
        # Issue 11: sem bloqueio — elegível
        body_11 = _write_body(col_dir, "11", "issue-elegivel",
                               "# Issue elegível\n\nTexto normal.\n")

        _write_snapshot(tmp_path, board_id, [
            {"id": "10", "column": col_id, "status": "ok",
             "body_path": str(body_10), "labels": []},
            {"id": "11", "column": col_id, "status": "ok",
             "body_path": str(body_11), "labels": []},
        ])

        from src.__main__ import keep_task
        config = _minimal_config(board_id, col_id)

        task = keep_task(board_id, config)

        assert task is not None, "keep_task não deve retornar None quando há issue elegível"
        assert task["issue"]["id"] == "11", (
            f"A issue retornada deve ser a #11 (não bloqueada), não a #{task['issue']['id']}"
        )

    # ── Teste 2 ───────────────────────────────────────────────────────────────

    def test_need_human_does_not_stop_loop(self, tmp_path, monkeypatch):
        """Se todas as issues têm /need_human, keep_task retorna None sem exceção.

        Garante que o gate não levanta SystemExit, RuntimeError ou qualquer
        outra exceção — o loop principal pode continuar normalmente.
        """
        monkeypatch.chdir(tmp_path)

        board_id = "task"
        col_id = "doing"
        col_dir = tmp_path / ".pipe" / "boards" / board_id / col_id
        col_dir.mkdir(parents=True, exist_ok=True)

        # Três issues, todas com /need_human
        body_files = []
        for i, slug in enumerate(["alpha", "beta", "gamma"], start=20):
            bf = _write_body(col_dir, str(i), slug,
                             f"# Issue {slug}\n\n@---\n/need_human\n")
            body_files.append((str(i), bf))

        _write_snapshot(tmp_path, board_id, [
            {"id": issue_id, "column": col_id, "status": "ok",
             "body_path": str(bf), "labels": []}
            for issue_id, bf in body_files
        ])

        from src.__main__ import keep_task
        config = _minimal_config(board_id, col_id)

        # Não deve levantar exceção — apenas retornar None
        result = keep_task(board_id, config)

        assert result is None, (
            "keep_task deve retornar None quando todas as issues estão bloqueadas"
        )

    # ── Teste 3 ───────────────────────────────────────────────────────────────

    def test_blocked_by_also_skips_issue(self, tmp_path, monkeypatch):
        """/blocked_by ativa o mesmo gate que /need_human; issue deve ser pulada.

        Usa o mesmo mecanismo (_is_blocked) — verifica que blocked_by também
        faz keep_task retornar None quando é a única issue no board.
        """
        monkeypatch.chdir(tmp_path)

        board_id = "task"
        col_id = "doing"
        col_dir = tmp_path / ".pipe" / "boards" / board_id / col_id
        col_dir.mkdir(parents=True, exist_ok=True)

        body_file = _write_body(col_dir, "30", "issue-dependente",
                                "# Issue dependente\n\n@---\n/blocked_by #5\n")

        _write_snapshot(tmp_path, board_id, [
            {"id": "30", "column": col_id, "status": "ok",
             "body_path": str(body_file), "labels": []},
        ])

        from src.__main__ import keep_task
        config = _minimal_config(board_id, col_id)

        result = keep_task(board_id, config)

        assert result is None, (
            "Issue com /blocked_by deve ser ignorada; keep_task deve retornar None"
        )

    # ── Teste 4 ───────────────────────────────────────────────────────────────

    def test_is_blocked_detects_need_human_in_commands_block(self, tmp_path, monkeypatch):
        """_is_blocked detecta /need_human corretamente no bloco @---.

        Verifica dois casos:
        - Issue com /need_human no bloco → True
        - Issue sem qualquer comando de bloqueio → False

        ATENÇÃO: _is_blocked lê o arquivo via `body_path` (não o campo `body`
        do dict). O teste cria arquivos reais em disco, respeitando o contrato
        de produção.
        """
        monkeypatch.chdir(tmp_path)

        from src.__main__ import _is_blocked

        # Arquivo com /need_human no bloco @---
        body_blocked = tmp_path / "10-bloqueada-body.md"
        body_blocked.write_text(
            "# Título\n\nTexto normal.\n\n@---\n/need_human\n",
            encoding="utf-8",
        )

        # Arquivo sem nenhum comando de bloqueio
        body_clean = tmp_path / "11-limpa-body.md"
        body_clean.write_text(
            "# Título\n\nTexto normal.\n",
            encoding="utf-8",
        )

        issue_with_need_human = {"body_path": str(body_blocked)}
        issue_without = {"body_path": str(body_clean)}

        assert _is_blocked(issue_with_need_human) is True, (
            "_is_blocked deve retornar True para issue com /need_human"
        )
        assert _is_blocked(issue_without) is False, (
            "_is_blocked deve retornar False para issue sem /need_human ou /blocked_by"
        )

    # ── Teste 5 (complementar) ────────────────────────────────────────────────

    def test_is_blocked_returns_false_for_missing_body_file(self, tmp_path, monkeypatch):
        """_is_blocked retorna False quando body_path não existe (arquivo ausente).

        Situação possível em race condition entre sync e execução do agente.
        O gate deve ser conservador: sem arquivo = sem evidência de bloqueio.
        """
        monkeypatch.chdir(tmp_path)

        from src.__main__ import _is_blocked

        issue_no_file = {"body_path": str(tmp_path / "nao-existe-body.md")}
        assert _is_blocked(issue_no_file) is False

    # ── Teste 6 (complementar) ────────────────────────────────────────────────

    def test_need_human_and_clean_issues_mixed_returns_clean(self, tmp_path, monkeypatch):
        """Com issues mistas (bloqueadas + limpas), a primeira limpa é retornada.

        Garante ordenação e seleção correta: a issue mais antiga elegível vence,
        independentemente de quantas issues bloqueadas existam antes dela.
        """
        monkeypatch.chdir(tmp_path)

        board_id = "task"
        col_id = "doing"
        col_dir = tmp_path / ".pipe" / "boards" / board_id / col_id
        col_dir.mkdir(parents=True, exist_ok=True)

        # Issues #40, #41, #42 bloqueadas; #43 limpa
        snapshot_issues = []
        for i in range(40, 43):
            bf = _write_body(col_dir, str(i), f"bloqueada-{i}",
                             f"# Bloqueada {i}\n\n@---\n/need_human\n")
            snapshot_issues.append({
                "id": str(i), "column": col_id, "status": "ok",
                "body_path": str(bf), "labels": [],
                "created_at": f"2026-01-{i-39:02d}T00:00:00Z",
            })

        bf_clean = _write_body(col_dir, "43", "elegivel",
                               "# Elegível\n\nTexto.\n")
        snapshot_issues.append({
            "id": "43", "column": col_id, "status": "ok",
            "body_path": str(bf_clean), "labels": [],
            "created_at": "2026-01-05T00:00:00Z",
        })

        _write_snapshot(tmp_path, board_id, snapshot_issues)

        from src.__main__ import keep_task
        config = _minimal_config(board_id, col_id)

        task = keep_task(board_id, config)

        assert task is not None
        assert task["issue"]["id"] == "43"
