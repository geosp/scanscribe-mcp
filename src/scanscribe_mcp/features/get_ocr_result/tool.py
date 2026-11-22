"""MCP tool: get_ocr_result (R2, R13, R14)."""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from pydantic import Field

from ...ocr_service import OcrService
from ...results import reply, tool_errors


def register_tool(mcp: FastMCP, ocr: OcrService) -> None:
    @mcp.tool()
    async def get_ocr_result(
        job_id: Annotated[str, Field(description="The job_id of a succeeded job")],
        first_page: Annotated[
            int | None, Field(description="Return only pages from this one (1-based)")
        ] = None,
        last_page: Annotated[
            int | None, Field(description="Return only pages up to this one (inclusive)")
        ] = None,
        output_path: Annotated[
            str | None,
            Field(
                description="Absolute path of a file on this machine to write the whole text "
                "to, replacing any file there (local stdio server only)"
            ),
        ] = None,
    ) -> ToolResult:
        """
        Get a succeeded job's page-marked text

        Each page starts with a `--- Page N ---` line. The whole text comes back inline when
        it is short enough; otherwise ask for page ranges with first_page and last_page, or
        save it with output_path. A range that is too long comes back cut at a page boundary,
        and the reply names the next first_page.
        """
        if output_path is not None:
            if first_page is not None or last_page is not None:
                raise ToolError(
                    "output_path writes the whole text; leave out first_page and last_page"
                )
            with tool_errors():
                path, chars = ocr.write_result(job_id, output_path)
                total = len(ocr.succeeded_pages(job_id))
            return reply(
                [f"Wrote {total} pages ({chars} characters) to {path}."],
                {"job_id": job_id, "output_path": str(path), "pages": total, "chars": chars},
            )
        with tool_errors():
            result = ocr.result(job_id, first_page, last_page)
        limit = ocr.config.max_inline_chars
        structured: dict[str, Any] = {
            "job_id": job_id,
            "pages": result.total_pages,
            "first_page": result.first_page,
            "last_page": result.last_page,
            "next_first_page": result.next_first_page,
            "inline": result.text is not None,
        }
        ways = ["ask for page ranges with first_page and last_page"]
        if ocr.local_paths:
            ways.append("pass output_path to write the whole text to a local file")
        if first_page is None and last_page is None:
            structured["chars"] = result.chars
            if result.text is not None:
                lines = [f"Job {job_id}: {result.total_pages} pages, {result.chars} characters."]
                return reply(lines, structured, result.text)
            lines = [
                f"Job {job_id}: {result.total_pages} pages, {result.chars} characters, more than "
                f"the {limit}-character inline limit, so no text is returned here.",
                "To get it, " + ", or ".join(ways) + ".",
            ]
            return reply(lines, structured)
        if result.text is None:
            lines = [
                f"Page {first_page or 1} alone is longer than the {limit}-character inline "
                "limit, so no text is returned here."
            ]
            if ocr.local_paths:
                lines.append("Pass output_path to write the whole text to a local file.")
            return reply(lines, structured)
        lines = [f"Pages {result.first_page} to {result.last_page} of {result.total_pages}."]
        if result.next_first_page is not None:
            lines.append(
                f"The range was cut at the {limit}-character inline limit; continue with "
                f"first_page={result.next_first_page}."
            )
        return reply(lines, structured, result.text)
