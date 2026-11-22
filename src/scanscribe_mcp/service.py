"""The MCP service for scanscribe-mcp (D1).

Builds the OCR service, starts its worker in `initialize()` and stops it in `cleanup()`, and
registers the tools from features/*/tool.py. Over HTTP it also builds the document store and
the upload links, serves stored documents at /documents/<id>/<filename> (D6), and takes uploads
at /upload/<token> (POST, or GET for a browser form) (D7, D8).
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

import scanscribe
from fastmcp import FastMCP
from mcp_service_kit import BaseService
from starlette.requests import ClientDisconnect, Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)

from .config import AppConfig
from .documents import DocumentStore
from .ocr_service import EngineFactory, OcrService
from .uploads import UploadError, UploadLinks, UploadReceiver

logger = logging.getLogger(__name__)

MULTIPART_OVERHEAD = 64 * 1024
"""Bytes a multipart request may hold beyond its files: boundaries, headers, small fields."""

LINK_GONE_PAGE = (
    "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
    "<title>Upload link expired</title><body style='font:15px system-ui;max-width:640px;"
    "margin:2rem auto;padding:0 16px'><h1>This upload link is invalid or expired</h1>"
    "<p>Links work for a few minutes and a limited number of files. "
    "Ask the assistant for a new one.</p>"
)


class ScanscribeMCPService(BaseService):
    """Each package in features/ with a tool.py exposing register_tool(mcp, ocr) adds one tool.

    `engine_factory` is `scanscribe.load_engine` in production; tests pass a fake (D3).
    """

    def __init__(self, config: AppConfig, engine_factory: EngineFactory | None = None) -> None:
        self.config = config
        self.engine_factory: EngineFactory = engine_factory or scanscribe.load_engine
        self.ocr: OcrService | None = None

    def initialize(self) -> None:
        if self.ocr is not None:
            return
        store = uploads = None
        ocr = self.config.ocr
        if self.config.server.transport == "http":
            store = DocumentStore(ocr.output_dir, self.config.base_url)
            store.ensure_directory()
            uploads = UploadLinks(
                ocr.upload_link_ttl_s, ocr.upload_link_max_active, ocr.max_upload_bytes
            )
        self.ocr = OcrService(
            self.config.ocr,
            self.engine_factory,
            local_paths=self.config.local_paths_allowed,
            transport=self.config.server.transport,
            store=store,
            uploads=uploads,
        )
        self.ocr.start()
        logger.info(
            "OCR worker started; languages %s; local paths %s",
            ",".join(self.config.ocr.langs),
            "allowed" if self.config.local_paths_allowed else "disabled",
        )

    def cleanup(self) -> None:
        if self.ocr is not None:
            self.ocr.stop()
            self.ocr = None

    def get_service_name(self) -> str:
        return "scanscribe"

    def register_mcp_tools(self, mcp: FastMCP) -> None:
        if self.ocr is None:
            raise RuntimeError("initialize() must run before the tools are registered")
        features_package = f"{__package__}.features"
        features_path = Path(__file__).parent / "features"
        for _, feature_name, is_pkg in sorted(pkgutil.iter_modules([str(features_path)])):
            if not is_pkg:
                continue
            tool_module = importlib.import_module(f"{features_package}.{feature_name}.tool")
            tool_module.register_tool(mcp, self.ocr)
            logger.info("Registered tool from feature: %s", feature_name)
        if self.ocr.store is not None:
            self._register_document_route(mcp, self.ocr.store)
        if self.ocr.store is not None and self.ocr.uploads is not None:
            self._register_upload_routes(mcp, self.ocr.uploads, self.ocr.store)

    def _register_document_route(self, mcp: FastMCP, store: DocumentStore) -> None:
        @mcp.custom_route(
            "/documents/{doc_id}/{filename}", methods=["GET"], include_in_schema=False
        )
        async def get_document(request: Request) -> Response:
            doc_id, filename = request.path_params["doc_id"], request.path_params["filename"]
            path = store.path_for(doc_id, filename)
            document = store.get(doc_id) if path is not None else None
            if path is None or document is None:
                return PlainTextResponse("Not found", status_code=404)
            return FileResponse(path, media_type=document.mime_type, filename=path.name)

    def _register_upload_routes(
        self, mcp: FastMCP, links: UploadLinks, store: DocumentStore
    ) -> None:
        max_file_bytes = self.config.ocr.max_file_bytes
        upload_page = (Path(__file__).parent / "upload_page.html").read_text()

        @mcp.custom_route("/upload/{token}", methods=["GET"], include_in_schema=False)
        async def upload_form(request: Request) -> Response:
            if links.for_token(request.path_params["token"]) is None:
                return HTMLResponse(LINK_GONE_PAGE, status_code=404)
            return HTMLResponse(upload_page)

        @mcp.custom_route("/upload/{token}", methods=["POST"], include_in_schema=False)
        async def upload(request: Request) -> Response:
            # The link itself is the credential: no Authorization header. It is checked only
            # here, when the request starts, so an upload that began in time may end after
            # the link expires (R15).
            grant = links.for_token(request.path_params["token"])
            if grant is None:
                return JSONResponse(
                    {"error": "this upload link is invalid, expired or used up"}, status_code=404
                )
            try:
                declared = int(request.headers.get("content-length") or 0)
            except ValueError:
                return JSONResponse({"error": "invalid Content-Length"}, status_code=400)
            if (
                declared
                > min(grant.remaining * max_file_bytes, grant.remaining_bytes) + MULTIPART_OVERHEAD
            ):
                return JSONResponse(
                    {"error": f"too large: each file may be at most {max_file_bytes} bytes, "
                     f"and this link takes {grant.remaining_bytes} more bytes"},
                    status_code=413,
                )  # fmt: skip
            try:
                receiver = UploadReceiver(
                    links, grant, store, request.headers.get("content-type", ""), max_file_bytes
                )
                stored = await receiver.receive(request.stream())
            except UploadError as exc:
                logger.info("upload %s refused (%d)", grant.upload_id, exc.status)
                return JSONResponse({"error": exc.message}, status_code=exc.status)
            except ClientDisconnect:
                logger.info("upload %s: the client went away", grant.upload_id)
                return Response(status_code=400)
            logger.info(
                "upload %s: stored %d file(s), %d bytes",
                grant.upload_id,
                len(stored),
                sum(document.size for document in stored),
            )
            return JSONResponse(
                {
                    "files": [{"filename": d.filename, "size": d.size} for d in stored],
                    "remaining": grant.remaining if links.open(grant) else 0,
                }
            )
