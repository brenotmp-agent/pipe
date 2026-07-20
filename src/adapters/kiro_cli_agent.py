"""Adapter kiro-cli - execução de agentes via kiro-cli."""

import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.core.agent import AgentPort, AgentParams
from src.core.log import log
from src.core.session import SessionIndex
from src.core.context_generator import CONTEXT_FILE, AGENT_FILE

_tz = timezone(timedelta(hours=-3))

# Timeout máximo de uma execução do agente (segundos).
_TIMEOUT = 3600

# Remove sequências ANSI/escape do output capturado.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\].*?(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")

# UUID de sessão do kiro-cli (formato canônico 8-4-4-4-12).
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class KiroCliAgent(AgentPort):
    """Adapter de agente para kiro-cli."""

    def execute(self, params: AgentParams) -> None:
        log_path = self._create_log(params)
        log.info("Agent", f"[{params.board_id}] #{params.issue_id} agent='{params.agent_name}' "
                          f"model='{params.model}' cwd='{params.work_dir}' log='{log_path}'")
        try:
            work_dir = Path(params.work_dir)
            if not work_dir.is_dir():
                raise FileNotFoundError(
                    f"Diretório de trabalho (repo) não encontrado: {work_dir}"
                )
            output = self._run(params, work_dir)
            self._append_log(log_path, self._strip_ansi(output) + "\n")
            log.info("Agent", f"[{params.board_id}] #{params.issue_id} execução concluída")
        except Exception as e:
            self._append_log(log_path, f"\n**ERRO**: {e}\n")
            log.error("Agent", f"[{params.board_id}] #{params.issue_id} erro: {e}")
            raise

    def _run(self, params: AgentParams, work_dir: Path) -> str:
        """Executa kiro-cli chat em modo headless DENTRO de repo/<repo_id>.

        O cwd do processo é o clone do repositório alvo, garantindo que toda
        operação git/arquivos do agente fique confinada ao repo — nunca no
        diretório da esteira.

        Sessão: se houver um session_id conhecido para (board, issue, agente) e
        ele ainda existir no kiro-cli, retoma via `--resume-id` (o agente
        recupera o raciocínio da execução anterior). Após executar, captura o id
        da sessão (mais recente do cwd) e grava no índice. A esteira não gerencia
        o ciclo de vida das sessões — o kiro-cli cuida disso.
        """
        # Sem cor nos logs do kiro-cli (facilita parsing/limpeza).
        # KIRO_HOME: aponta o kiro-cli para o diretório de configuração global
        # da esteira (.kiro/agents/pipe_context.json). O kiro-cli é executado
        # com cwd=repo/<repo_id>, onde buscaria agentes locais em
        # repo/<repo_id>/.kiro/agents/ — diretório diferente do gerado no startup.
        # Com KIRO_HOME apontando para o diretório raiz da esteira (onde está
        # .kiro/), o kiro-cli encontra o arquivo de agente como agente global.
        kiro_home = str(AGENT_FILE.parent.parent.parent)
        env = {**os.environ, "KIRO_LOG_NO_COLOR": "1", "KIRO_HOME": kiro_home}

        cmd = [
            "kiro-cli", "chat",
            "--no-interactive",
            "--trust-all-tools",
        ]
        if params.model:
            cmd += ["--model", params.model]

        # Injeta o contexto do sistema via --agent (quando CONTEXT.md existe).
        # O arquivo .kiro/agents/pipe_context.json foi gerado pelo startup a
        # partir do pipe.yml e contém as instruções explícitas para o agente.
        if CONTEXT_FILE.exists():
            cmd += ["--agent", "pipe_context"]

        # Retoma a sessão anterior se ainda existir.
        index = SessionIndex()
        known_id = index.get(params.board_id, params.issue_id, params.agent_id)
        if known_id and self._session_exists(known_id, work_dir, env):
            cmd += ["--resume-id", known_id]
            log.info("Agent", f"[{params.board_id}] #{params.issue_id} "
                     f"retomando sessão {known_id}",
                     session_id=known_id, agent=params.agent_id)

        cmd.append(self._compose_input(params))

        try:
            result = subprocess.run(
                cmd,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return f"[TIMEOUT] Agente excedeu {_TIMEOUT}s"
        except FileNotFoundError:
            return "[ERRO] kiro-cli não encontrado no PATH"

        # Captura o id da sessão recém-usada (mais recente do cwd) e persiste.
        # O loop da esteira é sequencial, então a sessão do topo é a desta
        # execução (mesma quando retomada por id, nova quando criada agora).
        current_id = self._latest_session_id(work_dir, env)
        if current_id:
            index.set(params.board_id, params.issue_id, params.agent_id, current_id)

        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            output += f"\n[exit-code: {result.returncode}]"
        return output

    def _list_session_ids(self, work_dir: Path, env: dict) -> list[str]:
        """Lista os session_ids do cwd (mais recente primeiro) via kiro-cli."""
        try:
            result = subprocess.run(
                ["kiro-cli", "chat", "--list-sessions"],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []
        if result.returncode != 0:
            return []
        return _UUID.findall(self._strip_ansi(result.stdout or ""))

    def _session_exists(self, session_id: str, work_dir: Path, env: dict) -> bool:
        """True se o session_id ainda existe no kiro-cli para este cwd."""
        return session_id in self._list_session_ids(work_dir, env)

    def _latest_session_id(self, work_dir: Path, env: dict) -> str | None:
        """Retorna o session_id mais recente do cwd (topo da listagem)."""
        ids = self._list_session_ids(work_dir, env)
        return ids[0] if ids else None

    def _compose_input(self, params: AgentParams) -> str:
        """Monta o input do agente: contexto do papel + prompt da tarefa."""
        if params.context and params.context.strip():
            return f"{params.context.strip()}\n\n---\n\n{params.prompt}"
        return params.prompt

    def _strip_ansi(self, text: str) -> str:
        """Remove códigos ANSI do output."""
        return _ANSI.sub("", text)

    def _append_log(self, log_path: Path, content: str) -> None:
        """Adiciona conteúdo ao final do log."""
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(content)

    def _create_log(self, params: AgentParams) -> Path:
        """Cria o arquivo de log de execução em markdown."""
        issue_dir = log.log_dir / str(params.issue_id)
        issue_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(_tz).strftime("%Y-%m-%d_%H-%M-%S")
        log_file = issue_dir / f"{timestamp}.md"

        content = self._build_log(params)
        log_file.write_text(content, encoding="utf-8")
        return log_file

    def _build_log(self, params: AgentParams) -> str:
        """Monta o conteúdo do log em markdown."""
        lines = []

        # Parâmetros
        lines.append("## Parâmetros")
        lines.append("")
        lines.append(f"- **plataforma**: {params.platform}")
        lines.append(f"- **agente**: {params.agent_name}")
        lines.append(f"- **model**: {params.model}")
        lines.append(f"- **board**: {params.board_id}")
        lines.append(f"- **coluna**: {params.col_id}")
        lines.append(f"- **issue**: #{params.issue_id}")
        if params.repo_id:
            lines.append(f"- **repo**: {params.repo_id}")
        if params.work_dir:
            lines.append(f"- **work_dir**: {params.work_dir}")
        lines.append("")

        # Prompt
        lines.append("---")
        lines.append("")
        lines.append("## Prompt")
        lines.append("")
        lines.append(params.prompt)
        lines.append("")

        # Chat (preenchido durante execução)
        lines.append("---")
        lines.append("")
        lines.append("## Chat")
        lines.append("")

        return "\n".join(lines)
