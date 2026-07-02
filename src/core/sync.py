"""Sync core - sincronização entre local e board remoto."""

import re
from pathlib import Path

from src.core.board import Board, ChangeItem, Issue, PenaltyException, SyncEvent
from src.core.change_queue import ChangeQueue
from src.core.commands import apply_events_to_commands, compose_body, from_issue, split_body
from src.core.log import log
from src.core.snapshot import BOARDS_DIR, Snapshot


def _slugify(text: str) -> str:
    """Converte texto para slug filesystem-safe."""
    import unicodedata
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", text)


def _issue_files(board_id: str, col_id: str, issue_id: str, slug: str) -> dict:
    """Retorna paths dos 3 arquivos de uma issue."""
    base = BOARDS_DIR / board_id / col_id
    prefix = f"{issue_id}-{slug}"
    return {
        "body": base / f"{prefix}-body.md",
        "history": base / f"{prefix}-history.md",
        "addcomment": base / f"{prefix}-addcomment.md",
    }


def _find_issue_files(board_id: str, issue_id: str) -> Path | None:
    """Encontra o arquivo body de uma issue em qualquer coluna do board."""
    board_dir = BOARDS_DIR / board_id
    if not board_dir.exists():
        return None
    for body_file in board_dir.rglob(f"{issue_id}-*-body.md"):
        return body_file
    return None


def _col_from_path(file_path: Path, board_id: str) -> str:
    """Extrai col_id do path do arquivo."""
    # .pipe/boards/<board_id>/<col_id>/<file>
    return file_path.parent.name


def _fire_column_events(board_id: str, issue_id: str, board_obj: Board,
                        config: dict, old_col: str, new_col: str) -> None:
    """Dispara eventos on_out (coluna de origem) e on_in (coluna de destino)."""
    if not config:
        return
    columns = (config.get("boards", {}).get(board_id, {}) or {}).get("columns", {})

    out_events = (columns.get(old_col, {}) or {}).get("on_out") if old_col else None
    if out_events:
        log.info("Sync", f"[{board_id}] #{issue_id} on_out '{old_col}': {out_events}")
        board_obj.apply_column_events(board_id, issue_id, out_events)

    in_events = (columns.get(new_col, {}) or {}).get("on_in") if new_col else None
    if in_events:
        log.info("Sync", f"[{board_id}] #{issue_id} on_in '{new_col}': {in_events}")
        board_obj.apply_column_events(board_id, issue_id, in_events)


def _compose_down_body(issue: Issue) -> str:
    """Monta o conteúdo do arquivo body no fluxo down.

    Formato: '# {title}\n\n{body_limpo}' + bloco @--- de comandos derivado do
    estado real da issue no board (relações, labels, need_human).
    O body vindo do board é limpo de qualquer bloco @--- pré-existente para
    evitar duplicação, e os comandos autoritativos da API são reescritos.
    """
    clean_body, _ = split_body(issue.body or "")
    cmds = from_issue(issue)
    full = compose_body(clean_body, cmds)
    return f"# {issue.title}\n\n{full}\n"


# ══════════════════════════════════════════════════════════════════════════════
# Estado conhecido no snapshot + gatilho de par recíproco (dependências)
# ══════════════════════════════════════════════════════════════════════════════

# Mapa de relação -> relação recíproca no alvo.
# Se X.parent = Y      então Y.children contém X
# Se X.children ∋ Y     então Y.parent = X
# Se X.blocked_by ∋ Y   então Y.blocks contém X
# Se X.blocks ∋ Y       então Y.blocked_by contém X
_RECIPROCAL = {
    "parent": "children",
    "children": "parent",
    "blocked_by": "blocks",
    "blocks": "blocked_by",
}


def _empty_state() -> dict:
    """Estado conhecido vazio (para issues recém-criadas, sem baseline)."""
    return {
        "labels": [], "parent": None, "children": [],
        "blocked_by": [], "blocks": [], "archived": False, "state": "open",
    }


def _known_state(issue_data: dict) -> dict:
    """Extrai o estado conhecido (para diff) de um registro de snapshot."""
    if not issue_data:
        return _empty_state()
    return {
        "labels": list(issue_data.get("labels") or []),
        "parent": issue_data.get("parent"),
        "children": list(issue_data.get("children") or []),
        "blocked_by": list(issue_data.get("blocked_by") or []),
        "blocks": list(issue_data.get("blocks") or []),
        "archived": bool(issue_data.get("archived")),
        "state": (issue_data.get("state") or "open"),
    }


