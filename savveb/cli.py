"""savveb command line: `savveb save URL` and `savveb play FILE`."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

from . import __version__

INSTALL_BROWSER = [sys.executable, "-m", "playwright", "install", "chromium"]


def web_root() -> Path:
    """The player files: bundled as savveb/web when installed, docs/ in a source checkout."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "web", here.parent / "docs"):
        if (candidate / "index.html").exists():
            return candidate
    raise SystemExit("Player files not found (savveb/web or docs/).")


def default_name(url: str) -> str:
    """https://kim.github.io/chess/ -> kim.github.io-chess-2026-10-18.wacz"""
    parts = urlsplit(url)
    path = re.sub(r"\.(html?|php)$", "", parts.path.strip("/"))
    stem = "-".join(filter(None, [parts.netloc, re.sub(r"[^\w.-]+", "-", path).strip("-")]))
    return f"{stem or 'site'}-{date.today().isoformat()}.wacz"


def save(args: argparse.Namespace) -> int:
    urls = [u if re.match(r"https?://", u) else f"https://{u}" for u in args.urls]
    url = urls[0]
    out = Path(args.output or default_name(url))
    if out.suffix != ".wacz":
        out = out.with_suffix(".wacz")
    if args.no_optimize:
        os.environ["ARCHIVE_OPTIMIZE"] = "0"

    from .capture import BrowserMissing, capture

    print(f"Saving {url}")
    for extra in urls[1:]:
        print(f"  also starting from {extra}")
    started = time.monotonic()
    try:
        result = capture(urls, out, page_limit=args.pages, depth=args.depth)
    except KeyboardInterrupt:
        print("\nCancelled. Nothing was saved.", flush=True)
        # Exit now: Playwright's half-closed connection would print noise at shutdown.
        os._exit(130)
    except BrowserMissing:
        print("\nChromium for Playwright is not installed. It is needed once (~100 MB):")
        print("  " + " ".join(INSTALL_BROWSER))
        if sys.stdin.isatty() and input("Install it now? [Y/n] ").strip().lower() in {"", "y", "yes"}:
            subprocess.run(INSTALL_BROWSER, check=True)
            return save(args)
        return 1
    except Exception as error:  # noqa: BLE001
        print(f"Could not save {url}: {error}")
        return 1

    pages, saved = result["pages"], result["saved"]
    size = out.stat().st_size / 1048576
    note = f", {saved / 1048576:.1f} MB smaller after image optimization" if saved > 0 else ""
    print(f"\nSaved {out}  ({pages} page{'s' * (pages != 1)}, {result['resources']} files, {size:.1f} MB{note}, "
          f"{time.monotonic() - started:.0f}s)")
    if result["left"]:
        print(f"{result['left']} more page(s) were found but not saved (limit --pages {args.pages}). "
              f"Run again with a higher --pages to get them.")
    print(f"Replay it:  savveb play {shlex.quote(str(out))}")
    print("or drop the file on https://duskarb.github.io/savveb/")
    return 0


def free_port(preferred: int) -> int:
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def play(args: argparse.Namespace) -> int:
    from .server import make_server

    local_files = {}
    if re.match(r"https?://", args.archive):
        source = args.archive
        title = Path(urlsplit(source).path).name
    else:
        path = Path(args.archive).expanduser().resolve()
        if not path.is_file():
            print(f"No such file: {path}")
            return 1
        source = f"/local/{quote(path.name)}"
        local_files[source] = str(path)
        title = path.name

    port = free_port(args.port)
    server = make_server(port, str(web_root()), local_files)
    url = f"http://localhost:{port}/?{urlencode({'source': source, 'title': title})}"
    print(f"Playing {title} at {url}")
    print("Press Ctrl+C to stop.")
    threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="savveb", description="Save a website as a WACZ file and replay it.")
    parser.add_argument("--version", action="version", version=f"savveb {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("save", help="capture a website into a .wacz file")
    p.add_argument("urls", nargs="+", metavar="URL",
                   help="site to save; give more URLs of the same site for pages nothing links to")
    p.add_argument("-o", "--output", help="file to write (default: <site>-<date>.wacz)")
    p.add_argument("--pages", type=int, default=500, help="most pages to save (default 500)")
    p.add_argument("--depth", type=int, default=20, help="how many links deep to follow (default 20)")
    p.add_argument("--no-optimize", action="store_true", help="keep large images as they are")
    p.set_defaults(func=save)

    p = sub.add_parser("play", help="replay a .wacz file (or URL) in your browser")
    p.add_argument("archive", help="path or URL of a .wacz / .warc file")
    p.add_argument("--port", type=int, default=8817)
    p.set_defaults(func=play)

    args = parser.parse_args(argv)
    return args.func(args)
