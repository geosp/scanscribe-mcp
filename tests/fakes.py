"""Test doubles: a clock, a fake OCR engine and its factory. No PaddlePaddle anywhere."""

from __future__ import annotations

import threading


class FakeClock:
    """A monotonic clock that moves only when a test says so."""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start
        self._lock = threading.Lock()

    def __call__(self) -> float:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._now += seconds