def _write_state_from_cmds(issue_data: dict, cmds) -> None:
    """Grava no snapshot o estado desejado declarado nos comandos (fluxo up)."""
    issue_data["labels"] = cmds.all_labels()
    issue_data["parent"] = str(cmds.parent) if cmds.parent else None
    issue_data["children"] = [str(c) for c in (cmds.children or [])]
    issue_data["blocked_by"] = [str(b) for b in (cmds.blocked_by or [])]
    issue_data["blocks"] = [str(b) for b in (cmds.blocks or [])]
    issue_data["archived"] = bool(cmds.archive)
    if cmds.close:
        issue_data["state"] = "closed"
    elif cmds.reopen:
        issue_data["state"] = "open"


def _write_state_from_issue(issue_data: dict, issue, fullsync: bool) -> None:
    """Grava no snapshot o estado real vindo do board (fluxo down).

    Sempre grava labels/parent/children/archived/state (chamada única).
    blocked_by/blocks só são sobrescritos em fullsync (senão preserva o que já
    havia no snapshot, pois deps não vêm na chamada única).
    """
    issue_data["labels"] = list(issue.labels or [])
    issue_data["parent"] = issue.parent
    issue_data["children"] = list(issue.children or [])
    issue_data["archived"] = bool(getattr(issue, "archived", False))
    issue_data["state"] = (issue.state or "open")
    if fullsync:
        issue_data["blocked_by"] = list(issue.blocked_by or [])
        issue_data["blocks"] = list(issue.blocks or [])


def _find_snapshot_issue(target_id: str) -> tuple[str, dict] | None:
    """Localiza o registro de snapshot de uma issue em qualquer board.

    Retorna (board_id, issue_data) ou None se a issue não é rastreada.
    """
    if not BOARDS_DIR.exists():
        return None
    for snap_file in BOARDS_DIR.glob("*/snapshot.json"):
        board_id = snap_file.parent.name
        snap = Snapshot(board_id).load()
        data = snap.issue(target_id)
        if data is not None:
            return board_id, data
    return None


def _reciprocates(target_data: dict, reciprocal_rel: str, source_id: str) -> bool:
    """True se o snapshot do alvo já reflete o par recíproco apontando p/ source."""
    source_id = str(source_id)
    if reciprocal_rel == "parent":
        return str(target_data.get("parent") or "") == source_id
    return source_id in {str(x) for x in (target_data.get(reciprocal_rel) or [])}


def _trigger_reciprocal_downs(source_id: str, deltas: dict, queue) -> None:
    """Enfileira down fullsync dos alvos cujo par recíproco está inconsistente.

    Para cada relação com alvos adicionados/removidos, checa o snapshot do
    alvo:
      - adicionado: enfileira se o alvo AINDA NÃO reciproca source (par a criar)
      - removido:   enfileira se o alvo AINDA reciproca source (par a desfazer)
    A checagem de par é a condição de parada: quando o alvo já está coerente,
    nada é enfileirado, evitando reação em cadeia infinita.
    """
    for rel, reciprocal_rel in _RECIPROCAL.items():
        change = deltas.get(rel) or {}
        for target_id in change.get("added", []):
            found = _find_snapshot_issue(str(target_id))
            if not found:
                continue  # alvo não rastreado - ignora
            t_board, t_data = found
            if not _reciprocates(t_data, reciprocal_rel, source_id):
                if queue.add(ChangeItem.of(SyncEvent.CHANGE_DOWN, id=str(target_id),
                                           board=t_board, fullsync=True)):
                    log.info("Sync", f"[{t_board}] #{target_id} down full (par {rel} "
                             f"adicionado por #{source_id})")
        for target_id in change.get("removed", []):
            found = _find_snapshot_issue(str(target_id))
            if not found:
                continue
            t_board, t_data = found
            if _reciprocates(t_data, reciprocal_rel, source_id):
                if queue.add(ChangeItem.of(SyncEvent.CHANGE_DOWN, id=str(target_id),
                                           board=t_board, fullsync=True)):
                    log.info("Sync", f"[{t_board}] #{target_id} down full (par {rel} "
                             f"removido por #{source_id})")


