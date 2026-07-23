"""Testes dos 3 remédios de bloqueio (blocked_by/blocks).

Remédio 1: ao arquivar uma issue, todos os bloqueios são removidos antes de
           arquivar; as issues reciprocamente vinculadas recebem fullsync.
Remédio 2: ao deletar (up/down) uma issue, as issues apontadas por ela têm o
           bloqueio removido no board e recebem fullsync.
Remédio 3: na inicialização, as mudanças detectadas são fullsync.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core import sync
from src.core.board import Board, BoardPort, ChangeItem, Issue, SyncEvent
from src.core.change_queue import ChangeQueue
from src.core.snapshot import Snapshot


@pytest.fixture(autouse=True)
def _chdir_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield


class FakePort(BoardPort):
    def __init__(self):
        self.calls = []

    def connect(self, config): pass
    def sync_boards(self, boards): pass
    def list_issues(self, board_id): return []
    def list_issues_since(self, board_id, since): return []
    def get_issue(self, board_id, issue_id, fullsync=False):
        return Issue(id=issue_id, title="", body="", column="")
    def create_issue(self, board_id, title, body, column):
        return Issue(id="1", title=title, body=body, column=column)
    def move_issue(self, board_id, issue_id, column, from_column=None): pass
    def update_issue(self, board_id, issue_id, title=None, body=None): pass
    def add_comment(self, board_id, issue_id, comment): pass
    def list_comments(self, board_id, issue_id): return []
    def close_issue(self, board_id, issue_id):
        self.calls.append(("close", issue_id))
    def reopen_issue(self, board_id, issue_id):
        self.calls.append(("reopen", issue_id))
    def set_labels(self, board_id, issue_id, labels):
        self.calls.append(("set_labels", issue_id, sorted(labels)))
    def add_label(self, board_id, issue_id, label): pass
    def remove_label(self, board_id, issue_id, label): pass
    def set_parent(self, board_id, issue_id, parent_id, known_current=None): pass
    def set_children(self, board_id, issue_id, children_ids, known_current=None): pass
    def set_blocked_by(self, board_id, issue_id, blocker_ids, known_current=None):
        self.calls.append(("set_blocked_by", issue_id, sorted(blocker_ids)))
    def set_blocks(self, board_id, issue_id, blocked_ids, known_current=None):
        self.calls.append(("set_blocks", issue_id, sorted(blocked_ids)))
    def archive_issue(self, board_id, issue_id):
        self.calls.append(("archive", issue_id))
    def unarchive_issue(self, board_id, issue_id):
        self.calls.append(("unarchive", issue_id))


def _make_snapshot(board_id, issue_id, column="todo", **state):
    snap = Snapshot(board_id).load()
    data = {"id": issue_id, "column": column, "status": "ok",
            "labels": [], "parent": None, "children": [],
            "blocked_by": [], "blocks": [], "archived": False, "state": "open"}
    data.update(state)
    snap.issues.append(data)
    snap.save()
    return data


def _drain(queue):
    """Retorna {(id, fullsync)} de todos os itens da fila."""
    out = set()
    while True:
        it = queue.getNext()
        if it is None:
            break
        out.add((it.id, it.event, it.fullsync))
        queue.remove(it.uuid)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Remédio 1
# ══════════════════════════════════════════════════════════════════════════════

def _write_issue_files(board_id, column, issue_id, slug, body_text):
    d = Path(".pipe/boards") / board_id / column
    d.mkdir(parents=True, exist_ok=True)
    body = d / f"{issue_id}-{slug}-body.md"
    body.write_text(body_text, encoding="utf-8")
    (d / f"{issue_id}-{slug}-addcomment.md").write_text("", encoding="utf-8")
    (d / f"{issue_id}-{slug}-history.md").write_text("", encoding="utf-8")
    return body


def test_remedio1_archive_command_removes_blocks_and_triggers_fullsync():
    # Issue #1 na coluna pre-prod, com /archive + bloqueios no body.
    body = _write_issue_files(
        "epic", "pre-prod", "1", "rodar",
        "# Rodar\n\ncorpo\n\n@---\n/archive\n/blocked_by #16\n/blocks #99\n")
    _make_snapshot("epic", "1", column="pre-prod",
                   body_path=str(body), body_mtime="1.0",
                   blocked_by=["16"], blocks=["99"])
    # Alvos recíprocos rastreados em outro board.
    _make_snapshot("task", "16", blocks=["1"])       # #16 bloqueia #1
    _make_snapshot("task", "99", blocked_by=["1"])   # #99 é bloqueada por #1

    port = FakePort()
    queue = ChangeQueue()
    sync._apply_change_up("epic", ChangeItem.of(SyncEvent.CHANGE_UP, id="1", board="epic"),
                          Board(port), queue, config=None)

    # Bloqueios removidos no board ANTES de arquivar.
    assert ("set_blocked_by", "1", []) in port.calls
    assert ("set_blocks", "1", []) in port.calls
    assert ("archive", "1") in port.calls

    # Snapshot da #1 reflete bloqueios zerados.
    reloaded = Snapshot("epic").load().issue("1")
    assert reloaded["blocked_by"] == [] and reloaded["blocks"] == []

    # Alvos recíprocos enfileirados como change-down fullsync.
    drained = _drain(queue)
    assert ("16", "change-down", True) in drained
    assert ("99", "change-down", True) in drained


def test_remedio1_archive_via_column_on_in():
    # Sem /archive no body, mas a coluna de destino arquiva (on_in:[archive]).
    body = _write_issue_files(
        "epic", "encerrado", "1", "rodar",
        "# Rodar\n\ncorpo\n\n@---\n/blocked_by #16\n")
    _make_snapshot("epic", "1", column="encerrado",
                   body_path=str(body), body_mtime="1.0", blocked_by=["16"])
    _make_snapshot("task", "16", blocks=["1"])

    config = {"boards": {"epic": {"columns": {
        "encerrado": {"name": "Encerrado", "on_in": ["archive"]}}}}}

    port = FakePort()
    queue = ChangeQueue()
    sync._apply_change_up("epic", ChangeItem.of(SyncEvent.CHANGE_UP, id="1", board="epic"),
                          Board(port), queue, config=config)

    assert ("set_blocked_by", "1", []) in port.calls
    drained = _drain(queue)
    assert ("16", "change-down", True) in drained


def test_remedio1_no_archive_keeps_blocks():
    # Sem arquivamento: bloqueios permanecem, nenhum setter de bloqueio é chamado.
    body = _write_issue_files(
        "epic", "pre-prod", "1", "rodar",
        "# Rodar\n\ncorpo\n\n@---\n/blocked_by #16\n")
    _make_snapshot("epic", "1", column="pre-prod",
                   body_path=str(body), body_mtime="1.0", blocked_by=["16"])
    _make_snapshot("task", "16", blocks=["1"])

    port = FakePort()
    queue = ChangeQueue()
    sync._apply_change_up("epic", ChangeItem.of(SyncEvent.CHANGE_UP, id="1", board="epic"),
                          Board(port), queue, config=None)

    # blocked_by desejado (=["16"]) igual ao conhecido → nenhum set_blocked_by.
    assert not any(c[0] == "set_blocked_by" for c in port.calls)
    assert Snapshot("epic").load().issue("1")["blocked_by"] == ["16"]
    assert _drain(queue) == set()


# ══════════════════════════════════════════════════════════════════════════════
# Remédio 2
# ══════════════════════════════════════════════════════════════════════════════

def test_remedio2_cleanup_removes_reciprocal_blocks_and_enqueues_fullsync():
    # #5 será deletada: bloqueia #10 e é bloqueada por #7.
    _make_snapshot("b1", "10", blocked_by=["5"])  # recíproco de blocks de #5
    _make_snapshot("b2", "7", blocks=["5"])       # recíproco de blocked_by de #5

    port = FakePort()
    queue = ChangeQueue()
    deleted_data = {"blocks": ["10"], "blocked_by": ["7"]}
    sync._cleanup_block_relations_on_delete("5", deleted_data, Board(port), queue)

    # Vínculo removido no board nas issues apontadas.
    assert ("set_blocked_by", "10", []) in port.calls
    assert ("set_blocks", "7", []) in port.calls

    # Snapshots dos alvos atualizados.
    assert Snapshot("b1").load().issue("10")["blocked_by"] == []
    assert Snapshot("b2").load().issue("7")["blocks"] == []

    # Alvos enfileirados como change-down fullsync.
    drained = _drain(queue)
    assert ("10", "change-down", True) in drained
    assert ("7", "change-down", True) in drained


def test_remedio2_delete_up_triggers_cleanup():
    _make_snapshot("epic", "5", blocks=["10"], blocked_by=[])
    _make_snapshot("task", "10", blocked_by=["5"])

    port = FakePort()
    queue = ChangeQueue()
    sync._apply_delete_up("epic", ChangeItem.of(SyncEvent.DELETE_UP, id="5", board="epic"),
                          Board(port), queue)

    assert ("close", "5") in port.calls
    assert ("set_blocked_by", "10", []) in port.calls
    # #5 removida do snapshot; #10 recebeu fullsync.
    assert Snapshot("epic").load().issue("5") is None
    assert ("10", "change-down", True) in _drain(queue)


def test_remedio2_delete_down_triggers_cleanup():
    _make_snapshot("epic", "5", blocks=["10"], blocked_by=[])
    _make_snapshot("task", "10", blocked_by=["5"])

    port = FakePort()
    queue = ChangeQueue()
    sync._apply_delete_down("epic", ChangeItem.of(SyncEvent.DELETE_DOWN, id="5", board="epic"),
                            Board(port), queue)

    assert ("set_blocked_by", "10", []) in port.calls
    assert Snapshot("epic").load().issue("5") is None
    assert ("10", "change-down", True) in _drain(queue)


def test_remedio2_untracked_targets_skipped():
    # Alvo não rastreado em nenhum snapshot → nada acontece.
    port = FakePort()
    queue = ChangeQueue()
    deleted_data = {"blocks": ["999"], "blocked_by": []}
    sync._cleanup_block_relations_on_delete("5", deleted_data, Board(port), queue)
    assert port.calls == []
    assert _drain(queue) == set()


# ══════════════════════════════════════════════════════════════════════════════
# Remédio 3
# ══════════════════════════════════════════════════════════════════════════════

def test_remedio3_detected_change_is_fullsync():
    snap = Snapshot("b").load()
    snap.issues = [{"id": "1", "column": "todo",
                    "updated_at": "2020-01-01T00:00:00Z", "status": "ok"}]
    snap.last_board_update = "2020-01-01T00:00:00Z"
    snap.save()

    class P(FakePort):
        def list_issues(self, board_id):
            return [Issue(id="1", title="t", body="", column="todo",
                          updated_at="2030-01-01T00:00:00Z")]

    queue = ChangeQueue()
    Board(P()).detect_board_changes("b", Snapshot("b").load(), queue)

    it = queue.getNext()
    assert it is not None
    assert it.id == "1" and it.event == "change-down" and it.fullsync is True


def test_remedio3_detected_create_is_fullsync():
    Snapshot("b").load().save()  # snapshot vazio

    class P(FakePort):
        def list_issues(self, board_id):
            return [Issue(id="2", title="novo", body="", column="todo",
                          updated_at="2030-01-01T00:00:00Z")]

    queue = ChangeQueue()
    Board(P()).detect_board_changes("b", Snapshot("b").load(), queue)

    it = queue.getNext()
    assert it.id == "2" and it.event == "create-down" and it.fullsync is True
