"""MCP tool: create_upload_link (D7, R15), HTTP only."""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from pydantic import Field

from ...config import MAX_FILES_PER_LINK
from ...ocr_service import OcrService
from ...results import reply, tool_errors


def register_tool(mcp: FastMCP, ocr: OcrService) -> None:
    @mcp.tool()
    async def create_upload_link(
        max_files: Annotated[
            int | None,
            Field(
                ge=1,
                le=MAX_FILES_PER_LINK,
                description="How many files the link accepts; default: the server's setting",
            ),
        ] = None,
    ) -> ToolResult:
        """
        Get a short-lived, upload-only link for the pages to OCR

        Upload page images, one PDF, or one zip of page images through it: give the link to
        the user to open in a browser, or upload with curl. Then start the job with
        start_ocr_job(upload_id=...); check_upload(upload_id, wait_s=60) shows what arrived.
        """
        if ocr.uploads is None or ocr.store is None:
            raise ToolError(
                "create_upload_link needs the HTTP server. On this local server, pass "
                "input_path to start_ocr_job instead."
            )
        count = ocr.config.upload_link_max_files if max_files is None else max_files
        with tool_errors("create_upload_link"):
            token, grant = ocr.uploads.create(count)
        url = f"{ocr.store.base_url}/upload/{token}"
        minutes = ocr.uploads.ttl_s / 60
        lines = [
            f"Upload link (valid {minutes:g} min for new uploads, up to {count} file(s), "
            f"{grant.max_bytes} bytes in all, upload only):",
            url,
            "",
            "Browser: open the link and drop the page images, a PDF or a zip.",
            f"Shell: curl -F file=@chapter.pdf {url}",
            f"   or: curl -F file=@pages.zip {url}",
            f"   or: curl -F file=@p1.png -F file=@p2.png {url}",
            "",
            f"Then start the job with start_ocr_job(upload_id={grant.upload_id!r}); "
            f"check_upload(upload_id={grant.upload_id!r}, wait_s=60) shows what arrived.",
        ]
        return reply(
            lines,
            {
                "upload_url": url,
                "upload_id": grant.upload_id,
                "expires_in_s": ocr.uploads.ttl_s,
                "max_files": count,
                "max_bytes": grant.max_bytes,
            },
        )
