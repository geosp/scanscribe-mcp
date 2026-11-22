"""scanscribe-mcp: OCR scanned PDFs and page images into page-marked text over MCP.

Run it with:
    scanscribe-mcp                # stdio
    scanscribe-mcp --mode stdio

Over stdio, stdout carries the MCP protocol: nothing here prints, and logs go to stderr (D10).
"""

from __future__ import annotations

from mcp_service_kit import BaseMCPServer, create_main_with_modes

from . import __version__
from .config import AppConfig
from .service import ScanscribeMCPService

INSTRUCTIONS = """\
This server OCRs scanned books: a PDF, or a folder of page images (png, jpg, tif, bmp, webp),
into page-marked text where each page starts with a `--- Page N ---` line.

OCR takes minutes for a chapter, so it runs as a job, one job at a time on this server:
1. start_ocr_job(input_path=...) with the absolute path of a PDF or an image folder on this
   machine. Optional: lang, dpi (higher for small print), columns (pages with 2+ text columns).
   It returns a job_id at once.
2. get_ocr_job(job_id, wait_s=60) until the state is succeeded, failed, cancelled or expired.
   While running it shows the step (checking pages, loading engine, recognizing), the page and
   the total. The first job may take longer while the OCR engine and its models load.
3. get_ocr_result(job_id) returns the text inline when it is short enough. For a long result,
   ask for page ranges with first_page and last_page, or pass output_path (an absolute path)
   to save the whole text to a file on this machine.
cancel_ocr_job(job_id) stops a job before its next page. Other jobs wait in a queue, in order.
"""


class ScanscribeMCPServer(BaseMCPServer):
    @property
    def service_title(self) -> str:
        return "scanscribe MCP Server"

    @property
    def service_description(self) -> str:
        return "OCRs scanned PDFs and page images into page-marked text with scanscribe."

    @property
    def service_version(self) -> str:
        return __version__

    @property
    def instructions(self) -> str:
        return INSTRUCTIONS


main = create_main_with_modes(
    ScanscribeMCPServer,
    ScanscribeMCPService,
    AppConfig,
    "scanscribe-mcp",
    "scanscribe-mcp - OCR scanned PDFs and page images over MCP",
)


if __name__ == "__main__":
    main()