def _deps_deltas_from_snapshot(issue, issue_data: dict) -> dict:
    """Calcula deltas de blocked_by/blocks entre issue (board) e snapshot.

    Usado no fluxo down fullsync para disparar o gatilho de par recíproco.
    Retorna deltas só das relações de dependência (parent/children não mudam
    de forma reflexiva no down).
    """
    known_bb = {str(x) for x in (issue_data.get("blocked_by") or [])}
    known_bk = {str(x) for x in (issue_data.get("blocks") or [])}
    now_bb = {str(x) for x in (issue.blocked_by or [])}
    now_bk = {str(x) for x in (issue.blocks or [])}
    return {
        "blocked_by": {"added": list(now_bb - known_bb),
                       "removed": list(known_bb - now_bb)},
        "blocks": {"added": list(now_bk - known_bk),
                   "removed": list(known_bk - now_bk)},
    }


# ══════════════════════════════════════════════════════════════════════════════
# sync_remote - busca mudanças do board remoto desde last_board_update
# ══════════════════════════════════════════════════════════════════════════════

def sync_remote(board_id: str, board_obj: Board, queue: ChangeQueue):
    """Busca issues modificados desde last_board_update e enfileira mudanças."""
    snap = Snapshot(board_id).load()
    since = snap.last_board_update

    if not since:
        # Sem data anterior, usa detect_board_changes (full)
        board_obj.detect_board_changes(board_id, snap, queue)
        return

    remote_issues = board_obj.list_issues_since(board_id, since)
    snapshot_by_id = {str(i["id"]): i for i in snap.issues if i.get("id")}
    max_updated = since

    for issue in remote_issues:
        issue_id = str(issue.id)
        if issue.updated_at and issue.updated_at > max_updated:
            max_updated = issue.updated_at

        known = snapshot_by_id.get(issue_id)
        if known is None:
            # Create precisa de fullsync: monta o body com deps (from_issue) e
            # não há baseline no snapshot para preservá-las.
            if queue.add(ChangeItem.of(SyncEvent.CREATE_DOWN, id=issue_id,
                                       board=board_id, fullsync=True)):
                log.info("Sync", f"[{board_id}] #{issue_id} create-down")
        else:
            if queue.add(ChangeItem.of(SyncEvent.CHANGE_DOWN, id=issue_id, board=board_id)):
                known["status"] = SyncEvent.CHANGE_DOWN.value
                log.info("Sync", f"[{board_id}] #{issue_id} change-down")

    if max_updated != since:
        snap.last_board_update = max_updated
    snap.save()


# ══════════════════════════════════════════════════════════════════════════════
# detect_local_changes - descobre movimentos locais
# ══════════════════════════════════════════════════════════════════════════════

def detect_local_changes(board_id: str, queue: ChangeQueue):
    """Detecta criações, modificações e deleções locais."""
    snap = Snapshot(board_id).load()
    board_dir = BOARDS_DIR / board_id
    snapshot_by_id = {str(i["id"]): i for i in snap.issues if i.get("id")}

    # Scan de arquivos body locais
    local_bodies = {}  # id -> Path
    for body_file in board_dir.rglob("*-body.md"):
        match = re.match(r"^(\d+)-", body_file.name)
        if match:
            local_bodies[match.group(1)] = body_file
        elif body_file.name.count("-") >= 2:
            # Arquivo sem id numérico = issue criada localmente (sem id)
            body_path_str = str(body_file)
            # Verificar se já está no snapshot por body_path
            known = any(
                i.get("body_path") == body_path_str
                for i in snap.issues
            )
            if not known:
                if queue.add(ChangeItem.of(SyncEvent.CREATE_UP, identifier=body_path_str, board=board_id)):
                    snap.issues.append({
                        "id": None,
                        "column": _col_from_path(body_file, board_id),
                        "body_path": body_path_str,
                        "body_mtime": str(body_file.stat().st_mtime),
                        "status": SyncEvent.CREATE_UP.value,
                    })
                    log.info("Sync", f"[{board_id}] '{body_file.name}' create-up")

    # Para cada issue no snapshot com id, verificar mudanças
    for issue in snap.issues:
        issue_id = str(issue.get("id") or "")
        if not issue_id or issue.get("status") in (
            SyncEvent.CREATE_UP.value, SyncEvent.CREATE_DOWN.value,
            SyncEvent.DELETE_UP.value, SyncEvent.DELETE_DOWN.value,
            SyncEvent.CHANGE_DOWN.value,
        ):
            continue

        body_path = Path(issue.get("body_path", ""))
        local_file = local_bodies.get(issue_id)

        # Delete-up: body não encontrado em nenhum diretório
        if not local_file or not local_file.exists():
            if queue.add(ChangeItem.of(SyncEvent.DELETE_UP, id=issue_id, board=board_id)):
                issue["status"] = SyncEvent.DELETE_UP.value
                log.info("Sync", f"[{board_id}] #{issue_id} delete-up")
            continue

        # Change-up: mtime maior, coluna diferente, ou addcomment com conteúdo
        changed = False
        current_mtime = str(local_file.stat().st_mtime)
        stored_mtime = issue.get("body_mtime", "")

        if current_mtime > stored_mtime:
            changed = True

        current_col = _col_from_path(local_file, board_id)
        if current_col != issue.get("column"):
            changed = True

        # Verificar addcomment em qualquer diretório
        slug = local_file.stem.removesuffix("-body")
        for ac_file in board_dir.rglob(f"{slug}-addcomment.md"):
            if ac_file.exists() and ac_file.read_text(encoding="utf-8").strip():
                changed = True
                break

        if changed:
            if queue.add(ChangeItem.of(SyncEvent.CHANGE_UP, id=issue_id, board=board_id)):
                issue["status"] = SyncEvent.CHANGE_UP.value
                log.info("Sync", f"[{board_id}] #{issue_id} change-up")

    snap.save()


