"""Testes de migrate_agent_level_labels (sync.py).

Cobre:
- Issue com /agent_level no body e sem label no snapshot → enfileira change-up.
- Issue com /agent_level no body E label agent-level-* já no snapshot → ignora.
- Issue sem /agent_level no body → ignora.
- Issue com status pendente (não 'ok') → ignora.
- Issue sem body_path válido → ignora.
- Contagem correta de migradas.
- Snapshot é atualizado (status=change-up) para issues enfileiradas.
- Corrida de ordenação: CHANGE_UP de migração deve preceder CHANGE_DOWN da mesma issue.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.board import ChangeItem, SyncEvent
from src.core.change_queue import ChangeQueue
from src.core.snapshot import BOARDS_DIR, Snapshot
from src.core.sync import migrate_agent_level_labels


@pytest.fixture(autouse=True)
def _chdir_tmp(tmp_path, monkeypatch):
    """Isola .pipe/ em diretório temporário por teste."""
    monkeypatch.chdir(tmp_path)
    yield


def _make_board(board_id: str, columns: list[str] = ("todo",)):
    """Cria estrutura de diretórios e snapshot mínimo para o board."""
    board_dir = Path(".pipe/boards") / board_id
    for col in columns:
        (board_dir / col).mkdir(parents=True, exist_ok=True)
    snap = Snapshot(board_id).load()
    snap.board = {col: col for col in columns}
    snap.save()
    return board_dir


def _make_body(board_dir: Path, col: str, issue_id: str, body_block: str) -> Path:
    """Cria arquivo body com conteúdo dado e retorna o path."""
    col_dir = board_dir / col
    col_dir.mkdir(parents=True, exist_ok=True)
    body = col_dir / f"{issue_id}-slug-body.md"
    body.write_text(f"# Título\n\n{body_block}", encoding="utf-8")
    return body


def _add_issue(board_id: str, issue_id: str, body_path: Path,
               labels: list = None, status: str = "ok"):
    """Adiciona registro de issue no snapshot."""
    snap = Snapshot(board_id).load()
    snap.issues.append({
        "id": issue_id,
        "column": "todo",
        "body_path": str(body_path),
        "body_mtime": str(body_path.stat().st_mtime),
        "status": status,
        "labels": list(labels or []),
    })
    snap.save()


# ── Casos principais ──────────────────────────────────────────────────────────

def test_migra_issue_com_agent_level_sem_label():
    """Issue com /agent_level no body e sem label agent-level-* → change-up enfileirado."""
    board_id = "task"
    board_dir = _make_board(board_id)
    body = _make_body(board_dir, "todo", "10", "@---\n/agent_level high\n")
    _add_issue(board_id, "10", body, labels=["backend"])

    queue = ChangeQueue()
    count = migrate_agent_level_labels(board_id, queue)

    assert count == 1
    assert queue.size() == 1


def test_nao_migra_issue_com_label_agent_level_no_snapshot():
    """Issue que já tem label agent-level-* no snapshot → não enfileira."""
    board_id = "task"
    board_dir = _make_board(board_id)
    body = _make_body(board_dir, "todo", "11", "@---\n/agent_level high\n")
    _add_issue(board_id, "11", body, labels=["agent-level-high"])

    queue = ChangeQueue()
    count = migrate_agent_level_labels(board_id, queue)

    assert count == 0
    assert queue.size() == 0


def test_nao_migra_issue_sem_agent_level_no_body():
    """Issue sem /agent_level no bloco @--- → não enfileira."""
    board_id = "task"
    board_dir = _make_board(board_id)
    body = _make_body(board_dir, "todo", "12", "@---\n/labels backend\n")
    _add_issue(board_id, "12", body)

    queue = ChangeQueue()
    count = migrate_agent_level_labels(board_id, queue)

    assert count == 0
    assert queue.size() == 0


def test_nao_migra_issue_sem_bloco_commands():
    """Issue com body sem @--- → não enfileira."""
    board_id = "task"
    board_dir = _make_board(board_id)
    body = _make_body(board_dir, "todo", "13", "Só texto, sem bloco de comandos.")
    _add_issue(board_id, "13", body)

    queue = ChangeQueue()
    count = migrate_agent_level_labels(board_id, queue)

    assert count == 0


def test_nao_migra_issue_com_status_pendente():
    """Issue com status != 'ok' é ignorada pela migração."""
    board_id = "task"
    board_dir = _make_board(board_id)
    body = _make_body(board_dir, "todo", "14", "@---\n/agent_level low\n")
    _add_issue(board_id, "14", body, status="change-down")

    queue = ChangeQueue()
    count = migrate_agent_level_labels(board_id, queue)

    assert count == 0


def test_nao_migra_issue_sem_body_path_valido():
    """Issue cujo body_path não existe no filesystem → ignorada."""
    board_id = "task"
    _make_board(board_id)

    snap = Snapshot(board_id).load()
    snap.issues.append({
        "id": "15",
        "column": "todo",
        "body_path": "/nao/existe/15-x-body.md",
        "body_mtime": "0",
        "status": "ok",
        "labels": [],
    })
    snap.save()

    queue = ChangeQueue()
    count = migrate_agent_level_labels(board_id, queue)

    assert count == 0


def test_migra_multiplas_issues():
    """Múltiplas issues candidatas → todas enfileiradas."""
    board_id = "task"
    board_dir = _make_board(board_id)

    for issue_id, level in [("20", "high"), ("21", "low"), ("22", "medium")]:
        body = _make_body(board_dir, "todo", issue_id, f"@---\n/agent_level {level}\n")
        _add_issue(board_id, issue_id, body)

    queue = ChangeQueue()
    count = migrate_agent_level_labels(board_id, queue)

    assert count == 3
    assert queue.size() == 3


def test_snapshot_atualizado_apos_migracao():
    """O snapshot deve registrar status=change-up para issues migradas."""
    board_id = "task"
    board_dir = _make_board(board_id)
    body = _make_body(board_dir, "todo", "30", "@---\n/agent_level medium\n")
    _add_issue(board_id, "30", body)

    queue = ChangeQueue()
    migrate_agent_level_labels(board_id, queue)

    snap = Snapshot(board_id).load()
    issue_data = snap.issue("30")
    assert issue_data is not None
    assert issue_data["status"] == "change-up"


def test_migracao_idempotente():
    """Chamar migrate duas vezes seguidas não duplica itens na fila."""
    board_id = "task"
    board_dir = _make_board(board_id)
    body = _make_body(board_dir, "todo", "40", "@---\n/agent_level high\n")
    _add_issue(board_id, "40", body)

    queue = ChangeQueue()
    first = migrate_agent_level_labels(board_id, queue)
    second = migrate_agent_level_labels(board_id, queue)

    # Na segunda chamada, o status já é 'change-up' (não 'ok') → ignorada
    assert first == 1
    assert second == 0
    assert queue.size() == 1


def test_mistura_migradas_e_nao_migradas():
    """Apenas issues candidatas são enfileiradas; as demais são ignoradas."""
    board_id = "task"
    board_dir = _make_board(board_id)

    # Candidata: tem /agent_level, sem label
    body_a = _make_body(board_dir, "todo", "50", "@---\n/agent_level low\n")
    _add_issue(board_id, "50", body_a)

    # Já migrada: tem a label no snapshot
    body_b = _make_body(board_dir, "todo", "51", "@---\n/agent_level high\n")
    _add_issue(board_id, "51", body_b, labels=["agent-level-high"])

    # Sem /agent_level
    body_c = _make_body(board_dir, "todo", "52", "@---\n/labels backend\n")
    _add_issue(board_id, "52", body_c)

    queue = ChangeQueue()
    count = migrate_agent_level_labels(board_id, queue)

    assert count == 1
    assert queue.size() == 1


# ── Teste de corrida de ordenação ────────────────────────────────────────────

def test_migracao_antes_de_change_down_garante_ordem_fifo():
    """CHANGE_UP de migração deve preceder CHANGE_DOWN da mesma issue na fila.

    Simula o cenário de corrida apontado no code review: uma issue legada
    (com /agent_level no body, sem label no board) é também alterada
    remotamente no mesmo ciclo de full sync.

    Quando migrate_agent_level_labels() é chamado ANTES de detect_board_changes,
    o CHANGE_UP entra primeiro na fila. O processamento FIFO garante que:
      1. CHANGE_UP sobe a label agent-level-* para o board.
      2. CHANGE_DOWN relê a issue com a label já presente → preserva o nível.

    O teste verifica apenas a precondição sob controle do código corrigido:
    o CHANGE_UP está na posição 0 da fila e o CHANGE_DOWN está na posição 1.
    """
    board_id = "task"
    board_dir = _make_board(board_id)
    body = _make_body(board_dir, "todo", "99", "@---\n/agent_level high\n")
    _add_issue(board_id, "99", body, labels=[])  # sem label no snapshot

    queue = ChangeQueue()

    # Passo 1: migração enfileira CHANGE_UP (simula board_full_sync após reordenação)
    count = migrate_agent_level_labels(board_id, queue)
    assert count == 1, "migração deve enfileirar 1 issue"

    # Passo 2: enfileira CHANGE_DOWN manualmente (simula detect_board_changes)
    change_down = ChangeItem.of(SyncEvent.CHANGE_DOWN, id="99", board=board_id, fullsync=True)
    queue.add(change_down)

    # Verifica a ordem: CHANGE_UP (posição 0) antes do CHANGE_DOWN (posição 1)
    items = queue._read()
    assert len(items) == 2, "fila deve ter exatamente 2 itens"
    assert items[0].event == SyncEvent.CHANGE_UP.value, (
        f"posição 0 deve ser CHANGE_UP, mas é {items[0].event!r}"
    )
    assert items[1].event == SyncEvent.CHANGE_DOWN.value, (
        f"posição 1 deve ser CHANGE_DOWN, mas é {items[1].event!r}"
    )
