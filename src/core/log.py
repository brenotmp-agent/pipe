"""Log core - terminal (resumo colorido) + arquivo (detalhe com extras/trace)."""

import logging
import re
import traceback
from datetime import date, datetime
from pathlib import Path

_DEFAULT_DIR = "logs"
_DEFAULT_TTL = 10

_RESET = "\033[0m"
_BOLD = "\033[1m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_WHITE = "\033[37m"

_LEVEL_COLOR = {
    logging.DEBUG: _WHITE,
    logging.INFO: _BOLD,
    logging.WARNING: _YELLOW,
    logging.ERROR: _RED,
}

_BRACKET = re.compile(r"\[([^\]]+)\]")


class Log:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._log_dir = Path(_DEFAULT_DIR)
            cls._instance._ttl = _DEFAULT_TTL
            cls._instance._file = None
            cls._instance._setup()
        return cls._instance

    def configure(self, config: dict):
        """Aplica configuração de log do pipe.yml."""
        log_cfg = config.get("log", {})
        new_dir = Path(log_cfg.get("dir", _DEFAULT_DIR))
        self._ttl = log_cfg.get("ttl", _DEFAULT_TTL)
        if new_dir != self._log_dir:
            self._log_dir = new_dir
            if self._file:
                self._file.close()
            self._setup()

    def _setup(self):
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self._log_dir / f"{date.today().strftime('%Y-%m-%d')}.json"
        self._file = open(log_file, "a", encoding="utf-8")

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    def cleanup(self):
        """Remove arquivos de log com mais de ttl dias."""
        if not self._log_dir.exists():
            return
        now = date.today()
        for path in sorted(self._log_dir.rglob("*")):
            if path.is_file():
                age = (now - date.fromtimestamp(path.stat().st_mtime)).days
                if age > self._ttl:
                    path.unlink()
        for path in sorted(self._log_dir.rglob("*"), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()

    def separator(self):
        """Escreve linha em branco no arquivo para demarcar início de execução."""
        self._file.write("\n")
        self._file.flush()

    def info(self, module: str, msg: str, *args, **extra):
        self._log("INFO", module, msg, args, extra)

    def warning(self, module: str, msg: str, *args, **extra):
        self._log("WARNING", module, msg, args, extra)

    def error(self, module: str, msg: str, *args, exc: BaseException = None, **extra):
        self._log("ERROR", module, msg, args, extra, exc=exc)

    def debug(self, module: str, msg: str, *args, **extra):
        self._log("DEBUG", module, msg, args, extra)

    def _log(self, level: str, module: str, msg: str, args: tuple, extra: dict, exc: BaseException = None):
        formatted = msg % args if args else msg

        now = datetime.now()

        # Terminal: hora + resumo colorido
        color = _LEVEL_COLOR.get(getattr(logging, level), _BOLD)
        terminal_msg = f"[{module}] {formatted}"
        terminal_msg = _BRACKET.sub(f"{color}[\\1]{_RESET}", terminal_msg)
        print(f"{now.strftime('%H:%M:%S')} {terminal_msg}")

        # Arquivo: timestamp - level - module - message + extras
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        file_line = f"{ts} - {level} - {module} - {formatted}"
        if extra:
            file_line += f" | {extra}"
        if exc:
            file_line += f"\n{traceback.format_exception(type(exc), exc, exc.__traceback__)[-1].rstrip()}"
            file_line += f"\n{''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))}"
        self._file.write(file_line + "\n")
        self._file.flush()


log = Log()
