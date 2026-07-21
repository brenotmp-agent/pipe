"""Session index - mapeia (board, issue, agente) -> session_id do kiro-cli.

Persiste em .pipe/sessions.json um índice de ponteiros para as sessões do
kiro-cli. A esteira NÃO gerencia o ciclo de vida das sessões (não apaga, não
limpa): apenas guarda o id para retomar a conversa com `--resume-id` quando a
sessão ainda existir. Se o kiro-cli tiver descartado a sessão, a execução
seguinte cria uma nova e o índice é atualizado com o novo id.

Filosofia por agente (não por coluna): a chave inclui o agente, então o mesmo
agente atuando em colunas diferentes retoma o próprio raciocínio da etapa
anterior. Agentes distintos nunca herdam a sessão um do outro.

Estrutura do arquivo:
{
  "<board>/<issue>/<agente>": {
    "session_id": "<uuid>",
    "updated_at": "<ISO 8601 UTC>"
  }
}
"""

import json
from datetime import datetime, timezone
from pathlib import Path

PIPE_DIR = Path(".pipe")
SESSIONS_FILE = PIPE_DIR / "sessions.json"


class SessionIndex:
    """Índice persistente de sessões do kiro-cli (ponteiros por agente)."""

    def _read(self) -> dict:
        if not SESSIONS_FILE.exists():
            return {}
        try:
            return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict) -> None:
        PIPE_DIR.mkdir(parents=True, exist_ok=True)
        SESSIONS_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @staticmethod
    def _key(board_id: str, issue_id: str, agent_id: str) -> str:
        return f"{board_id}/{issue_id}/{agent_id}"

    def get(self, board_id: str, issue_id: str, agent_id: str) -> str | None:
        """Retorna o session_id conhecido para (board, issue, agente) ou None."""
        entry = self._read().get(self._key(board_id, issue_id, agent_id))
        return entry.get("session_id") if entry else None

    def set(self, board_id: str, issue_id: str, agent_id: str,
            session_id: str) -> None:
        """Grava/atualiza o session_id para (board, issue, agente)."""
        if not session_id:
            return
        data = self._read()
        data[self._key(board_id, issue_id, agent_id)] = {
            "session_id": session_id,
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._write(data)
