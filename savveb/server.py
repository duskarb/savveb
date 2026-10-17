"""Minimal static server with HTTP Range support (standard library only).

ReplayWeb.page reads only the parts of a WACZ it needs, using Range requests.
Python's built-in `http.server` has no Range support, so large files fail with
"lack of range request support". This server answers 206 Partial Content.

`savveb play` uses it to serve the player (the web/ files) plus one local
archive file, which is mapped to /local/<name>.
"""

from __future__ import annotations

import functools
import http.server
import os


class _LimitReader:
    """Reads exactly `length` bytes from the wrapped file."""

    def __init__(self, fp, length):
        self.fp = fp
        self.remaining = length

    def read(self, size=-1):
        if self.remaining <= 0:
            return b""
        if size is None or size < 0 or size > self.remaining:
            size = self.remaining
        data = self.fp.read(size)
        self.remaining -= len(data)
        return data

    def close(self):
        self.fp.close()


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    local_files: dict[str, str] = {}  # URL path -> file on disk

    def translate_path(self, path):
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean in self.local_files:
            return self.local_files[clean]
        return super().translate_path(path)

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()

        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        try:
            stat = os.fstat(f.fileno())
            size = stat.st_size
            ctype = self.guess_type(path)
            rng = self.headers.get("Range")

            if not rng:
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
                self.end_headers()
                return f

            # parse "bytes=start-end" (and the suffix form "bytes=-N")
            try:
                unit, _, spec = rng.partition("=")
                if unit.strip().lower() != "bytes":
                    raise ValueError
                start_s, _, end_s = spec.strip().partition("-")
                if start_s == "":
                    length = int(end_s)
                    start = max(0, size - length)
                    end = size - 1
                else:
                    start = int(start_s)
                    end = int(end_s) if end_s else size - 1
                if start > end or start >= size:
                    raise ValueError
                end = min(end, size - 1)
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                f.close()
                return None

            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
            self.end_headers()
            f.seek(start)
            return _LimitReader(f, length)
        except Exception:
            f.close()
            raise

    def log_message(self, *args):
        pass  # keep the terminal quiet


def make_server(port: int, web_root: str, local_files: dict[str, str]):
    handler = type("Handler", (RangeHandler,), {"local_files": local_files})
    factory = functools.partial(handler, directory=web_root)
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), factory)
