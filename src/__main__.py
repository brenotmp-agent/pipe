from src.core.log import log
from src.core.config import check_config as validate_config, ConfigError, SSH_KEY_ENV
from src.core.board import Board, PenaltyException, BoardAccessError
from src.core.snapshot import Snapshot
from src.core.change_queue import ChangeQueue, QUEUE_FILE
from src.core.sync import sync_remote, detect_local_changes, apply_changes
from src.core.version import VERSION
from src.adapters.github_board import GitHubBoardAdapter
from pathlib import Path
from datetime import datetime, timedelta
import subprocess
import shutil
import os
import time

REPO_DIR = Path("repo")
SSH_DIR = Path.home() / ".ssh"

board: Board = None

ADAPTERS = {
    "github": GitHubBoardAdapter,
}


def check_config():
    log.info("Config", "Validando pipe.yml")
    try:
        config = validate_config()
        log.configure(config)
        log.cleanup()
        log.info("Config", "pipe.yml válido")
        return config
    except ConfigError as e:
        log.error("Config", str(e))
        raise SystemExit(1)


def _setup_ssh():
    SSH_DIR.mkdir(mode=0o700, exist_ok=True)
    key_file = SSH_DIR / "id_pipe"
    source_key = Path(os.environ[SSH_KEY_ENV]).expanduser()
    key_file.write_bytes(source_key.read_bytes())
    key_file.chmod(0o600)
    
    # Configura SSH para usar essa chave no github
    ssh_config = SSH_DIR / "config"
    config_block = "\nHost github.com\n  IdentityFile ~/.ssh/id_pipe\n  StrictHostKeyChecking no\n"
    if ssh_config.exists():
        content = ssh_config.read_text()
        if "id_pipe" not in content:
            ssh_config.write_text(content + config_block)
    else:
        ssh_config.write_text(config_block)


def startup(config: dict):
    log.info("Startup", "Verificando repositórios")
    _setup_ssh()
    REPO_DIR.mkdir(exist_ok=True)

    # Limpa a fila de mudanças de execuções anteriores
    if QUEUE_FILE.exists():
        log.info("Startup", "Removendo fila de mudanças anterior")
        QUEUE_FILE.unlink()

    expected = set(config["git"]["repo"].keys())
    existing = {d.name for d in REPO_DIR.iterdir() if d.is_dir()}
    
    # Clonar faltantes
    for repo_id in expected - existing:
        url = config["git"]["repo"][repo_id]
        log.info("Startup", f"Clonando {repo_id}")
        subprocess.run(["git", "clone", url, repo_id], cwd=REPO_DIR, check=True)
    
    # Remover extras
    for repo_id in existing - expected:
        log.info("Startup", f"Removendo {repo_id}")
        shutil.rmtree(REPO_DIR / repo_id)


def board_full_sync(config: dict):
    global board
    log.info("Board", "Sincronizando estrutura local")

    # Criar diretórios e sincronizar snapshot local por board
    for board_id in board.board_ids(config):
        board_cfg = config["boards"][board_id]
        columns = board_cfg.get("columns", {})

        # Criar diretórios .pipe/boards/<board_id>/<col_id>
        board_dir = Path(".pipe/boards") / board_id
        board_dir.mkdir(parents=True, exist_ok=True)
        for col_id in columns:
            (board_dir / col_id).mkdir(exist_ok=True)

        # Sincronizar snapshot local (estrutura de colunas)
        snap = Snapshot(board_id).load()
        snap.board = {col_id: col["name"] for col_id, col in columns.items()}
        snap.save()

    # Sync online
    log.info("Board", "Sincronizando boards remotos")
    attempt = 0
    while True:
        try:
            attempt += 1
            if attempt > 1:
                log.info("Board", f"Sincronizando boards remotos - tentativa {attempt}")
            board.sync_boards(config)
            break
        except PenaltyException as e:
            back_at = (datetime.now() + timedelta(seconds=e.wait_seconds)).strftime('%H:%M:%S')
            log.warning("Board", f"Rate limit - retorna às {back_at}")
            time.sleep(e.wait_seconds)

    # Recuperar issues com status pendente (sistema caiu antes de processar)
    queue = ChangeQueue()
    recovered = 0
    for board_id in board.board_ids(config):
        snap = Snapshot(board_id).load()
        for issue in snap.issues:
            status = issue.get("status", "ok")
            if status != "ok":
                from src.core.board import ChangeItem
                item = ChangeItem.of(status, id=issue.get("id"),
                                     board=board_id)
                if queue.add(item):
                    recovered += 1
    if recovered:
        log.info("Board", f"{recovered} item(ns) recuperado(s) de execução anterior")

    # Detectar mudanças remotas
    log.info("Board", "Detectando mudanças remotas")
    total = 0
    for board_id in board.board_ids(config):
        snap = Snapshot(board_id).load()
        attempt = 0
        while True:
            try:
                attempt += 1
                log.info("Board", f"Analisando board '{board_id}'"
                         + (f" - tentativa {attempt}" if attempt > 1 else ""))
                total += board.detect_board_changes(board_id, snap, queue)
                break
            except PenaltyException as e:
                back_at = (datetime.now() + timedelta(seconds=e.wait_seconds)).strftime('%H:%M:%S')
                log.warning("Board", f"Rate limit em '{board_id}' - retorna às {back_at}")
                time.sleep(e.wait_seconds)
    log.info("Board", f"{total} mudança(s) remota(s) adicionada(s) à fila")


