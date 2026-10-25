"""Module boundary guards: core code never imports parsley_ml (CLAUDE.md rule 7);
only semantic.py writes the symbol table, reference stack and history (rule 3)."""

import re
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "src" / "parsley"
SESSION_WRITES = re.compile(
    r"\.declare\("
    r"|\b(ref_stack|history)\.(append|remove|insert|extend|pop|clear)\("
    r"|\b(ref_stack|history)\s*(\[[^\]]*\])?\s*[+]?=(?!=)"
    r"|\._symbols\b"
)


def test_session_write_pattern_catches_writes():
    for line in ["t.declare(", "session.history.append(s)", "s.ref_stack.remove(n)",
                 "s.ref_stack = []", "s.history += [x]", "table._symbols[k] = v"]:
        assert SESSION_WRITES.search(line), line
    for line in ["session.symbols", "s.ref_stack[-1]", "len(s.history)", "s.ref_stack == []"]:
        assert not SESSION_WRITES.search(line), line


def test_only_semantic_writes_session_state():
    allowed = {Path("compiler/semantic.py"), Path("compiler/symbols.py")}
    offenders = [
        str(rel)
        for path in CORE.rglob("*.py")
        if (rel := path.relative_to(CORE)) not in allowed
        and SESSION_WRITES.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_core_never_imports_parsley_ml():
    offenders = [
        str(path.relative_to(CORE))
        for path in CORE.rglob("*.py")
        if "parsley_ml" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
