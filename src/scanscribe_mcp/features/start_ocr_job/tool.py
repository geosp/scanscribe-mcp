"""MCP tool: start_ocr_job (R1-R4, R6)."""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.tools import ToolResult
from pydantic import Field

from ...ocr_service import OcrService
from ...results import job_fields, reply, tool_errors


def register_tool(mcp: FastMCP, ocr: OcrService) -> None:
    @mcp.tool()
    async def start_ocr_job(
        input_path: Annotated[
            str | None,
            Field(
                description="Absolute path of a PDF or a folder of page images on this machine "
                "(local stdio server only)"
            ),
        ] = None,
        upload_id: Annotated[
            str | None, Field(description="The upload_id of an upload link (HTTP server only)")
        ] = None,
        document: Annotated[
            str | None,
            Field(description="The id of an uploaded PDF or zip document (HTTP server only)"),
        ] = None,
        lang: Annotated[
            str | None, Field(description="OCR language; default: the server's first language")
        ] = None,
        dpi: Annotated[
            int | None, Field(description="Resolution for rendering PDF pages; default 200")
        ] = None,
        columns: Annotated[
            int | None,
            Field(description="Text columns per page, read left to right; default 1"),
        ] = None,
    ) -> ToolResult:
        """
        Start OCR of one input as a background job and return its job_id at once

        Pass exactly one of input_path, upload_id or document. Jobs run one at a time, in
        order. Follow the job with get_ocr_job(job_id, wait_s=60), then fetch the text with
        get_ocr_result(job_id).
        """
        with tool_errors():
            job = ocr.start_job(
                input_path=input_path,
                upload_id=upload_id,
                document=document,
                lang=lang,
                dpi=dpi,
                columns=columns,
            )
        fields = job_fields(job, ocr.clock())
        if job.input.page_count is not None:
            fields["page_images"] = job.input.page_count
        lines = [
            f"Job {job.id} is {job.state} (lang {job.options.lang}, dpi {job.options.dpi}, "
            f"columns {job.options.columns}).",
            f"Follow it with get_ocr_job(job_id={job.id!r}, wait_s=60).",
        ]
        return reply(lines, fields)
