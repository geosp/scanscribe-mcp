"""The MCP service for scanscribe-mcp (D1).

Builds the OCR service, starts its worker in `initialize()` and stops it in `cleanup()`, and
registers the tools from features/*/tool.py. Over HTTP it also builds the document store and
serves stored documents at /documents/<id>/<filename> (D6).
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

import scanscribe
from fastmcp import FastMCP
from mcp_service_kit import BaseService
from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, Response

from .config import AppConfig
from .documents import DocumentStore
from .ocr_service import EngineFactory, OcrService

logger = logging.getLogger(__name__)


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
        store = None
        if self.config.server.transport == "http":
            store = DocumentStore(self.config.ocr.output_dir, self.config.base_url)
            store.ensure_directory()
        self.ocr = OcrService(
            self.config.ocr,
            self.engine_factory,
            local_paths=self.config.local_paths_allowed,
            transport=self.config.server.transport,
            store=store,
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
