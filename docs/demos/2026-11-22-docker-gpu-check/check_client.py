"""Run one OCR job against the server in the container, from the host, as an MCP client would.

    TOKEN_FILE=... uv run python docs/demos/2026-11-22-docker-gpu-check/check_client.py \
        <pdf> <text out> <lang>

Uploads the PDF through an upload link, starts the job, follows it, saves the text, and prints
one JSON line: state, device, pages, run seconds, the result's download URL and any error.
Reads the server's token from the file TOKEN_FILE names, so it never appears on a command line.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from fastmcp import Client

BASE = os.environ.get("BASE", "http://localhost:8302")


async def main(pdf: str, out: str, lang: str) -> None:
    token = Path(os.environ["TOKEN_FILE"]).read_text().strip()
    async with Client(f"{BASE}/mcp", auth=token) as client:
        link = (await client.call_tool("create_upload_link", {})).structured_content
        async with httpx.AsyncClient(timeout=120) as http:
            with open(pdf, "rb") as handle:
                files = {"file": (Path(pdf).name, handle, "application/pdf")}
                (await http.post(link["upload_url"], files=files)).raise_for_status()
        arguments = {"upload_id": link["upload_id"], "lang": lang}
        job = (await client.call_tool("start_ocr_job", arguments)).structured_content
        while True:
            wait = {"job_id": job["job_id"], "wait_s": 60}
            status = (await client.call_tool("get_ocr_job", wait)).structured_content
            if status["state"] not in ("queued", "running"):
                break
        result: dict[str, object] = {}
        if status["state"] == "succeeded":
            got = await client.call_tool("get_ocr_result", {"job_id": job["job_id"]})
            result = got.structured_content
            Path(out).write_text(str(result["text"]), encoding="utf-8")
    print(
        json.dumps(
            {
                "state": status["state"],
                "device": status.get("device"),
                "pages": result.get("pages"),
                "run_seconds": status.get("run_seconds"),
                "url": result.get("url"),
                "error": status.get("error"),
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:]))
