# Notes · A working scanscribe MCP server

## scanscribe API

Read on 2026-11-21 at scanscribe tag `v0.2.0` (`src/scanscribe/__init__.py`, `api.py`,
`engine.py`, `pages.py`, `output.py`), plus its README section "Use as a library" and ADR-0001 to
ADR-0003.

`scanscribe.__all__` is exactly: `IMAGE_EXTENSIONS`, `EngineFactory`, `EngineMissingError`,
`InputError`, `OcrEngine`, `PageImage`, `PageSource`, `ProgressCallback`, `ScanscribeError`,
`UsageError`, `format_pages`, `load_engine`, `ocr_source`, `open_source`, `transcribe`. This plan
uses only `load_engine`, `open_source`, `ocr_source`, `format_pages`, `PageSource`, `OcrEngine`,
`PageImage`, `IMAGE_EXTENSIONS` and the four error types.

| Name | Behaviour the plan relies on |
| --- | --- |
| `load_engine(lang, device, *, on_device=None) -> OcrEngine` | imports Paddle only here; raises `EngineMissingError` with "the OCR engine is not installed; install one build: `uv sync --extra gpu` (NVIDIA GPU) or `uv sync --extra cpu`"; calls `on_device(resolved)` before building the engine, so the device is known during a first-run model download |
| device choice | `device=None` → `gpu:0` on a CUDA build that sees a GPU, else `cpu` |
| `open_source(path, dpi, columns) -> PageSource` | a folder is read as images, any other path as a PDF; `UsageError` for `dpi`/`columns` < 1 or a missing path; the pre-check decodes every image (or sizes every PDF page) and raises `InputError` for an unreadable or too narrow page; messages contain the full path |
| `PageSource` | context manager; `len(source)` is the page count after the pre-check; `close()` releases the PDF |
| `ocr_source(source, engine, on_page=None) -> list[list[str]]` | calls `on_page(n, total)` before each page; an exception from it propagates and stops the run before that page is recognized |
| `format_pages(pages) -> str` | `--- Page N ---` then the lines; pages joined by a blank line |
| folder order | regular, non-hidden files with an `IMAGE_EXTENSIONS` suffix in any case, in natural order (digit runs as numbers, case-folded) |
| `IMAGE_EXTENSIONS` | `.png .jpg .jpeg .tif .tiff .bmp .webp` |
| one job per process | the engine wraps each call in `contextlib.redirect_stdout(sys.stderr)`, and pdfium isn't thread safe |

`transcribe` isn't used: it gives no hook between the pre-check and OCR for R4 and R27 (D5).

## R27 · PDF page size check

pypdfium2 comes with scanscribe; task 01/1.1 also makes it a direct dependency, for this check
only. In the worker thread, before `open_source`, open the PDF, read each page's width and height
in points, and refuse a page where `ceil(w × dpi / 72) × ceil(h × dpi / 72)` exceeds
`MAX_PAGE_PIXELS`, then close it. It runs only in the worker, so pdfium is still used from one
thread. Image pages need no check of ours: Pillow refuses images above twice its
`MAX_IMAGE_PIXELS` (~179 MP), and scanscribe reports that as `InputError`.

## D1 · What is copied from pandoc-mcp, and what changes

Read on 2026-11-21 at pandoc-mcp `cbe8023` and mcp-service-kit `v0.2.1`.

| pandoc-mcp | here | change |
| --- | --- | --- |
| `server.py` `PandocMCPServer` | `ScanscribeMCPServer` | instructions text; token `SCANSCRIBE_MCP_TOKEN` |
| `service.py` tool discovery from `features/*/tool.py`, `register_tool(mcp, service)` | same | adds the worker start in `initialize()` and its stop in `cleanup()` |
| `auth.py` `BearerTokenVerifier` | same | none |
| `documents.py` `DocumentStore`, `safe_filename` | same | MIME table reduced to text, PDF, images, zip |
| `uploads.py` `UploadLinks`, `Grant` | same | `max_files` up to 200; total bytes per grant (R16) |
| `results.py` `tool_errors()` | same | maps `scanscribe.UsageError` / `InputError` and strips server paths (R23) |
| `config.py` `AppConfig` + `PandocConfig` | `AppConfig` + `ScanscribeMcpConfig` | `local_paths_allowed` kept as is |

