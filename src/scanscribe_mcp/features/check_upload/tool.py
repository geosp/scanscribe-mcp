"""MCP tool: check_upload (D7, R15), HTTP only."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from pydantic import Field

from ...ocr_service import OcrService
from ...results import reply

POLL_S = 0.5


def register_tool(mcp: FastMCP, ocr: OcrService) -> None:
    @mcp.tool()
    async def check_upload(
        upload_id: Annotated[str, Field(description="The upload_id from create_upload_link")],
        wait_s: Annotated[
            float,
            Field(
                ge=0,
                le=60,
                description="Wait up to this many seconds for a first file to arrive and for "
                "uploads in progress to end (0-60)",
            ),
        ] = 0,
    ) -> ToolResult:
        """
        List the files uploaded through a link from create_upload_link

        Returns each file's name, size and document id, and whether uploads are still in
        progress. Start the OCR with start_ocr_job(upload_id=...) once they are all there.
        """
        links, store = ocr.uploads, ocr.store
        if links is None or store is None:
            raise ToolError(
                "check_upload needs the HTTP server. On this local server, pass input_path "
                "to start_ocr_job instead."
            )
        grant = links.get(upload_id)
        if grant is None:
            raise ToolError(f"unknown or expired upload_id {upload_id!r}")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_s
        while (not grant.files or grant.in_progress) and loop.time() < deadline:
            if not grant.in_progress and not links.open(grant):
                break  # nothing more can arrive
            await asyncio.sleep(min(POLL_S, max(deadline - loop.time(), 0)))

        files: list[dict[str, Any]] = []
        for doc_id in grant.files:
            stored = store.get(doc_id)
            if stored is not None:
                files.append({"id": stored.id, "filename": stored.filename, "size": stored.size})
        if files:
            lines = [
                f"{len(files)} file(s) uploaded:",
                *(f"- {f['filename']} ({f['size']} bytes), id {f['id']}" for f in files),
            ]
        else:
            lines = ["No files uploaded yet."]
        if grant.in_progress:
            lines.append(f"{grant.in_progress} upload(s) still in progress; wait for them.")
        if grant.closed:
            lines.append("A job has taken these files; the link takes no more.")
        elif links.expired(grant):
            lines.append("The link has expired for new uploads.")
        else:
            lines.append(f"The link accepts {grant.remaining} more file(s).")
        if files and not grant.in_progress:
            lines.append(f"Start the OCR with start_ocr_job(upload_id={upload_id!r}).")
        return reply(
            lines,
            {
                "upload_id": upload_id,
                "files": files,
                "in_progress": grant.in_progress,
                "remaining": grant.remaining if links.open(grant) else 0,
                "expired": links.expired(grant),
                "closed": grant.closed,
            },
        )
