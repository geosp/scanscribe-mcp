"""Shared helpers for the tools: error mapping and job replies."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.tools import ToolResult
from mcp_types import TextContent

from .jobs import Job, JobState

logger = logging.getLogger(__name__)


@contextmanager
def tool_errors(tool: str) -> Iterator[None]:
    """Report a caller's mistake to the client as a tool error.

    The service raises ValueError only with messages meant for the caller, which never hold
    server paths (D11). Any other exception becomes "<tool> failed (<class>)" and is logged by
    class only: its text, or a traceback fastmcp would log, may hold a path (R22).
    """
    try:
        yield
    except ToolError:
        raise
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:
        logger.warning("tool %s failed (%s)", tool, type(exc).__name__)
        raise ToolError(f"{tool} failed ({type(exc).__name__})") from None


def job_fields(job: Job, now: float) -> dict[str, Any]:
    """The structured status of a job (R8)."""
    fields: dict[str, Any] = {
        "job_id": job.id,
        "state": job.state.value,
        "input": job.input.kind,
        "lang": job.options.lang,
        "dpi": job.options.dpi,
        "columns": job.options.columns,
    }
    if job.state is JobState.RUNNING and job.step is not None:
        fields["step"] = job.step.value
    if job.page is not None:
        fields["page"] = job.page
    if job.total is not None:
        fields["total"] = job.total
    if job.state is JobState.RUNNING and job.page is not None and job.page_started is not None:
        fields["page_seconds"] = round(now - job.page_started, 1)
    if job.device is not None:
        fields["device"] = job.device
    if job.error is not None:
        fields["error"] = job.error
    if job.state is JobState.QUEUED:
        fields["queued_seconds"] = round(now - job.created, 1)
    if job.started is not None:
        end = job.finished if job.finished is not None else now
        fields["run_seconds"] = round(end - job.started, 1)
    return fields


def job_summary(fields: dict[str, Any]) -> str:
    """One line a person can read, from `job_fields`."""
    parts = [f"Job {fields['job_id']}: {fields['state']}"]
    if "step" in fields:
        parts.append(fields["step"])
    if "page" in fields and "total" in fields:
        parts.append(f"page {fields['page']} of {fields['total']}")
    elif "total" in fields:
        parts.append(f"{fields['total']} pages")
    if "page_seconds" in fields:
        parts.append(f"{fields['page_seconds']} s on this page")
    if "device" in fields:
        parts.append(f"on {fields['device']}")
    line = ", ".join(parts)
    if "error" in fields:
        line += f". Error: {fields['error']}"
    return line


def reply(lines: list[str], structured: dict[str, Any], *texts: str) -> ToolResult:
    """A summary text block, then any further text blocks, plus structured content.

    Some clients (Claude Code among them) give the model only the structured content when
    there is one, so the summary goes into it as `message` too; a tool whose text blocks
    matter puts them in its structured content as well.
    """
    message = "\n".join(lines)
    content = [TextContent(type="text", text=message)]
    content += [TextContent(type="text", text=text) for text in texts]
    return ToolResult(content=content, structured_content={**structured, "message": message})
