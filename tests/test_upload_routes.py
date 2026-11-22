"""The /upload/<token> form and route (task 02/3.2).

R15, R16, R29.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from scanscribe_mcp.uploads import UploadLinks

from .http_helpers import (
    BOUNDARY,
    CONTENT_TYPE,
    HttpServer,
    chunked,
    http_server,
    multipart,
    png,
    post_stream,
)

MB = 1024 * 1024


async def new_link(s: HttpServer, max_files: int = 5) -> tuple[str, str]:
    links = uploads(s)
    token, grant = links.create(max_files)
    return f"/upload/{token}", grant.upload_id


def uploads(s: HttpServer) -> UploadLinks:
    assert s.service.ocr is not None and s.service.ocr.uploads is not None
    return s.service.ocr.uploads


def stored_count(tmp_path: Path) -> int:
    folder = tmp_path / "data" / "documents"
    return sum(1 for p in folder.iterdir() if p.is_dir())


async def post(s: HttpServer, url: str, body: bytes, **headers: str) -> tuple[int, Any]:
    headers = {"Content-Type": CONTENT_TYPE, **headers}
    response = await s.http.post(url, content=body, headers=headers)
    return response.status_code, response.json() if response.content else {}


async def test_a_good_upload(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        url, upload_id = await new_link(s, max_files=3)
        form = await s.http.get(url)
        assert form.status_code == 200 and "Upload pages" in form.text
        status, data = await post(s, url, multipart(("p1.png", png(1)), ("p2.png", png(2))))
        assert status == 200
        assert [f["filename"] for f in data["files"]] == ["p1.png", "p2.png"]
        assert data["remaining"] == 1 and "id" not in data["files"][0]
        grant = uploads(s).get(upload_id)
        assert grant is not None and len(grant.files) == 2 and grant.in_progress == 0
        store = s.service.ocr.store if s.service.ocr else None
        assert store is not None
        first = store.get(grant.files[0])
        assert first is not None and first.path.read_bytes() == png(1)
        assert store.metadata(first)["kind"] == "upload"


async def test_expired_and_used_up_links_answer_404(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        url, _ = await new_link(s, max_files=1)
        assert (await post(s, url, multipart(("a.png", png()))))[0] == 200
        status, data = await post(s, url, multipart(("b.png", png())))
        assert status == 404 and "expired or used up" in data["error"]
        assert (await s.http.get(url)).status_code == 404

        url, _ = await new_link(s)
        uploads(s).clock = lambda: float("inf")
        assert (await post(s, url, multipart(("c.png", png()))))[0] == 404
        assert (await s.http.get(url)).status_code == 404
        assert (await post(s, "/upload/not-a-token", multipart(("d.png", png()))))[0] == 404
        assert stored_count(tmp_path) == 1


async def test_a_declared_length_past_the_limit_answers_413(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        url, _ = await new_link(s, max_files=1)
        body = multipart(("big.pdf", b"%PDF tiny"))
        status, data = await post(s, url, body, **{"Content-Length": str(250 * MB)})
        assert status == 413 and "at most" in data["error"]
        assert stored_count(tmp_path) == 0


async def test_a_stream_past_the_file_limit_stores_nothing(tmp_path: Path) -> None:
    async with http_server(tmp_path, max_file_bytes=1000) as s:
        url, upload_id = await new_link(s)
        body = multipart(("ok.png", b"x" * 10), ("big.png", b"x" * 1500))
        response = await s.http.post(
            url, content=chunked(body, 256), headers={"Content-Type": CONTENT_TYPE}
        )
        assert response.status_code == 413 and "each file" in response.json()["error"]
        grant = uploads(s).get(upload_id)
        assert grant is not None and grant.files == [] and grant.bytes == 0
        assert grant.in_progress == 0
        assert stored_count(tmp_path) == 0  # the small file before it isn't kept either


async def test_the_files_of_one_link_share_a_byte_total(tmp_path: Path) -> None:
    async with http_server(tmp_path, max_file_bytes=1000, max_upload_bytes=1500) as s:
        url, _ = await new_link(s)
        assert (await post(s, url, multipart(("a.png", b"x" * 1000))))[0] == 200
        body = multipart(("b.png", b"x" * 600))
        response = await s.http.post(
            url, content=chunked(body, 128), headers={"Content-Type": CONTENT_TYPE}
        )
        assert response.status_code == 413 and "in all" in response.json()["error"]
        assert stored_count(tmp_path) == 1


async def test_empty_files_and_other_bodies_answer_400(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        url, _ = await new_link(s)
        status, data = await post(s, url, multipart(("empty.png", b"")))
        assert status == 400 and "empty" in data["error"]
        assert (await post(s, url, multipart(("a.png", png()), field="other")))[0] == 400
        assert (await post(s, url, b"garbage"))[0] == 400
        plain = await s.http.post(url, content=b"x", headers={"Content-Type": "text/plain"})
        assert plain.status_code == 400
        too_many = multipart(*((f"p{n}.png", png()) for n in range(6)))
        status, data = await post(s, url, too_many)
        assert status == 400 and "too many files" in data["error"]
        assert stored_count(tmp_path) == 0


async def test_names_are_reduced_to_plain_names(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        url, upload_id = await new_link(s)
        files = (("../../etc/x.png", png()), ("C:\\scans\\y.png", png()), (".DS_Store", b"x"))
        status, data = await post(s, url, multipart(*files))
        assert status == 200
        assert [f["filename"] for f in data["files"]] == ["x.png", "y.png", "DS_Store"]
        store = s.service.ocr.store if s.service.ocr else None
        grant = uploads(s).get(upload_id)
        assert store is not None and grant is not None
        hidden = [store.metadata(d)["hidden"] for d in map(store.get, grant.files) if d]
        assert hidden == [False, False, True]
        assert not (tmp_path / "etc").exists()


async def test_an_upload_begun_in_time_may_finish_after_expiry(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        url, upload_id = await new_link(s, max_files=1)
        links = uploads(s)
        grant = links.get(upload_id)
        assert grant is not None
        seen: list[tuple[int, int]] = []

        def expire_midway(index: int) -> None:
            if index == 5:  # well past the part's headers
                seen.append((grant.in_progress, grant.remaining))
                links.clock = lambda: float("inf")

        body = multipart(("late.png", png() * 20))
        response = await post_stream(s, url, chunked(body, 64, expire_midway))
        assert response.status_code == 200
        assert seen == [(1, 0)]  # the running upload held the link's only file
        assert len(grant.files) == 1 and links.expired(grant)
        assert (await post(s, url, multipart(("again.png", png()))))[0] == 404


# --- implementation review, phase 02 round 1 ------------------------------------------------


async def test_a_body_cut_before_its_closing_boundary_stores_nothing(tmp_path: Path) -> None:
    """M1: python-multipart's finalize() doesn't check the end, so the receiver must."""
    async with http_server(tmp_path) as s:
        url, upload_id = await new_link(s)
        whole = multipart(("p1.png", png()))
        no_closing = whole[: whole.rindex(f"--{BOUNDARY}--".encode())]
        half_file = whole[: len(whole) // 2]
        headers_only = whole[: whole.index(b"\r\n\r\n") + 4]
        for body in (no_closing, half_file, headers_only):
            status, data = await post(s, url, body)
            assert status == 400 and "incomplete" in data["error"], (status, data)
        grant = uploads(s).get(upload_id)
        assert grant is not None and grant.files == [] and grant.in_progress == 0
        assert grant.bytes == 0 and stored_count(tmp_path) == 0


async def test_header_and_part_counts_are_limited(tmp_path: Path) -> None:
    """M3: a huge part header, or endless empty field parts, is refused without growing."""
    async with http_server(tmp_path) as s:
        url, _ = await new_link(s)
        huge = (
            (
                f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="p1.png"\r\nX-Pad: {"x" * 80_000}\r\n\r\n'
            ).encode()
            + png()
            + f"\r\n--{BOUNDARY}--\r\n".encode()
        )
        response = await post_stream(s, url, chunked(huge, 1024))
        assert response.status_code == 400
        field = f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="x"\r\n\r\n\r\n'.encode()
        many = field * 5000 + multipart(("p1.png", png()))
        response = await post_stream(s, url, chunked(many, 4096))
        assert response.status_code == 400 and "send only files" in response.json()["error"]
        assert stored_count(tmp_path) == 0


async def test_a_250_mb_file_answers_413_at_the_default_limits(tmp_path: Path) -> None:
    """N8, R16: on a default link (100 files, 200 MiB each, 2 GiB in all) the declared length
    passes, so the streaming check must stop a 250 MB file, and nothing is stored."""
    async with http_server(tmp_path) as s:
        url, upload_id = await new_link(s, max_files=100)
        head = multipart(("big.pdf", b""))
        head = head[: head.index(b"\r\n\r\n") + 4]

        async def body() -> AsyncIterator[bytes]:
            yield head
            for _ in range(250):
                yield b"\0" * MB
            yield f"\r\n--{BOUNDARY}--\r\n".encode()

        response = await post_stream(s, url, body())
        assert response.status_code == 413 and "each file" in response.json()["error"]
        grant = uploads(s).get(upload_id)
        assert grant is not None and grant.bytes == 0 and stored_count(tmp_path) == 0


async def test_a_store_error_gives_back_the_upload_and_hides_its_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """N3: an OSError while starting a file must not leave the link counting it as arriving."""
    async with http_server(tmp_path) as s:
        url, upload_id = await new_link(s)
        assert s.service.ocr is not None and s.service.ocr.store is not None

        def broken(filename: str) -> None:
            raise OSError(f"disk full writing {tmp_path}/secret-name.png")

        monkeypatch.setattr(s.service.ocr.store, "begin", broken)
        status, data = await post(s, url, multipart(("secret-name.png", png())))
        assert status == 500 and "secret-name" not in str(data)
        grant = uploads(s).get(upload_id)
        assert grant is not None and grant.in_progress == 0 and grant.requests == 0
        assert "secret-name" not in caplog.text
