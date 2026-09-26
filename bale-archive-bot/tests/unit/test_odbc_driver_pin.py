"""Guards for ODBC Driver 17 pinning and operator docs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Paths that must not reintroduce the old driver pin.
_SCAN_GLOBS = (
    "*.md",
    "*.py",
    "*.ps1",
    "*.toml",
    "*.example",
    "*.ini",
    ".cursorrules",
)

_SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "data",
    "node_modules",
}


def _forbidden_driver_needles() -> tuple[str, ...]:
    """Build needles at runtime so this file itself stays clean."""
    eighteen = str(10 + 8)
    return (
        f"ODBC+Driver+{eighteen}+for+SQL+Server",
        f"ODBC Driver {eighteen}",
        f"Driver+{eighteen}+for+SQL+Server",
        "درایور ۱۸",
    )


def _iter_project_text_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.name == "test_odbc_driver_pin.py":
            continue
        if path.suffix in {".md", ".py", ".ps1", ".toml", ".ini", ".example"} or path.name in {
            ".cursorrules",
            ".env.example",
        }:
            files.append(path)
        elif any(path.match(glob) for glob in _SCAN_GLOBS):
            files.append(path)
    return sorted(set(files))


def test_no_odbc_driver_eighteen_left_in_project_files() -> None:
    needles = _forbidden_driver_needles()
    hits: list[str] = []
    for path in _iter_project_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle in text:
                rel = path.relative_to(ROOT).as_posix()
                hits.append(f"{rel}: {needle}")
    assert hits == [], "ODBC Driver eighteen must not remain; found:\n" + "\n".join(hits)


def test_env_example_pins_driver_seventeen() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    seventeen = str(10 + 7)
    assert f"ODBC+Driver+{seventeen}+for+SQL+Server" in text
    assert "bale_archive" in text
    assert "ehya" not in text.lower() or "هرگز" in text or "never" in text.lower()


def test_runbook_documents_collate_memory_ehya_and_port() -> None:
    runbook = (ROOT / "docs" / "RUNBOOK.md").read_text(encoding="utf-8")
    deploy = (ROOT / "docs" / "DEPLOY_WINDOWS.md").read_text(encoding="utf-8")
    combined = runbook + "\n" + deploy
    assert "Persian_100_CI_AS" in combined or "Arabic_100_CI_AS" in combined
    assert "max server memory" in combined
    assert "512" in combined
    assert "ehya" in combined
    assert "1433" in combined
