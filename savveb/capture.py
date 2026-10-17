"""Capture a website into a WARC with a real browser.

Loads pages in Chromium (Playwright) and records every response. Rendering in a
real browser means JavaScript-heavy sites replay well. Finds pages under the
start URL's path from links, sitemap.xml and link-like buttons (single-page apps),
within depth / page limit. Several tabs work in parallel.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import tempfile
from collections import deque
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

# Scroll down one screen at a time so lazy-loaded content anywhere on the page
# loads, then return to the top. Stops at the bottom, or after ~10 seconds.
_AUTOSCROLL = """
async () => {
  const pause = () => new Promise(r => setTimeout(r, 120));
  const started = Date.now();
  let y = 0;
  while (Date.now() - started < 10000) {
    y += window.innerHeight;
    window.scrollTo(0, y);
    await pause();
    if (y + window.innerHeight >= document.documentElement.scrollHeight) {
      await pause();
      if (y + window.innerHeight >= document.documentElement.scrollHeight) break;
    }
  }
  window.scrollTo(0, 0);
}
"""


async def _settle(page, timeout: int) -> None:
    """Wait until the network goes quiet, but never longer than timeout ms
    (sites with analytics or polling never go fully quiet)."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:  # noqa: BLE001
        pass


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

# Ads, analytics and tracking: useless in an archive, so they are never downloaded.
_TRACKERS = re.compile(
    r"^https?://([^/]*\.)?("
    r"google-analytics\.com|googletagmanager\.com|doubleclick\.net|googlesyndication\.com|"
    r"googleadservices\.com|adservice\.google\.[a-z.]+|facebook\.net|connect\.facebook\.com|"
    r"hotjar\.com|hotjar\.io|clarity\.ms|segment\.(io|com)|mixpanel\.com|amplitude\.com|"
    r"plausible\.io|matomo\.cloud|newrelic\.com|nr-data\.net|fullstory\.com|"
    r"analytics\.tiktok\.com|ads-twitter\.com|analytics\.twitter\.com|bat\.bing\.com|"
    r"scorecardresearch\.com|quantserve\.com|criteo\.(com|net)|taboola\.com|outbrain\.com|"
    r"wcs\.naver\.(net|com)|ssl\.pstatic\.net/tveta|analytics\.kakao\.com|analytics\.yahoo\.com|"
    r"usefathom\.com|adsrvr\.org|adnxs\.com|rubiconproject\.com|pubmatic\.com|casalemedia\.com|"
    r"openx\.net|bidswitch\.net|demdex\.net|everesttech\.net|adform\.net|smartadserver\.com"
    r")/|/_vercel/(insights|speed-insights)/|/cdn-cgi/rum"
)


class _Fetched:
    """A response fetched outside the page (e.g. a file the browser would download),
    shaped like a Playwright response for _write_record."""

    def __init__(self, response, body: bytes):
        self.url = response.url
        self.status = response.status
        self.status_text = response.status_text
        self.headers = response.headers
        self.request = type("Request", (), {"method": "GET", "headers": {}})()
        self.body = body


async def _discover_routes(page, url: str, flush, tried: set[str]) -> list[str]:
    """Click link-like buttons; collect the addresses a single-page app moves to.
    Such apps change the address with JavaScript, so the pages never appear as links.
    flush() records what has loaded so far; it must run before navigating away,
    because the browser drops response bodies of the previous document.
    tried holds buttons already clicked on other pages (menus repeat on every page)."""
    found = []
    candidates = page.locator(_CLICKABLE)
    try:
        count = min(await candidates.count(), _MAX_CLICKS)
    except Exception:  # noqa: BLE001
        return found
    for index in range(count):
        try:
            target = candidates.nth(index)
            if not await target.is_visible():
                continue
            label = await target.evaluate("e => e.tagName + ':' + (e.textContent || '').trim().slice(0, 80)")
            if label in tried:
                continue
            tried.add(label)
            await target.click(timeout=1500)
            await page.wait_for_timeout(400)
        except Exception:  # noqa: BLE001
            continue
        now = urldefrag(page.url).url
        await flush()
        if now != url:
            found.append(now)
            # Going back is instant for single-page apps; reload only if that fails.
            try:
                await page.go_back(timeout=5000)
            except Exception:  # noqa: BLE001
                pass
            if urldefrag(page.url).url != url:
                try:
                    await page.goto(url, wait_until="load", timeout=45000)
                except Exception:  # noqa: BLE001
                    break
            await page.wait_for_timeout(200)
    return found


