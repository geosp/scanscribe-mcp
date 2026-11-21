# Notes · A working scanscribe MCP server

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

| Variable | Default | Used by |
| --- | --- | --- |
| `LANGS` | `en` | R3, R11 (comma-separated) |
| `DEFAULT_LANG` | first of `LANGS` | `start_ocr_job` without `lang` |
| `DEVICE` | unset (scanscribe picks GPU, else CPU) | passed to `load_engine` |
| `MAX_PAGES` | 500 | R4 |
| `MIN_DPI`, `MAX_DPI` | 72, 400 | R3 |
| `MAX_COLUMNS` | 8 | R3 |
| `MAX_QUEUED` | 20 | R6 |
| `QUEUE_TIMEOUT_S` | 3600 | R7 |
| `JOB_RETENTION_S` | 86400 | finished jobs listed |
| `MAX_INLINE_CHARS` | 50000 | R13 |
| `ALLOW_LOCAL_PATHS` | stdio only | R2, R14 |
| `TOKEN` | unset | R19 |
| `PUBLIC_BASE_URL` | `http://localhost:8302` | R20 |
| `OUTPUT_DIR` | `data/documents` | R20 |
| `WORK_DIR` | `data/work` | job folders for uploads and zips |
| `RETENTION_DAYS` | 7 | R20 |
| `MAX_FILE_BYTES` | 200 MB | R16 |
| `MAX_UPLOAD_BYTES` | 2 GB | R16, R17 |
| `UPLOAD_LINK_TTL_S` | 600 | R15 |
| `UPLOAD_LINK_MAX_FILES` | 200 | R15 |
| `UPLOAD_LINK_MAX_ACTIVE` | 100 | open links at once |

Port 8302 keeps it apart from pandoc-mcp's 8301 on the same host.

## D7 · Turning an upload into a scanscribe input

`open_source` takes a path: a folder of images, or a file read as a PDF. A job folder
`WORK_DIR/<job id>/` is made for each job from an upload or document and deleted when the job ends.

| Upload contents | Job input |
| --- | --- |
| one `.pdf` | the stored file's path, used in place |
| one `.zip` | entries extracted into `<job>/pages/`, then that folder |
| 1–200 images | hard links (or copies) into `<job>/pages/` under their stored names, then that folder |
| anything else, or a mix | tool error at `start_ocr_job` |

Zip rules (R17), checked from the central directory before anything is written:
- entry count ≤ `MAX_PAGES`; directories are skipped, every other entry must have an
  `IMAGE_EXTENSIONS` suffix, so nested zips are refused;
- the name is reduced with `safe_filename`; an entry whose reduced name differs from its base
  name only by case or is a duplicate is refused;
- symlink entries (Unix mode `S_IFLNK` in `external_attr`) are refused;
- the sum of `file_size` ≤ `MAX_UPLOAD_BYTES`, and extraction streams each entry with a running
  byte count, so a lying header can't exceed it;
- hidden names (leading `.`, e.g. `__MACOSX/._p1.png` after reduction) are skipped, as scanscribe
  skips them in folders.

Pages then follow scanscribe's own natural order, because the folder goes through `open_source`.

## D9 · The Docker image

- `python:3.12-slim`, `git` for the Git dependencies, uv copied from `ghcr.io/astral-sh/uv` at
  CI's version.
- `uv sync --frozen --no-dev --extra ${ENGINE}` with `ENGINE=gpu` by default.
- `PADDLE_PDX_CACHE_HOME=/cache/paddlex` on a named volume `models`; `/data` on a named volume
  `documents`. Both owned by an unprivileged user (uid 1000).
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
it too. The subprocess test in phase 01 checks this end to end with a fake engine that prints.