# ══════════════════════════════════════════════════════════════════════════════
# apply_changes - persiste mudanças da fila
# ══════════════════════════════════════════════════════════════════════════════

def apply_changes(board_id: str, board_obj: Board, queue: ChangeQueue, config: dict = None):
    """Consome a fila e aplica mudanças. Para no primeiro PenaltyException."""
    while True:
        item = queue.getNext()
        if not item or item.board != board_id:
            return

        try:
            if item.event == SyncEvent.CREATE_UP.value:
                _apply_create_up(board_id, item, board_obj, queue)
            elif item.event == SyncEvent.CREATE_DOWN.value:
                _apply_create_down(board_id, item, board_obj, queue)
            elif item.event == SyncEvent.CHANGE_UP.value:
                _apply_change_up(board_id, item, board_obj, queue, config)
            elif item.event == SyncEvent.CHANGE_DOWN.value:
                _apply_change_down(board_id, item, board_obj, queue, config)
            elif item.event == SyncEvent.DELETE_UP.value:
                _apply_delete_up(board_id, item, board_obj)
            elif item.event == SyncEvent.DELETE_DOWN.value:
                _apply_delete_down(board_id, item, board_obj)

            queue.remove(item.uuid)
        except PenaltyException:
            log.warning("Sync", f"[{board_id}] Penalty - abandonando apply_changes")
            return


def _apply_create_up(board_id: str, item: ChangeItem, board_obj: Board, queue: ChangeQueue = None):
    """Cria issue no board a partir do arquivo local."""
    snap = Snapshot(board_id).load()
    issue_data = next((i for i in snap.issues if i.get("body_path") == item.identifier), None)
    if not issue_data:
        return

    body_path = Path(issue_data["body_path"])
    if not body_path.exists():
        return

    content = body_path.read_text(encoding="utf-8")
    # Primeira linha = título
    lines = content.strip().splitlines()
    title = lines[0].lstrip("# ").strip() if lines else Path(item.identifier).stem
    raw_body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
    # Separar comandos do body real
    body, cmds = split_body(raw_body)
    column = issue_data["column"]

    created = board_obj.create_issue(board_id, title, body, column)
    log.info("Sync", f"[{board_id}] create-up '{title}' -> #{created.id}",
             issue_id=created.id, column=column)

    # Aplicar comandos (labels, relações, etc). Create parte de estado vazio:
    # known=_empty_state() garante que os deltas 'added' reflitam tudo que foi
    # declarado, e que os setters não façam GET redundante (nada existe ainda).
    deltas = {}
    if not cmds.is_empty():
        deltas = board_obj.apply_commands(board_id, created.id, cmds, known=_empty_state())

    # Verificar addcomment
    slug = body_path.stem.removesuffix("-body")
    ac_file = body_path.parent / f"{slug}-addcomment.md"
    if ac_file.exists() and ac_file.read_text(encoding="utf-8").strip():
        board_obj.add_comment(board_id, created.id, ac_file.read_text(encoding="utf-8").strip())
        ac_file.write_text("", encoding="utf-8")

    # Renomear arquivos com o id atribuído
    new_slug = _slugify(title)
    new_files = _issue_files(board_id, column, created.id, new_slug)
    new_files["body"].parent.mkdir(parents=True, exist_ok=True)
    body_path.rename(new_files["body"])

    # History
    comments = board_obj.list_comments(board_id, created.id)
    history_content = _format_history(comments)
    new_files["history"].write_text(history_content, encoding="utf-8")

    # Addcomment limpo
    new_files["addcomment"].write_text("", encoding="utf-8")

    # Remover arquivos antigos (history/addcomment do path anterior)
    old_history = body_path.parent / f"{slug}-history.md"
    old_ac = body_path.parent / f"{slug}-addcomment.md"
    if old_history.exists():
        old_history.unlink()
    if old_ac.exists():
        old_ac.unlink()

    # Atualizar snapshot
    issue_data["id"] = created.id
    issue_data["body_path"] = str(new_files["body"])
    issue_data["body_mtime"] = str(new_files["body"].stat().st_mtime)
    issue_data["updated_at"] = created.updated_at
    issue_data["status"] = "ok"
    # Gravar o estado desejado (declarado) como conhecido no snapshot ANTES de
    # disparar o gatilho, para que o alvo, ao reciprocar, encontre este vínculo.
    _write_state_from_cmds(issue_data, cmds)
    snap.save()

    # Gatilho de par recíproco sobre as relações recém-criadas.
    if queue is not None and deltas:
        _trigger_reciprocal_downs(created.id, deltas, queue)


