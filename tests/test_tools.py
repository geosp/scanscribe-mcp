"""The MCP tools through a real fastmcp.Client against the in-process server (tasks 3.1-3.5).

R1-R4, R6, R8-R10, R13, R14.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
import scanscribe
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp_service_kit import BaseServerConfig

from scanscribe_mcp.config import AppConfig, ScanscribeMcpConfig
from scanscribe_mcp.server import ScanscribeMCPServer
from scanscribe_mcp.service import ScanscribeMCPService

from .fakes import FakeEngineFactory, make_images, make_pages

PHASE_01_TOOLS = {"start_ocr_job", "get_ocr_job", "cancel_ocr_job", "get_ocr_result"}

MakeClient = Callable[..., Any]


@pytest.fixture
async def make_client() -> AsyncIterator[MakeClient]:
    """Builds a server with a fake engine and returns a connected client for it."""
    services: list[ScanscribeMCPService] = []
    clients: list[Client[Any]] = []

    async def make(
        factory: FakeEngineFactory | None = None, transport: str = "stdio", **ocr: Any
    ) -> Client[Any]:
        config = AppConfig(
            # Phase 01 has no token yet, so an HTTP test server runs with auth off.
            server=BaseServerConfig(  # type: ignore[arg-type]
                transport=transport, auth_enabled=transport != "http"
            ),
            ocr=ScanscribeMcpConfig(**ocr),
        )
        service = ScanscribeMCPService(config, factory or FakeEngineFactory())
        server = ScanscribeMCPServer(config.server, service)
        service.initialize()
        services.append(service)
        client: Client[Any] = Client(server.create_mcp_app())
        await client.__aenter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.__aexit__(None, None, None)
    for service in services:
        service.cleanup()


async def start(client: Client[Any], **arguments: Any) -> str:
    result = await client.call_tool("start_ocr_job", arguments)
    job_id: str = result.structured_content["job_id"]
    return job_id


async def finish(client: Client[Any], job_id: str) -> dict[str, Any]:
    result = await client.call_tool("get_ocr_job", {"job_id": job_id, "wait_s": 30})
    fields: dict[str, Any] = result.structured_content
    return fields


# --- 3.1 server, service, discovery ----------------------------------------------------------


async def test_lists_exactly_the_phase_01_tools(make_client: MakeClient) -> None:
    client = await make_client()
    assert {tool.name for tool in await client.list_tools()} == PHASE_01_TOOLS
    instructions = client.instructions
    assert instructions is not None
    assert "start_ocr_job" in instructions and "get_ocr_result" in instructions


# --- 3.2 start_ocr_job -------------------------------------------------------------------------


async def test_start_needs_exactly_one_input(make_client: MakeClient, tmp_path: Path) -> None:
    client = await make_client()
    with pytest.raises(ToolError, match="exactly one input"):
        await client.call_tool("start_ocr_job", {})
    with pytest.raises(ToolError, match="got upload_id, input_path"):
        await client.call_tool("start_ocr_job", {"input_path": str(tmp_path), "upload_id": "abc"})


async def test_upload_inputs_need_http(make_client: MakeClient) -> None:
    client = await make_client()
    for argument in ("upload_id", "document"):
        with pytest.raises(ToolError, match="needs the HTTP server"):
            await client.call_tool("start_ocr_job", {argument: "abc"})


async def test_bad_options_are_refused(make_client: MakeClient, tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    client = await make_client()
    with pytest.raises(ToolError, match=r"lang 'xx' is not available.*allows: en"):
        await start(client, input_path=str(folder), lang="xx")
    with pytest.raises(ToolError, match="dpi must be 72 to 400, got 600"):
        await start(client, input_path=str(folder), dpi=600)
    with pytest.raises(ToolError, match="columns must be 1 to 8, got 9"):
        await start(client, input_path=str(folder), columns=9)
    with pytest.raises(ToolError, match="columns must be 1 to 8, got 0"):
        await start(client, input_path=str(folder), columns=0)


async def test_defaults_are_200_dpi_and_one_column(make_client: MakeClient, tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 2)
    client = await make_client()
    result = await client.call_tool("start_ocr_job", {"input_path": str(folder)})
    fields = result.structured_content
    assert (fields["lang"], fields["dpi"], fields["columns"]) == ("en", 200, 1)
    assert fields["state"] in {"queued", "running"} and fields["page_images"] == 2
    assert fields["input"] == "folder"
    assert fields["job_id"] in result.content[0].text


async def test_folder_over_the_page_limit_is_refused(
    make_client: MakeClient, tmp_path: Path
) -> None:
    folder = tmp_path / "big"
    folder.mkdir()
    image = make_images(tmp_path / "one", ["p.png"]) / "p.png"
    for n in range(501):
        (folder / f"p{n}.png").hardlink_to(image)
    (folder / ".hidden.png").hardlink_to(image)
    (folder / "notes.txt").write_text("not a page")
    factory = FakeEngineFactory()
    client = await make_client(factory)
    with pytest.raises(ToolError, match="has 501 pages.*SCANSCRIBE_MCP_MAX_PAGES"):
        await start(client, input_path=str(folder))
    (folder / "p0.png").unlink()
    job_id = await start(client, input_path=str(folder))  # 500 pages is within the limit
    await client.call_tool("cancel_ocr_job", {"job_id": job_id})


async def test_missing_input_path(make_client: MakeClient, tmp_path: Path) -> None:
    client = await make_client()
    with pytest.raises(ToolError, match="input_path not found: .*nope"):
        await start(client, input_path=str(tmp_path / "nope"))


async def test_full_queue_is_refused(make_client: MakeClient, tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    release = threading.Event()
    factory = FakeEngineFactory(on_load=lambda: release.wait(10) and None)
    client = await make_client(factory, max_queued=2)
    try:
        first = await start(client, input_path=str(folder))
        await wait_state(client, first, "running")  # held in the engine load
        await wait_state(client, await start(client, input_path=str(folder)), "queued")
        await start(client, input_path=str(folder))
        with pytest.raises(ToolError, match="queue is full"):
            await start(client, input_path=str(folder))
    finally:
        release.set()


async def test_local_paths_turned_off_over_stdio(make_client: MakeClient, tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    client = await make_client(allow_local_paths=False)
    with pytest.raises(ToolError, match="SCANSCRIBE_MCP_ALLOW_LOCAL_PATHS=false"):
        await start(client, input_path=str(folder))


async def test_local_paths_never_over_http(make_client: MakeClient, tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    client = await make_client(transport="http", allow_local_paths=True)
    with pytest.raises(ToolError, match="not accepted over HTTP.*create_upload_link"):
        await start(client, input_path=str(folder))


# --- 3.3 get_ocr_job ---------------------------------------------------------------------------


async def wait_state(client: Client[Any], job_id: str, state: str, **match: Any) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while True:
        result = await client.call_tool("get_ocr_job", {"job_id": job_id})
        fields: dict[str, Any] = result.structured_content
        if fields["state"] == state and all(fields.get(k) == v for k, v in match.items()):
            return fields
        assert time.monotonic() < deadline, fields
        await asyncio.sleep(0.01)


async def test_wait_returns_when_the_job_ends(make_client: MakeClient, tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 2)
    factory = FakeEngineFactory(hooks={1: lambda: time.sleep(1)})
    client = await make_client(factory)
    job_id = await start(client, input_path=str(folder))
    began = time.monotonic()
    result = await client.call_tool("get_ocr_job", {"job_id": job_id, "wait_s": 30})
    elapsed = time.monotonic() - began
    fields = result.structured_content
    assert elapsed < 3
    assert fields["state"] == "succeeded" and fields["total"] == 2
    assert fields["device"] == "fake:0"
    assert "get_ocr_result" in result.content[0].text


async def test_wait_is_bounded(make_client: MakeClient, tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    release = threading.Event()
    client = await make_client(FakeEngineFactory(on_load=lambda: release.wait(10) and None))
    try:
        job_id = await start(client, input_path=str(folder))
        began = time.monotonic()
        result = await client.call_tool("get_ocr_job", {"job_id": job_id, "wait_s": 0.6})
        assert 0.5 < time.monotonic() - began < 2
        assert result.structured_content["state"] == "running"
        with pytest.raises(ToolError):
            await client.call_tool("get_ocr_job", {"job_id": job_id, "wait_s": 61})
    finally:
        release.set()


async def test_running_job_reports_step_page_and_seconds(
    make_client: MakeClient, tmp_path: Path
) -> None:
    folder = make_pages(tmp_path / "pages", 12)
    release = threading.Event()
    client = await make_client(FakeEngineFactory(hooks={3: lambda: release.wait(10) and None}))
    try:
        job_id = await start(client, input_path=str(folder))
        await wait_state(client, job_id, "running", page=3)
        await asyncio.sleep(0.2)
        result = await client.call_tool("get_ocr_job", {"job_id": job_id})
        fields = result.structured_content
        assert fields["step"] == "recognizing"
        assert (fields["page"], fields["total"], fields["device"]) == (3, 12, "fake:0")
        assert fields["page_seconds"] >= 0.1
        assert "page 3 of 12" in result.content[0].text
    finally:
        release.set()


async def test_unknown_job_is_a_tool_error(make_client: MakeClient) -> None:
    client = await make_client()
    for tool in ("get_ocr_job", "cancel_ocr_job", "get_ocr_result"):
        with pytest.raises(ToolError, match="no job with id 'nope'"):
            await client.call_tool(tool, {"job_id": "nope"})


async def test_failed_job_reports_its_error(make_client: MakeClient, tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    (folder / "p1.png").write_bytes(b"broken")
    client = await make_client()
    fields = await finish(client, await start(client, input_path=str(folder)))
    assert fields["state"] == "failed" and "p1.png" in fields["error"]


# --- 3.4 cancel_ocr_job ------------------------------------------------------------------------


async def test_cancel_queued_running_and_finished(make_client: MakeClient, tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 4)
    release = threading.Event()
    factory = FakeEngineFactory(hooks={2: lambda: release.wait(10) and None})
    client = await make_client(factory)
    running = await start(client, input_path=str(folder))
    await wait_state(client, running, "running", page=2)
    queued = await start(client, input_path=str(folder))

    result = await client.call_tool("cancel_ocr_job", {"job_id": queued})
    assert result.structured_content["state"] == "cancelled"
    assert "before it started" in result.content[0].text

    result = await client.call_tool("cancel_ocr_job", {"job_id": running})
    assert result.structured_content["state"] == "running"
    assert "next check" in result.content[0].text
    release.set()
    assert (await finish(client, running))["state"] == "cancelled"
    assert factory.last is not None and len(factory.last.seen) == 2

    done = await start(client, input_path=str(folder))
    assert (await finish(client, done))["state"] == "succeeded"
    result = await client.call_tool("cancel_ocr_job", {"job_id": done})
    assert result.structured_content["state"] == "succeeded"
    assert result.structured_content["cancel_requested"] is False
    assert "already finished as succeeded" in result.content[0].text


# --- 3.5 get_ocr_result ------------------------------------------------------------------------


async def succeeded_job(client: Client[Any], folder: Path) -> str:
    job_id = await start(client, input_path=str(folder))
    assert (await finish(client, job_id))["state"] == "succeeded"
    return job_id


def expected_text(pages: int, lines_per_page: int = 1) -> str:
    """What the fake engine's output looks like after scanscribe.format_pages."""
    return scanscribe.format_pages(
        [
            [
                f"page {n}",
                f"gray {n}",
                *[f"line {i} of page {n} in en" for i in range(2, lines_per_page + 1)],
            ]
            for n in range(1, pages + 1)
        ]
    )


