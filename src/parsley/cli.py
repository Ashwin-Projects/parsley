"""CLI modes and options: one sentence, a file, or a REPL, all through pipeline.run.

REPL lines that start with ``:`` are commands (``:help``, ``:run``, ``:program``, ``:undo``,
``:reset``, ``:quit``), never English, so they cannot clash with a sentence.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import sys
import tomllib
from pathlib import Path

from parsley import pipeline
from parsley.compiler import codegen
from parsley.compiler.ast_nodes import Program
from parsley.compiler.semantic import analyze
from parsley.session import Session
from parsley.verify import Verification
from parsley.verify.interpreter import run as interpret

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

# :help examples; they run in order as one session (tests/unit/test_cli_commands.py).
HELP_EXAMPLES = (
    "make a variable called score and set it to 10",
    "add 5 to it",
    "define bonus as 3",
    "set score to score plus bonus",
    "print score",
    "if score is greater than 15 then print high else print low",
    "repeat 2 times print hello",
    "decrease score by 1",
    "show me the score",
)
COMMANDS = (
    (":run", "run the program so far and show what it prints"),
    (":program", "show all accepted MiniLang so far"),
    (":undo", "remove the last accepted statement"),
    (":reset", "start a new, empty session"),
    (":help", "show this help"),
    (":quit", "leave the REPL (end of input also works)"),
)


def run_sentence(text: str, options: argparse.Namespace) -> int:
    """Process one sentence, returning zero on success, nonzero on error.

    The same options object is used throughout one CLI invocation; its session is
    created on the first call and shared by later sentences. Only the pipeline
    changes the session. Diagnostics go to stderr; the back-translation, MiniLang
    and trace go to stdout, as do REPL prompts (written by ``input``). With
    ``--output``, the whole program so far is written after every successful sentence.

    Only the REPL asks questions. Elsewhere a clarification becomes diagnostic E102
    and ``--confirm`` cannot be answered (E103), so file mode never waits for input.
    An end of input while answering propagates as EOFError to end the REPL.
    """
    if options.session is None:
        options.session = Session()
    use_context = not options.no_context
    confirm = _confirmer(options)
    result = pipeline.run(text, options.session, use_context=use_context, confirm=confirm)
    while result.status == "needs_clarification":
        if not options.interactive:
            print(f"ambiguity E102: {result.question}{_choices(result.options)}", file=sys.stderr)
            return 1
        reply = input(_question_prompt(result))
        if not reply.strip():
            print("clarify: cancelled; nothing was recorded", file=sys.stderr)
            return 1
        answered = pipeline.answer(result, reply, options.session, use_context=use_context, confirm=confirm)
        if answered is result:
            print(f"clarify: I did not understand that answer to: {result.question}", file=sys.stderr)
        result = answered
    if options.trace:
        _print_trace(result.trace)
    for diagnostic in result.diagnostics:
        print(f"{diagnostic.stage} {diagnostic.code}: {diagnostic.message}", file=sys.stderr)
    if result.suggestion is not None:
        print(f"Try: {result.suggestion}", file=sys.stderr)
    if result.status != "ok":
        return 1
    print(f"I understood: {result.back_translation}")
    print(f"MiniLang: {result.minilang}")
    if result.verification is not None:
        print(_verification_summary(result.verification))
    if options.output is not None:
        options.output.write_text(_program(options.session) + "\n", encoding="utf-8")
    return 0


def _program(session: Session | None) -> str:
    """The accepted MiniLang so far ("" when nothing was accepted)."""
    if session is None or not session.history:
        return ""
    return codegen.generate(Program(tuple(session.history)))


def run_program(session: Session | None) -> int:
    """Run the program so far with the V3 interpreter; nonzero if it had a runtime error.

    Code generation is unchanged: the interpreter runs exactly the MiniLang ``:program`` shows.
    """
    source = _program(session)
    if not source:
        print("Nothing to run yet.")
        return 0
    _, output, errors = interpret(source)
    if output:
        print("Output:")
        for line in output:
            print(f"  {line}")
    else:
        print("Output: (nothing printed)")
    for error in errors:
        print(f"runtime error: {error}", file=sys.stderr)
    return 1 if errors else 0


def _undo(session: Session) -> Session:
    """A session without the last accepted statement.

    The earlier statements are replayed through semantic analysis, the only writer of the
    symbol table, reference stack and history, so the state is exactly as it was before.
    """
    restored = Session()
    for statement in session.history[:-1]:
        analyze(statement, restored)
    return restored


def _help() -> None:
    print("Type one English sentence per line. Commands start with ':'.")
    for command, meaning in COMMANDS:
        print(f"  {command:<9} {meaning}")
    print("Examples:")
    for example in HELP_EXAMPLES:
        print(f"    {example}")


def _command(text: str, options: argparse.Namespace) -> int | None:
    """Run one REPL command; returns its status, or None for ``:quit``."""
    command = text.strip().lower()
    if command == ":quit":
        return None
    if command == ":help":
        _help()
    elif command == ":run":
        return run_program(options.session)
    elif command == ":program":
        print(_program(options.session) or "(no statements yet)")
    elif command == ":undo":
        if options.session is None or not options.session.history:
            print("Nothing to undo.")
        else:
            removed = codegen.generate(Program((options.session.history[-1],)))
            options.session = _undo(options.session)
            print(f"Undid: {removed}")
    elif command == ":reset":
        options.session = Session()
        print("Session cleared.")
    else:
        print(f"cli E507: Unknown command {text.strip()} (type :help)", file=sys.stderr)
    return 0


def _version() -> str:
    """The version in pyproject.toml; the installed package metadata if the file is absent."""
    try:
        return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        try:
            return importlib.metadata.version("parsley")
        except importlib.metadata.PackageNotFoundError:
            return "unknown"


def _verification_summary(verification: Verification) -> str:
    """``V1 ok | V2 skipped | V3 failed``: one word per layer."""
    def word(match: bool | None) -> str:
        return "skipped" if match is None else "ok" if match else "failed"

    v1 = "ok" if verification.back_translation else "failed"
    return f"V1 {v1} | V2 {word(verification.v2_match)} | V3 {word(verification.v3_match)}"


def _choices(options: tuple[str, ...]) -> str:
    return f" ({' / '.join(options)})" if options else ""


def _question_prompt(result: pipeline.PipelineResult) -> str:
    """Numbered options for a choice between readings; inline options for yes/no."""
    clarification = result.clarification
    if clarification is not None and clarification.kind in ("alternatives", "operator_scope"):
        listed = "".join(f"\n  {i}) {option}" for i, option in enumerate(result.options, 1))
        return f"{result.question}{listed}\n> "
    return f"{result.question}{_choices(result.options)} "


def _confirmer(options: argparse.Namespace) -> pipeline.Confirm | None:
    """The --confirm callback: ask in the REPL; elsewhere refuse, since nobody can answer."""
    if not options.confirm:
        return None
    if not options.interactive:
        def refuse(back_translation: str) -> bool:
            print("cli W506: --confirm asks only in the REPL (run parsley with no sentence or file)",
                  file=sys.stderr)
            return False
        return refuse

    def ask(back_translation: str) -> bool:
        """Re-asks until yes or no; an empty reply means no, as an empty answer cancels."""
        while True:
            reply = input(f"I understood: {back_translation} Is that right? (yes / no) ")
            word = reply.strip().lower().rstrip(".!?")
            if word in ("yes", "y"):
                return True
            if word in ("no", "n", ""):
                return False
    return ask


def _print_trace(trace: pipeline.Trace) -> None:
    print(f"input: {trace.input}")
    print(f"normalized: {trace.normalized}")
    print("candidates:")
    for c in trace.candidates:
        print(f"  {c.rule_id} {c.intent} score {c.score:.4g}")
    if trace.ranked != trace.candidates:
        print("after context:")
        for c in trace.ranked:
            print(f"  {c.rule_id} {c.intent} score {c.score:.4g}")
    print(f"decision: {trace.decision}")
    if trace.chosen is not None:
        notes = f" ({'; '.join(trace.chosen.notes)})" if trace.chosen.notes else ""
        print(f"chosen: {trace.chosen.rule_id} {trace.chosen.intent}{notes}")
    if trace.ast is not None:
        print(f"AST: {trace.ast!r}")
    if trace.verification is not None:
        print("verification:")
        for detail in trace.verification.details:
            print(f"  {detail}")


def _process(text: str, options: argparse.Namespace) -> int:
    try:
        return 0 if run_sentence(text, options) == 0 else 1
    except EOFError:
        raise  # input ended while answering a question: the REPL stops
    except Exception as error:
        # Last-resort CLI boundary: a pipeline failure must never mean success.
        print(
            f"cli E502: Could not process sentence: {error}", file=sys.stderr,
        )
        return 1


def _run_file(options: argparse.Namespace) -> int:
    status = 0
    try:
        with options.file.open(encoding="utf-8") as source:
            for line in source:
                text = line.rstrip("\r\n")
                if text.strip():
                    status = max(status, _process(text, options))
    except (OSError, UnicodeError) as error:
        print(
            f"cli E503: Could not read {options.file}: {error}", file=sys.stderr,
        )
        return 1
    return status


def _repl(options: argparse.Namespace) -> int:
    status = 0
    while True:
        try:
            text = input("parsley> ")
        except EOFError:
            return status
        if text.strip().startswith(":"):
            result = _command(text, options)
            if result is None:
                return status
            status = max(status, result)
        elif text.strip():
            try:
                status = max(status, _process(text, options))
            except EOFError:
                return max(status, 1)  # the open question was never answered


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run sentence, file or REPL mode.

    Returns 0 on success, 1 on processing/I/O errors, or 130 on interruption.
    Argparse raises SystemExit with 0 for help and 2 for invalid arguments.
    """
    parser = argparse.ArgumentParser(
        prog="parsley",
        description="English-to-MiniLang compiler",
        allow_abbrev=False,
    )
    parser.add_argument(
        "sentence", nargs="?", help="one quoted English sentence",
    )
    parser.add_argument("--file", type=Path, help="read one sentence per line")
    parser.add_argument(
        "--trace", action="store_true", help="show pipeline trace",
    )
    parser.add_argument(
        "--output", type=Path, help="write MiniLang to this path",
    )
    parser.add_argument(
        "--confirm", action="store_true", help="confirm each interpretation",
    )
    parser.add_argument(
        "--no-context", action="store_true", help="disable context resolution",
    )
    parser.add_argument(
        "--run", action="store_true", help="run the program afterwards and show its output",
    )
    parser.add_argument("--version", action="version", version=f"parsley {_version()}")
    options = parser.parse_args(argv)
    if options.sentence is not None and options.file is not None:
        parser.error("sentence and --file cannot be used together")
    options.interactive = options.sentence is None and options.file is None
    options.session = None
    try:
        if options.file is not None:
            status = _run_file(options)
        elif options.sentence is not None:
            status = _process(options.sentence, options)
        else:
            return _repl(options)
        if options.run:
            status = max(status, run_program(options.session))
        return status
    except KeyboardInterrupt:
        print("cli E504: Interrupted.", file=sys.stderr)
        return 130
    except (OSError, UnicodeError) as error:
        print(f"cli E505: Could not read input: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
