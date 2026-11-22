"""stdout carries only the MCP protocol, end to end over stdio (task 01/4.2; D10, R21)."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import IO, Any

import mcp_types
import pytest

from .fakes import make_pages

ROOT = Path(__file__).resolve().parent.parent


class StdioSession:
    """Speaks raw JSON-RPC to the server and keeps every line it writes to stdout."""

    def __init__(self, *args: str) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("MCP_", "SCANSCRIBE_MCP_"))}
        self.process = subprocess.Popen(
            [sys.executable, "-m", "tests.stdio_launcher", *args],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.lines: list[str] = []
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._next_id = 0
        assert self.process.stdout is not None and self.process.stderr is not None
        threading.Thread(target=self._read, args=(self.process.stdout,), daemon=True).start()
        self.stderr: list[str] = []
        threading.Thread(target=self._drain, args=(self.process.stderr,), daemon=True).start()

    def _read(self, stream: IO[str]) -> None:
        for line in stream:
            self.lines.append(line)
            self._queue.put(line)
        self._queue.put(None)

    def _drain(self, stream: IO[str]) -> None:
        self.stderr.extend(stream)

    def send(self, message: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        self.send({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params})
        while True:
            line = self._queue.get(timeout=30)
            if line is None:
                raise AssertionError("the server closed stdout:\n" + "".join(self.stderr))
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue  # reported by the check on every line
            if isinstance(message, dict) and message.get("id") == self._next_id:
                assert "error" not in message, message
                result: dict[str, Any] = message["result"]
                return result

    def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        result = self.request("tools/call", {"name": tool, "arguments": arguments})
        assert not result.get("isError"), result
        return result

    def close(self) -> None:
        assert self.process.stdin is not None
        self.process.stdin.close()
        try:
            self.process.wait(timeout=15)
        finally:
            if self.process.poll() is None:
                self.process.kill()


def non_mcp_lines(lines: list[str]) -> list[str]:
    """Every stdout line that isn't one valid JSON-RPC message."""
    bad = []
    for line in lines:
        try:
            mcp_types.jsonrpc_message_adapter.validate_json(line)
        except ValueError:
            bad.append(line)
    return bad


def run_one_job(session: StdioSession, folder: Path) -> str:
    session.request(
        "initialize",
        {
            "protocolVersion": mcp_types.LATEST_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "stdio-test", "version": "0"},
        },
    )
    session.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    started = session.call("start_ocr_job", input_path=str(folder))
    job_id: str = started["structuredContent"]["job_id"]
    for _ in range(20):
        status = session.call("get_ocr_job", job_id=job_id, wait_s=5)["structuredContent"]
        if status["state"] != "running" and status["state"] != "queued":
            break
    assert status["state"] == "succeeded", status
    result = session.call("get_ocr_result", job_id=job_id)
    text: str = result["content"][1]["text"]
    return text


def test_stdout_carries_only_mcp(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 3)
    session = StdioSession()
    try:
        text = run_one_job(session, folder)
    finally:
        session.close()
    assert text.startswith("--- Page 1 ---\npage 1\n")
    assert session.lines, "the server wrote nothing to stdout"
    assert non_mcp_lines(session.lines) == []
    stderr = "".join(session.stderr)
    assert "fake engine stray output, page 3" in stderr  # the prints went to stderr instead


def test_the_check_catches_output_before_the_server_starts(tmp_path: Path) -> None:
    folder = make_pages(tmp_path / "pages", 1)
    session = StdioSession("--print-before-start")
    try:
        run_one_job(session, folder)
    finally:
        session.close()
    assert non_mcp_lines(session.lines) == ["stray output before the server starts\n"]


@pytest.mark.parametrize(
    "line", ["not json\n", "{}\n", '{"jsonrpc": "2.0", "id": 1}\n', "[1, 2]\n"]
)
def test_non_mcp_lines_are_found(line: str) -> None:
    assert non_mcp_lines([line]) == [line]