pandoc-mcp pins kit v0.1.0. Since v0.2.0 the kit refuses to start HTTP when
`create_auth_provider()` returns `None` and auth is on, which is what R19 wants. v0.2.1 lets
`MCP_TRANSPORT` pick the transport without `--mode`; the Dockerfile still passes `--mode http`.

## Configuration

All variables read by `ScanscribeMcpConfig` (pydantic-settings, prefix `SCANSCRIBE_MCP_`), next to
the kit's `MCP_TRANSPORT`, `MCP_HOST`, `MCP_PORT` and `MCP_AUTH_ENABLED`.

| Variable | Default | Phase | Used by |
| --- | --- | --- | --- |
| `LANGS` | `en` | 01 | R3, R11 (comma-separated) |
| `DEFAULT_LANG` | first of `LANGS` | 01 | `start_ocr_job` without `lang` |
| `DEFAULT_DPI`, `DEFAULT_COLUMNS` | 200, 1 (scanscribe's) | 01 | R3 |
| `DEVICE` | unset (scanscribe picks GPU, else CPU) | 01 | passed to `load_engine` |
| `MAX_PAGES` | 500 | 01 | R4 |
| `MIN_DPI`, `MAX_DPI` | 72, 400 | 01 | R3 |
| `MAX_COLUMNS` | 8 | 01 | R3 |
| `MAX_PAGE_PIXELS` | 100000000 | 01 | R27 |
| `PAGE_TIMEOUT_S` | 600 | 01 | R28 |
| `MAX_QUEUED` | 20 | 01 | R6 |
| `QUEUE_TIMEOUT_S` | 3600 | 01 | R7 |
| `JOB_RETENTION_S` | 86400 | 01 | finished jobs listed |
| `MAX_INLINE_CHARS` | 50000 | 01 | R13 |
| `ALLOW_LOCAL_PATHS` | true; only `false` has an effect, and only over stdio | 01 | R2, R14 |
| `TOKEN` | unset | 02 | R19 |
| `PUBLIC_BASE_URL` | `http://localhost:<MCP_PORT>` | 02 | R20; set it behind a proxy or in Docker |
| `OUTPUT_DIR` | `data/documents` | 02 | R20; HTTP only |
| `WORK_DIR` | `data/work` | 02 | job folders for uploads and zips; HTTP only (D12) |
| `RETENTION_DAYS` | 7 | 02 | R20 |
| `MAX_FILE_BYTES` | 200 MB | 02 | R16 |
| `MAX_UPLOAD_BYTES` | 2 GB | 02 | R16 (all files of one link), R17 (one zip unpacked) |
| `UPLOAD_LINK_TTL_S` | 600 | 02 | R15 |
| `UPLOAD_LINK_MAX_FILES` | 100 | 02 | R15; default `max_files`; values above 200 are rejected at start-up |
| `UPLOAD_LINK_MAX_ACTIVE` | 100 | 02 | open links at once |

The Docker image uses port 8302, apart from pandoc-mcp's 8301 on the same host.

## D7 · Turning an upload into a scanscribe input

`open_source` takes a path: a folder of images, or a file read as a PDF.

At `start_ocr_job` (in the event loop, cheap): the server refuses while the grant counts an
upload in progress (R29). It lists the link's stored files, skips hidden names and files that are
neither PDF, zip nor image (`.DS_Store`, `Thumbs.db`), and checks the kind, the count and, for
images, that no two reduce to the same name. Any refusal leaves the link open. Once the job is
created, it snapshots the document ids, closes the link, and replies with the count and names
taken; a second start on the same `upload_id` reuses that snapshot. The job keeps the ids; documents live for `RETENTION_DAYS`, far longer than the queue
timeout, and purge skips documents a live job uses.

In the worker, when the job starts: it builds `WORK_DIR/<job id>/` and deletes it when the job
ends in any state. At start-up the HTTP server takes an exclusive lock file in `WORK_DIR` (a
second server on the same folder refuses to start) and deletes leftover entries whose names match
the job-id pattern, because no job survives a restart (D12).

| Upload contents | Job input |
| --- | --- |
| one `.pdf` | the stored file's path, used in place |
| one `.zip` | entries extracted into `<job>/pages/`, then that folder |
| 1–200 images | hard links (copies if on another filesystem) into `<job>/pages/`, then that folder |
| several PDFs or zips, anything else, or a mix | tool error at `start_ocr_job` |

Zip rules (R17), checked from the central directory before anything is written:
- an entry name containing `..` as a part, starting with `/` or `\`, or with a drive letter is
  refused;
- directory entries are skipped; hidden names (any part starting with `.`, and everything under
  `__MACOSX/`) are skipped, as scanscribe skips hidden files in folders;
- every other entry must have an `IMAGE_EXTENSIONS` suffix, so nested zips are refused;
- the page name is the entry's base name, and two entries with the same base name are refused,
  so `chapter/p1.png` (as a zipped folder holds it) becomes `p1.png`;
- symlink entries (Unix mode `S_IFLNK` in `external_attr`) are refused;
- at most `MAX_PAGES` entries; the sum of `file_size` ≤ `MAX_UPLOAD_BYTES`, and extraction
  streams each entry with a running byte count, so a header that understates its size can't
  exceed the limit.

Pages then follow scanscribe's natural order, because the folder goes through `open_source`.

## D9 · The Docker image

- `python:3.12-slim`, `git` for the Git dependencies, uv copied from `ghcr.io/astral-sh/uv` at
  CI's version.
- Copies only `pyproject.toml`, `uv.lock`, `README.md` (pyproject's `readme`) and `src/`, then
  `uv sync --frozen --no-dev --extra gpu`.
- `PADDLE_PDX_CACHE_HOME=/cache/paddlex` on the named volume `models` at `/cache`; the named
  volume `documents` at `/data`, with `SCANSCRIBE_MCP_OUTPUT_DIR=/data/documents` and
  `SCANSCRIBE_MCP_WORK_DIR=/data/work` set in the image, so uploads and job folders share one
  filesystem and hard links work. Both owned by an unprivileged user (uid 1000).
- `PATH=/app/.venv/bin:$PATH`, `MCP_PORT=8302`; compose sets `SCANSCRIBE_MCP_PUBLIC_BASE_URL`,
  a memory limit (`mem_limit`, default 16g), `restart: unless-stopped`, and a healthcheck on the
  HTTP port; R28's watchdog exits the process on a hung page, so the restart policy recovers it.
- `.dockerignore` keeps `in/`, `out/`, `data/`, `.env`, `.env.*`, `.venv` and `.git` out.
- Compose asks for the GPU with `deploy.resources.reservations.devices: [{driver: nvidia, count:
  1, capabilities: [gpu]}]`.
- If the slim image lacks a library the wheels need (seen as an `ImportError` or a CPU fallback on
  a GPU host), switch the base to `nvidia/cuda:12.6.x-cudnn-runtime-ubuntu24.04` with uv's Python.

## D10 · Why the engine's stdout swap can't corrupt stdio

fastmcp 4.2.4 (the version the kit's `fastmcp>=4.1.3` resolves to today) serves stdio through
`mcp.server.stdio.stdio_server`. Its docstring and code: "While serving, fd 0 points at the null
device and fd 1 at stderr, so handlers and children read EOF and their stray output misses the
wire." It writes the protocol through its own wrapper of the original descriptor, so
`contextlib.redirect_stdout(sys.stderr)` inside scanscribe's engine only changes the Python
object, never the wire. The worker thread is a plain thread of the same process, so this covers
it too. The protection starts when the transport starts: a `print()` at import or in `main()`
before `run()` would still reach the wire, which is what task 01/4.2's failing case injects.
`fastmcp>=4.2.4` becomes a direct dependency so a re-resolve can't drop below the version read. The subprocess test in phase 01 checks this end to end with a fake engine that prints.
