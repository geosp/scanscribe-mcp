# scanscribe-mcp

MCP server that OCRs scanned PDFs and page-image folders into page-marked text with [scanscribe](https://github.com/geosp/scanscribe), on the GPU when available.

An agent starts an OCR **job**, follows its progress page by page, can cancel it, and fetches the text. The text comes back inline when it is short, in page ranges when it is long, by download URL over HTTP, or into a local file over stdio. Each page starts with a `--- Page N ---` line.

**Status:** the stdio server and the HTTP server with upload links and a document store work (phases 01 and 02 of [the plan](docs/plans/2026-11-21-mcp-server/plan.md)), and a Docker image runs it on an NVIDIA GPU (phase 03). Agents working here follow [AGENTS.md](AGENTS.md). How it is built: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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

## Run it over HTTP

```bash
export SCANSCRIBE_MCP_TOKEN="$(openssl rand -hex 32)"
uv run scanscribe-mcp --mode http --port 8302
claude mcp add --transport http scanscribe http://localhost:8302/mcp \
  --header "Authorization: Bearer $SCANSCRIBE_MCP_TOKEN"
```

Over HTTP the server never reads or writes a path the client names. Files arrive through upload links instead:

1. The agent calls `create_upload_link` and gets a short-lived link and an `upload_id`.
2. The user opens the link in a browser and drops the page images, a PDF or a zip, or the agent's shell uploads them with `curl -F file=@pages.zip <link>`.
3. The agent calls `start_ocr_job(upload_id=...)`, follows the job, and gets the text with `get_ocr_result`. The reply has a download URL for the whole text.

`/mcp` needs the bearer token, and the server refuses to start over HTTP without one unless you pass `--no-auth`. The upload link is the only credential an upload needs, so never hand out the token. Set `SCANSCRIBE_MCP_PUBLIC_BASE_URL` when clients reach the server through a proxy or another host name, because the links and download URLs are built from it.

| Route | Auth | What it does |
| --- | --- | --- |
| `POST /mcp` | bearer token | The MCP endpoint (streamable HTTP) |
| `GET /upload/<token>` | the link | A browser form for the upload |
| `POST /upload/<token>` | the link | Multipart upload in field `file`. Answers 404 once the link is expired, used up or closed, 413 past a size limit, 400 for an empty file. Stores the request's files only when all of them have arrived |
| `GET /documents/<id>/<filename>` | the random id | Downloads a stored document: a result, or an upload |

## Run it in Docker on an NVIDIA GPU

Needs Docker with Compose, an NVIDIA driver on the host, and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html), so containers can reach the GPU. The image installs the `gpu` extra; its PaddlePaddle wheels bring their own CUDA libraries, and the host brings only the driver.

```bash
cp .env.example .env    # then set SCANSCRIBE_MCP_TOKEN: openssl rand -hex 32
docker compose up -d --build
claude mcp add --transport http scanscribe http://localhost:8302/mcp \
  --header "Authorization: Bearer <the token from .env>"
```

The server listens on port 8302. Compose refuses to start without `SCANSCRIBE_MCP_TOKEN`. Set `SCANSCRIBE_MCP_PUBLIC_BASE_URL` in `.env` when clients reach the host by another name, because upload links and download URLs are built from it. `SCANSCRIBE_MCP_HOST_PORT` changes the host port, `SCANSCRIBE_MCP_MEM_LIMIT` the memory limit (default `16g`), and `SCANSCRIBE_MCP_LANGS` the languages.

Two named volumes keep data across container restarts and rebuilds:

| Volume | Mounted at | Holds |
| --- | --- | --- |
| `documents` | `/data` | Uploads and results (`/data/documents`) and job folders (`/data/work`), on one filesystem so uploaded images are hard-linked into job folders |
| `models` | `/cache` | The OCR models PaddleX downloads at the first job (`/cache/paddlex`, about 130 MB for English), so later containers don't download them again |

`docker compose down` keeps both volumes; `docker compose down -v` deletes them, with every stored document.

**A hung job.** When a page takes longer than `SCANSCRIBE_MCP_PAGE_TIMEOUT_S`, the server fails the job and exits with code 70, and `restart: unless-stopped` starts it again. The restart forgets jobs and upload links, which live in memory, so agents start the job again; stored documents stay. A healthcheck polls the HTTP port every 30 s.

## Tools

| Tool | Arguments | What it does |
| --- | --- | --- |
| `start_ocr_job` | exactly one of `input_path` (stdio), `upload_id` or `document` (HTTP); optional `lang`, `dpi`, `columns` | Checks the input and options and queues a job. Returns its `job_id` at once. From an `upload_id` the job takes the link's files and the link closes; starting again on the same `upload_id` reads the same files. A `document` is the id of an uploaded PDF or zip. |
| `get_ocr_job` | `job_id`, `wait_s` (0-60, default 0) | The job's state, and for a running job its step, page, total, seconds on the current page and device. Returns as soon as the job ends, or after `wait_s`. |
| `cancel_ocr_job` | `job_id` | Cancels a queued job at once, and a running job before its next page. A finished job keeps its state. |
| `get_ocr_result` | `job_id`, optional `first_page`, `last_page`, `output_path` (stdio) | The text of a succeeded job. The whole text is inline when it fits in `SCANSCRIBE_MCP_MAX_INLINE_CHARS`. A page range is cut at a page boundary to fit, and the reply names the next `first_page`. Over HTTP the reply also has the result's document id and download URL. `output_path` (absolute, in an existing folder) writes the whole text to that file, replacing it. |
| `create_upload_link` | optional `max_files` (1-200, default `SCANSCRIBE_MCP_UPLOAD_LINK_MAX_FILES`) | HTTP only. A short-lived, upload-only link, the `upload_id` that goes with it, and the curl commands to use it. |
| `check_upload` | `upload_id`, `wait_s` (0-60, default 0) | HTTP only. The files that arrived, with names, sizes and document ids, and how many uploads are still in progress. Waits up to `wait_s` for a first file and for running uploads to end. |

