"""The create_upload_link and check_upload tools (task 02/3.3).

D7, R15.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from scanscribe_mcp.config import AppConfig
from scanscribe_mcp.server import ScanscribeMCPServer
from scanscribe_mcp.service import ScanscribeMCPService

from .fakes import FakeEngineFactory
from .http_helpers import BASE_URL, CONTENT_TYPE, HttpServer, http_server, multipart, png


async def link(s: HttpServer, **arguments: Any) -> dict[str, Any]:
    result = await s.mcp.call_tool("create_upload_link", arguments)
    fields: dict[str, Any] = result.structured_content
    return fields


async def test_create_upload_link(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        fields = await link(s)
        url, upload_id = fields["upload_url"], fields["upload_id"]
        assert url.startswith(f"{BASE_URL}/upload/") and upload_id not in url
        assert fields["max_files"] == 100 and fields["expires_in_s"] == 600
        assert f"curl -F file=@pages.zip {url}" in fields["message"]
        assert f"start_ocr_job(upload_id={upload_id!r})" in fields["message"]
        assert (await s.http.get(s.path(url))).status_code == 200

        assert (await link(s, max_files=200))["max_files"] == 200
        with pytest.raises(ToolError):
            await link(s, max_files=201)


async def test_open_link_limit_is_a_tool_error(tmp_path: Path) -> None:
    async with http_server(tmp_path, upload_link_max_active=1) as s:
        await link(s)
        with pytest.raises(ToolError, match="too many open upload links"):
            await link(s)


async def test_check_upload_before_and_after(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        fields = await link(s, max_files=3)
        url, upload_id = s.path(fields["upload_url"]), fields["upload_id"]
        before = await s.mcp.call_tool("check_upload", {"upload_id": upload_id})
        assert before.structured_content["files"] == []
        assert before.structured_content["remaining"] == 3
        assert "No files uploaded yet" in before.structured_content["message"]

        body = multipart(("p2.png", png(2)), ("p1.png", png(1)))
        response = await s.http.post(url, content=body, headers={"Content-Type": CONTENT_TYPE})
        assert response.status_code == 200
        after = (await s.mcp.call_tool("check_upload", {"upload_id": upload_id})).structured_content
        assert [f["filename"] for f in after["files"]] == ["p2.png", "p1.png"]
        assert all(len(f["id"]) == 32 for f in after["files"])
        assert after["remaining"] == 1 and after["in_progress"] == 0
        assert "start_ocr_job(upload_id=" in after["message"]

        with pytest.raises(ToolError, match="unknown or expired upload_id"):
            await s.mcp.call_tool("check_upload", {"upload_id": "0" * 32})


async def test_check_upload_waits_for_a_file(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        fields = await link(s)
        url, upload_id = s.path(fields["upload_url"]), fields["upload_id"]

        async def upload_later() -> None:
            await asyncio.sleep(0.3)
            body = multipart(("p1.png", png()))
            await s.http.post(url, content=body, headers={"Content-Type": CONTENT_TYPE})

        task = asyncio.create_task(upload_later())
        started = time.monotonic()
        result = await s.mcp.call_tool("check_upload", {"upload_id": upload_id, "wait_s": 10})
        await task
        assert len(result.structured_content["files"]) == 1
        assert time.monotonic() - started < 5


async def test_upload_tools_need_http() -> None:
    config = AppConfig()
    service = ScanscribeMCPService(config, FakeEngineFactory())
    server = ScanscribeMCPServer(config.server, service)
    service.initialize()
    try:
        async with Client(server.create_mcp_app()) as client:
            with pytest.raises(ToolError, match="needs the HTTP server.*input_path"):
                await client.call_tool("create_upload_link", {})
            with pytest.raises(ToolError, match="needs the HTTP server.*input_path"):
                await client.call_tool("check_upload", {"upload_id": "abc"})
    finally:
        service.cleanup()
