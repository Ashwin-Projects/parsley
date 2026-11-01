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


def test_llm_code_never_evaluates_model_text():
    calls = re.compile(r"(?<![.\w])(eval|exec|compile|__import__)\(|\b(subprocess|os\.system|pickle)\b")
    assert calls.search("value = eval(text)") and not calls.search('re.compile("x")')
    assert [p.name for p in (CORE / "llm").glob("*.py") if calls.search(p.read_text(encoding="utf-8"))] == []


def test_llm_code_cannot_write_minilang_or_the_session():
    banned = re.compile(r"^\s*(from|import) parsley\.(verify|compiler\.(codegen|semantic|parser))\b", re.MULTILINE)
    assert banned.search("from parsley.compiler.codegen import generate")
    assert [p.name for p in (CORE / "llm").glob("*.py") if banned.search(p.read_text(encoding="utf-8"))] == []


def test_only_the_provider_module_opens_connections():
    network = re.compile(r"\bimport (urllib|http|socket)\b")
    offenders = [
        str(path.relative_to(CORE))
        for path in CORE.rglob("*.py")
        if path.relative_to(CORE) != Path("llm/provider.py") and network.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_the_nlp_stages_do_not_depend_on_the_llm_package():
    offenders = [p.name for p in (CORE / "nlp").glob("*.py") if "parsley.llm" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_core_never_imports_parsley_ml():
    offenders = [
        str(path.relative_to(CORE))
        for path in CORE.rglob("*.py")
        if "parsley_ml" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
