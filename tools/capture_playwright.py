#!/usr/bin/env python3
"""Capture a website into a WACZ file without Docker.

Loads pages in a real Chromium (Playwright), records every response into a WARC,
then packages it as WACZ with the `wacz` tool. Like Browsertrix, rendering in a
real browser means JavaScript-heavy sites replay well.

Follows links under the seed URL's path prefix, within depth / page-limit.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter

# Drop headers that break replay. Playwright's body() is already decoded,
# so the original content-encoding/length no longer apply.
_SKIP_HEADERS = {"content-encoding", "content-length", "transfer-encoding", "connection"}

# ── Image optimization (env vars; ARCHIVE_OPTIMIZE=0 turns it off) ──
# Unoptimized photos make WACZ files huge. Large images are downscaled to screen size
# and recompressed, and replaced only when the result is smaller.
_OPTIMIZE = os.environ.get("ARCHIVE_OPTIMIZE", "1") != "0"
_OPT_MAX_DIM = int(os.environ.get("ARCHIVE_IMG_MAX_DIM", "2000"))   # max long edge, px
_OPT_QUALITY = int(os.environ.get("ARCHIVE_IMG_QUALITY", "82"))     # JPEG quality
_OPT_MIN_BYTES = int(os.environ.get("ARCHIVE_IMG_MIN_BYTES", "300000"))  # smaller files are left alone


def _optimize_image(content_type: str, body: bytes) -> tuple[bytes, str]:
    """Downscale and recompress a large image; keep it only if smaller.
    Returns (body, content_type). Without Pillow, or on failure, returns the original."""
    if not _OPTIMIZE or len(body) < _OPT_MIN_BYTES:
        return body, content_type
    ct = (content_type or "").lower()
    if "image/jpeg" not in ct and "image/png" not in ct:
        return body, content_type
    try:
        from PIL import Image
    except Exception:
        return body, content_type
    try:
        im = Image.open(BytesIO(body))
        im.load()
    except Exception:
        return body, content_type
    if getattr(im, "is_animated", False):  # leave animations (APNG etc.) alone
        return body, content_type

    width, height = im.size
    if max(width, height) > _OPT_MAX_DIM:
        scale = _OPT_MAX_DIM / max(width, height)
        im = im.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.LANCZOS)

    has_alpha = "a" in im.mode.lower() or (im.mode == "P" and "transparency" in im.info)
    out = BytesIO()
    if "png" in ct and has_alpha:
        # keep PNG when there is transparency
        im.save(out, format="PNG", optimize=True)
        new_ct = "image/png"
    else:
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.save(out, format="JPEG", quality=_OPT_QUALITY, optimize=True, progressive=True)
        new_ct = "image/jpeg"

    data = out.getvalue()
    return (data, new_ct) if len(data) < len(body) else (body, content_type)

# Scroll to trigger lazy-loaded content, then return to the top.
_AUTOSCROLL = """
async () => {
  const step = () => new Promise(r => setTimeout(r, 250));
  let last = -1;
  for (let i = 0; i < 40; i++) {
    window.scrollTo(0, document.body.scrollHeight);
    await step();
    const h = document.body.scrollHeight;
    if (h === last) break;
    last = h;
  }
  window.scrollTo(0, 0);
}
"""


def _scope_prefix(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rsplit("/", 1)[0] + "/" if "/" in parts.path else "/"
    return f"{parts.scheme}://{parts.netloc}{path}"


def _in_scope(url: str, prefix: str) -> bool:
    return url.startswith(prefix)


def _write_record(writer: WARCWriter, response, body: bytes, content_type: str) -> None:
    raw = response.request
    url = response.url

    # set content-type ourselves (optimization may change it)
    skip = _SKIP_HEADERS | {"content-type"}
    headers = [(k, v) for k, v in response.headers.items() if k.lower() not in skip]
    if content_type:
        headers.append(("Content-Type", content_type))
    headers.append(("Content-Length", str(len(body))))
    status_line = f"{response.status} {response.status_text or 'OK'}"
    http_headers = StatusAndHeaders(status_line, headers, protocol="HTTP/1.1")
    record = writer.create_warc_record(
        url, "response", payload=BytesIO(body), http_headers=http_headers
    )
    writer.write_record(record)

    req_headers = StatusAndHeaders(
        f"{raw.method} {urlsplit(url).path or '/'} HTTP/1.1",
        [(k, v) for k, v in raw.headers.items() if k.lower() not in _SKIP_HEADERS],
        is_http_request=True,
    )
    writer.write_record(
        writer.create_warc_record(url, "request", http_headers=req_headers)
    )


def _capture_to_warc(seed_url: str, warc_path: Path, page_limit: int, depth: int):
    from playwright.sync_api import sync_playwright

    prefix = _scope_prefix(seed_url)
    seen_resources: set[str] = set()
    visited_pages: set[str] = set()
    pages: list[dict] = []
    queue: list[tuple[str, int]] = [(urldefrag(seed_url).url, 0)]
    written = 0
    saved = 0

    with open(warc_path, "wb") as stream:
        writer = WARCWriter(stream, gzip=True)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36 savveb-playwright"
                )
            )
            page = context.new_page()
            pending = []
            page.on("response", lambda response: pending.append(response))

            while queue and len(visited_pages) < page_limit:
                url, level = queue.pop(0)
                if url in visited_pages:
                    continue
                visited_pages.add(url)
                pending.clear()

                page_title = url
                try:
                    page.goto(url, wait_until="load", timeout=45000)
                    page.wait_for_timeout(1200)
                    page.evaluate(_AUTOSCROLL)
                    page.wait_for_timeout(500)
                    page_title = page.title() or url
                except Exception as error:  # noqa: BLE001
                    print(f"    warn: {url} load warning: {error}")

                pages.append({
                    "id": hashlib.sha1(url.encode()).hexdigest()[:16],
                    "url": url,
                    "title": page_title,
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

                for response in list(pending):
                    res_url = urldefrag(response.url).url
                    if not res_url.startswith(("http://", "https://")):
                        continue
                    if res_url in seen_resources:
                        continue
                    seen_resources.add(res_url)
                    try:
                        body = response.body()
                    except Exception:  # noqa: BLE001 (redirects etc. have no body)
                        body = b""
                    content_type = ""
                    for key, value in response.headers.items():
                        if key.lower() == "content-type":
                            content_type = value
                            break
                    original_len = len(body)
                    body, content_type = _optimize_image(content_type, body)
                    saved += original_len - len(body)
                    try:
                        _write_record(writer, response, body, content_type)
                        written += 1
                    except Exception as error:  # noqa: BLE001
                        print(f"    warn: {res_url} not recorded: {error}")

                if level < depth:
                    try:
                        links = page.eval_on_selector_all(
                            "a[href]", "els => els.map(e => e.href)"
                        )
                    except Exception:  # noqa: BLE001
                        links = []
                    for link in links:
                        target = urldefrag(link).url
                        if _in_scope(target, prefix) and target not in visited_pages:
                            queue.append((target, level + 1))

            browser.close()

    return written, pages, saved


def _wacz_bin() -> str:
    candidate = Path(sys.executable).parent / "wacz"
    return str(candidate) if candidate.exists() else "wacz"


def capture(seed_url: str, wacz_path: Path, page_limit: int = 30, depth: int = 3,
            title: str = "", description: str = "") -> Path:
    """Capture seed_url into a WACZ at wacz_path and return that path."""
    wacz_path = Path(wacz_path)
    wacz_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        warc_path = Path(tmp) / "capture.warc.gz"
        count, pages, saved = _capture_to_warc(seed_url, warc_path, page_limit, depth)
        if count == 0:
            raise RuntimeError(f"no responses were recorded from {seed_url}")
        saved_note = f", images optimized, {saved / 1024 / 1024:.1f} MB saved" if saved > 0 else ""
        print(f"    {count} resources, {len(pages)} page(s){saved_note} → packaging WACZ")

        pages_path = Path(tmp) / "pages.jsonl"
        with pages_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(
                {"format": "json-pages-1.0", "id": "pages", "title": "All Pages"}
            ) + "\n")
            for entry in pages:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

        argv = [
            _wacz_bin(), "create", str(warc_path),
            "-o", str(wacz_path),
            "--pages", str(pages_path), "--url", seed_url,
        ]
        if title:
            argv += ["--title", title]
        if description:
            argv += ["--desc", description]
        if wacz_path.exists():  # replace the old file on recapture
            wacz_path.unlink()
        subprocess.run(argv, check=True, env={**os.environ})

    return wacz_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Capture a website into a WACZ file")
    parser.add_argument("url")
    parser.add_argument("-o", "--out", required=True)
    parser.add_argument("--page-limit", type=int, default=30)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    args = parser.parse_args()

    out = capture(
        args.url, Path(args.out), args.page_limit, args.depth,
        args.title, args.description,
    )
    print(f"Saved: {out}")
