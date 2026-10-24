"""Command-line entry point; Phase 0 placeholder that echoes its input."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    """Echo the given sentence (or stdin when none is given) and exit 0."""
    parser = argparse.ArgumentParser(
        prog="parsley",
        description="English-to-MiniLang compiler (Phase 0 placeholder: echoes input).",
    )
    parser.add_argument("sentence", nargs="*", help="English sentence to compile")
    args = parser.parse_args(argv)

    text = " ".join(args.sentence) if args.sentence else sys.stdin.read().rstrip("\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
