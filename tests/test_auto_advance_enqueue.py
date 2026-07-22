"""Testes do _auto_advance: mover arquivos + atualizar snapshot + enfileirar change-up.

Regressão do bug em que o auto-advance movia os arquivos da coluna todo para a
próxima coluna mas NÃO atualizava o snapshot nem informava a ChangeQueue,
fazendo o keep_task refazer um auto-advance no-op a cada ciclo e nunca
selecionar tarefas prontas.
"""

import json
from pathlib import Path

import pytest

from src.__main__ import _auto_advance
from src.core.change_queue import ChangeQueue
from src.core.snapshot import Snapshot


@pytest.fixture
def task_board(tmp_path, monkeypatch):
    """Board 'task' com a issue #39 em backlog (3 arquivos) e snapshot."""
    monkeypatch.chdir(tmp_path)

    board_dir = Path(".pipe/boards/task")
    backlog = board_dir / "backlog"
    backlog.mkdir(parents=True)

    stem = "39-testes_automatizados"
    (backlog / f"{stem}-body.md").write_text("# Testes automatizados\n\nbody\n")
    (backlog / f"{stem}-history.md").write_text("hist\n")
    (backlog / f"{stem}-addcomment.md").write_text("")

    snapshot = {
        "board": {"backlog": "Backlog", "planning-poker": "Planning Poker"},
        "issues": [
            {
                "id": "39",
                "column": "backlog",
                "body_path": f".pipe/boards/task/backlog/{stem}-body.md",
                "body_mtime": "1.0",
                "updated_at": "2026-07-21T20:50:28Z",
                "status": "ok",
                "labels": [],
                "parent": None,
                "children": [],
                "blocked_by": [],
                "blocks": [],
                "archived": False,
                "state": "open",
            }
        ],
        "last_sync": None,
        "last_board_update": "2026-07-21T20:50:28Z",
    }
    (board_dir / "snapshot.json").write_text(json.dumps(snapshot, indent=2))

    return board_dir, stem


def test_auto_advance_moves_files(task_board):
    board_dir, stem = task_board
    snap = Snapshot("task").load()
    issue = snap.issue("39")

    _auto_advance("task", issue, "planning-poker", snap)

    planning = board_dir / "planning-poker"
    for suffix in ("-body.md", "-history.md", "-addcomment.md"):
        assert (planning / f"{stem}{suffix}").exists(), f"faltou mover {suffix}"
        assert not (board_dir / "backlog" / f"{stem}{suffix}").exists(), \
            f"arquivo {suffix} não deveria permanecer no backlog"


def test_auto_advance_updates_snapshot(task_board):
    board_dir, stem = task_board
    snap = Snapshot("task").load()
    issue = snap.issue("39")

    _auto_advance("task", issue, "planning-poker", snap)

    # Recarrega do disco para confirmar persistência
    reloaded = Snapshot("task").load().issue("39")
    assert reloaded["status"] == "change-up"
    assert reloaded["body_path"] == f".pipe/boards/task/planning-poker/{stem}-body.md"
    # A coluna permanece a de origem para o apply_change_up propagar o movimento
    assert reloaded["column"] == "backlog"


def test_auto_advance_enqueues_change_up(task_board):
    snap = Snapshot("task").load()
    issue = snap.issue("39")

    _auto_advance("task", issue, "planning-poker", snap)

    item = ChangeQueue().getNext()
    assert item is not None, "esperava um item enfileirado"
    assert item.id == "39"
    assert item.board == "task"
    assert item.event == "change-up"


def test_auto_advance_change_up_is_deduplicated(task_board):
    """Chamar auto-advance e depois detectar a mesma mudança não duplica a fila."""
    snap = Snapshot("task").load()
    issue = snap.issue("39")

    _auto_advance("task", issue, "planning-poker", snap)

    # Segunda tentativa de enfileirar o mesmo alvo deve deduplicar
    from src.core.board import ChangeItem, SyncEvent
    added = ChangeQueue().add(ChangeItem.of(SyncEvent.CHANGE_UP, id="39", board="task"))
    assert added is False

    queue = ChangeQueue()
    first = queue.getNext()
    queue.remove(first.uuid)
    assert queue.getNext() is None, "não deveria haver item duplicado"


# ── keep_task: sentinela AUTO_ADVANCED vs None vs task ────────────────────────

_CONFIG = {
    "boards": {
        "task": {
            "todo": "backlog",
            "columns": {
                "backlog": {"name": "Backlog", "change": {"advance": "planning-poker"}},
                "planning-poker": {
                    "name": "Planning Poker",
                    "agent": "tech-lead",
                    "change": {"advance": "casos-de-teste"},
                },
            },
        }
    }
}


def _add_planning_issue(board_dir, issue_id, stem, updated_at):
    """Adiciona uma issue elegível em planning-poker (arquivo + snapshot)."""
    planning = board_dir / "planning-poker"
    planning.mkdir(parents=True, exist_ok=True)
    body = planning / f"{stem}-body.md"
    body.write_text("# Task pronta\n\nsem comandos de bloqueio\n")
    (planning / f"{stem}-addcomment.md").write_text("")

    snap_file = board_dir / "snapshot.json"
    data = json.loads(snap_file.read_text())
    data["issues"].append({
        "id": issue_id,
        "column": "planning-poker",
        "body_path": str(body),
        "body_mtime": "1.0",
        "updated_at": updated_at,
        "status": "ok",
        "labels": [], "parent": None, "children": [],
        "blocked_by": [], "blocks": [], "archived": False, "state": "open",
    })
    snap_file.write_text(json.dumps(data, indent=2))


def test_keep_task_returns_auto_advanced_for_todo(task_board):
    """Só há issue no backlog (todo) → keep_task faz auto-advance e sinaliza AUTO_ADVANCED."""
    from src.__main__ import keep_task, AUTO_ADVANCED

    result = keep_task("task", _CONFIG)

    assert result is AUTO_ADVANCED


def test_keep_task_returns_none_when_empty(task_board):
    """Sem issues elegíveis nem no todo → None (loop avança de board)."""
    from src.__main__ import keep_task

    # Remove a única issue (39) do snapshot
    snap = Snapshot("task").load()
    snap.issues = []
    snap.save()

    assert keep_task("task", _CONFIG) is None


def test_keep_task_prefers_advanced_column_over_todo(task_board):
    """Com issue pronta em planning-poker e uma no backlog, retorna a de planning-poker.

    Valida a varredura coluna a coluna (última primeiro) + a distinção de retorno:
    NÃO deve fazer auto-advance do backlog enquanto houver tarefa pronta adiante.
    """
    from src.__main__ import keep_task, AUTO_ADVANCED

    board_dir, _ = task_board
    _add_planning_issue(board_dir, "40", "40-task_pronta", "2026-07-22T14:00:00Z")

    result = keep_task("task", _CONFIG)

    assert result is not AUTO_ADVANCED and result is not None
    assert result["issue"]["id"] == "40"
    assert result["col_id"] == "planning-poker"

