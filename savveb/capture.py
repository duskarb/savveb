"""Capture a website into a WARC with a real browser.

Loads pages in Chromium (Playwright) and records every response. Rendering in a
real browser means JavaScript-heavy sites replay well. Finds pages under the
start URL's path from links, sitemap.xml and link-like buttons (single-page apps),
within depth / page limit.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter

from . import wacz

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


def _in_scope(url: str, prefixes: list[str]) -> bool:
    return any(url.startswith(prefix) for prefix in prefixes)


# Elements that often act as links in single-page apps without an <a href>.
_CLICKABLE = (
    "button:not([type=submit]):not([disabled]), [role=link], [role=tab], [role=menuitem]"
)
_MAX_CLICKS = 20


def _discover_routes(page, url: str, flush, tried: set[str]) -> list[str]:
    """Click link-like buttons; collect the addresses a single-page app moves to.
    Such apps change the address with JavaScript, so the pages never appear as links.
    flush() records what has loaded so far; it must run before navigating away,
    because the browser drops response bodies of the previous document.
    tried holds buttons already clicked on other pages (menus repeat on every page)."""
    found = []
    candidates = page.locator(_CLICKABLE)
    try:
        count = min(candidates.count(), _MAX_CLICKS)
    except Exception:  # noqa: BLE001
        return found
    for index in range(count):
        try:
            target = candidates.nth(index)
            if not target.is_visible():
                continue
            label = target.evaluate("e => e.tagName + ':' + (e.textContent || '').trim().slice(0, 80)")
            if label in tried:
                continue
            tried.add(label)
            target.click(timeout=1500)
            page.wait_for_timeout(500)
        except Exception:  # noqa: BLE001
            continue
        now = urldefrag(page.url).url
        flush()
        if now != url:
            found.append(now)
            try:
                page.goto(url, wait_until="load", timeout=45000)
                page.wait_for_timeout(500)
            except Exception:  # noqa: BLE001
                break
    return found


def _sitemap_urls(context, page_url: str) -> list[str]:
    parts = urlsplit(page_url)
    try:
        response = context.request.get(f"{parts.scheme}://{parts.netloc}/sitemap.xml", timeout=15000)
        if not response.ok:
            return []
        return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", response.text())
    except Exception:  # noqa: BLE001
        return []


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


def _capture_to_warc(seed_urls: list[str], warc_path: Path, page_limit: int, depth: int):
    from playwright.sync_api import sync_playwright

    # The scope is set from where each start URL ends up after redirects (e.g. adding www.).
    prefixes = [_scope_prefix(url) for url in seed_urls]
    seen_resources: set[str] = set()
    visited_pages: set[str] = set()
    pages: list[dict] = []
    queue: list[tuple[str, int]] = [(urldefrag(url).url, 0) for url in seed_urls]
    queued = {url for url, _ in queue}
    written = 0
    saved = 0

    def enqueue(target: str, level: int) -> None:
        target = urldefrag(target).url
        if target not in queued and _in_scope(target, prefixes):
            queued.add(target)
            queue.append((target, level))

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
            # Buttons that open new tabs or windows are not followed.
            context.on("page", lambda popup: popup.close() if popup != page else None)
            pending = []
            page.on("response", lambda response: pending.append(response))
            checked_sitemaps: set[str] = set()
            tried_buttons: set[str] = set()

            def flush() -> None:
                """Write every response seen so far that is not recorded yet."""
                nonlocal written, saved
                for response in list(pending):
                    res_url = urldefrag(response.url).url
                    if not res_url.startswith(("http://", "https://")) or res_url in seen_resources:
                        continue
                    try:
                        body = response.body()
                    except Exception:  # noqa: BLE001
                        if not 300 <= response.status < 400:
                            continue  # body not available now; record it if it loads again
                        body = b""  # redirects have no body
                    seen_resources.add(res_url)
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
                pending.clear()

            while queue and len(pages) < page_limit:
                url, level = queue.pop(0)
                if url in visited_pages:
                    continue
                visited_pages.add(url)

                page_title = url
                print(f"  [{len(pages) + 1}] {url}")
                try:
                    page.goto(url, wait_until="load", timeout=45000)
                    page.wait_for_timeout(1200)
                    page.evaluate(_AUTOSCROLL)
                    page.wait_for_timeout(500)
                    page_title = page.title() or url
                except Exception as error:  # noqa: BLE001
                    print(f"    warn: {url} load warning: {error}")

                landed = urldefrag(page.url).url
                if landed != url:
                    visited_pages.add(landed)
                    queued.add(landed)
                    if level == 0 and not _in_scope(landed, prefixes):
                        prefixes.append(_scope_prefix(landed))

                origin = "{0.scheme}://{0.netloc}".format(urlsplit(landed))
                if origin not in checked_sitemaps:
                    checked_sitemaps.add(origin)
                    for target in _sitemap_urls(context, landed):
                        enqueue(target, 1)

                pages.append({
                    "id": hashlib.sha1(landed.encode()).hexdigest()[:16],
                    "url": landed,
                    "title": page_title,
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
                flush()

                links = []
                if level < depth:
                    try:
                        links = page.eval_on_selector_all(
                            "a[href]", "els => els.map(e => e.href)"
                        )
                    except Exception:  # noqa: BLE001
                        links = []
                    # Clicking also loads lazily fetched code; flush() records it.
                    links += _discover_routes(page, landed, flush, tried_buttons)
                    flush()

                for link in links:
                    enqueue(link, level + 1)

            browser.close()

    left = len({u for u, _ in queue} - visited_pages)
    return written, pages, saved, left


class BrowserMissing(RuntimeError):
    """Playwright is installed but its Chromium is not."""


def capture(seed_urls: list[str], out_path: Path, page_limit: int = 500, depth: int = 20) -> dict:
    """Capture one site, starting from seed_urls, into a WACZ at out_path.
    Returns counts: pages, resources, saved (bytes), left (pages found but over the limit)."""
    out_path = Path(out_path)
    with tempfile.TemporaryDirectory() as tmp:
        warc_path = Path(tmp) / "data.warc.gz"
        try:
            count, pages, saved, left = _capture_to_warc(seed_urls, warc_path, page_limit, depth)
        except Exception as error:  # noqa: BLE001
            if "Executable doesn't exist" in str(error):
                raise BrowserMissing(str(error)) from error
            raise
        if count == 0:
            raise RuntimeError(f"nothing was recorded from {seed_urls[0]}")
        title = pages[0]["title"] if pages else seed_urls[0]
        partial = out_path.with_name(out_path.name + ".part")
        wacz.package(warc_path, partial, pages, pages[0]["url"] if pages else seed_urls[0], title)
        partial.replace(out_path)
    return {"pages": len(pages), "resources": count, "saved": saved, "left": left}
