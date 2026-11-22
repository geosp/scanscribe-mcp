"""Zip inputs: the checks before anything is written, and streaming extraction (task 02/4.2).

R17. Every zip is built in memory by the test; none holds book material.
"""

from __future__ import annotations

import io
import stat
import struct
import zipfile
from pathlib import Path

import pytest

from scanscribe_mcp.uploads import InputRefused, extract_zip, zip_pages

from .fakes import FakeEngineFactory
from .http_helpers import http_server, png, run_job, upload


def build_zip(*entries: zipfile.ZipInfo | tuple[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            if isinstance(entry, zipfile.ZipInfo):
                archive.writestr(entry, b"target.png")
            else:
                archive.writestr(*entry)
    return buffer.getvalue()


def symlink_entry(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return info


def understate(data: bytes, size: int) -> bytes:
    """Rewrite every header's uncompressed size, as a hostile zip would."""
    patched = bytearray(data)
    for signature, offset in ((b"PK\x03\x04", 22), (b"PK\x01\x02", 24)):
        start = 0
        while (index := patched.find(signature, start)) >= 0:
            struct.pack_into("<I", patched, index + offset, size)
            start = index + 4
    return bytes(patched)


NESTED = build_zip(("p1.png", png()), ("inner.zip", build_zip(("p2.png", png()))))
DUPLICATES = build_zip(("a/1.png", png(1)), ("b/1.png", png(2)))

HOSTILE = {
    "parent path": (build_zip(("../x.png", png())), "points outside"),
    "absolute path": (build_zip(("/x.png", png())), "points outside"),
    "backslash path": (build_zip(("scan\\..\\..\\x.png", png())), "points outside"),
    "drive letter": (build_zip(("C:/x.png", png())), "points outside"),
    "symlink": (build_zip(symlink_entry("x.png")), "symbolic link"),
    "nested zip": (
        build_zip(("p1.png", png()), ("inner.zip", build_zip(("p2.png", png())))),
        "not a page image",
    ),
    "duplicate names": (
        build_zip(("a/1.png", png(1)), ("b/1.png", png(2))),
        "two entries are named '1.png'",
    ),
    "understated size": (understate(build_zip(("x.png", b"\0" * 50_000)), 10), "damaged"),
    "not a zip": (b"PK but not really a zip", "not a readable zip"),
}


@pytest.mark.parametrize("case", sorted(HOSTILE))
async def test_hostile_zips_fail_before_ocr(tmp_path: Path, case: str) -> None:
    data, message = HOSTILE[case]
    factory = FakeEngineFactory()
    async with http_server(tmp_path, factory) as s:
        upload_id = await upload(s, ("pages.zip", data))
        try:
            done = await run_job(s, upload_id=upload_id)
        except Exception as exc:  # refused at start: the count reads the same directory
            assert message in str(exc)
        else:
            assert done["state"] == "failed", done
            assert message in done["error"] and "pages.zip" in done["error"]
            assert str(tmp_path) not in done["error"]
    assert factory.calls == []
    assert not any(tmp_path.rglob("x.png")) and not Path("/x.png").exists()
    assert not any(p for p in (tmp_path / "data" / "work").iterdir() if len(p.name) == 32)


def test_a_zipped_folder_becomes_flat_pages(tmp_path: Path) -> None:
    data = build_zip(
        ("chapter/", b""),
        ("chapter/p1.png", png(1)),
        ("chapter/P2.PNG", png(2)),
        ("__MACOSX/chapter/._p1.png", b"resource fork"),
        ("chapter/.DS_Store", b"junk"),
    )
    path = tmp_path / "pages.zip"
    path.write_bytes(data)
    folder = tmp_path / "job" / "pages"
    assert extract_zip(path, "pages.zip", folder, max_pages=10, max_bytes=10**6) == 2
    assert sorted(p.name for p in folder.iterdir()) == ["P2.PNG", "p1.png"]
    assert (folder / "p1.png").read_bytes() == png(1)


def test_limits_on_pages_and_bytes(tmp_path: Path) -> None:
    path = tmp_path / "pages.zip"
    path.write_bytes(build_zip(*((f"p{n}.png", png(n)) for n in range(1, 4))))
    with pytest.raises(InputRefused, match="more than 2 pages"):
        zip_pages(path, "pages.zip", max_pages=2, max_bytes=10**6)
    with pytest.raises(InputRefused, match="unpacks to more than 100 bytes"):
        zip_pages(path, "pages.zip", max_pages=10, max_bytes=100)
    assert len(zip_pages(path, "pages.zip", max_pages=3, max_bytes=10**6)) == 3


def test_bytes_are_counted_while_streaming(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reader that gives more than the header declares is stopped by the running count."""
    path = tmp_path / "pages.zip"
    path.write_bytes(build_zip(("p1.png", b"\0" * 10)))
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda self, info: io.BytesIO(b"\0" * 5000))
    folder = tmp_path / "job" / "pages"
    with pytest.raises(InputRefused, match="unpacks to more than 1000 bytes"):
        extract_zip(path, "pages.zip", folder, max_pages=10, max_bytes=1000)
    assert (folder / "p1.png").stat().st_size <= 1000


def test_zip_entries_get_plain_names(tmp_path: Path) -> None:
    """N2, D8: entry names go through safe_filename like any uploaded name."""
    path = tmp_path / "pages.zip"
    path.write_bytes(
        build_zip(("scan/p\x01one?.png", png(1)), ("scan/" + "y" * 300 + ".png", png(2)))
    )
    folder = tmp_path / "job" / "pages"
    assert extract_zip(path, "pages.zip", folder, max_pages=10, max_bytes=10**6) == 2
    names = sorted(p.name for p in folder.iterdir())
    assert all(name.endswith(".png") and len(name) <= 120 for name in names)
    assert "p_one_.png" in names


def test_names_equal_after_cleaning_are_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "pages.zip"
    path.write_bytes(build_zip(("a/p?1.png", png(1)), ("b/p*1.png", png(2))))
    with pytest.raises(InputRefused, match="two entries are named 'p_1.png'"):
        zip_pages(path, "pages.zip", max_pages=10, max_bytes=10**6)


async def test_a_non_image_entry_is_named_at_start(tmp_path: Path) -> None:
    """N4: a zip of the page limit plus readme.txt is refused for the readme, not as too long."""
    data = build_zip(*((f"p{n}.png", png()) for n in range(1, 4)), ("readme.txt", b"x"))
    async with http_server(tmp_path, max_pages=3) as s:
        upload_id = await upload(s, ("pages.zip", data))
        with pytest.raises(Exception, match="readme.txt.*not a page image"):
            await s.mcp.call_tool("start_ocr_job", {"upload_id": upload_id})
