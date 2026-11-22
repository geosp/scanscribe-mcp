"""The document store and its download route (task 02/2.1).

D6, R20.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scanscribe_mcp.documents import DocumentStore, mime_type_for, safe_filename

from .fakes import FakeClock
from .http_helpers import http_server

BASE = "http://scanscribe.test:8302"


@pytest.fixture
def store(tmp_path: Path) -> DocumentStore:
    store = DocumentStore(tmp_path / "documents", BASE + "/")
    store.ensure_directory()
    return store


def test_save_and_get(store: DocumentStore) -> None:
    saved = store.save(b"--- Page 1 ---\nhello", "ocr-abc.txt", {"pages": 1})
    assert saved.url == f"{BASE}/documents/{saved.id}/ocr-abc.txt"
    got = store.get(saved.id)
    assert got == saved
    assert got.path.read_bytes() == b"--- Page 1 ---\nhello"
    assert got.mime_type == "text/plain; charset=utf-8"
    meta = store.metadata(got)
    assert meta["pages"] == 1 and "created" in meta


def test_streamed_document_is_invisible_until_committed(store: DocumentStore) -> None:
    pending = store.begin("p1.png")
    pending.write(b"\x89PNG")
    assert store.get(pending.id) is None
    document = pending.commit({"kind": "upload"})
    assert store.get(pending.id) == document and document.size == 4
    aborted = store.begin("p2.png")
    aborted.write(b"x")
    aborted.abort()
    assert store.get(aborted.id) is None and not (store.directory / aborted.id).exists()


def test_wrong_filename_and_malformed_ids(store: DocumentStore) -> None:
    saved = store.save(b"x", "a.txt")
    assert store.path_for(saved.id, "a.txt") == saved.path
    assert store.path_for(saved.id, "b.txt") is None
    assert store.path_for(saved.id, "../a.txt") is None
    for bad in ("..", "../etc", saved.id.upper(), saved.id[:-1], "", "0" * 32):
        assert store.get(bad) is None


def test_purge_spares_new_and_kept_documents(tmp_path: Path) -> None:
    clock = FakeClock(start=10 * 86400.0)
    store = DocumentStore(tmp_path / "documents", BASE, clock=clock)
    store.ensure_directory()
    old, used, new = (store.save(b"x", f"{n}.txt") for n in ("old", "used", "new"))
    eight_days_ago = clock() - 8 * 86400
    for document in (old, used):
        os.utime(document.path.parent, (eight_days_ago, eight_days_ago))
    os.utime(new.path.parent, (clock(), clock()))
    (store.directory / "not-a-document").mkdir()
    assert store.purge(7, keep={used.id}) == 1
    assert store.get(old.id) is None
    assert store.get(used.id) is not None and store.get(new.id) is not None
    assert (store.directory / "not-a-document").is_dir()


def test_safe_filename() -> None:
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("C:\\scans\\p1.png") == "p1.png"
    assert safe_filename(".hidden") == "hidden"
    assert safe_filename("page 1 (copy).png") == "page 1 _copy_.png"
    assert safe_filename("...") == "document"


def test_mime_types() -> None:
    assert mime_type_for("PDF") == "application/pdf"
    assert mime_type_for("zip") == "application/zip"
    assert mime_type_for("tif") == "image/tiff"
    assert mime_type_for("exe") == "application/octet-stream"


async def test_download_route(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        store = s.service.ocr.store if s.service.ocr else None
        assert store is not None
        saved = store.save("--- Page 1 ---\nné".encode(), "ocr-x.txt")
        ok = await s.http.get(s.path(saved.url))
        assert ok.status_code == 200 and ok.text == "--- Page 1 ---\nné"
        assert ok.headers["content-type"].startswith("text/plain")
        for path in (
            f"/documents/{saved.id}/other.txt",
            f"/documents/{'0' * 32}/ocr-x.txt",
            "/documents/nothex/ocr-x.txt",
            f"/documents/{saved.id}/..%2Fmeta.json",
        ):
            assert (await s.http.get(path)).status_code == 404, path
        meta = json.loads((saved.path.parent / "meta.json").read_text())
        assert "created" in meta


def test_a_long_name_keeps_its_extension() -> None:
    """N1: the 120-character cut must not drop the suffix that makes a file a page."""
    name = safe_filename("p" + "x" * 300 + ".png")
    assert name.endswith(".png") and len(name) <= 120
    assert safe_filename("a" * 300).startswith("a") and len(safe_filename("a" * 300)) <= 120
