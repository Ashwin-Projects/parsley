"""CLI modes and options: one sentence, a file, or a REPL, all through pipeline.run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from parsley import pipeline
from parsley.compiler import codegen
from parsley.compiler.ast_nodes import Program
from parsley.session import Session


def run_sentence(text: str, options: argparse.Namespace) -> int:
    """Process one sentence, returning zero on success, nonzero on error.

    The same options object is used throughout one CLI invocation; its session is
    created on the first call and shared by later sentences. Only the pipeline
    changes the session. Diagnostics and questions go to stderr; the
    back-translation, MiniLang and trace go to stdout. With ``--output``, the
    whole program so far is written after every successful sentence.
    """
    if options.session is None:
        options.session = Session()
    result = pipeline.run(text, options.session, use_context=not options.no_context)
    if options.trace:
        _print_trace(result.trace)
    for diagnostic in result.diagnostics:
        print(f"{diagnostic.stage} {diagnostic.code}: {diagnostic.message}", file=sys.stderr)
    if result.status == "needs_clarification":
        choices = f" ({' / '.join(result.options)})" if result.options else ""
        print(f"clarify: {result.question}{choices}", file=sys.stderr)
        return 1
    if result.status != "ok":
        return 1
    print(f"I understood: {result.back_translation}")
    print(f"MiniLang: {result.minilang}")
    if options.output is not None:
        program = codegen.generate(Program(tuple(options.session.history)))
        options.output.write_text(program + "\n", encoding="utf-8")
    return 0


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


def _process(text: str, options: argparse.Namespace) -> int:
    try:
        return 0 if run_sentence(text, options) == 0 else 1
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
        if text.strip():
            status = max(status, _process(text, options))


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
    options = parser.parse_args(argv)
    if options.sentence is not None and options.file is not None:
        parser.error("sentence and --file cannot be used together")
    options.interactive = options.sentence is None and options.file is None
    options.session = None
    try:
        if options.file is not None:
            return _run_file(options)
        if options.sentence is not None:
            return _process(options.sentence, options)
        return _repl(options)
    except KeyboardInterrupt:
        print("cli E504: Interrupted.", file=sys.stderr)
        return 130
    except (OSError, UnicodeError) as error:
        print(f"cli E505: Could not read input: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
