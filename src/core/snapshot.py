"""Snapshot core - estado conhecido de um board entre execuções.

Persiste em .pipe/boards/<board_id>/snapshot.json.

Estrutura:
{
  "board": {"<col_id>": "<col_name>", ...},
  "issues": [{"id": "...", "updated_at": "...", ...}],
  "last_sync": "<ISO 8601>"
}
"""

import json
from pathlib import Path

BOARDS_DIR = Path(".pipe/boards")


class Snapshot:
    """Estado conhecido de um board, persistido entre execuções."""

    def __init__(self, board_id: str):
        self._board_id = board_id
        self._path = BOARDS_DIR / board_id / "snapshot.json"
        self._data: dict = {"board": {}, "issues": [], "last_sync": None}

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> "Snapshot":
        """Carrega do disco (vazio se não existir)."""
        if self._path.exists():
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
            self._data.setdefault("board", {})
            self._data.setdefault("issues", [])
            self._data.setdefault("last_sync", None)
            self._data.setdefault("last_board_update", None)
        return self

    def save(self) -> None:
        """Persiste no disco."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @property
    def board(self) -> dict:
        """Mapa col_id -> col_name."""
        return self._data["board"]

    @board.setter
    def board(self, columns: dict):
        self._data["board"] = columns

    @property
    def issues(self) -> list[dict]:
        return self._data["issues"]

    @issues.setter
    def issues(self, value: list[dict]):
        self._data["issues"] = value

    @property
    def last_sync(self) -> str | None:
        return self._data.get("last_sync")

    @last_sync.setter
    def last_sync(self, value: str):
        self._data["last_sync"] = value

    @property
    def last_board_update(self) -> str | None:
        return self._data.get("last_board_update")

    @last_board_update.setter
    def last_board_update(self, value: str):
        self._data["last_board_update"] = value

    def issue(self, issue_id: str) -> dict | None:
        """Busca uma issue pelo id."""
        for issue in self.issues:
            if str(issue.get("id")) == str(issue_id):
                return issue
        return None
