"""An HTTP-mode server on its ASGI app: an MCP client and a plain HTTP client (phase 02)."""

from __future__ import annotations

import contextlib
import io
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from fastmcp import Client
from mcp_service_kit import BaseServerConfig
from PIL import Image
from pydantic import SecretStr

from scanscribe_mcp.config import AppConfig, ScanscribeMcpConfig
from scanscribe_mcp.server import ScanscribeMCPServer
from scanscribe_mcp.service import ScanscribeMCPService

from .fakes import FakeEngineFactory

BASE_URL = "http://scanscribe.test:8302"
TOKEN = "test-token-not-a-secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def http_config(tmp_path: Path, *, auth: bool = True, **ocr: Any) -> AppConfig:
    ocr.setdefault("output_dir", tmp_path / "data" / "documents")
    ocr.setdefault("work_dir", tmp_path / "data" / "work")
    ocr.setdefault("public_base_url", BASE_URL)
    if auth:
        ocr.setdefault("token", SecretStr(TOKEN))
    return AppConfig(
        server=BaseServerConfig(transport="http", auth_enabled=auth),  # type: ignore[arg-type]
        ocr=ScanscribeMcpConfig(**ocr),
    )


@dataclass
class HttpServer:
    server: ScanscribeMCPServer
    service: ScanscribeMCPService
    mcp: Client[Any]
    http: httpx.AsyncClient

    def path(self, url: str) -> str:
        """A URL the server handed out, as a path for the ASGI client."""
        assert url.startswith(BASE_URL), url
        return url.removeprefix(BASE_URL)


@contextlib.asynccontextmanager
async def http_server(
    tmp_path: Path,
    factory: FakeEngineFactory | None = None,
    *,
    auth: bool = True,
    **ocr: Any,
) -> AsyncIterator[HttpServer]:
    config = http_config(tmp_path, auth=auth, **ocr)
    service = ScanscribeMCPService(config, factory or FakeEngineFactory())
    server = ScanscribeMCPServer(config.server, service)
    app = server.create_asgi_app()
    assert server._mcp_app is not None
    try:
        async with (
            app.router.lifespan_context(app),  # type: ignore[attr-defined]
            httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as http,
            Client(server._mcp_app) as mcp,
        ):
            yield HttpServer(server, service, mcp, http)
    finally:
        service.cleanup()


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


# --- multipart bodies, built by hand so a test can send them in chunks ---------------------

BOUNDARY = "test-boundary-7f3a"
CONTENT_TYPE = f"multipart/form-data; boundary={BOUNDARY}"


def png(gray: int = 1) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (gray,) * 3).save(buffer, "PNG")
    return buffer.getvalue()


def multipart(*files: tuple[str, bytes], field: str = "file") -> bytes:
    body = b""
    for name, data in files:
        body += (
            (
                f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="{field}"; '
                f'filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'
            ).encode()
            + data
            + b"\r\n"
        )
    return body + f"--{BOUNDARY}--\r\n".encode()


# --- uploads and jobs through the tools ----------------------------------------------------


async def new_link(s: HttpServer, max_files: int = 20) -> tuple[str, str]:
    result = await s.mcp.call_tool("create_upload_link", {"max_files": max_files})
    fields = result.structured_content
    return s.path(fields["upload_url"]), fields["upload_id"]


async def post(s: HttpServer, url: str, *files: tuple[str, bytes]) -> int:
    headers = {"Content-Type": CONTENT_TYPE}
    response = await s.http.post(url, content=multipart(*files), headers=headers)
    return response.status_code


async def send(s: HttpServer, url: str, *files: tuple[str, bytes]) -> None:
    assert await post(s, url, *files) == 200


async def upload(s: HttpServer, *files: tuple[str, bytes]) -> str:
    url, upload_id = await new_link(s)
    await send(s, url, *files)
    return upload_id


async def run_job(s: HttpServer, **arguments: Any) -> dict[str, Any]:
    started = await s.mcp.call_tool("start_ocr_job", arguments)
    job_id = started.structured_content["job_id"]
    done = await s.mcp.call_tool("get_ocr_job", {"job_id": job_id, "wait_s": 30})
    fields: dict[str, Any] = {**done.structured_content, "start": started.structured_content}
    return fields
