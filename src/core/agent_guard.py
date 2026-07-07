"""Validação pós-agente — Correção 4 (defesa em profundidade).

Detecta e corrige dois tipos de corrupção que um agente pode causar no
diretório .pipe/ durante sua execução:

  1. Sobrescrita do snapshot.json:
     Compara o mtime antes/depois da execução. Se mudou, restaura o backup
     feito antes da chamada.

  2. Criação de arquivos com prefixo numérico não rastreado:
     Varre o diretório da coluna ativa por arquivos ``<id>-*-body.md`` cujo
     ID numérico não existia no snapshot antes da execução. Se encontrado,
     renomeia removendo o prefixo, convertendo o "arquivo fantasma" num
     arquivo local sem id (comportamento esperado para novas tasks criadas
     pelo agente).

Uso típico em call_agent()::

    with AgentGuard(board_id, col_id) as guard:
        adapter.execute(params)
    # — corrupções já corrigidas ao sair do bloco

Ou em estilo explícito::

    guard = AgentGuard(board_id, col_id)
    guard.before()
    try:
        adapter.execute(params)
    finally:
        guard.after()
"""

import json
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from src.core.log import log

BOARDS_DIR = Path(".pipe/boards")


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários públicos (também usados pelos testes de integração)
# ─────────────────────────────────────────────────────────────────────────────

def snapshot_mtime(board_id: str) -> float | None:
    """Retorna o mtime do snapshot.json do board, ou None se não existir."""
    snap_path = BOARDS_DIR / board_id / "snapshot.json"
    if snap_path.exists():
        return snap_path.stat().st_mtime
    return None


def snapshot_known_ids(board_id: str) -> set[str]:
    """Retorna o conjunto de IDs numéricos presentes no snapshot antes da execução."""
    snap_path = BOARDS_DIR / board_id / "snapshot.json"
    if not snap_path.exists():
        return set()
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    return {str(i["id"]) for i in data.get("issues", []) if i.get("id")}


def restore_snapshot(board_id: str, backup_path: Path) -> None:
    """Restaura o snapshot.json a partir do backup."""
    snap_path = BOARDS_DIR / board_id / "snapshot.json"
    shutil.copy2(backup_path, snap_path)


def fix_phantom_files(board_id: str, col_id: str, known_ids: set[str]) -> list[tuple[str, str]]:
    """Renomeia arquivos *-body.md com prefixo numérico não rastreado.

    Varre ```.pipe/boards/<board_id>/<col_id>/``` e, para cada arquivo
    ``<n>-*-body.md`` onde ``n`` não está em ``known_ids``, remove o prefixo
    numérico e registra um warning no log.

    Retorna lista de pares (nome_original, nome_novo) para cada arquivo
    renomeado.
    """
    col_dir = BOARDS_DIR / board_id / col_id
    renamed: list[tuple[str, str]] = []

    if not col_dir.exists():
        return renamed

    for body_file in col_dir.glob("*-body.md"):
        match = re.match(r"^(\d+)-", body_file.name)
        if match and match.group(1) not in known_ids:
            new_name = re.sub(r"^\d+-", "", body_file.name)
            new_path = body_file.parent / new_name
            log.warning(
                "AgentGuard",
                f"[{board_id}] Arquivo com prefixo numérico indevido renomeado: "
                f"{body_file.name} → {new_name}",
            )
            body_file.rename(new_path)
            renamed.append((body_file.name, new_name))

    return renamed


# ─────────────────────────────────────────────────────────────────────────────
# Guard principal
# ─────────────────────────────────────────────────────────────────────────────

class AgentGuard:
    """Guarda o estado de .pipe/ antes/após a execução de um agente.

    Suporta uso como context manager (``with AgentGuard(...) as g:``) ou
    chamadas explícitas (``g.before()`` / ``g.after()``).

    Atributos públicos (disponíveis após ``after()``):
        snapshot_restored (bool): True se o snapshot foi restaurado.
        renamed_files (list): Pares (original, novo) de arquivos renomeados.
    """

    def __init__(self, board_id: str, col_id: str):
        self._board_id = board_id
        self._col_id = col_id

        self._mtime_before: float | None = None
        self._known_ids: set[str] = set()
        self._backup: Path | None = None

        self.snapshot_restored: bool = False
        self.renamed_files: list[tuple[str, str]] = []

    # ── lifecycle ────────────────────────────────────────────────────────────

    def before(self) -> None:
        """Captura estado pré-execução: mtime + IDs conhecidos + backup."""
        snap_path = BOARDS_DIR / self._board_id / "snapshot.json"

        self._mtime_before = snapshot_mtime(self._board_id)
        self._known_ids = snapshot_known_ids(self._board_id)

        # Backup atômico em arquivo temporário do sistema
        if snap_path.exists():
            fd, tmp = tempfile.mkstemp(suffix=".bak")
            import os
            os.close(fd)
            self._backup = Path(tmp)
            shutil.copy2(snap_path, self._backup)

    def after(self) -> None:
        """Verifica estado pós-execução e corrige corrupções."""
        try:
            self._check_snapshot()
            self._check_phantom_files()
        finally:
            self._cleanup_backup()

    # ── context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "AgentGuard":
        self.before()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.after()
        return None  # não suprime exceções

    # ── internos ─────────────────────────────────────────────────────────────

    def _check_snapshot(self) -> None:
        mtime_after = snapshot_mtime(self._board_id)
        if self._mtime_before is not None and mtime_after != self._mtime_before:
            log.warning(
                "AgentGuard",
                f"[{self._board_id}] snapshot.json modificado pelo agente — restaurando",
            )
            if self._backup and self._backup.exists():
                restore_snapshot(self._board_id, self._backup)
                self.snapshot_restored = True

    def _check_phantom_files(self) -> None:
        self.renamed_files = fix_phantom_files(
            self._board_id, self._col_id, self._known_ids
        )

    def _cleanup_backup(self) -> None:
        if self._backup and self._backup.exists():
            self._backup.unlink()
        self._backup = None
