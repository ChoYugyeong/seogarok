"""서가 서버 실행:  python -m server.app [--port 8100]"""
from __future__ import annotations

import argparse
import sys

from .api import serve


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="서가 API + 정적 서버")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args(argv)
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
