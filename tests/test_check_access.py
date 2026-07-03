"""Testes do gate de permissões (check_access) do GitHubBoardAdapter.

A esteira não deve iniciar quando o token não puder operar o repositório
configurado. check_access usa chamadas diretas ao gh (não passa por _gh, para
não confundir 403 de permissão com rate limit).
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.github_board import GitHubBoardAdapter
from src.core.board import BoardAccessError


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_adapter(repo="brenodpm/br.com.escrevas"):
    a = GitHubBoardAdapter()
    a._repo = repo
    return a


def _patch_run(monkeypatch, handler):
    """Substitui subprocess.run no módulo por um handler(args) -> _FakeCompleted."""
    def fake_run(args, capture_output=True, text=True, input=None):
        return handler(args)
    monkeypatch.setattr("src.adapters.github_board.subprocess.run", fake_run)


def test_sem_repo_configurado():
    a = GitHubBoardAdapter()
    a._repo = None
    with pytest.raises(BoardAccessError, match="não configurado"):
        a.check_access({})


def test_token_nao_autenticado(monkeypatch):
    a = _make_adapter()

    def handler(args):
        if args[:3] == ["gh", "api", "user"]:
            return _FakeCompleted(returncode=1, stderr="not logged in")
        raise AssertionError("não deveria consultar o repo sem auth")

    _patch_run(monkeypatch, handler)
    with pytest.raises(BoardAccessError, match="não autenticado"):
        a.check_access({})


def test_repo_inacessivel(monkeypatch):
    a = _make_adapter()

    def handler(args):
        if args[:3] == ["gh", "api", "user"]:
            return _FakeCompleted(stdout="brenotmp-agent\n")
        return _FakeCompleted(returncode=1, stderr="HTTP 404: Not Found")

    _patch_run(monkeypatch, handler)
    with pytest.raises(BoardAccessError, match="Sem acesso ao repositório"):
        a.check_access({})


def test_sem_permissao_de_escrita(monkeypatch):
    a = _make_adapter()

    def handler(args):
        if args[:3] == ["gh", "api", "user"]:
            return _FakeCompleted(stdout="brenotmp-agent\n")
        return _FakeCompleted(
            stdout='{"permissions":{"admin":false,"maintain":false,'
                   '"push":false,"triage":true,"pull":true}}'
        )

    _patch_run(monkeypatch, handler)
    with pytest.raises(BoardAccessError, match="permissão de escrita"):
        a.check_access({})


def test_com_permissao_push_ok(monkeypatch):
    a = _make_adapter()

    def handler(args):
        if args[:3] == ["gh", "api", "user"]:
            return _FakeCompleted(stdout="brenodpm\n")
        return _FakeCompleted(
            stdout='{"permissions":{"admin":false,"maintain":false,'
                   '"push":true,"triage":true,"pull":true}}'
        )

    _patch_run(monkeypatch, handler)
    # Não deve levantar.
    assert a.check_access({}) is None


def test_com_permissao_admin_ok(monkeypatch):
    a = _make_adapter()

    def handler(args):
        if args[:3] == ["gh", "api", "user"]:
            return _FakeCompleted(stdout="brenodpm\n")
        return _FakeCompleted(stdout='{"permissions":{"admin":true}}')

    _patch_run(monkeypatch, handler)
    assert a.check_access({}) is None


def test_resposta_json_invalida(monkeypatch):
    a = _make_adapter()

    def handler(args):
        if args[:3] == ["gh", "api", "user"]:
            return _FakeCompleted(stdout="brenodpm\n")
        return _FakeCompleted(stdout="not json")

    _patch_run(monkeypatch, handler)
    with pytest.raises(BoardAccessError, match="Resposta inválida"):
        a.check_access({})
