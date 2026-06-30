"""Adapter kiro-cli - execução de agentes via kiro-cli."""

import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.core.agent import AgentPort, AgentParams
from src.core.log import log

_tz = timezone(timedelta(hours=-3))

# Timeout máximo de uma execução do agente (segundos).
_TIMEOUT = 3600

# Remove sequências ANSI/escape do output capturado.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\].*?(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")


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
        """
        cmd = [
            "kiro-cli", "chat",
            "--no-interactive",
            "--trust-all-tools",
        ]
        if params.model:
            cmd += ["--model", params.model]
        cmd.append(self._compose_input(params))

        # Sem cor nos logs do kiro-cli (facilita parsing/limpeza).
        env = {**os.environ, "KIRO_LOG_NO_COLOR": "1"}

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

        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0:
            output += f"\n[exit-code: {result.returncode}]"
        return output

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
