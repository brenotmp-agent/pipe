"""Testes da otimização de sincronização (diff vs snapshot + pair-trigger).

Cobrem:
- Upgrade de fullsync no ChangeQueue (superset).
- apply_commands: só chama setter no diff; retorna deltas corretos.
- Gatilho de par recíproco: termina (não entra em loop) quando o par já bate.
"""

import os
import sys
from pathlib import Path

import pytest

# Permite importar o pacote src quando rodado de qualquer lugar.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.board import Board, BoardPort, ChangeItem, Issue, SyncEvent
from src.core.change_queue import ChangeQueue
from src.core.commands import IssueCommands


@pytest.fixture(autouse=True)
def _chdir_tmp(tmp_path, monkeypatch):
    """Isola .pipe/ em um diretório temporário por teste."""
    monkeypatch.chdir(tmp_path)
    yield


# ── Fake adapter que registra chamadas em vez de bater na rede ────────────────

class FakePort(BoardPort):
    def __init__(self):
        self.calls = []

    def connect(self, config): pass
    def sync_boards(self, boards): pass
    def list_issues(self, board_id): return []
    def list_issues_since(self, board_id, since): return []
    def get_issue(self, board_id, issue_id, fullsync=False):
        self.calls.append(("get_issue", issue_id, fullsync))
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
    def set_parent(self, board_id, issue_id, parent_id, known_current=None):
        self.calls.append(("set_parent", issue_id, parent_id))
    def set_children(self, board_id, issue_id, children_ids, known_current=None):
        self.calls.append(("set_children", issue_id, sorted(children_ids)))
    def set_blocked_by(self, board_id, issue_id, blocker_ids, known_current=None):
        self.calls.append(("set_blocked_by", issue_id, sorted(blocker_ids)))
    def set_blocks(self, board_id, issue_id, blocked_ids, known_current=None):
        self.calls.append(("set_blocks", issue_id, sorted(blocked_ids)))
    def archive_issue(self, board_id, issue_id):
        self.calls.append(("archive", issue_id))
    def unarchive_issue(self, board_id, issue_id):
        self.calls.append(("unarchive", issue_id))


def _ops(port):
    return [c[0] for c in port.calls]


# ── ChangeQueue: upgrade de fullsync ──────────────────────────────────────────

def test_queue_upgrade_partial_to_full():
    q = ChangeQueue()
    assert q.add(ChangeItem.of(SyncEvent.CHANGE_DOWN, id="5", board="b"))
    # Mesmo alvo, agora fullsync -> não duplica, mas promove o existente.
    assert not q.add(ChangeItem.of(SyncEvent.CHANGE_DOWN, id="5", board="b", fullsync=True))
    item = q.getNext()
    assert item.id == "5"
    assert item.fullsync is True
    # Só existe um item.
    q.remove(item.uuid)
    assert q.getNext() is None


def test_queue_full_not_downgraded():
    q = ChangeQueue()
    assert q.add(ChangeItem.of(SyncEvent.CHANGE_DOWN, id="7", board="b", fullsync=True))
    assert not q.add(ChangeItem.of(SyncEvent.CHANGE_DOWN, id="7", board="b"))
    assert q.getNext().fullsync is True


# ── apply_commands: diff vs known ─────────────────────────────────────────────

def test_apply_commands_noop_when_equal():
    port = FakePort()
    board = Board(port)
    cmds = IssueCommands(labels=["a"], parent="10", blocked_by=["2"])
    known = {
        "labels": ["a"], "parent": "10", "children": [],
        "blocked_by": ["2"], "blocks": [], "archived": False, "state": "open",
    }
    deltas = board.apply_commands("b", "1", cmds, known=known)
    # Nada mudou -> nenhum setter chamado.
    assert port.calls == []
    for rel in deltas.values():
        assert rel["added"] == [] and rel["removed"] == []


def test_apply_commands_only_changed_setter():
    port = FakePort()
    board = Board(port)
    cmds = IssueCommands(labels=["a", "b"], parent="10")
    known = {
        "labels": ["a"], "parent": "10", "children": [],
        "blocked_by": [], "blocks": [], "archived": False, "state": "open",
    }
    board.apply_commands("b", "1", cmds, known=known)
    # Só labels mudou (parent igual, deps vazias iguais).
    assert _ops(port) == ["set_labels"]


def test_apply_commands_deltas_added_removed():
    port = FakePort()
    board = Board(port)
    cmds = IssueCommands(blocked_by=["2", "3"])
    known = {
        "labels": [], "parent": None, "children": [],
        "blocked_by": ["3", "9"], "blocks": [], "archived": False, "state": "open",
    }
    deltas = board.apply_commands("b", "1", cmds, known=known)
    assert set(deltas["blocked_by"]["added"]) == {"2"}
    assert set(deltas["blocked_by"]["removed"]) == {"9"}


