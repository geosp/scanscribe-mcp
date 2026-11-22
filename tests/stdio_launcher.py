"""Run the real server over stdio with the fake engine, for the stdio subprocess test (D3, D10).

    python -m tests.stdio_launcher [--print-before-start]

The fake engine prints to stdout while it recognizes, as a stray library might. With
--print-before-start, one line is printed before the server starts: the transport can't protect
that, so the test must catch it. Production has no such hook; this file is test-only.
"""

from __future__ import annotations

import logging
import sys

from scanscribe_mcp.config import AppConfig
from scanscribe_mcp.server import ScanscribeMCPServer
from scanscribe_mcp.service import ScanscribeMCPService

from .fakes import FakeEngineFactory


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    if "--print-before-start" in sys.argv:
        print("stray output before the server starts", flush=True)
    config = AppConfig()
    config.server.transport = "stdio"
    service = ScanscribeMCPService(config, FakeEngineFactory(print_to_stdout=True))
    ScanscribeMCPServer(config.server, service).run()


if __name__ == "__main__":
    main()
