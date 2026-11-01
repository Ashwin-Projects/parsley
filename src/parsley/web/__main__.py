"""``parsley-web`` or ``python -m parsley.web``: start the API server."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="parsley-web", description="Parsley web API")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on (default: 8000)")
    args = parser.parse_args(argv)
    try:
        import uvicorn

        from parsley.web.app import create_app
    except ImportError:
        print('parsley-web needs the web extra: pip install -e ".[web]"', file=sys.stderr)
        return 1
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