async def test_small_result_inline(make_client: MakeClient, tmp_path: Path) -> None:
    client = await make_client()
    job_id = await succeeded_job(client, make_pages(tmp_path / "pages", 3))
    result = await client.call_tool("get_ocr_result", {"job_id": job_id})
    assert result.content[1].text == expected_text(3)
    assert result.structured_content["inline"] is True
    assert result.structured_content["pages"] == 3


async def test_large_result_not_inline(make_client: MakeClient, tmp_path: Path) -> None:
    client = await make_client(FakeEngineFactory(lines_per_page=20), max_inline_chars=2000)
    job_id = await succeeded_job(client, make_pages(tmp_path / "pages", 30))
    result = await client.call_tool("get_ocr_result", {"job_id": job_id})
    assert len(result.content) == 1
    summary = result.content[0].text
    assert "30 pages" in summary and "first_page" in summary and "output_path" in summary
    assert result.structured_content["inline"] is False


async def test_page_slice_with_markers(make_client: MakeClient, tmp_path: Path) -> None:
    client = await make_client(max_inline_chars=2000)
    job_id = await succeeded_job(client, make_pages(tmp_path / "pages", 30))
    result = await client.call_tool(
        "get_ocr_result", {"job_id": job_id, "first_page": 10, "last_page": 12}
    )
    assert result.content[1].text == (
        "--- Page 10 ---\npage 10\ngray 10\n\n"
        "--- Page 11 ---\npage 11\ngray 11\n\n"
        "--- Page 12 ---\npage 12\ngray 12"
    )
    assert result.structured_content["next_first_page"] is None