- **Job states:** `queued`, `running`, `succeeded`, `failed`, `cancelled`, `expired`.
- **Steps of a running job, in order:** `checking pages`, `loading engine`, `recognizing`.
- **Input:** a folder is read as page images (`.png .jpg .jpeg .tif .tiff .bmp .webp`, not hidden), in natural file-name order (`p2` before `p10`). Any other file is read as a PDF.
- **Uploads:** one link's files must be one PDF, one zip of page images, or page images with distinct names; hidden files and other files (`.DS_Store`, `Thumbs.db`) are skipped. A zip may hold only page images, in folders or not; its folders are dropped, so two pages may not share a name. Entries that leave the zip's folder, symbolic links and nested zips fail the job before any OCR.

**One job at a time.** The OCR engine and the PDF renderer can't safely run twice in one process. So one worker thread runs the jobs, in the order they were started, and the others wait in the queue. The engine loads at the first job and again only when a job asks for a different language. Jobs live in memory, so a restart forgets them.

## Configuration

Environment variables, also read from a `.env` file (see `.env.example`). The kit's `MCP_TRANSPORT` (`stdio` by default), `MCP_HOST`, `MCP_PORT` and `MCP_AUTH_ENABLED` choose the transport. Variables marked HTTP have no effect over stdio, which writes nothing to disk but `output_path`.

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
| `SCANSCRIBE_MCP_PAGE_TIMEOUT_S` | `600` | A page that takes longer fails its job. Queued jobs fail too. Over stdio the server refuses new jobs until it is restarted; over HTTP it exits with code 70, so its supervisor restarts it |
| `SCANSCRIBE_MCP_MAX_QUEUED` | `20` | Most jobs waiting at once |
| `SCANSCRIBE_MCP_QUEUE_TIMEOUT_S` | `3600` | A job that waits longer in the queue expires without running |
| `SCANSCRIBE_MCP_JOB_RETENTION_S` | `86400` | How long a finished job stays listed |
| `SCANSCRIBE_MCP_MAX_INLINE_CHARS` | `50000` | Longest text `get_ocr_result` returns inline |
| `SCANSCRIBE_MCP_ALLOW_LOCAL_PATHS` | `true` | `false` turns off `input_path` and `output_path` over stdio. Over HTTP they are never accepted |
| `SCANSCRIBE_MCP_TOKEN` | unset | HTTP. The bearer token `/mcp` requires; without it the HTTP server won't start unless you pass `--no-auth` |
| `SCANSCRIBE_MCP_PUBLIC_BASE_URL` | `http://localhost:<MCP_PORT>` | HTTP. Base of upload links and download URLs; set it behind a proxy or in Docker |
| `SCANSCRIBE_MCP_OUTPUT_DIR` | `data/documents` | HTTP. The document store: uploads and results, one folder per random id |
| `SCANSCRIBE_MCP_WORK_DIR` | `data/work` | HTTP. Job folders for uploaded images and unpacked zips, deleted when each job ends. One server per folder: a second one refuses to start |
| `SCANSCRIBE_MCP_RETENTION_DAYS` | `7` | HTTP. Stored documents older than this are deleted, checked hourly, except those a queued or running job reads |
| `SCANSCRIBE_MCP_MAX_FILE_BYTES` | `209715200` (200 MiB) | HTTP. Largest uploaded file |
| `SCANSCRIBE_MCP_MAX_UPLOAD_BYTES` | `2147483648` (2 GiB) | HTTP. Most bytes all files of one link may hold, and most bytes one zip may unpack to |
| `SCANSCRIBE_MCP_UPLOAD_LINK_TTL_S` | `600` | HTTP. How long a link accepts new uploads; an upload that began in time may finish later |
| `SCANSCRIBE_MCP_UPLOAD_LINK_MAX_FILES` | `100` | HTTP. `max_files` of a link that names none; above 200 the server refuses to start |
| `SCANSCRIBE_MCP_UPLOAD_LINK_MAX_ACTIVE` | `100` | HTTP. Most upload links open at once |

## Privacy

Logs go to stderr. They name jobs by id and inputs by kind, size and page count, never by file name, and they never hold recognized text, error messages or upload tokens; uvicorn's access log is off, because request paths hold tokens and document ids. Error messages name your input as you gave it (an uploaded page by its file name), never a path on the server. Over HTTP, `meta.json` next to each stored document holds options and counts, never text.

## Development

```bash
uv sync --locked
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest
uv run .agents/sync_agents.py --check
```

The tests use a fake OCR engine and a real `fastmcp.Client`. They need no GPU and no PaddlePaddle, and they fail if `paddle` or `paddleocr` is ever imported.