async def _sitemap_urls(context, page_url: str) -> list[str]:
    parts = urlsplit(page_url)
    try:
        response = await context.request.get(f"{parts.scheme}://{parts.netloc}/sitemap.xml", timeout=15000)
        if not response.ok:
            return []
        return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", await response.text())
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


async def _capture_to_warc(seed_urls: list[str], warc_path: Path, page_limit: int, depth: int,
                           parallel: int, log, progress):
    from playwright.async_api import async_playwright

    # The scope is set from where each start URL ends up after redirects (e.g. adding www.).
    prefixes = [_scope_prefix(url) for url in seed_urls]
    seen_resources: set[str] = set()
    fetching: set[str] = set()
    refetch: set[str] = set()
    visited_pages: set[str] = set()
    pages: list[dict] = []
    queue: deque[tuple[str, int]] = deque((urldefrag(url).url, 0) for url in seed_urls)
    queued = {url for url, _ in queue}
    checked_sitemaps: set[str] = set()
    tried_buttons: set[str] = set()
    counts = {"written": 0, "saved": 0, "started": 0, "busy": 0}

    def enqueue(target: str, level: int) -> None:
        target = urldefrag(target).url
        if target not in queued and _in_scope(target, prefixes):
            queued.add(target)
            queue.append((target, level))

    with open(warc_path, "wb") as stream:
        writer = WARCWriter(stream, gzip=True)

        def report(current: str = "") -> None:
            progress(len(pages), counts["written"], stream.tell(), current)

        async def flush(pending: list) -> None:
            """Write every response this tab has seen that is not recorded yet."""
            batch = list(pending)
            pending.clear()
            for response in batch:
                res_url = urldefrag(response.url).url
                if not res_url.startswith(("http://", "https://")) or _TRACKERS.search(res_url):
                    continue  # trackers reached through redirects are not blocked, so skip them here
                if res_url in seen_resources or res_url in fetching:
                    continue
                fetching.add(res_url)
                try:
                    try:
                        body = await response.body()
                    except Exception:  # noqa: BLE001
                        if not 300 <= response.status < 400:
                            continue  # body not available now; record it if it loads again
                        body = b""  # redirects have no body
                    headers = await response.all_headers()
                    if not body and 200 <= response.status < 300 and headers.get("content-length") != "0":
                        # Prefetched or evicted responses can come back empty; fetch it again later.
                        refetch.add(res_url)
                        continue
                    content_type = headers.get("content-type", "")
                    original_len = len(body)
                    if _OPTIMIZE and original_len >= _OPT_MIN_BYTES:
                        body, content_type = await asyncio.to_thread(_optimize_image, content_type, body)
                    counts["saved"] += original_len - len(body)
                    try:
                        _write_record(writer, response, body, content_type)
                        counts["written"] += 1
                        seen_resources.add(res_url)
                    except Exception as error:  # noqa: BLE001
                        log(f"    warn: {res_url} not recorded: {error}")
                finally:
                    fetching.discard(res_url)
            report()

        async def save_download(context, url: str) -> None:
            """Fetch url directly and record it: files such as PDFs make the browser
            download instead of showing a page, and some bodies never reach the page."""
            if url in seen_resources:
                return
            try:
                response = await context.request.get(url, timeout=60000)
                fetched = _Fetched(response, await response.body())
                _write_record(writer, fetched, fetched.body, response.headers.get("content-type", ""))
                counts["written"] += 1
                seen_resources.add(url)
            except Exception as error:  # noqa: BLE001
                log(f"       could not download {url}: {str(error).splitlines()[0]}")

        async def visit(context, page, pending: list, url: str, level: int) -> None:
            number = counts["started"]
            log(f"  {number:>3}  {url}")
            report(url)
            page_title = url
            try:
                await page.goto(url, wait_until="load", timeout=45000)
                await _settle(page, 1500)
                await page.evaluate(_AUTOSCROLL)
                await _settle(page, 1000)
                page_title = await page.title() or url
            except Exception as error:  # noqa: BLE001
                if "Download is starting" in str(error):
                    await save_download(context, url)
                    page_title = url.rsplit("/", 1)[-1]
                else:
                    log(f"       could not fully load: {str(error).splitlines()[0]}")

            landed = urldefrag(page.url).url
            if landed != url:
                visited_pages.add(landed)
                queued.add(landed)
                if level == 0 and not _in_scope(landed, prefixes):
                    prefixes.append(_scope_prefix(landed))

            origin = "{0.scheme}://{0.netloc}".format(urlsplit(landed))
            if origin not in checked_sitemaps:
                checked_sitemaps.add(origin)
                for target in await _sitemap_urls(context, landed):
                    enqueue(target, 1)

            pages.append({
                "id": hashlib.sha1(landed.encode()).hexdigest()[:16],
                "url": landed,
                "title": page_title,
                "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            await flush(pending)

            if level < depth:
                try:
                    links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                except Exception:  # noqa: BLE001
                    links = []
                # Clicking also loads lazily fetched code; flush() records it.
                links += await _discover_routes(page, landed, lambda: flush(pending), tried_buttons)
                await flush(pending)
                for link in links:
                    enqueue(link, level + 1)

        async def worker(context, page) -> None:
            pending: list = []
            page.on("response", lambda response: pending.append(response))
            while counts["started"] < page_limit:
                if not queue:
                    if counts["busy"] == 0:
                        return  # nothing left, and no other tab can find more
                    await asyncio.sleep(0.1)
                    continue
                url, level = queue.popleft()
                if url in visited_pages:
                    continue
                visited_pages.add(url)
                counts["started"] += 1
                counts["busy"] += 1
                try:
                    await visit(context, page, pending, url, level)
                finally:
                    counts["busy"] -= 1

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36 savveb-playwright"
                )
            )
            await context.route(_TRACKERS, lambda route: route.abort())
            tabs = [await context.new_page() for _ in range(max(1, parallel))]
            # Buttons that open new tabs or windows are not followed.
            context.on("page", lambda popup: None if popup in tabs else asyncio.ensure_future(popup.close()))
            # The first tab finds the real address (redirects) before the others start.
            first = asyncio.ensure_future(worker(context, tabs[0]))
            while not pages and not first.done():
                await asyncio.sleep(0.05)
            await asyncio.gather(first, *(worker(context, tab) for tab in tabs[1:]))
            for url in sorted(refetch - seen_resources):
                await save_download(context, url)
            await browser.close()

    left = len({u for u, _ in queue} - visited_pages)
    return counts["written"], pages, counts["saved"], left


class BrowserMissing(RuntimeError):
    """Playwright is installed but its Chromium is not."""


def capture(seed_urls: list[str], out_path: Path, page_limit: int = 500, depth: int = 20,
            parallel: int = 4, log=print, progress=lambda *args: None) -> dict:
    """Capture one site, starting from seed_urls, into a WACZ at out_path.
    log(line) prints a line; progress(pages, files, bytes, url) reports where it is.
    Returns counts: pages, resources, saved (bytes), left (pages found but over the limit)."""
    out_path = Path(out_path)
    with tempfile.TemporaryDirectory() as tmp:
        warc_path = Path(tmp) / "data.warc.gz"
        try:
            count, pages, saved, left = asyncio.run(
                _capture_to_warc(seed_urls, warc_path, page_limit, depth, parallel, log, progress))
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
