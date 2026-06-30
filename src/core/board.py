"""Board core - gerencia boards via port."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from src.core.log import log


class PenaltyException(Exception):
    """Rate limit atingido - aguardar antes de tentar novamente."""
    def __init__(self, wait_seconds: int):
        self.wait_seconds = wait_seconds
        super().__init__(f"Rate limit - aguardar {wait_seconds}s")


class SyncEvent(str, Enum):
    """Evento de sincronismo registrado na fila de mudanças.

    Sufixo '-up' = origem local (precisa subir para o board).
    Sufixo '-down' = origem no board (precisa descer para o local).
    """
    CREATE_UP = "create-up"      # criado localmente
    CREATE_DOWN = "create-down"  # criado no board
    CHANGE_UP = "change-up"      # modificado localmente
    CHANGE_DOWN = "change-down"  # modificado no board
    DELETE_UP = "delete-up"      # deletado localmente
    DELETE_DOWN = "delete-down"  # deletado no board


@dataclass
class ChangeItem:
    """Item da fila de sincronismo (.pipe/changeQueue.json)."""
    timestamp: str       # horário em que foi adicionado na fila (ISO 8601 UTC)
    event: str           # SyncEvent
    id: str = None       # id da issue no board (None quando ainda não existe)
    identifier: str = None  # body_path para issues criadas localmente (sem id)
    board: str = None       # board_id ao qual a issue pertence
    uuid: str = None        # id único na fila (atribuído por add/addAll)

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def of(cls, event, id: str = None, identifier: str = None,
           board: str = None) -> "ChangeItem":
        """Cria um ChangeItem com timestamp atual."""
        return cls(
            timestamp=cls.now(),
            event=event.value if isinstance(event, SyncEvent) else event,
            id=id,
            identifier=identifier,
            board=board,
        )

    def same_target(self, other: "ChangeItem") -> bool:
        """True se representa o mesmo alvo de sincronismo (para deduplicação).

        Considera duplicado quando event, id, identifier e board são iguais.
        """
        return (
            self.event == other.event
            and self.id == other.id
            and self.identifier == other.identifier
            and self.board == other.board
        )


@dataclass
class Issue:
    id: str
    title: str
    body: str
    column: str
    labels: list[str] = None
    updated_at: str = None
    # Relações e estado (preenchidos pelo adapter quando disponível)
    parent: str = None
    children: list[str] = None
    blocked_by: list[str] = None
    blocks: list[str] = None
    state: str = None  # 'open' | 'closed'
    archived: bool = False


class BoardPort(ABC):
    """Port para adapters de board (GitHub, ClickUp, etc)."""

    @abstractmethod
    def connect(self, config: dict) -> None:
        """Conecta ao serviço."""
        pass

    @abstractmethod
    def sync_boards(self, boards: list[dict]) -> None:
        """Sincroniza estrutura de boards e colunas."""
        pass

    @abstractmethod
    def list_issues(self, board_id: str) -> list[Issue]:
        """Lista todas as issues de um board."""
        pass

    @abstractmethod
    def list_issues_since(self, board_id: str, since: str) -> list[Issue]:
        """Lista issues modificadas desde a data informada (ISO 8601)."""
        pass

    @abstractmethod
    def get_issue(self, board_id: str, issue_id: str) -> Issue:
        """Busca uma issue específica."""
        pass

    @abstractmethod
    def create_issue(self, board_id: str, title: str, body: str, column: str) -> Issue:
        """Cria uma issue no board. Retorna a issue criada com id."""
        pass

    @abstractmethod
    def move_issue(self, board_id: str, issue_id: str, column: str, from_column: str = None) -> None:
        """Move issue para outra coluna."""
        pass

    @abstractmethod
    def update_issue(self, board_id: str, issue_id: str, title: str = None, body: str = None) -> None:
        """Atualiza título e/ou body da issue."""
        pass

    @abstractmethod
    def add_comment(self, board_id: str, issue_id: str, comment: str) -> None:
        """Adiciona comentário na issue."""
        pass

    @abstractmethod
    def list_comments(self, board_id: str, issue_id: str) -> list[dict]:
        """Lista comentários de uma issue. Retorna [{author, date, body}]."""
        pass

    @abstractmethod
    def close_issue(self, board_id: str, issue_id: str) -> None:
        """Fecha/arquiva uma issue no board."""
        pass

    # ── Operações opcionais (defaults no-op; adapters sobrescrevem) ───────────

    def reopen_issue(self, board_id: str, issue_id: str) -> None:
        """Reabre uma issue fechada."""
        log.warning("Board", "reopen_issue não implementado neste adapter")

    def set_labels(self, board_id: str, issue_id: str, labels: list[str]) -> None:
        """Define (SET) as labels da issue, substituindo as existentes."""
        log.warning("Board", "set_labels não implementado neste adapter")

    def add_label(self, board_id: str, issue_id: str, label: str) -> None:
        """Adiciona uma única label à issue (mantém as demais)."""
        log.warning("Board", "add_label não implementado neste adapter")

    def remove_label(self, board_id: str, issue_id: str, label: str) -> None:
        """Remove uma única label da issue (mantém as demais)."""
        log.warning("Board", "remove_label não implementado neste adapter")

    def set_parent(self, board_id: str, issue_id: str, parent_id: str | None) -> None:
        """Define o parent (sub-issue de parent_id). None remove o vínculo."""
        log.warning("Board", "set_parent não implementado neste adapter")

    def set_children(self, board_id: str, issue_id: str, children_ids: list[str]) -> None:
        """Define (SET) os filhos (sub-issues) desta issue."""
        log.warning("Board", "set_children não implementado neste adapter")

    def set_blocked_by(self, board_id: str, issue_id: str, blocker_ids: list[str]) -> None:
        """Define (SET) as issues que bloqueiam esta."""
        log.warning("Board", "set_blocked_by não implementado neste adapter")

    def set_blocks(self, board_id: str, issue_id: str, blocked_ids: list[str]) -> None:
        """Define (SET) as issues que esta bloqueia."""
        log.warning("Board", "set_blocks não implementado neste adapter")

    def archive_issue(self, board_id: str, issue_id: str) -> None:
        """Arquiva o item da issue no project."""
        log.warning("Board", "archive_issue não implementado neste adapter")

    def unarchive_issue(self, board_id: str, issue_id: str) -> None:
        """Desarquiva o item da issue no project."""
        log.warning("Board", "unarchive_issue não implementado neste adapter")


class Board:
    """Core de boards - usa port para operações."""

    def __init__(self, port: BoardPort):
        self._port = port

    def connect(self, config: dict):
        self._port.connect(config)

    def sync_boards(self, config: dict):
        """Extrai boards do config e sincroniza via port."""
        boards = []
        for board_id, board_cfg in config.get("boards", {}).items():
            if board_id == "platform":
                continue
            columns = list(board_cfg.get("columns", {}).keys())
            boards.append({
                "id": board_id,
                "name": board_cfg.get("name"),
                "columns": columns
            })
        # Ordena por prioridade
        boards.sort(key=lambda b: config["boards"][b["id"]].get("priority", 999))
        self._port.sync_boards(boards)

    def list_issues(self, board_id: str) -> list[Issue]:
        return self._port.list_issues(board_id)

    def list_issues_since(self, board_id: str, since: str) -> list[Issue]:
        return self._port.list_issues_since(board_id, since)

    def get_issue(self, board_id: str, issue_id: str) -> Issue:
        return self._port.get_issue(board_id, issue_id)

    def create_issue(self, board_id: str, title: str, body: str, column: str) -> Issue:
        return self._port.create_issue(board_id, title, body, column)

    def move_issue(self, board_id: str, issue_id: str, column: str, from_column: str = None):
        self._port.move_issue(board_id, issue_id, column, from_column)

    def update_issue(self, board_id: str, issue_id: str, title: str = None, body: str = None):
        self._port.update_issue(board_id, issue_id, title, body)

    def add_comment(self, board_id: str, issue_id: str, comment: str):
        self._port.add_comment(board_id, issue_id, comment)

    def list_comments(self, board_id: str, issue_id: str) -> list[dict]:
        return self._port.list_comments(board_id, issue_id)

    def close_issue(self, board_id: str, issue_id: str):
        self._port.close_issue(board_id, issue_id)

    def reopen_issue(self, board_id: str, issue_id: str):
        self._port.reopen_issue(board_id, issue_id)

    def set_labels(self, board_id: str, issue_id: str, labels: list[str]):
        self._port.set_labels(board_id, issue_id, labels)

    def add_label(self, board_id: str, issue_id: str, label: str):
        self._port.add_label(board_id, issue_id, label)

    def remove_label(self, board_id: str, issue_id: str, label: str):
        self._port.remove_label(board_id, issue_id, label)

    def set_parent(self, board_id: str, issue_id: str, parent_id: str | None):
        self._port.set_parent(board_id, issue_id, parent_id)

    def set_children(self, board_id: str, issue_id: str, children_ids: list[str]):
        self._port.set_children(board_id, issue_id, children_ids)

    def set_blocked_by(self, board_id: str, issue_id: str, blocker_ids: list[str]):
        self._port.set_blocked_by(board_id, issue_id, blocker_ids)

    def set_blocks(self, board_id: str, issue_id: str, blocked_ids: list[str]):
        self._port.set_blocks(board_id, issue_id, blocked_ids)

    def archive_issue(self, board_id: str, issue_id: str):
        self._port.archive_issue(board_id, issue_id)

    def unarchive_issue(self, board_id: str, issue_id: str):
        self._port.unarchive_issue(board_id, issue_id)

    def apply_commands(self, board_id: str, issue_id: str, cmds) -> None:
        """Aplica os comandos anotados (IssueCommands) como atributos no board.

        Filosofia presença/ausência: o estado enviado reflete exatamente o que
        está declarado. Labels usam SET (substitui todas), incluindo a label
        especial need_human via all_labels().
        """
        # Labels (SET completo, inclui need_human como label comum no board)
        self.set_labels(board_id, issue_id, cmds.all_labels())

        # Relações hierárquicas
        self.set_parent(board_id, issue_id, cmds.parent)
        self.set_children(board_id, issue_id, cmds.children)

        # Dependências
        self.set_blocked_by(board_id, issue_id, cmds.blocked_by)
        self.set_blocks(board_id, issue_id, cmds.blocks)

        # Arquivamento (presença arquiva; ausência desarquiva)
        if cmds.archive:
            self.archive_issue(board_id, issue_id)
        else:
            self.unarchive_issue(board_id, issue_id)

        # Fechamento / reabertura
        # (close presente fecha; reopen presente reabre; ausência de ambos
        #  não altera o estado open/closed)
        if cmds.close:
            self.close_issue(board_id, issue_id)
        elif cmds.reopen:
            self.reopen_issue(board_id, issue_id)

    def apply_column_events(self, board_id: str, issue_id: str, events: list[str]) -> None:
        """Aplica eventos de coluna (on_in/on_out).

        Cada token do array é interpretado:
          'close'          -> fecha a issue
          'open'           -> reabre (se fechada) e desarquiva (se arquivada)
          'archive'        -> arquiva o item no project
          '-archive'       -> desarquiva o item no project
          'need_human'     -> adiciona a label especial need_human
          '-need_human'    -> remove a label need_human
          '<label>'        -> adiciona a label
          '-<label>'       -> remove a label
        """
        from src.core.commands import NEED_HUMAN_LABEL

        for raw in events or []:
            token = str(raw).strip()
            if not token:
                continue

            if token == "close":
                self.close_issue(board_id, issue_id)
            elif token == "open":
                self.reopen_issue(board_id, issue_id)
                self.unarchive_issue(board_id, issue_id)
            elif token == "archive":
                self.archive_issue(board_id, issue_id)
            elif token == "-archive":
                self.unarchive_issue(board_id, issue_id)
            elif token == "need_human":
                self.add_label(board_id, issue_id, NEED_HUMAN_LABEL)
            elif token == "-need_human":
                self.remove_label(board_id, issue_id, NEED_HUMAN_LABEL)
            elif token.startswith("-"):
                self.remove_label(board_id, issue_id, token[1:])
            else:
                self.add_label(board_id, issue_id, token)

    def board_ids(self, config: dict) -> list[str]:
        """Retorna os ids dos boards configurados (ignora 'platform')."""
        return [bid for bid in config.get("boards", {}) if bid != "platform"]

    def detect_board_changes(self, board_id: str, snapshot, queue) -> int:
        """Detecta mudanças de um board comparando com o snapshot e registra na fila.

          - issue no board sem correspondência no snapshot  -> create-down
          - issue no snapshot (com id) ausente no board      -> delete-down
          - issue com updated_at no board > snapshot         -> change-down

        Atualiza snapshot.last_board_update com a data mais recente.
        Atualiza status das issues no snapshot conforme o evento detectado.
        Retorna a quantidade de itens efetivamente adicionados à fila.
        """
        remote_issues = self._port.list_issues(board_id)
        remote_by_id = {str(i.id): i for i in remote_issues}

        snapshot_issues = snapshot.issues
        snapshot_by_id = {
            str(i["id"]): i for i in snapshot_issues if i.get("id") is not None
        }

        added = 0
        max_updated = snapshot.last_board_update or ""

        # Criadas ou modificadas no board
        for issue in remote_issues:
            issue_id = str(issue.id)
            known = snapshot_by_id.get(issue_id)

            if issue.updated_at and issue.updated_at > max_updated:
                max_updated = issue.updated_at

            if known is None:
                if queue.add(ChangeItem.of(SyncEvent.CREATE_DOWN, id=issue_id, board=board_id)):
                    added += 1
                continue

            remote_at = issue.updated_at or ""
            snap_at = known.get("updated_at") or ""
            changed = (remote_at and snap_at and remote_at > snap_at) or \
                      (issue.column and issue.column != known.get("column"))
            if changed:
                if queue.add(ChangeItem.of(SyncEvent.CHANGE_DOWN, id=issue_id, board=board_id)):
                    known["status"] = SyncEvent.CHANGE_DOWN.value
                    added += 1

        # Deletadas no board (existiam no snapshot com id, sumiram do board)
        for issue_id in snapshot_by_id:
            if issue_id not in remote_by_id:
                if queue.add(ChangeItem.of(SyncEvent.DELETE_DOWN, id=issue_id, board=board_id)):
                    snapshot_by_id[issue_id]["status"] = SyncEvent.DELETE_DOWN.value
                    added += 1

        if max_updated:
            snapshot.last_board_update = max_updated
        snapshot.save()

        return added
