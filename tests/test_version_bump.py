"""Testes de verificação do bump de versão MINOR — US-02 (preflight).

Confirma que:
1. src/core/version.py contém VERSION = "1.5.0" (bump MINOR a partir de 1.4.3).
2. A versão segue o padrão semântico MAJOR.MINOR.PATCH.
3. O MINOR foi incrementado (de 4 para 5) e o PATCH zerado.
4. CONTEXT.md contém a seção de changelog "Preflight de Credenciais (v1.5.0 — US-02)".
5. A versão é exibida no log de inicialização via __main__.

Nota sobre a discrepância da issue:
  O body da issue #36 cita versão atual "1.5.0" → alvo "1.6.0". Porém o estado
  real do repositório (branch epic, commit 6019f62) tem VERSION = "1.4.3" —
  as tasks de desenvolvimento (#34, #35) não fizeram o bump oportunamente.
  O bump correto, portanto, é 1.4.3 → 1.5.0 (MINOR: adição de comportamento
  novo — preflight()). Esta task registra e valida esse estado.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VERSION_FILE = ROOT / "src" / "core" / "version.py"
CONTEXT_FILE = ROOT / "CONTEXT.md"


# ─── Verificação de src/core/version.py ──────────────────────────────────────

class TestVersionFile:
    """Garante que src/core/version.py contém a versão correta após o bump."""

    def test_version_file_exists(self):
        """O arquivo src/core/version.py deve existir."""
        assert VERSION_FILE.exists(), (
            f"Arquivo de versão não encontrado: {VERSION_FILE}"
        )

    def test_version_importable(self):
        """VERSION deve ser importável de src.core.version."""
        from src.core.version import VERSION  # noqa: F401

    def test_version_is_string(self):
        """VERSION deve ser uma string."""
        from src.core.version import VERSION
        assert isinstance(VERSION, str), (
            f"VERSION deve ser str, mas é {type(VERSION).__name__}"
        )

    def test_version_semantic_format(self):
        """VERSION deve seguir o formato semântico MAJOR.MINOR.PATCH."""
        import re
        from src.core.version import VERSION
        pattern = r"^\d+\.\d+\.\d+$"
        assert re.match(pattern, VERSION), (
            f"VERSION '{VERSION}' não segue o formato semântico MAJOR.MINOR.PATCH"
        )

    def test_version_is_target(self):
        """VERSION deve ser '1.5.0' após o bump MINOR da US-02."""
        from src.core.version import VERSION
        assert VERSION == "1.5.0", (
            f"Esperado VERSION = '1.5.0' após bump MINOR (1.4.3 → 1.5.0 pela "
            f"adição do preflight de credenciais — US-02). Atual: '{VERSION}'"
        )

    def test_version_minor_incremented(self):
        """MINOR deve ser 5 (incrementado de 4)."""
        from src.core.version import VERSION
        parts = VERSION.split(".")
        assert len(parts) == 3, f"Formato inválido: '{VERSION}'"
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        assert major == 1, f"MAJOR deve ser 1. Atual: {major}"
        assert minor == 5, (
            f"MINOR deve ser 5 (bump de 4 pela adição do preflight). Atual: {minor}"
        )

    def test_version_patch_zeroed(self):
        """PATCH deve ser 0 após bump MINOR."""
        from src.core.version import VERSION
        parts = VERSION.split(".")
        assert len(parts) == 3, f"Formato inválido: '{VERSION}'"
        patch = int(parts[2])
        assert patch == 0, (
            f"PATCH deve ser 0 após bump MINOR. Atual: {patch}"
        )


# ─── Verificação de CONTEXT.md ────────────────────────────────────────────────

class TestContextMD:
    """Confirma que CONTEXT.md contém a seção de changelog da v1.5.0."""

    def test_context_md_exists(self):
        """O arquivo CONTEXT.md deve existir."""
        assert CONTEXT_FILE.exists(), (
            f"CONTEXT.md não encontrado: {CONTEXT_FILE}"
        )

    def test_context_contains_v150_section(self):
        """CONTEXT.md deve conter seção de changelog para v1.5.0 — US-02."""
        content = CONTEXT_FILE.read_text(encoding="utf-8")
        assert "1.5.0" in content, (
            "CONTEXT.md deve mencionar v1.5.0 (seção de changelog da US-02 / preflight)"
        )

    def test_context_contains_preflight_section(self):
        """CONTEXT.md deve conter seção descrevendo o preflight de credenciais."""
        content = CONTEXT_FILE.read_text(encoding="utf-8")
        # Aceita variações de título (v1.5.0 ou v1.6.0 conforme refatoração)
        assert "Preflight de Credenciais" in content or "preflight" in content.lower(), (
            "CONTEXT.md deve conter seção sobre Preflight de Credenciais (US-02)"
        )

    def test_context_contains_us02_reference(self):
        """CONTEXT.md deve fazer referência à US-02."""
        content = CONTEXT_FILE.read_text(encoding="utf-8")
        assert "US-02" in content, (
            "CONTEXT.md deve referenciar US-02 na seção do preflight"
        )


# ─── Verificação de integração: versão no log de boot ────────────────────────

class TestVersionInBootLog:
    """Verifica que a versão importada pelo __main__ é a 1.5.0."""

    def test_main_imports_version(self):
        """src/__main__.py deve importar VERSION de src.core.version."""
        main_source = (ROOT / "src" / "__main__.py").read_text(encoding="utf-8")
        assert "from src.core.version import VERSION" in main_source, (
            "__main__.py deve importar VERSION de src.core.version"
        )

    def test_main_version_is_150(self):
        """VERSION importado por __main__ deve ser '1.5.0'."""
        import importlib
        import src.core.version as version_mod
        importlib.reload(version_mod)
        assert version_mod.VERSION == "1.5.0", (
            f"__main__ usará VERSION = '{version_mod.VERSION}'. Esperado '1.5.0'"
        )

    def test_version_log_message_format(self):
        """A mensagem de log de boot deve incluir a versão formatada."""
        main_source = (ROOT / "src" / "__main__.py").read_text(encoding="utf-8")
        # Verifica que o log exibe a versão (padrão: f"...v{VERSION}")
        assert "VERSION" in main_source, (
            "__main__.py deve usar VERSION na mensagem de inicialização"
        )
        assert "v{VERSION}" in main_source or f"v{'{VERSION}'}" in main_source, (
            "A mensagem de boot deve exibir a versão no formato v{VERSION}"
        )
