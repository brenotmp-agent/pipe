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
            if queue.add(ChangeItem.of(SyncEvent.CREATE_DOWN, id=issue_id, board=board_id)):
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
                _apply_create_up(board_id, item, board_obj)
            elif item.event == SyncEvent.CREATE_DOWN.value:
                _apply_create_down(board_id, item, board_obj)
            elif item.event == SyncEvent.CHANGE_UP.value:
                _apply_change_up(board_id, item, board_obj, config)
            elif item.event == SyncEvent.CHANGE_DOWN.value:
                _apply_change_down(board_id, item, board_obj, config)
            elif item.event == SyncEvent.DELETE_UP.value:
                _apply_delete_up(board_id, item, board_obj)
            elif item.event == SyncEvent.DELETE_DOWN.value:
                _apply_delete_down(board_id, item, board_obj)

            queue.remove(item.uuid)
        except PenaltyException:
            log.warning("Sync", f"[{board_id}] Penalty - abandonando apply_changes")
            return


def _apply_create_up(board_id: str, item: ChangeItem, board_obj: Board):
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

    # Aplicar comandos (labels, relações, etc) como atributos no board
    if not cmds.is_empty():
        board_obj.apply_commands(board_id, created.id, cmds)

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
    snap.save()


def _apply_create_down(board_id: str, item: ChangeItem, board_obj: Board):
    """Cria arquivos locais a partir do issue no board."""
    snap = Snapshot(board_id).load()
    issue = board_obj.get_issue(board_id, item.id)
    remote_full = board_obj.list_issues(board_id)
    # Obter coluna do issue
    column = ""
    for ri in remote_full:
        if str(ri.id) == str(item.id):
            column = ri.column
            break

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
    snap.issues.append({
        "id": item.id,
        "column": column,
        "body_path": str(files["body"]),
        "body_mtime": str(files["body"].stat().st_mtime),
        "updated_at": issue.updated_at,
        "status": "ok",
    })
    snap.save()


def _apply_change_up(board_id: str, item: ChangeItem, board_obj: Board, config: dict = None):
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

    # Aplicar comandos como estado autoritativo. Mesmo bloco vazio é aplicado:
    # ausência de um comando significa remoção (SET/presença-ausência).
    board_obj.apply_commands(board_id, item.id, cmds)

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

    log.info("Sync", f"[{board_id}] change-up #{item.id} -> {current_col}",
             issue_id=item.id, column=current_col)

    # Atualizar snapshot
    issue_data["body_path"] = str(body_path)
    issue_data["body_mtime"] = str(body_path.stat().st_mtime)
    issue_data["status"] = "ok"
    snap.save()


def _apply_change_down(board_id: str, item: ChangeItem, board_obj: Board, config: dict = None):
    """Propaga mudança do board para local."""
    snap = Snapshot(board_id).load()
    issue_data = snap.issue(item.id)
    if not issue_data:
        return

    old_col = issue_data.get("column")
    issue = board_obj.get_issue(board_id, item.id)
    remote_full = board_obj.list_issues(board_id)
    remote_col = ""
    for ri in remote_full:
        if str(ri.id) == str(item.id):
            remote_col = ri.column
            break

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

    # Atualizar snapshot
    issue_data["column"] = current_col
    issue_data["body_path"] = str(body_path)
    issue_data["body_mtime"] = str(body_path.stat().st_mtime)
    issue_data["updated_at"] = issue.updated_at
    issue_data["status"] = "ok"
    snap.save()

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
