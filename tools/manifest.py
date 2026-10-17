"""Shared manifest.csv and savveb.json helpers (standard library only)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.csv"
CONFIG = ROOT / "savveb.json"

# Editable columns on the left, machine-filled columns on the right.
FIELDS = [
    "title", "creator", "collection", "original_url", "status", "notes",
    "link", "wacz_file", "archived_date", "sha256",
]

# Older or hand-made manifests may use other header names; they are read as the canonical ones.
ALIASES = {
    "creator": ("creator", "student_name", "name", "author", "student", "이름", "성명"),
    "collection": ("collection", "semester", "class", "course", "수업", "학기"),
    "original_url": ("original_url", "url", "link_url", "링크", "주소"),
    "title": ("title", "work", "제목", "작품"),
    "link": ("link", "drive_link"),
}

STATUSES = [
    "pending", "ready-to-capture", "review-needed", "ok", "partial",
    "recapture-needed", "private", "hidden",
]
CAPTURE_STATUSES = {"", "pending", "ready-to-capture", "recapture-needed"}
PUBLIC_STATUSES = {"ok", "partial"}

DEFAULT_CONFIG = {
    "title": "Web Archive",
    "description": "",
    "labels": {"creator": "Creator", "collection": "Collection"},
    "intake_sheet": "",
    "capture": {"page_limit": 30, "depth": 3},
}


def clean(value: str | None) -> str:
    return (value or "").strip()


def slug(value: str) -> str:
    allowed = []
    for char in value.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {" ", "-", "_", "."}:
            allowed.append("-")
    collapsed = "-".join(part for part in "".join(allowed).split("-") if part)
    return collapsed or "untitled"


def load_config() -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if CONFIG.exists():
        loaded = json.loads(CONFIG.read_text(encoding="utf-8"))
        for key, value in loaded.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    return config


def normalize(raw: dict[str, str]) -> dict[str, str]:
    """Map a raw CSV/sheet row onto canonical field names. Unknown columns are kept."""
    row = {clean(key): clean(value) for key, value in raw.items() if key is not None}
    out: dict[str, str] = {}
    used: set[str] = set()
    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            if alias in row:
                used.add(alias)
                if clean(row[alias]) and not out.get(canonical):
                    out[canonical] = row[alias]
        out.setdefault(canonical, "")
    for key, value in row.items():
        if key not in used:
            out.setdefault(key, value)
    return out


def parse_rows(text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text))
    extra = []
    for name in reader.fieldnames or []:
        name = clean(name)
        if name and name not in FIELDS and not any(name in a for a in ALIASES.values()):
            extra.append(name)
    rows = [normalize(raw) for raw in reader]
    return FIELDS + extra, [row for row in rows if any(row.values())]


def read_manifest(path: Path = MANIFEST) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return list(FIELDS), []
    return parse_rows(path.read_text(encoding="utf-8-sig"))


def write_manifest(fields: list[str], rows: list[dict[str, str]], path: Path = MANIFEST) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def row_key(row: dict[str, str]) -> str:
    """Identity of a row = creator (or title, or URL) + collection. Also the WACZ file stem."""
    base = clean(row.get("creator")) or clean(row.get("title")) or clean(row.get("original_url"))
    collection = clean(row.get("collection")) or "uncollected"
    return f"{slug(base)}-{slug(collection)}"


def wacz_path(row: dict[str, str]) -> str:
    """Relative path of a row's WACZ: wacz/<collection>/<file>. Same rule as index.html."""
    collection = clean(row.get("collection")) or "uncollected"
    name = clean(row.get("wacz_file")) or f"{row_key(row)}.wacz"
    return f"wacz/{collection}/{name}"


def needs_capture(row: dict[str, str]) -> bool:
    return bool(clean(row.get("original_url"))) and clean(row.get("status")).lower() in CAPTURE_STATUSES
