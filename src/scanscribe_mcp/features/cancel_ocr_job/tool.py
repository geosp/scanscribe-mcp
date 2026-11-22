"""MCP tool: cancel_ocr_job (R10)."""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.tools import ToolResult
from pydantic import Field

from ...jobs import JobState
from ...ocr_service import OcrService
from ...results import job_fields, reply, tool_errors


def register_tool(mcp: FastMCP, ocr: OcrService) -> None:
    @mcp.tool()
    async def cancel_ocr_job(
        job_id: Annotated[str, Field(description="The job_id from start_ocr_job")],
    ) -> ToolResult:
        """
        Cancel a job: a queued job at once, a running job before its next page

        A job that has already finished keeps its state. Check a running job with get_ocr_job
        until it reports cancelled.
        """
        with tool_errors():
            job, changed = ocr.cancel_job(job_id)
        fields = job_fields(job, ocr.clock())
        fields["cancel_requested"] = changed
        if job.state is JobState.CANCELLED and changed:
            line = f"Job {job.id} was cancelled before it started."
        elif job.state is JobState.RUNNING:
            line = (
                f"Job {job.id} will stop at its next check (before the next page); "
                "get_ocr_job shows when it is cancelled."
            )
        else:
            line = f"Job {job.id} has already finished as {job.state}; nothing was cancelled."
        return reply([line], fields)
