# scanscribe-mcp

MCP server that OCRs scanned PDFs and page-image folders into page-marked text with [scanscribe](https://github.com/geosp/scanscribe), on the GPU when available.

An agent starts an OCR **job**, follows its progress page by page, can cancel it, and fetches the text. The text comes back inline when it is short, in page ranges when it is long, or into a local file. Each page starts with a `--- Page N ---` line.

**Status:** the stdio server works (phase 01 of [the plan](docs/plans/2026-11-21-mcp-server/plan.md)). HTTP with upload links and a document store, and a Docker image for an NVIDIA GPU, are the next phases. Agents working here follow [AGENTS.md](AGENTS.md). How it is built: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Install

Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/). Install exactly one OCR engine build:

```bash
uv sync --extra gpu   # NVIDIA GPU (PaddlePaddle with CUDA 12.6)
uv sync --extra cpu   # CPU only
```

A plain `uv sync` installs the server without an engine. The server starts, but every job fails with a message that names the two commands above. The first job also downloads the OCR models, so it takes longer.

## Use it from Claude Code (stdio)

```bash
claude mcp add scanscribe -- uv run --directory /path/to/scanscribe-mcp scanscribe-mcp
```

Then ask the agent to OCR a PDF or a folder of page images by its absolute path. Over stdio, the server reads and writes files on your machine, so give it absolute paths.

## Tools

| Tool | Arguments | What it does |
| --- | --- | --- |
| `start_ocr_job` | exactly one of `input_path`, `upload_id`, `document`; optional `lang`, `dpi`, `columns` | Checks the input and options and queues a job. Returns its `job_id` at once. Only `input_path` works so far: `upload_id` and `document` need the HTTP server (phase 02). |
| `get_ocr_job` | `job_id`, `wait_s` (0-60, default 0) | The job's state, and for a running job its step, page, total, seconds on the current page and device. Returns as soon as the job ends, or after `wait_s`. |
| `cancel_ocr_job` | `job_id` | Cancels a queued job at once, and a running job before its next page. A finished job keeps its state. |
| `get_ocr_result` | `job_id`, optional `first_page`, `last_page`, `output_path` | The text of a succeeded job. The whole text is inline when it fits in `SCANSCRIBE_MCP_MAX_INLINE_CHARS`. A page range is cut at a page boundary to fit, and the reply names the next `first_page`. `output_path` (absolute, in an existing folder) writes the whole text to that file, replacing it. |

- **Job states:** `queued`, `running`, `succeeded`, `failed`, `cancelled`, `expired`.
- **Steps of a running job, in order:** `checking pages`, `loading engine`, `recognizing`.
- **Input:** a folder is read as page images (`.png .jpg .jpeg .tif .tiff .bmp .webp`, not hidden), in natural file-name order (`p2` before `p10`). Any other file is read as a PDF.

**One job at a time.** The OCR engine and the PDF renderer can't safely run twice in one process. So one worker thread runs the jobs, in the order they were started, and the others wait in the queue. The engine loads at the first job and again only when a job asks for a different language. Jobs live in memory, so a restart forgets them.

## Configuration

Environment variables, also read from a `.env` file. The kit's `MCP_TRANSPORT` (`stdio` by default), `MCP_HOST`, `MCP_PORT` and `MCP_AUTH_ENABLED` choose the transport. HTTP needs phase 02's token, so it refuses to start unless you pass `--no-auth`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SCANSCRIBE_MCP_LANGS` | `en` | OCR languages a job may ask for, comma-separated |
| `SCANSCRIBE_MCP_DEFAULT_LANG` | first of `LANGS` | Language of a job that names none |
| `SCANSCRIBE_MCP_DEFAULT_DPI` | `200` | Resolution of PDF pages when a job names none |
| `SCANSCRIBE_MCP_DEFAULT_COLUMNS` | `1` | Text columns per page when a job names none |
| `SCANSCRIBE_MCP_DEVICE` | unset | Engine device, e.g. `gpu:0` or `cpu`; unset means the GPU if there is one, else the CPU |
| `SCANSCRIBE_MCP_MIN_DPI`, `SCANSCRIBE_MCP_MAX_DPI` | `72`, `400` | The `dpi` a job may ask for |
| `SCANSCRIBE_MCP_MAX_COLUMNS` | `8` | The most `columns` a job may ask for |
| `SCANSCRIBE_MCP_MAX_PAGES` | `500` | Most pages in one job |
| `SCANSCRIBE_MCP_MAX_PAGE_PIXELS` | `100000000` | Largest PDF page, in pixels at the job's dpi; a larger page fails the job before anything is rendered |
| `SCANSCRIBE_MCP_PAGE_TIMEOUT_S` | `600` | A page that takes longer fails its job. Queued jobs fail too, and the server refuses new jobs until it is restarted |
| `SCANSCRIBE_MCP_MAX_QUEUED` | `20` | Most jobs waiting at once |
| `SCANSCRIBE_MCP_QUEUE_TIMEOUT_S` | `3600` | A job that waits longer in the queue expires without running |
| `SCANSCRIBE_MCP_JOB_RETENTION_S` | `86400` | How long a finished job stays listed |
| `SCANSCRIBE_MCP_MAX_INLINE_CHARS` | `50000` | Longest text `get_ocr_result` returns inline |
| `SCANSCRIBE_MCP_ALLOW_LOCAL_PATHS` | `true` | `false` turns off `input_path` and `output_path` over stdio. Over HTTP they are never accepted |

## Privacy

Logs go to stderr. They name jobs by id and inputs by kind, size and page count, never by file name, and they never hold recognized text or error messages. Error messages name your input as you gave it, never another path on the server.

## Development

```bash
uv sync --locked
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run .agents/sync_agents.py --check
```

The tests use a fake OCR engine and a real `fastmcp.Client`. They need no GPU and no PaddlePaddle, and they fail if `paddle` or `paddleocr` is ever imported.
