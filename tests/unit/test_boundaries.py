"""Module boundary guards (CLAUDE.md rule 7): core code never imports parsley_ml."""

from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "src" / "parsley"


def test_core_never_imports_parsley_ml():
    offenders = [
        str(path.relative_to(CORE))
        for path in CORE.rglob("*.py")
        if "parsley_ml" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