def sync_board(config: dict) -> bool:
    """Sincroniza boards e retorna True se houve qualquer movimentação.

    Boards são processados em ordem de prioridade (menor = mais prioritário).
    Se um board apresenta mudanças (up ou down), processa-o e não avança para
    os seguintes — garante que o board mais prioritário com trabalho pendente
    seja resolvido primeiro.

    Penalty dentro do sync não propaga - apenas interrompe o sync do board
    afetado e prossegue para que tasks já disponíveis possam ser executadas.
    """
    global board
    queue = ChangeQueue()
    had_changes = False

    boards_cfg = config["boards"]
    boards_sorted = sorted(
        ((bid, boards_cfg[bid]) for bid in board.board_ids(config)),
        key=lambda x: x[1].get("priority", 999),
    )

    for board_id, _ in boards_sorted:
        try:
            sync_remote(board_id, board, queue)
        except PenaltyException:
            log.warning("Sync", f"[{board_id}] Penalty no sync remoto - pulando board")
            continue

        detect_local_changes(board_id, queue)

        # Se há itens na fila para este board, houve movimentação
        board_had_changes = queue.has_board(board_id)
        if board_had_changes:
            had_changes = True

        try:
            apply_changes(board_id, board, queue, config)
        except PenaltyException:
            log.warning("Sync", f"[{board_id}] Penalty no apply - saindo do sync")
            break

        # Se houve mudanças neste board, não avança para os menos prioritários
        if board_had_changes:
            break

    return had_changes


def keep_task(config: dict) -> dict | None:
    """Seleciona a próxima tarefa elegível para execução.

    Lógica:
    - Boards ordenados por prioridade (menor = mais prioritário)
    - Issues ordenadas por created_at (mais antiga primeiro)
    - Se issue está em 'todo', faz auto-advance local e retorna None (espera sync)
    - Elegível se: status=='ok', coluna tem 'agent', coluna tem 'change.advance'
    - parallel:false → bloqueia auto-advance se já existe issue ativa
    - /need_human ou /blocked_by no body → bloqueada
    """
    boards_cfg = config["boards"]
    boards_sorted = sorted(
        ((bid, bcfg) for bid, bcfg in boards_cfg.items() if bid != "platform"),
        key=lambda x: x[1].get("priority", 999),
    )

    for board_id, board_cfg in boards_sorted:
        snap = Snapshot(board_id).load()
        columns = board_cfg.get("columns", {})
        todo_col = board_cfg.get("todo")
        issues = [i for i in snap.issues if i.get("id") and i.get("status") == "ok"]

        # parallel:false → bloquear auto-advance se issue ativa fora de todo/terminais
        block_auto_advance = False
        if board_cfg.get("parallel") is False:
            terminal = {col_id for col_id, col in columns.items() if col.get("archive")}
            inactive = (terminal | {todo_col}) if todo_col else terminal
            block_auto_advance = any(i["column"] not in inactive for i in issues)

        # Ordenar por created_at (campo pode não existir)
        issues.sort(key=lambda i: i.get("created_at") or i.get("updated_at") or "")

        for issue in issues:
            col_id = issue["column"]

            # Auto-advance do todo
            if todo_col and col_id == todo_col:
                if block_auto_advance:
                    continue
                advance_col = columns.get(todo_col, {}).get("change", {}).get("advance")
                if advance_col:
                    _auto_advance(board_id, issue, advance_col, snap)
                    return None
                continue

            col = columns.get(col_id, {})
            if not col.get("agent"):
                continue
            if not col.get("change", {}).get("advance"):
                continue
            if _is_blocked(issue):
                continue

            log.info("KeepTask", f"[{board_id}] #{issue['id']} selecionada em '{col_id}'")
            return {
                "board_id": board_id,
                "issue": issue,
                "column": col,
                "col_id": col_id,
                "board": board_cfg,
            }

    return None


def _is_blocked(issue: dict) -> bool:
    """Verifica se a issue está bloqueada via comandos no body.

    Bloqueada se: tem /need_human, ou tem /blocked_by com pelo menos uma issue.
    """
    body_path = Path(issue.get("body_path", ""))
    if not body_path.exists():
        return False
    content = body_path.read_text(encoding="utf-8")
    # Remove a primeira linha (título) e faz parse do bloco @---
    raw_body = content.split("\n", 1)[1] if "\n" in content else ""
    from src.core.commands import split_body
    _, cmds = split_body(raw_body)
    return cmds.need_human or bool(cmds.blocked_by)


