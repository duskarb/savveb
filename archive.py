#!/usr/bin/env python3
"""savveb — capture websites into WACZ files and replay them from this folder.

    python3 archive.py add https://example.com --title "Example"
    python3 archive.py capture
    python3 archive.py view
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import manifest as m  # noqa: E402

ROOT = m.ROOT
CAPTURE_DEPS = {"playwright": "playwright", "warcio": "warcio", "wacz": "wacz", "PIL": "pillow"}
PIP_PACKAGES = ["playwright", "warcio", "wacz", "pillow"]

# Header names accepted from the intake sheet. "link"/"url" mean the site address there.
INTAKE_ALIASES = {
    "original_url": ("original_url", "url", "link", "링크", "주소"),
    "creator": m.ALIASES["creator"],
    "collection": m.ALIASES["collection"],
    "title": m.ALIASES["title"],
}


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, check=check)


# ── intake ───────────────────────────────────────────────────────────


def sheet_csv_url(value: str) -> str:
    """Turn a Google Sheet edit link into its CSV export URL. Other URLs pass through."""
    match = re.search(r"docs\.google\.com/spreadsheets/d/([\w-]+)", value)
    if match:
        return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/gviz/tq?tqx=out:csv"
    return value


def fetch_text(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.URLError:
        # python.org builds on macOS may lack root certificates; curl usually has them.
        return subprocess.run(
            ["curl", "-sfL", url], capture_output=True, text=True, check=True, timeout=30
        ).stdout


def intake_row(raw: dict[str, str]) -> dict[str, str]:
    row = {m.clean(k): m.clean(v) for k, v in raw.items() if k is not None}
    out = {}
    for canonical, aliases in INTAKE_ALIASES.items():
        out[canonical] = next((row[a] for a in aliases if m.clean(row.get(a))), "")
    return out


def merge_rows(fields, rows, incoming) -> list[dict[str, str]]:
    """Append rows that are new by row_key; fill only blank URL/title on existing ones.
    Never overwrites management data already in manifest.csv."""
    by_key = {m.row_key(row): row for row in rows}
    added = []
    for item in incoming:
        if not item.get("original_url") and not item.get("creator") and not item.get("title"):
            continue
        key = m.row_key(item)
        if key in by_key:
            existing = by_key[key]
            for field in ("original_url", "title"):
                if not m.clean(existing.get(field)) and item.get(field):
                    existing[field] = item[field]
            continue
        row = {field: "" for field in fields}
        row.update({k: v for k, v in item.items() if k in fields})
        row["status"] = row.get("status") or "pending"
        rows.append(row)
        by_key[key] = row
        added.append(row)
    return added


def sync_sheet(config: dict) -> None:
    sheet = m.clean(config.get("intake_sheet"))
    if not sheet:
        return
    print("Reading new rows from the intake sheet...")
    try:
        import csv
        import io

        text = fetch_text(sheet_csv_url(sheet))
        incoming = [intake_row(raw) for raw in csv.DictReader(io.StringIO(text))]
    except Exception as error:  # noqa: BLE001
        print(f"  Could not read the sheet ({error}); continuing with manifest.csv.")
        return
    fields, rows = m.read_manifest()
    added = merge_rows(fields, rows, incoming)
    m.write_manifest(fields, rows)
    for row in added:
        print(f"  added: {row.get('title') or row.get('creator') or row.get('original_url')}")
    print(f"  {len(incoming)} sheet row(s), {len(added)} new.")


def add(args: argparse.Namespace) -> int:
    if not re.match(r"https?://", args.url):
        print("URL must start with http:// or https://")
        return 1
    fields, rows = m.read_manifest()
    item = {
        "original_url": args.url,
        "title": args.title,
        "creator": args.creator,
        "collection": args.collection,
        "status": "ready-to-capture",
    }
    if not merge_rows(fields, rows, [item]):
        print(f"Already in manifest.csv: {m.row_key(item)}")
        return 1
    m.write_manifest(fields, rows)
    print(f"Added {args.url} → {m.wacz_path(item)}")
    print("Run `python3 archive.py capture` to capture it.")
    return 0


# ── capture ──────────────────────────────────────────────────────────


def missing_capture_deps() -> list[str]:
    return [pkg for mod, pkg in CAPTURE_DEPS.items() if importlib.util.find_spec(mod) is None]


def install_capture_deps() -> None:
    run([sys.executable, "-m", "pip", "install", "--upgrade", *PIP_PACKAGES])
    run([sys.executable, "-m", "playwright", "install", "chromium"])


def prompt_install(missing: list[str]) -> bool:
    print("Capture dependencies are missing:", ", ".join(missing))
    print(f"  {sys.executable} -m pip install {' '.join(PIP_PACKAGES)}")
    print(f"  {sys.executable} -m playwright install chromium")
    if not sys.stdin.isatty():
        return False
    return input("Install now? [y/N] ").strip().lower() in {"y", "yes"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_label(row: dict[str, str]) -> str:
    return row.get("title") or row.get("creator") or row.get("original_url")


def matches(row: dict[str, str], needle: str) -> bool:
    if not needle:
        return True
    fields = ("title", "creator", "collection", "original_url", "notes")
    return needle.lower() in " ".join(row.get(f, "") for f in fields).lower()


def capture(args: argparse.Namespace) -> int:
    missing = missing_capture_deps()
    if missing:
        if args.install or prompt_install(missing):
            install_capture_deps()
        else:
            return 1

    config = m.load_config()
    sync_sheet(config)

    fields, rows = m.read_manifest()
    targets = [
        row for row in rows
        if matches(row, args.match)
        and m.clean(row.get("original_url"))
        and row.get("status", "").lower() not in {"private", "hidden"}
        and (args.all or m.needs_capture(row))
    ]
    if not targets:
        print("Nothing to capture.")
        return 0

    print(f"{len(targets)} item(s) to capture:")
    for row in targets:
        print(f"  - {row_label(row)}  {row['original_url']}")
    if not args.yes and sys.stdin.isatty():
        if input("Press Enter to capture, or n to cancel: ").strip().lower().startswith("n"):
            print("Cancelled.")
            return 0

    from capture_playwright import capture as capture_site

    page_limit = args.page_limit or int(config["capture"]["page_limit"])
    depth = args.depth if args.depth is not None else int(config["capture"]["depth"])
    failed = 0
    for row in targets:
        target = ROOT / m.wacz_path(row)
        print(f"Capturing {row_label(row)} — {row['original_url']}")
        try:
            capture_site(
                row["original_url"], target, page_limit=page_limit, depth=depth,
                title=row.get("title") or target.stem,
                description=" / ".join(filter(None, [row.get("creator"), row.get("collection")])),
            )
        except Exception as error:  # noqa: BLE001
            if "Executable doesn't exist" in str(error):
                print("  The capture browser is not installed. Run:")
                print(f"    {sys.executable} -m playwright install chromium")
                return 1
            print(f"  ERROR: {error}")
            row["status"] = "recapture-needed"
            failed += 1
            continue
        row["wacz_file"] = target.name
        row["archived_date"] = datetime.now(timezone.utc).date().isoformat()
        row["sha256"] = sha256(target)
        # A successful capture is not a verified replay: a person checks it, then sets ok/partial.
        row["status"] = "review-needed"
        m.write_manifest(fields, rows)

    m.write_manifest(fields, rows)
    print(f"Captured {len(targets) - failed} of {len(targets)}.")
    print("Review with `python3 archive.py view --all`, then set status to ok or partial.")
    return 1 if failed else 0


# ── view / edit / check ──────────────────────────────────────────────


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def view(args: argparse.Namespace) -> int:
    page = "play.html" if args.play else ("index.html?mode=all" if args.all else "index.html")
    url = f"http://localhost:{args.port}/{page}"
    if port_is_open(args.port):
        print(f"Using the server already running at {url}")
        webbrowser.open(url)
        return 0
    print(f"Serving {ROOT} at {url}  (Ctrl+C to stop)")
    threading.Thread(target=lambda: (time.sleep(0.8), webbrowser.open(url)), daemon=True).start()
    return run([sys.executable, "tools/serve.py", str(args.port), str(ROOT)], check=False).returncode


def edit(_: argparse.Namespace) -> int:
    editor = ROOT / "tools" / "manifest-editor.html"
    webbrowser.open(editor.resolve().as_uri())
    print(f"Opened {editor}")
    return 0


def check(args: argparse.Namespace) -> int:
    """Validate manifest.csv and verify every WACZ against its recorded sha256."""
    _, rows = m.read_manifest()
    errors, warnings = [], []
    seen: dict[str, int] = {}
    for line, row in enumerate(rows, start=2):
        label = f"line {line} ({row_label(row) or 'untitled'})"
        status = row.get("status", "").lower()
        url = row.get("original_url", "")
        if status and status not in m.STATUSES:
            errors.append(f"{label}: unknown status '{status}'")
        if url and not re.match(r"https?://", url):
            errors.append(f"{label}: original_url must start with http:// or https://")
        key = m.row_key(row)
        if key in seen:
            warnings.append(f"{label}: same creator/title + collection as line {seen[key]}")
        seen.setdefault(key, line)

        if not row.get("wacz_file"):
            if status in {"review-needed", "ok", "partial"}:
                errors.append(f"{label}: status '{status}' but no wacz_file")
            continue
        path = ROOT / m.wacz_path(row)
        if not path.exists():
            errors.append(f"{label}: missing {m.wacz_path(row)}")
        elif not args.quick and row.get("sha256") and sha256(path) != row["sha256"]:
            errors.append(f"{label}: sha256 mismatch for {m.wacz_path(row)} (file changed or damaged)")

    for item in warnings:
        print(f"WARNING: {item}")
    for item in errors:
        print(f"ERROR: {item}")
    print(f"Checked {len(rows)} row(s): {len(errors)} error(s), {len(warnings)} warning(s).")
    return 1 if errors else 0


def doctor(_: argparse.Namespace) -> int:
    print(f"Python:  {sys.executable}")
    print(f"Folder:  {ROOT}")
    missing = missing_capture_deps()
    print("Capture: " + ("missing " + ", ".join(missing) if missing else "ok"))
    print("View:    ok (standard library only)")
    return 1 if missing else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture and replay websites as WACZ files.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="add a URL to manifest.csv")
    p.add_argument("url")
    p.add_argument("--title", default="")
    p.add_argument("--creator", default="")
    p.add_argument("--collection", default="")
    p.set_defaults(func=add)

    p = sub.add_parser("capture", help="capture rows that need it (pending, ready, recapture)")
    p.add_argument("--install", action="store_true", help="install missing capture dependencies")
    p.add_argument("-y", "--yes", action="store_true", help="do not ask before capturing")
    p.add_argument("--match", default="", help="only rows whose text contains this")
    p.add_argument("--all", action="store_true", help="recapture every matching row")
    p.add_argument("--page-limit", type=int, default=0)
    p.add_argument("--depth", type=int, default=None)
    p.set_defaults(func=capture)

    p = sub.add_parser("view", help="serve this folder locally and open the archive")
    p.add_argument("--all", action="store_true", help="show every row, not only public ones")
    p.add_argument("--play", action="store_true", help="open the standalone player instead")
    p.add_argument("--port", type=int, default=8817)
    p.set_defaults(func=view)

    p = sub.add_parser("edit", help="open the local manifest editor")
    p.set_defaults(func=edit)

    p = sub.add_parser("check", help="validate manifest.csv and verify WACZ checksums")
    p.add_argument("--quick", action="store_true", help="skip checksum verification")
    p.set_defaults(func=check)

    p = sub.add_parser("doctor", help="check installed dependencies")
    p.set_defaults(func=doctor)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