def _apply_create_down(board_id: str, item: ChangeItem, board_obj: Board, queue: ChangeQueue = None):
    """Cria arquivos locais a partir do issue no board."""
    snap = Snapshot(board_id).load()
    issue = board_obj.get_issue(board_id, item.id, fullsync=item.fullsync)
    # Coluna já vem na chamada única de get_issue (projectItems/Status).
    column = issue.column or ""

    if not column:
        column = list(snap.board.keys())[0] if snap.board else ""

    slug = _slugify(issue.title)
    files = _issue_files(board_id, column, item.id, slug)
    files["body"].parent.mkdir(parents=True, exist_ok=True)

    # Body
    files["body"].write_text(_compose_down_body(issue), encoding="utf-8")

    # History
    comments = board_obj.list_comments(board_id, item.id)
    files["history"].write_text(_format_history(comments), encoding="utf-8")

    # Addcomment vazio
    files["addcomment"].write_text("", encoding="utf-8")

    log.info("Sync", f"[{board_id}] create-down #{item.id} '{issue.title}' -> {column}",
             issue_id=item.id, column=column)

    # Atualizar snapshot
    new_data = {
        "id": item.id,
        "column": column,
        "body_path": str(files["body"]),
        "body_mtime": str(files["body"].stat().st_mtime),
        "updated_at": issue.updated_at,
        "status": "ok",
    }
    _write_state_from_issue(new_data, issue, fullsync=item.fullsync)
    snap.issues.append(new_data)
    snap.save()

    # Gatilho de par recíproco: alvos de deps recém-descobertas no board.
    # Só em fullsync (única situação em que blocked_by/blocks vêm preenchidos).
    if queue is not None and item.fullsync:
        deltas = _deps_deltas_from_snapshot(issue, _empty_state())
        _trigger_reciprocal_downs(item.id, deltas, queue)