def _auto_advance(board_id: str, issue: dict, target_col: str, snap: Snapshot):
    """Move issue do todo para a próxima coluna localmente."""
    old_col = issue["column"]
    old_path = Path(issue["body_path"])
    new_dir = Path(".pipe/boards") / board_id / target_col
    new_dir.mkdir(parents=True, exist_ok=True)

    # Mover os 3 arquivos
    stem = old_path.stem.rsplit("-body", 1)[0]
    for suffix in ("-body.md", "-history.md", "-addcomment.md"):
        src = old_path.parent / f"{stem}{suffix}"
        dst = new_dir / f"{stem}{suffix}"
        if src.exists():
            src.rename(dst)

    log.info("KeepTask", f"[{board_id}] auto-advance #{issue['id']}: {old_col} → {target_col}")


def call_agent(config: dict, task: dict | None):
    if not task:
        return
    board_id = task["board_id"]
    col_id = task["col_id"]
    col = task["column"]
    issue = task["issue"]

    from src.core.agent import (AgentParams, build_prompt,
                                resolve_agent_id, resolve_repo_id,
                                resolve_work_dir)
    from src.adapters.kiro_cli_agent import KiroCliAgent
    from src.core.config import CONTEXTS_DIR

    agent_id = resolve_agent_id(col, issue)
    # Resolver plataforma e config do agente
    agents_cfg = config.get("agents", {})
    platform = None
    agent_cfg = {}
    for platform_id, platform_agents in agents_cfg.items():
        if agent_id in platform_agents:
            platform = platform_id
            agent_cfg = platform_agents[agent_id]
            break

    if not platform:
        log.warning("Agent", f"Agente '{agent_id}' não encontrado na config")
        return

    # Resolução de model (definido na config do agente)
    model = agent_cfg.get("model", "")

    board_cfg = task["board"]
    repo_id = resolve_repo_id(config, board_cfg)
    work_dir = resolve_work_dir(config, board_cfg)

    prompt = build_prompt(config, task)

    params = AgentParams(
        platform=platform,
        agent_id=agent_id,
        agent_name=agent_cfg.get("name", agent_id),
        model=model,
        issue_id=issue["id"],
        board_id=board_id,
        col_id=col_id,
        prompt=prompt,
        work_dir=str(work_dir),
        repo_id=repo_id,
    )

    adapter = KiroCliAgent()
    adapter.execute(params)


def sleep_time(config: dict, had_changes: bool, task: dict | None):
    """Dorme pelo tempo configurado quando não há atividade.

    Ativa sleep apenas se sync_board não movimentou nada E keep_task não
    encontrou tarefa elegível.
    """
    if had_changes or task is not None:
        return
    seconds = config["sleep"]
    back_at = (datetime.now() + timedelta(seconds=seconds)).strftime('%H:%M:%S')
    log.info("Sleep", f"Nenhuma atividade - dormindo {seconds}s (retorna às {back_at})")
    time.sleep(seconds)


_BANNER = r"""
 _____ ____ _____ _____ ___ ____      _
| ____/ ___|_   _| ____|_ _|  _ \   / \
|  _| \___ \ | | |  _|  | || |_) | / _ \
| |___ ___) || | | |___ | ||  _ < / ___ \
|_____|____/ |_| |_____|___|_| \_/_/   \_\
"""


def main():
    global board
    print(_BANNER)
    log.separator()
    log.info("Pipe", f"Iniciando esteira agêntica v{VERSION}")

    config = check_config()
    startup(config)
    
    platform = config["boards"]["platform"]
    if platform not in ADAPTERS:
        log.error("Config", f"Plataforma '{platform}' não suportada. Use: {list(ADAPTERS.keys())}")
        raise SystemExit(1)
    
    adapter = ADAPTERS[platform]()
    board = Board(adapter)
    board.connect(config)

    # Gate de permissões: não inicia a esteira sem poder operar o repositório.
    try:
        board.check_access(config)
    except BoardAccessError as e:
        log.error("Startup", f"Permissões insuficientes - esteira não iniciada: {e}")
        raise SystemExit(1)

    board_full_sync(config)
    last_full_sync = datetime.now().date()

    log.info("Pipe", "Esteira agêntica iniciada")
    running = True
    while running:
        try:
            today = datetime.now().date()
            if today != last_full_sync:
                board_full_sync(config)
                last_full_sync = today

            had_changes = sync_board(config)
            queue = ChangeQueue()
            if not had_changes and queue.size() == 0:
                task = keep_task(config)
                call_agent(config, task)
                sleep_time(config, had_changes, task)
        except PenaltyException as e:
            # Penalty escapou do sync (board_full_sync) - não há tasks locais, esperar
            back_at = (datetime.now() + timedelta(seconds=e.wait_seconds)).strftime('%H:%M:%S')
            log.warning("Pipe", f"Penalty (pré-sync) - aguardando até {back_at}")
            time.sleep(e.wait_seconds)
        except KeyboardInterrupt:
            log.info("Pipe", "Interrompido pelo usuário")
            running = False
        except Exception as e:
            log.error("Pipe", f"Erro no ciclo (não fatal): {e}")
            time.sleep(config.get("sleep", 60))


if __name__ == "__main__":
    main()
