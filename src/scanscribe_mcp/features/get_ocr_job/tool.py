"""MCP tool: get_ocr_job (R8, R9)."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.tools import ToolResult
from pydantic import Field

from ...ocr_service import OcrService
from ...results import job_fields, job_summary, reply, tool_errors

POLL_S = 0.5


def register_tool(mcp: FastMCP, ocr: OcrService) -> None:
    @mcp.tool()
    async def get_ocr_job(
        job_id: Annotated[str, Field(description="The job_id from start_ocr_job")],
        wait_s: Annotated[
            float,
            Field(
                ge=0,
                le=60,
                description="Wait up to this many seconds for the job to finish (0-60)",
            ),
        ] = 0,
    ) -> ToolResult:
        """
        Get a job's state, step, page progress and device, waiting up to wait_s for it to end

        States: queued, running, succeeded, failed, cancelled, expired. A running job reports
        its step (checking pages, loading engine, recognizing), its page and total, and the
        seconds spent on the current page. When it has succeeded, call get_ocr_result.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_s
        while True:
            with tool_errors():
                job = ocr.get_job(job_id)
            remaining = deadline - loop.time()
            if job.is_final or remaining <= 0:
                break
            await asyncio.sleep(min(POLL_S, remaining))
        fields = job_fields(job, ocr.clock())
        lines = [job_summary(fields)]
        if job.state == "succeeded":
            lines.append(f"Get the text with get_ocr_result(job_id={job.id!r}).")
        return reply(lines, fields)
