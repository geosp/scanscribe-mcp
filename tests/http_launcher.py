"""Run the real HTTP server with the fake engine, for the HTTP subprocess tests (D3, R28).

    python -m tests.http_launcher [--hang-on-page N]

Configuration comes from the environment (MCP_PORT, SCANSCRIBE_MCP_TOKEN, ...), as in
production. With --hang-on-page N the fake engine blocks on page N for ever, so the watchdog
fires. Production has no such hook; this file is test-only.
"""

from __future__ import annotations

import logging
import sys
import threading

from scanscribe_mcp.config import AppConfig
from scanscribe_mcp.server import ScanscribeMCPServer
from scanscribe_mcp.service import ScanscribeMCPService

from .fakes import FakeEngineFactory


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    hooks = {}
    if "--hang-on-page" in sys.argv:
        page = int(sys.argv[sys.argv.index("--hang-on-page") + 1])
        never = threading.Event()
        hooks[page] = lambda: never.wait() and None
    config = AppConfig()
    config.server.transport = "http"
    service = ScanscribeMCPService(config, FakeEngineFactory(hooks=hooks))
    ScanscribeMCPServer(config.server, service).run()


if __name__ == "__main__":
    main()
