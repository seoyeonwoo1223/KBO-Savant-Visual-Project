"""Serve the static viewer with `web/` as the document root.

The pages fetch `../data/...` relative to themselves, so a server rooted at the
repository instead of `web/` returns 404 for every dataset and the tools render
empty. The root is derived from this file's location, so the command works from
any working directory.

    python scripts/serve_web.py            # http://localhost:8000/
    python scripts/serve_web.py --port 9000
"""
from __future__ import annotations

import argparse
import contextlib
import sys
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        # Pages carry ?v= cache busters for production; locally the freshest file
        # should always win so an edit shows up on reload.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:
        sys.stderr.write(f"  {self.address_string()} {format % args}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--open", action="store_true", help="open the homepage in a browser")
    args = parser.parse_args()

    if not WEB_ROOT.is_dir():
        print(f"web root not found: {WEB_ROOT}", file=sys.stderr)
        return 1

    handler = partial(Handler, directory=str(WEB_ROOT))
    try:
        server = ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as error:
        print(f"cannot bind {args.host}:{args.port} ({error}); try --port", file=sys.stderr)
        return 1

    url = f"http://{args.host}:{args.port}/"
    print(f"serving {WEB_ROOT} at {url}")
    print("  tools: /leaderboards/ /zones/ /swing-take/ /zone-awareness/")
    print("         /pitch-arsenal/ /movement-zones/ /blocking/")
    print("stop with Ctrl+C")
    if args.open:
        with contextlib.suppress(Exception):
            webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