def _apply_change_up(board_id: str, item: ChangeItem, board_obj: Board,
                     queue: ChangeQueue = None, config: dict = None):
    """Propaga mudança local para o board."""
    snap = Snapshot(board_id).load()
    issue_data = snap.issue(item.id)
    if not issue_data:
        return

    body_path = _find_issue_files(board_id, item.id)
    if not body_path:
        return

    content = body_path.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    title = lines[0].lstrip("# ").strip() if lines else ""
    raw_body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
    # Separar comandos do body real
    body, cmds = split_body(raw_body)

    # Atualizar body/title no board (body limpo, sem o bloco @---)
    board_obj.update_issue(board_id, item.id, title=title, body=body)

    # Aplicar comandos como estado autoritativo, comparando contra o estado
    # conhecido (snapshot): só chama o setter do atributo que realmente mudou,
    # e passa o estado conhecido ao setter para evitar GETs redundantes.
    known = _known_state(issue_data)
    deltas = board_obj.apply_commands(board_id, item.id, cmds, known=known)

    # Verificar mudança de coluna
    current_col = _col_from_path(body_path, board_id)
    old_col = issue_data.get("column")
    if current_col != old_col:
        board_obj.move_issue(board_id, item.id, current_col, from_column=old_col)
        _fire_column_events(board_id, item.id, board_obj, config, old_col, current_col)
        issue_data["column"] = current_col

    # Verificar addcomment
    slug = body_path.stem.removesuffix("-body")
    ac_file = body_path.parent / f"{slug}-addcomment.md"
    if ac_file.exists():
        comment = ac_file.read_text(encoding="utf-8").strip()
        if comment:
            board_obj.add_comment(board_id, item.id, comment)
            ac_file.write_text("", encoding="utf-8")

    # Atualizar history
    comments = board_obj.list_comments(board_id, item.id)
    history_file = body_path.parent / f"{slug}-history.md"
    history_file.write_text(_format_history(comments), encoding="utf-8")

    col_label = f"{old_col} -> {current_col}" if old_col and old_col != current_col else f"-> {current_col}"
    log.info("Sync", f"[{board_id}] change-up #{item.id} {col_label}",
             issue_id=item.id, column=current_col, from_column=old_col)

    # Atualizar snapshot
    issue_data["body_path"] = str(body_path)
    issue_data["body_mtime"] = str(body_path.stat().st_mtime)
    issue_data["status"] = "ok"
    # Gravar o estado desejado como conhecido ANTES de disparar o gatilho.
    _write_state_from_cmds(issue_data, cmds)
    snap.save()

    # Gatilho de par recíproco sobre relações adicionadas/removidas.
    if queue is not None and deltas:
        _trigger_reciprocal_downs(item.id, deltas, queue)


def _apply_change_down(board_id: str, item: ChangeItem, board_obj: Board,
                       queue: ChangeQueue = None, config: dict = None):
    """Propaga mudança do board para local."""
    snap = Snapshot(board_id).load()
    issue_data = snap.issue(item.id)
    if not issue_data:
        return

    old_col = issue_data.get("column")
    issue = board_obj.get_issue(board_id, item.id, fullsync=item.fullsync)
    # Sem fullsync, deps (blocked_by/blocks) não vêm na chamada única. Para não
    # apagar o bloco de deps ao reescrever o body, preserva o que o snapshot já
    # conhece sobre as dependências desta issue.
    if not item.fullsync:
        issue.blocked_by = list(issue_data.get("blocked_by") or [])
        issue.blocks = list(issue_data.get("blocks") or [])
    # Coluna já vem na chamada única de get_issue (projectItems/Status).
    remote_col = issue.column or ""

    body_path = _find_issue_files(board_id, item.id)
    if not body_path:
        # Arquivos não existem, criar
        slug = _slugify(issue.title)
        col = remote_col or issue_data.get("column", "")
        files = _issue_files(board_id, col, item.id, slug)
        files["body"].parent.mkdir(parents=True, exist_ok=True)
        body_path = files["body"]

    # Atualizar body
    body_path.write_text(_compose_down_body(issue), encoding="utf-8")

    # Mover se coluna mudou
    current_col = _col_from_path(body_path, board_id)
    if remote_col and remote_col != current_col:
        slug = body_path.stem.removesuffix("-body")
        new_files = _issue_files(board_id, remote_col, item.id, slug.split("-", 1)[1] if "-" in slug else slug)
        new_files["body"].parent.mkdir(parents=True, exist_ok=True)
        body_path.rename(new_files["body"])
        # Mover history e addcomment
        old_hist = body_path.parent / f"{slug}-history.md"
        old_ac = body_path.parent / f"{slug}-addcomment.md"
        if old_hist.exists():
            old_hist.rename(new_files["history"])
        if old_ac.exists():
            old_ac.rename(new_files["addcomment"])
        body_path = new_files["body"]
        current_col = remote_col

    # Atualizar history
    slug = body_path.stem.removesuffix("-body")
    comments = board_obj.list_comments(board_id, item.id)
    history_file = body_path.parent / f"{slug}-history.md"
    history_file.write_text(_format_history(comments), encoding="utf-8")

    # Limpar addcomment
    ac_file = body_path.parent / f"{slug}-addcomment.md"
    ac_file.write_text("", encoding="utf-8")

    log.info("Sync", f"[{board_id}] change-down #{item.id} -> {current_col}",
             issue_id=item.id, column=current_col)

    # Gatilho de par recíproco: calcula deltas de deps ANTES de sobrescrever o
    # estado conhecido no snapshot. Só em fullsync (deps preenchidas).
    deps_deltas = None
    if queue is not None and item.fullsync:
        deps_deltas = _deps_deltas_from_snapshot(issue, issue_data)

    # Atualizar snapshot
    issue_data["column"] = current_col
    issue_data["body_path"] = str(body_path)
    issue_data["body_mtime"] = str(body_path.stat().st_mtime)
    issue_data["updated_at"] = issue.updated_at
    issue_data["status"] = "ok"
    # Gravar o estado real do board como conhecido ANTES de disparar o gatilho.
    _write_state_from_issue(issue_data, issue, fullsync=item.fullsync)
    snap.save()

    if deps_deltas:
        _trigger_reciprocal_downs(item.id, deps_deltas, queue)

    # Movimentação manual no board: aplicar on_out/on_in da mudança de coluna.
    # O snapshot NÃO é alterado aqui; reescrevemos o arquivo APÓS o body_mtime
    # já registrado, de modo que o próximo sync detecte a modificação local e
    # dispare um change-up — garantindo que status/labels subam para o board.
    if config and old_col and current_col and old_col != current_col:
        _bake_column_events(board_id, body_path, config, old_col, current_col)


