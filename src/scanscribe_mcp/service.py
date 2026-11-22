"""The MCP service for scanscribe-mcp (D1).

Builds the OCR service, starts its worker in `initialize()` and stops it in `cleanup()`, and
registers the tools from features/*/tool.py.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

import scanscribe
from fastmcp import FastMCP
from mcp_service_kit import BaseService

from .config import AppConfig
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
        self.ocr = OcrService(
            self.config.ocr,
            self.engine_factory,
            local_paths=self.config.local_paths_allowed,
            transport=self.config.server.transport,
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