async def test_long_slice_is_cut_at_a_page(make_client: MakeClient, tmp_path: Path) -> None:
    client = await make_client(FakeEngineFactory(lines_per_page=20), max_inline_chars=2000)
    job_id = await succeeded_job(client, make_pages(tmp_path / "pages", 30))
    result = await client.call_tool(
        "get_ocr_result", {"job_id": job_id, "first_page": 5, "last_page": 30}
    )
    text = result.content[1].text
    fields = result.structured_content
    assert len(text) <= 2000
    assert text.startswith("--- Page 5 ---\n")
    next_page = fields["next_first_page"]
    assert fields["last_page"] == next_page - 1 and 5 < next_page <= 30
    assert text.endswith(f"line 20 of page {next_page - 1} in en")
    assert f"first_page={next_page}" in result.content[0].text
    whole = expected_text(30, lines_per_page=20)
    assert text in whole


async def test_out_of_range_slice(make_client: MakeClient, tmp_path: Path) -> None:
    client = await make_client()
    job_id = await succeeded_job(client, make_pages(tmp_path / "pages", 3))
    for first, last in ((0, 2), (2, 4), (3, 2)):
        with pytest.raises(ToolError, match="out of range; the result has 3 pages"):
            await client.call_tool(
                "get_ocr_result", {"job_id": job_id, "first_page": first, "last_page": last}
            )