def _bake_column_events(board_id: str, body_path: Path, config: dict,
                        old_col: str, new_col: str) -> None:
    """Reescreve o arquivo body aplicando on_out/on_in no bloco de comandos.

    Não toca no snapshot. Como o body_mtime já foi salvo, esta reescrita deixa
    o arquivo "mais novo" que o snapshot, fazendo o próximo sync tratá-lo como
    modificação local (change-up).
    """
    columns = (config.get("boards", {}).get(board_id, {}) or {}).get("columns", {})
    out_events = (columns.get(old_col, {}) or {}).get("on_out") or []
    in_events = (columns.get(new_col, {}) or {}).get("on_in") or []
    if not out_events and not in_events:
        return

    content = body_path.read_text(encoding="utf-8")
    first_nl = content.find("\n")
    header = content[:first_nl] if first_nl != -1 else content
    rest = content[first_nl + 1:] if first_nl != -1 else ""

    body, cmds = split_body(rest)
    apply_events_to_commands(cmds, out_events)
    apply_events_to_commands(cmds, in_events)

    new_content = f"{header}\n{compose_body(body, cmds)}\n"
    body_path.write_text(new_content, encoding="utf-8")
    log.info("Sync", f"[{board_id}] eventos de coluna aplicados localmente "
             f"({old_col} → {new_col}); change-up pendente",
             out_events=out_events, in_events=in_events)


def _apply_delete_up(board_id: str, item: ChangeItem, board_obj: Board):
    """Fecha issue no board (arquivo local já foi removido)."""
    board_obj.close_issue(board_id, item.id)

    snap = Snapshot(board_id).load()
    snap.issues = [i for i in snap.issues if str(i.get("id")) != str(item.id)]
    snap.save()

    log.info("Sync", f"[{board_id}] delete-up #{item.id} - issue fechada",
             issue_id=item.id)


def _apply_delete_down(board_id: str, item: ChangeItem, board_obj: Board):
    """Remove arquivos locais (issue foi removida do board)."""
    snap = Snapshot(board_id).load()

    # Remover arquivos
    body_path = _find_issue_files(board_id, item.id)
    if body_path:
        slug = body_path.stem.removesuffix("-body")
        for suffix in ("-body.md", "-history.md", "-addcomment.md"):
            f = body_path.parent / f"{slug}{suffix}"
            if f.exists():
                f.unlink()

    snap.issues = [i for i in snap.issues if str(i.get("id")) != str(item.id)]
    snap.save()

    log.info("Sync", f"[{board_id}] delete-down #{item.id} - arquivos removidos",
             issue_id=item.id)


def _format_history(comments: list[dict]) -> str:
    """Formata comentários para o arquivo history."""
    if not comments:
        return ""
    parts = []
    for c in comments:
        author = c.get("author", "?")
        body = c.get("body", "")
        date = c.get("date", "")
        if date:
            date = date.replace("T", " ").replace("Z", "")[:19]
        parts.append(f"## {author} - {date}\n\n{body}\n---")
    return "\n\n".join(parts) + "\n"
