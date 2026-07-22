"""Config core - carrega e valida pipe.yml."""

from pathlib import Path
import os
import yaml

PIPE_FILE = Path("pipe.yml")
SSH_KEY_ENV = "PIPE_SSH_KEY_FILE"


class ConfigError(Exception):
    """Erro de configuração do pipe.yml."""
    pass


def _require(data: dict, key: str, context: str):
    if key not in data:
        raise ConfigError(f"{context}: campo '{key}' é obrigatório")
    return data[key]


def _validate_env():
    key_path = os.environ.get(SSH_KEY_ENV, "").strip()
    if not key_path:
        raise ConfigError(
            "✗ SSH  variável PIPE_SSH_KEY_FILE não definida ou vazia\n"
            "    Causa:  o clone via SSH no arranque precisa saber onde está a chave privada.\n"
            "    Ação:   defina PIPE_SSH_KEY_FILE no serviço apontando para o secret montado.\n"
            "            ex.: PIPE_SSH_KEY_FILE=/run/secrets/ssh_key\n"
            "    Onde:   monte a chave como Docker secret (ver docker-compose / runbook)."
        )
    if not Path(key_path).expanduser().exists():
        raise ConfigError(
            f"✗ SSH  arquivo de chave não encontrado em {key_path}\n"
            "    Causa:  PIPE_SSH_KEY_FILE aponta para um caminho que não existe no container.\n"
            "    Ação:   confira se o secret/volume da chave está montado nesse caminho.\n"
            "    Onde:   seção 'secrets' do docker-compose (ver runbook)."
        )


def _validate_git(git: dict):
    _require(git, "repo", "git")
    _require(git, "flow", "git")
    
    flow = git["flow"]
    _require(flow, "base", "git.flow")
    
    for flow_id, flow_cfg in flow.items():
        if flow_id == "base":
            continue
        if "name" not in flow_cfg and "prefix" not in flow_cfg:
            raise ConfigError(f"git.flow.{flow_id}: requer 'name' ou 'prefix'")


CONTEXTS_DIR = Path("contexts")


def _validate_agents(agents: dict):
    empty = []
    for platform_id, platform in agents.items():
        for agent_id, agent_cfg in platform.items():
            _require(agent_cfg, "name", f"agents.{platform_id}.{agent_id}")
            # Garantir que o arquivo de contexto existe
            ctx_file = CONTEXTS_DIR / platform_id / f"{agent_id}.md"
            ctx_file.parent.mkdir(parents=True, exist_ok=True)
            if not ctx_file.exists():
                ctx_file.write_text("", encoding="utf-8")
            if not ctx_file.read_text(encoding="utf-8").strip():
                empty.append(str(ctx_file))
    if empty:
        raise ConfigError(
            "Arquivos de contexto vazios (preencha antes de executar):\n  - "
            + "\n  - ".join(empty)
        )


def _validate_boards(boards: dict, known_agents: set[str] | None = None):
    known_agents = known_agents or set()
    _require(boards, "platform", "boards")
    for board_id, board in boards.items():
        if board_id == "platform":
            continue
        _require(board, "name", f"boards.{board_id}")
        columns = _require(board, "columns", f"boards.{board_id}")
        
        for col_id, col in columns.items():
            _require(col, "name", f"boards.{board_id}.columns.{col_id}")
            for ev in ("on_in", "on_out"):
                if ev in col and not isinstance(col[ev], list):
                    raise ConfigError(
                        f"boards.{board_id}.columns.{col_id}.{ev}: deve ser uma lista"
                    )

            ctx = f"boards.{board_id}.columns.{col_id}"

            # Agente default da coluna deve existir
            agent = col.get("agent")
            if agent and known_agents and agent not in known_agents:
                raise ConfigError(f"{ctx}.agent: agente '{agent}' não definido em 'agents'")

            # override-agent: mapa nível → agente
            override = col.get("override-agent")
            if override is not None:
                if not isinstance(override, dict):
                    raise ConfigError(f"{ctx}.override-agent: deve ser um mapa <nível>: <agente>")
                if not col.get("agent"):
                    raise ConfigError(
                        f"{ctx}.override-agent: requer um 'agent' default na coluna"
                    )
                for level, ov_agent in override.items():
                    if known_agents and ov_agent not in known_agents:
                        raise ConfigError(
                            f"{ctx}.override-agent.{level}: agente '{ov_agent}' não definido em 'agents'"
                        )


def _validate_log(log_cfg: dict):
    ttl = log_cfg.get("ttl")
    if ttl is not None and (not isinstance(ttl, int) or ttl < 1):
        raise ConfigError("log.ttl: deve ser inteiro >= 1")


def _validate_sleep(sleep_val):
    """Valida campo sleep (segundos entre ciclos quando ocioso)."""
    if not isinstance(sleep_val, (int, float)) or sleep_val <= 0:
        raise ConfigError("sleep: deve ser número > 0 (segundos)")


def check_config() -> dict:
    """Valida e retorna configuração do pipe.yml."""
    _validate_env()
    
    if not PIPE_FILE.exists():
        raise ConfigError(f"Arquivo {PIPE_FILE} não encontrado")
    
    with open(PIPE_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    if not config:
        raise ConfigError("pipe.yml está vazio")
    
    if "log" in config:
        _validate_log(config["log"])
    
    _require(config, "sleep", "pipe.yml")
    _validate_sleep(config["sleep"])
    
    git = _require(config, "git", "pipe.yml")
    _validate_git(git)
    
    agents = _require(config, "agents", "pipe.yml")
    _validate_agents(agents)
    
    known_agents = {
        agent_id
        for platform in agents.values()
        for agent_id in platform
    }
    boards = _require(config, "boards", "pipe.yml")
    _validate_boards(boards, known_agents)
    
    return config
