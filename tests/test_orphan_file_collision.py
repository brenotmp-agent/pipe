"""Teste de regressão: arquivo órfão com ID duplicado NÃO deve disparar change-up.

Cenário: existe um arquivo legítimo em backlog/37-...-body.md registrado no
snapshot, e um arquivo órfão (não rastreado) em planning-poker/37-...-body.md.
O detect_local_changes deve usar o arquivo do snapshot (backlog) e ignorar o
órfão, sem disparar change-up espúrio.
"""

import json
from pathlib import Path

import pytest

from src.core.change_queue import ChangeQueue
from src.core.sync import detect_local_changes


@pytest.fixture
def boards_dir(tmp_path, monkeypatch):
    """Cria estrutura de board com snapshot e dois arquivos 37-...-body.md."""
    boards_base = tmp_path / ".pipe" / "boards"
    board_dir = boards_base / "task"
    backlog = board_dir / "backlog"
    planning = board_dir / "planning-poker"
    backlog.mkdir(parents=True)
    planning.mkdir(parents=True)

    # Arquivo legítimo (registrado no snapshot)
    legit_body = backlog / "37-criar_docker_compose-body.md"
    legit_body.write_text("# Criar docker-compose\n\nbody\n\n@---\n/labels docker\n")
    legit_mtime = str(legit_body.stat().st_mtime)

    # Addcomment vazio (necessário para não disparar por addcomment)
    (backlog / "37-criar_docker_compose-addcomment.md").write_text("")

    # Arquivo órfão (NÃO registrado no snapshot)
    orphan_body = planning / "37-testes_automatizados-body.md"
    orphan_body.write_text("# Testes automatizados\n\noutro body\n")
    (planning / "37-testes_automatizados-addcomment.md").write_text("")

    # Snapshot com apenas a issue legítima
    snapshot = {
        "board": {"backlog": "Backlog", "planning-poker": "Planning Poker"},
        "issues": [
            {
                "id": "37",
                "column": "backlog",
                "body_path": str(legit_body),
                "body_mtime": legit_mtime,
                "updated_at": "2026-07-21T10:00:00Z",
                "status": "ok",
                "labels": ["docker"],
                "parent": None,
                "children": [],
                "blocked_by": [],
                "blocks": [],
                "archived": False,
                "state": "open",
            }
        ],
        "last_sync": "2026-07-21T10:00:00Z",
        "last_board_update": "2026-07-21T10:00:00Z",
    }
    snap_file = board_dir / "snapshot.json"
    snap_file.write_text(json.dumps(snapshot, indent=2))

    # Monkeypatch BOARDS_DIR e QUEUE_FILE para apontar para o tmp
    monkeypatch.setattr("src.core.sync.BOARDS_DIR", boards_base)
    monkeypatch.setattr("src.core.snapshot.BOARDS_DIR", boards_base)

    pipe_dir = tmp_path / ".pipe"
    queue_file = pipe_dir / "changeQueue.json"
    monkeypatch.setattr("src.core.change_queue.PIPE_DIR", pipe_dir)
    monkeypatch.setattr("src.core.change_queue.QUEUE_FILE", queue_file)

    return board_dir


def test_orphan_file_does_not_trigger_change_up(boards_dir):
    """Arquivo órfão com mesmo ID numérico NÃO dispara change-up."""
    queue = ChangeQueue()

    detect_local_changes("task", queue)

    # A fila deve estar vazia: o arquivo legítimo não mudou, e o órfão deve
    # ser ignorado (não sobrescrever o legítimo no dicionário local_bodies).
    item = queue.getNext()
    assert item is None, (
        f"Esperava fila vazia mas encontrou: event={item.event}, id={item.id}"
    )


def test_orphan_file_with_modified_legit_triggers_single_change_up(boards_dir):
    """Se o body legítimo foi modificado, deve disparar exatamente 1 change-up."""
    # Modificar o body legítimo para simular edição humana
    legit_body = boards_dir / "backlog" / "37-criar_docker_compose-body.md"
    legit_body.write_text("# Criar docker-compose\n\nbody modificado\n\n@---\n/labels docker\n")

    queue = ChangeQueue()
    detect_local_changes("task", queue)

    item = queue.getNext()
    assert item is not None, "Esperava change-up para body modificado"
    assert item.id == "37"
    assert item.event == "change-up"

    # Confirmar o primeiro e verificar que não há segundo
    queue.remove(item.uuid)
    assert queue.getNext() is None
