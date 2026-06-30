"""Adapter kiro-cli - execução de agentes via kiro-cli."""

from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.core.agent import AgentPort, AgentParams
from src.core.log import log

_tz = timezone(timedelta(hours=-3))


class KiroCliAgent(AgentPort):
    """Adapter de agente para kiro-cli."""

    def execute(self, params: AgentParams) -> None:
        log_path = self._create_log(params)
        log.info("Agent", f"[{params.board_id}] #{params.issue_id} agent='{params.agent_name}' "
                          f"log='{log_path}'")
        try:
            # TODO: executar kiro-cli e preencher seção chat
            pass
        except Exception as e:
            self._append_log(log_path, f"\n**ERRO**: {e}\n")
            log.error("Agent", f"[{params.board_id}] #{params.issue_id} erro: {e}")
            raise

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
        if params.effort:
            lines.append(f"- **effort**: {params.effort}")
        lines.append(f"- **board**: {params.board_id}")
        lines.append(f"- **coluna**: {params.col_id}")
        lines.append(f"- **issue**: #{params.issue_id}")
        if params.context:
            lines.append(f"- **context**: {params.context}")
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
