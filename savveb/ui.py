"""Terminal output: a bear that paces while savveb works, and its moods.

In a terminal the bottom line is a live status that redraws in place; log lines
print above it. When output is piped or redirected, only plain lines are written.
"""

from __future__ import annotations

import os
import sys
import threading
import time

BEAR = "ʕ•ᴥ•ʔ"
BLINK = "ʕ-ᴥ-ʔ"
HAPPY = "ʕ•̀ᴥ•́ʔ✧"
SAD = "ʕ ´•̥ᴥ•̥`ʔ"
OOPS = "ʕ ºᴥºʔ"
ASK = "ʕ•ᴥ•ʔ?"
PLAY = "ʕ•ᴥ•ʔ▶"

_TRACK = 6  # how many columns the bear paces across


def _frame(tick: int) -> str:
    step = tick % (_TRACK * 2 - 2)
    pos = step if step < _TRACK else _TRACK * 2 - 2 - step
    face = BLINK if tick % 24 == 0 else BEAR
    return " " * pos + face + " " * (_TRACK - 1 - pos)


def elapsed(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}m {seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


class Status:
    """Live status line. Use as a context manager around the long-running work."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout
        self.live = self.stream.isatty()
        self.text = ""
        self.started = time.monotonic()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        if self.live:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join()
        self._clear()
        return False

    def _clear(self) -> None:
        if self.live:
            with self._lock:
                self.stream.write("\r\x1b[2K")
                self.stream.flush()

    def _run(self) -> None:
        tick = 0
        while not self._stop.wait(0.12):
            with self._lock:
                line = f"  {_frame(tick)}  {self.text}  {elapsed(time.monotonic() - self.started)}"
                width = _columns(self.stream)
                self.stream.write("\r\x1b[2K" + line[: width - 1])
                self.stream.flush()
            tick += 1

    def update(self, text: str) -> None:
        self.text = text

    def log(self, line: str) -> None:
        with self._lock:
            if self.live:
                self.stream.write("\r\x1b[2K")
            self.stream.write(line + "\n")
            self.stream.flush()


def _columns(stream) -> int:
    try:
        columns = os.get_terminal_size(stream.fileno()).columns
    except (OSError, ValueError, AttributeError):
        columns = 0
    return columns if columns > 20 else 80