def test_apply_commands_no_known_reconciles_all():
    port = FakePort()
    board = Board(port)
    cmds = IssueCommands(labels=["a"], parent="10", children=["2"],
                         blocked_by=["3"], blocks=["4"])
    board.apply_commands("b", "1", cmds, known=None)
    ops = _ops(port)
    # Reconciliação completa chama todos os setters + unarchive.
    assert "set_labels" in ops
    assert "set_parent" in ops
    assert "set_children" in ops
    assert "set_blocked_by" in ops
    assert "set_blocks" in ops
    assert "unarchive" in ops


def test_apply_commands_close_skipped_when_already_closed():
    port = FakePort()
    board = Board(port)
    cmds = IssueCommands(close="completed")
    known = {
        "labels": [], "parent": None, "children": [],
        "blocked_by": [], "blocks": [], "archived": False, "state": "closed",
    }
    board.apply_commands("b", "1", cmds, known=known)
    assert "close" not in _ops(port)


# ── Pair-trigger: terminação ──────────────────────────────────────────────────

def _make_snapshot(board_id, issue_id, **state):
    from src.core.snapshot import Snapshot
    snap = Snapshot(board_id).load()
    data = {"id": issue_id, "column": "todo", "status": "ok"}
    data.update(state)
    snap.issues.append(data)
    snap.save()


def test_pair_trigger_enqueues_when_not_reciprocated():
    from src.core import sync
    q = ChangeQueue()
    # Alvo B existe no snapshot mas NÃO reciproca A ainda.
    _make_snapshot("b", "20", blocks=[])
    deltas = {"blocked_by": {"added": ["20"], "removed": []},
              "blocks": {"added": [], "removed": []},
              "parent": {"added": [], "removed": []},
              "children": {"added": [], "removed": []}}
    sync._trigger_reciprocal_downs("10", deltas, q)
    item = q.getNext()
    assert item is not None
    assert item.id == "20" and item.fullsync is True


def test_pair_trigger_stops_when_reciprocated():
    from src.core import sync
    q = ChangeQueue()
    # Alvo B JÁ reciproca A (B.blocks contém 10) -> nada a enfileirar.
    _make_snapshot("b", "20", blocks=["10"])
    deltas = {"blocked_by": {"added": ["20"], "removed": []},
              "blocks": {"added": [], "removed": []},
              "parent": {"added": [], "removed": []},
              "children": {"added": [], "removed": []}}
    sync._trigger_reciprocal_downs("10", deltas, q)
    assert q.getNext() is None


def test_pair_trigger_untracked_target_skipped():
    from src.core import sync
    q = ChangeQueue()
    # Nenhum snapshot criado -> alvo não rastreado -> skip.
    deltas = {"blocked_by": {"added": ["999"], "removed": []},
              "blocks": {"added": [], "removed": []},
              "parent": {"added": [], "removed": []},
              "children": {"added": [], "removed": []}}
    sync._trigger_reciprocal_downs("10", deltas, q)
    assert q.getNext() is None


def test_pair_trigger_removed_only_when_still_reciprocated():
    from src.core import sync
    q = ChangeQueue()
    # Remoção: B ainda reciproca (B.blocks contém 10) -> precisa reconciliar B.
    _make_snapshot("b", "20", blocks=["10"])
    deltas = {"blocked_by": {"added": [], "removed": ["20"]},
              "blocks": {"added": [], "removed": []},
              "parent": {"added": [], "removed": []},
              "children": {"added": [], "removed": []}}
    sync._trigger_reciprocal_downs("10", deltas, q)
    assert q.getNext().id == "20"


# ── SessionIndex ──────────────────────────────────────────────────────────────

def test_session_index_set_get_roundtrip():
    from src.core.session import SessionIndex
    idx = SessionIndex()
    assert idx.get("b", "1", "eng") is None
    idx.set("b", "1", "eng", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert idx.get("b", "1", "eng") == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_session_index_isolated_by_agent_and_issue():
    from src.core.session import SessionIndex
    idx = SessionIndex()
    idx.set("b", "1", "eng", "id-eng")
    idx.set("b", "1", "qa", "id-qa")
    idx.set("b", "2", "eng", "id-eng-2")
    assert idx.get("b", "1", "eng") == "id-eng"
    assert idx.get("b", "1", "qa") == "id-qa"
    assert idx.get("b", "2", "eng") == "id-eng-2"


def test_session_index_overwrite_updates_id():
    from src.core.session import SessionIndex
    idx = SessionIndex()
    idx.set("b", "1", "eng", "old-id")
    idx.set("b", "1", "eng", "new-id")
    assert idx.get("b", "1", "eng") == "new-id"


def test_session_index_set_empty_is_noop():
    from src.core.session import SessionIndex
    idx = SessionIndex()
    idx.set("b", "1", "eng", "")
    assert idx.get("b", "1", "eng") is None

