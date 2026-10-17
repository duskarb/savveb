"""Package a WARC into a WACZ file (https://specs.webrecorder.net/wacz/1.1.1/).

A WACZ is a zip with the WARC, a CDXJ index of it, a page list and a manifest
(datapackage.json) holding a sha256 for every file. The WARC is stored
uncompressed in the zip so players can read it with range requests.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from cdxj_indexer.main import CDXJIndexer

from . import __version__

WACZ_VERSION = "1.1.1"


def _index(warc_path: Path) -> bytes:
    out = io.StringIO()
    CDXJIndexer(
        out,
        [str(warc_path)],
        sort=True,
        post_append=True,
        digest_records=True,
        fields="referrer,req.http:cookie",
    ).process_all()
    return out.getvalue().encode("utf-8")


def _pages(pages: list[dict]) -> bytes:
    lines = [{"format": "json-pages-1.0", "id": "pages", "title": "All Pages"}, *pages]
    return "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines).encode("utf-8")


def package(warc_path: Path, out_path: Path, pages: list[dict], main_url: str, title: str = "") -> None:
    """Write out_path (.wacz) from warc_path. warc_path's name becomes the name inside the zip."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with zipfile.ZipFile(out_path, "w") as wacz:
        wacz.write(warc_path, f"archive/{warc_path.name}", compress_type=zipfile.ZIP_STORED)
        wacz.writestr("indexes/index.cdxj", _index(warc_path), compress_type=zipfile.ZIP_DEFLATED)
        wacz.writestr("pages/pages.jsonl", _pages(pages), compress_type=zipfile.ZIP_DEFLATED)

        resources = []
        for entry in wacz.infolist():
            digest = hashlib.sha256()
            with wacz.open(entry) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            resources.append({
                "name": Path(entry.filename).name,
                "path": entry.filename,
                "hash": f"sha256:{digest.hexdigest()}",
                "bytes": entry.file_size,
            })

        datapackage = {
            "profile": "data-package",
            "resources": resources,
            "title": title or main_url,
            "mainPageURL": main_url,
            "mainPageDate": pages[0]["ts"] if pages else now,
            "created": now,
            "wacz_version": WACZ_VERSION,
            "software": f"savveb {__version__}",
        }
        data = json.dumps(datapackage, indent=2).encode("utf-8")
        wacz.writestr("datapackage.json", data, compress_type=zipfile.ZIP_DEFLATED)
        digest = {"path": "datapackage.json", "hash": "sha256:" + hashlib.sha256(data).hexdigest()}
        wacz.writestr("datapackage-digest.json", json.dumps(digest), compress_type=zipfile.ZIP_DEFLATED)