async def test_output_path_writes_the_exact_text(make_client: MakeClient, tmp_path: Path) -> None:
    client = await make_client()
    job_id = await succeeded_job(client, make_pages(tmp_path / "pages", 4))
    target = tmp_path / "out.txt"
    target.write_text("old contents")
    result = await client.call_tool(
        "get_ocr_result", {"job_id": job_id, "output_path": str(target)}
    )
    assert target.read_text(encoding="utf-8") == expected_text(4)
    assert result.structured_content["pages"] == 4
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []


async def test_output_path_refused_when_relative_or_without_folder(
    make_client: MakeClient, tmp_path: Path
) -> None:
    client = await make_client()
    job_id = await succeeded_job(client, make_pages(tmp_path / "pages", 1))
    with pytest.raises(ToolError, match="must be an absolute path"):
        await client.call_tool("get_ocr_result", {"job_id": job_id, "output_path": "out.txt"})
    missing = tmp_path / "missing" / "out.txt"
    with pytest.raises(ToolError, match="folder of output_path doesn't exist"):
        await client.call_tool("get_ocr_result", {"job_id": job_id, "output_path": str(missing)})
    assert not missing.parent.exists() and not Path("out.txt").exists()


async def test_output_path_refused_with_local_paths_off(
    make_client: MakeClient, tmp_path: Path
) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    on = await make_client()
    job_id = await succeeded_job(on, folder)
    off = await make_client(allow_local_paths=False)
    with pytest.raises(ToolError, match="ALLOW_LOCAL_PATHS=false"):
        await off.call_tool(
            "get_ocr_result", {"job_id": job_id, "output_path": str(tmp_path / "x.txt")}
        )
    assert not (tmp_path / "x.txt").exists()


async def test_result_of_an_unfinished_job(make_client: MakeClient, tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    release = threading.Event()
    client = await make_client(FakeEngineFactory(on_load=lambda: release.wait(10) and None))
    try:
        job_id = await start(client, input_path=str(folder))
        await wait_state(client, job_id, "running")
        with pytest.raises(ToolError, match="has no result: it is running"):
            await client.call_tool("get_ocr_result", {"job_id": job_id})
    finally:
        release.set()


async def test_output_path_with_a_page_range_is_refused(
    make_client: MakeClient, tmp_path: Path
) -> None:
    client = await make_client()
    job_id = await succeeded_job(client, make_pages(tmp_path / "pages", 2))
    target = tmp_path / "out.txt"
    for pages in ({"first_page": 1}, {"last_page": 2}):
        with pytest.raises(ToolError, match="output_path writes the whole text"):
            await client.call_tool(
                "get_ocr_result", {"job_id": job_id, "output_path": str(target), **pages}
            )
    assert not target.exists()


async def test_page_longer_than_the_limit_returns_no_text(
    make_client: MakeClient, tmp_path: Path
) -> None:
    client = await make_client(FakeEngineFactory(lines_per_page=20), max_inline_chars=100)
    job_id = await succeeded_job(client, make_pages(tmp_path / "pages", 3))
    result = await client.call_tool(
        "get_ocr_result", {"job_id": job_id, "first_page": 2, "last_page": 3}
    )
    assert len(result.content) == 1
    assert "Page 2 alone is longer than the 100-character inline limit" in result.content[0].text
    assert "output_path" in result.content[0].text
    fields = result.structured_content
    assert fields["inline"] is False and fields["next_first_page"] == 2


async def test_unexpected_tool_error_hides_the_path_from_logs_and_client(
    make_client: MakeClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    loop = tmp_path / "chapter-3.pdf"
    loop.symlink_to(loop)  # resolve() raises RuntimeError("Symlink loop from ...")
    client = await make_client()
    with pytest.raises(ToolError) as raised:
        await start(client, input_path=str(loop))
    assert "chapter-3" not in str(raised.value) and str(tmp_path) not in str(raised.value)
    assert "start_ocr_job failed (RuntimeError)" in str(raised.value)
    for record in caplog.records:
        text = f"{record.getMessage()} {record.exc_text or ''}"
        if record.exc_info and not record.exc_text:
            text += logging.Formatter().formatException(record.exc_info)
        assert "chapter-3" not in text, record.name
