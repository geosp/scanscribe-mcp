"""Test doubles: a clock, a fake OCR engine and its factory. No PaddlePaddle anywhere."""

from __future__ import annotations

import threading
import weakref
from collections.abc import Callable
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from scanscribe import PageImage


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


PageHook = Callable[[], None]


class FakeEngine:
    """scanscribe's one-method OcrEngine shape. Each call is one page when columns is 1.

    It returns `page <n>` (the call count) and `gray <v>` (the image's first pixel), so a test
    can tell which page and which image it saw. `hooks[n]` runs before page n is recognized:
    it may block, raise or print.
    """

    def __init__(
        self,
        lang: str,
        device: str,
        hooks: dict[int, PageHook] | None = None,
        lines_per_page: int = 1,
        print_to_stdout: bool = False,
    ) -> None:
        self.lang = lang
        self.device = device
        self.hooks = hooks or {}
        self.lines_per_page = lines_per_page
        self.print_to_stdout = print_to_stdout
        self.seen: list[int] = []

    def recognize(self, image: PageImage) -> list[str]:
        number = len(self.seen) + 1
        self.seen.append(int(image[0, 0, 0]))
        if self.print_to_stdout:
            print(f"fake engine stray output, page {number}")  # the stdio test needs this
        hook = self.hooks.get(number)
        if hook is not None:
            hook()
        extra = [
            f"line {i} of page {number} in {self.lang}" for i in range(2, self.lines_per_page + 1)
        ]
        return [f"page {number}", f"gray {self.seen[-1]}", *extra]


class FakeEngineFactory:
    """Stands in for `scanscribe.load_engine` (D3). Records every call and every engine."""

    def __init__(
        self,
        device: str = "fake:0",
        hooks: dict[int, PageHook] | None = None,
        on_load: PageHook | None = None,
        error: BaseException | None = None,
        lines_per_page: int = 1,
        print_to_stdout: bool = False,
    ) -> None:
        self.device = device
        self.hooks = hooks
        self.on_load = on_load
        self.error = error
        self.lines_per_page = lines_per_page
        self.print_to_stdout = print_to_stdout
        self.calls: list[tuple[str, str | None]] = []
        self.engines: list[weakref.ref[FakeEngine]] = []
        self.alive_at_load: list[list[bool]] = []

    def __call__(
        self, lang: str, device: str | None, *, on_device: Callable[[str], None] | None = None
    ) -> FakeEngine:
        self.calls.append((lang, device))
        self.alive_at_load.append([ref() is not None for ref in self.engines])
        if on_device is not None:
            on_device(device or self.device)
        if self.on_load is not None:
            self.on_load()
        if self.error is not None:
            raise self.error
        engine = FakeEngine(
            lang, device or self.device, self.hooks, self.lines_per_page, self.print_to_stdout
        )
        self.engines.append(weakref.ref(engine))
        return engine

    @property
    def last(self) -> FakeEngine | None:
        """The newest engine, while something else still holds it (only weakly kept here)."""
        return self.engines[-1]() if self.engines else None


# --- fixtures: small images and PDFs made in the tests, never book material -------------------


def make_images(folder: Path, names: list[str], size: tuple[int, int] = (40, 30)) -> Path:
    """One PNG (or the suffix given) per name; image i is filled with gray level i + 1."""
    folder.mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(names):
        Image.new("RGB", size, (index + 1,) * 3).save(folder / name)
    return folder


def make_pages(folder: Path, count: int) -> Path:
    return make_images(folder, [f"p{n}.png" for n in range(1, count + 1)])


def make_pdf(path: Path, pages: int, size_pt: tuple[float, float] = (72.0, 72.0)) -> Path:
    """A PDF of blank pages, `size_pt` points each (72 points to the inch)."""
    document = pdfium.PdfDocument.new()
    try:
        for _ in range(pages):
            document.new_page(*size_pt).close()
        document.save(path)
    finally:
        document.close()
    return path
