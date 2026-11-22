"""The bearer token on /mcp and the HTTP configuration checks (task 02/1.1).

D8, R2, R19.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest
from fastmcp.exceptions import ToolError
from pydantic import SecretStr

from scanscribe_mcp.server import ScanscribeMCPServer
from scanscribe_mcp.service import ScanscribeMCPService

from .fakes import FakeEngineFactory, make_pages
from .http_helpers import AUTH, INITIALIZE, MCP_HEADERS, http_config, http_server


async def test_mcp_needs_the_token(tmp_path: Path) -> None:
    async with http_server(tmp_path) as s:
        missing = await s.http.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS)
        assert missing.status_code == 401
        wrong = await s.http.post(
            "/mcp", json=INITIALIZE, headers={**MCP_HEADERS, "Authorization": "Bearer nope"}
        )
        assert wrong.status_code == 401
        right = await s.http.post("/mcp", json=INITIALIZE, headers={**MCP_HEADERS, **AUTH})
        assert right.status_code == 200
        assert "scanscribe" in right.text


@pytest.mark.parametrize("token", [None, ""])
def test_http_without_a_token_exits_with_a_configuration_error(
    tmp_path: Path,
    token: str | None,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = http_config(tmp_path, auth=True, token=None if token is None else SecretStr(token))
    service = ScanscribeMCPService(config, FakeEngineFactory())
    server = ScanscribeMCPServer(config.server, service)
    monkeypatch.setattr(sys, "argv", ["scanscribe-mcp"])
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as exited:
        server.run()
    assert exited.value.code == 1
    assert "Configuration error" in caplog.text and "SCANSCRIBE_MCP_TOKEN" in caplog.text
    assert service.ocr is None  # nothing started


def test_no_auth_serves_without_a_token(tmp_path: Path) -> None:
    config = http_config(tmp_path, auth=False)
    server = ScanscribeMCPServer(config.server, ScanscribeMCPService(config, FakeEngineFactory()))
    server.validate_configuration()
    assert server.create_auth_provider() is None


async def test_local_paths_refused_over_http_even_when_allowed(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    async with http_server(tmp_path, allow_local_paths=True) as s:
        assert s.service.config.local_paths_allowed is False
        with pytest.raises(ToolError, match="not accepted over HTTP.*create_upload_link"):
            await s.mcp.call_tool("start_ocr_job", {"input_path": str(folder)})
        with pytest.raises(
            ToolError, match="output_path is not accepted over HTTP.*download URL.*upload links"
        ):
            await s.mcp.call_tool(
                "get_ocr_result", {"job_id": "0" * 32, "output_path": str(tmp_path / "x.txt")}
            )
