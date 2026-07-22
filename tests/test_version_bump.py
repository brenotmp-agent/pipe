"""Testes de verificação do bump de versão MINOR — US-02 (preflight).

Confirma que:
1. src/core/version.py contém VERSION = "1.6.0" (bump MINOR a partir de 1.5.0).
2. A versão segue o padrão semântico MAJOR.MINOR.PATCH.
3. O MINOR foi incrementado (de 5 para 6) e o PATCH zerado.
4. CONTEXT.md contém a seção de changelog "Preflight de Credenciais (v1.6.0 — US-02)".
5. A versão é exibida no log de inicialização via __main__.

Contexto do bump:
  O body da issue #36 define bump 1.5.0 → 1.6.0. A versão 1.5.0 é o estado
  atual de `main` (release "Incidente — Issue Fantasma", commit 5a41183).
  As tasks #34 e #35 implementaram o preflight() na branch epic sem realizar
  o bump; esta task corrige omissão e registra a versão correta: 1.6.0.
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
        """VERSION deve ser '1.6.0' após o bump MINOR da US-02."""
        from src.core.version import VERSION
        assert VERSION == "1.6.0", (
            f"Esperado VERSION = '1.6.0' após bump MINOR (1.5.0 → 1.6.0 pela "
            f"adição do preflight de credenciais — US-02). Atual: '{VERSION}'"
        )

    def test_version_minor_incremented(self):
        """MINOR deve ser 6 (incrementado de 5)."""
        from src.core.version import VERSION
        parts = VERSION.split(".")
        assert len(parts) == 3, f"Formato inválido: '{VERSION}'"
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        assert major == 1, f"MAJOR deve ser 1. Atual: {major}"
        assert minor == 6, (
            f"MINOR deve ser 6 (bump de 5 pela adição do preflight). Atual: {minor}"
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
    """Confirma que CONTEXT.md contém a seção de changelog da v1.6.0."""

    def test_context_md_exists(self):
        """O arquivo CONTEXT.md deve existir."""
        assert CONTEXT_FILE.exists(), (
            f"CONTEXT.md não encontrado: {CONTEXT_FILE}"
        )

    def test_context_contains_v160_section(self):
        """CONTEXT.md deve conter seção de changelog para v1.6.0 — US-02."""
        content = CONTEXT_FILE.read_text(encoding="utf-8")
        assert "1.6.0" in content, (
            "CONTEXT.md deve mencionar v1.6.0 (seção de changelog da US-02 / preflight)"
        )

    def test_context_contains_preflight_section(self):
        """CONTEXT.md deve conter seção descrevendo o preflight de credenciais."""
        content = CONTEXT_FILE.read_text(encoding="utf-8")
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
    """Verifica que a versão importada pelo __main__ é a 1.6.0."""

    def test_main_imports_version(self):
        """src/__main__.py deve importar VERSION de src.core.version."""
        main_source = (ROOT / "src" / "__main__.py").read_text(encoding="utf-8")
        assert "from src.core.version import VERSION" in main_source, (
            "__main__.py deve importar VERSION de src.core.version"
        )

    def test_main_version_is_160(self):
        """VERSION importado por __main__ deve ser '1.6.0'."""
        import importlib
        import src.core.version as version_mod
        importlib.reload(version_mod)
        assert version_mod.VERSION == "1.6.0", (
            f"__main__ usará VERSION = '{version_mod.VERSION}'. Esperado '1.6.0'"
        )

    def test_version_log_message_format(self):
        """A mensagem de log de boot deve incluir a versão formatada."""
        main_source = (ROOT / "src" / "__main__.py").read_text(encoding="utf-8")
        assert "VERSION" in main_source, (
            "__main__.py deve usar VERSION na mensagem de inicialização"
        )
        # Verifica que o log exibe a versão no formato v{VERSION} (f-string)
        assert "v{VERSION}" in main_source, (
            "A mensagem de boot deve exibir a versão no formato v{VERSION}"
        )
