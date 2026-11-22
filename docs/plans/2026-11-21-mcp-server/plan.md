---
title: A working scanscribe MCP server
status: draft
created: 2026-11-21
updated: 2026-11-21
design_review: { status: changes-requested, rounds: 2, last: 2026-11-21 }
approved: null
adr_review: null
---

# A working scanscribe MCP server

## Summary

scanscribe-mcp becomes an MCP server that lets an agent OCR a scanned PDF or a set of page images
into page-marked text, through scanscribe v0.2.0's public API. An agent starts a **job**, follows
its progress page by page, can cancel it, and fetches the text: inline up to 50,000 characters, in
page slices, by download URL over HTTP, or into a local file over stdio. One worker thread runs one
job at a time from a queue, because the engine and pdfium aren't safe to run twice in one process;
it loads the engine at the first job and again only when the language changes (D2, D3). The layout
and security model are pandoc-mcp's (D1, D8): stdio with `input_path`, or HTTP with a bearer
token, upload links and a document store (D6, D7). It ships in three slices: stdio, then HTTP and
uploads, then a Docker image for an NVIDIA GPU. The main risks are hostile uploads such as zip
bombs and oversized PDF pages (R17, R27), book material or server paths leaking into logs and
errors (R22, R23), and an image that can't see the GPU (phase 03's manual check).

```text
agent ──start_ocr_job──▶ tool ──▶ OcrService ──queue──▶ worker thread ──▶ scanscribe
      ◀─get_ocr_job (state, step, page n/total, device)  (one engine, one job at a time)
      ◀─get_ocr_result (text or slice, id, URL) ◀── document store ◀──┘
```

## Why

scanscribe can already OCR a book chapter from the command line, and v0.2.0 added a library API
for exactly this server (ADR-0002, ADR-0003). Agents can't use the command well: a chapter of
20–100 pages takes minutes, longer than a tool call should block, and remote agents can't hand the
server a path. A job-based MCP server gives agents the OCR with progress, cancelling, uploads and
the GPU when the machine has one.

## What changes

- A new package `scanscribe_mcp` built on the kit v0.2.1, laid out like pandoc-mcp.
- Job tools: `start_ocr_job` (one input; `lang`, `dpi`, `columns`), `get_ocr_job` (`wait_s`),
  `cancel_ocr_job`, and `get_ocr_result` (`first_page`, `last_page`, `output_path`).
- Upload tools, HTTP only: `create_upload_link(max_files)` returns a link and an `upload_id`;
  `check_upload(upload_id, wait_s)` lists the files received, with their document ids.
- A job queue with one worker thread, and a document store for results and uploads.
- `pyproject.toml` gains scanscribe, the kit, pypdfium2 and fastmcp, the `gpu` and `cpu` extras,
  and the PaddlePaddle uv settings copied from scanscribe.
- A Dockerfile, a compose file and `.env.example` for an NVIDIA GPU host.
- README and `docs/ARCHITECTURE.md` describe tools, configuration and the security model.

### Non-goals

- OCR engines other than scanscribe's, and any change to scanscribe itself (new needs go through a
  new scanscribe tag, ADR-0003).
- Several jobs at once, several GPUs, or jobs that survive a restart.
- Searching or editing the text; the agent does that with the text it gets back.
- A CPU-only Docker image as a supported target (D9).

## Terms

- **The kit**: mcp-service-kit, the owner's library for FastMCP servers: transports, CLI, config.
- **Job**: one OCR run over one input, with an id, a state, a step and progress.
- **Job state**: `queued`, `running`, `succeeded`, `failed`, `cancelled` or `expired`.
- **Step**: what a `running` job is doing: `loading engine`, `checking pages` or `recognizing`.
- **Input**: what a job reads: an `upload_id`, a `document` id, or an `input_path`.
- **Document**: a file in the document store. A job may read an uploaded PDF or zip by its id;
  result `.txt` documents are refused as input.
- **Page-marked text**: scanscribe's output, each page under a `--- Page N ---` line.
- **scanscribe API**: `load_engine(lang, device, on_device=)` builds the engine;
  `open_source(path, dpi, columns)` opens a PDF or image folder and runs the pre-check;
  `ocr_source(source, engine, on_page)` returns each page's lines; `format_pages` joins them.
  Details: notes.md#scanscribe-api
- **Pre-check**: `open_source` reads every page once before any OCR, to find unreadable or too
  narrow pages; it reports no progress.
- **`on_page`**: scanscribe calls it as `on_page(n, total)` before OCR of each page; raising from
  it stops the run. **`on_device`** receives the device name.
- **Engine**: the object `load_engine` returns; it OCRs one image at a time.
- **Device**: where the engine runs, as scanscribe reports it, for example `gpu:0` or `cpu`.
- **pdfium**: the PDF renderer scanscribe uses, through pypdfium2.
- **Fake engine**: a test class with scanscribe's one-method `OcrEngine` shape; no PaddlePaddle.
- **Local paths**: `input_path` and `output_path`, allowed when `SCANSCRIBE_MCP_ALLOW_LOCAL_PATHS`
  is true; unset, it is true over stdio and false over HTTP.
- **Upload link**: a short-lived, upload-only URL from `create_upload_link`, as in pandoc-mcp.
- **upload_id**: the non-secret handle the MCP caller gets with a link, to list what arrived.
- **Document store**: files under `SCANSCRIBE_MCP_OUTPUT_DIR`, one folder per random id.
- **Job folder**: `SCANSCRIBE_MCP_WORK_DIR/<job id>/`, where the worker lays out a job's pages.
- **PaddleX**: the PaddleOCR layer that downloads and caches the OCR models.
- **Book material**: PDFs, page images and OCR text of books; never in Git, fixtures or logs.

## Requirements

### R1 · A job reads exactly one input

`start_ocr_job` must receive exactly one of `upload_id`, `document` or `input_path`.
- **Given** none, or two of them, **when** `start_ocr_job` is called, **then** it returns a tool error and no job is created.

### R2 · Local paths only where allowed

`input_path` and `output_path` are accepted only when local paths are allowed (Terms).
- **Given** local paths not allowed, **when** a call passes `input_path` or `output_path`, **then** it returns a tool error that names upload links instead.

### R3 · Options are checked before a job is queued

`lang` must be one of `SCANSCRIBE_MCP_LANGS` (default `en`), `dpi` must be 72–400, and `columns`
must be 1–8.
- **Given** `lang: "xx"` with `SCANSCRIBE_MCP_LANGS=en`, **when** a job is started, **then** it returns a tool error listing the allowed languages.
- **Given** `dpi: 600` or `columns: 9`, **when** a job is started, **then** it returns a tool error.

### R4 · A job has at most the page limit

A job whose input has more than `SCANSCRIBE_MCP_MAX_PAGES` pages (default 500) never reaches the
engine.
- **Given** a folder or zip of 501 images, **when** a job is started, **then** it returns a tool error.
- **Given** a 501-page PDF, **when** the job runs, **then** it fails after the pre-check with a message naming the limit, and the engine never runs.

### R5 · One job runs at a time, in order

Only one job may run at a time; queued jobs start in the order they were started.
- **Given** jobs A then B, **when** both are queued, **then** B stays `queued` until A is no longer `running`, and B starts next.

### R6 · The queue has a length limit

At most `SCANSCRIBE_MCP_MAX_QUEUED` jobs (default 20) may be in the `queued` state at once.
- **Given** 20 queued jobs, **when** another job is started, **then** it returns a tool error and no job is created.
- **Given** 20 jobs that were queued and then cancelled, **when** another job is started, **then** it is accepted.

### R7 · A job that waits too long expires

A queued job that hasn't started within `SCANSCRIBE_MCP_QUEUE_TIMEOUT_S` (default 3600 s) is
`expired` and never runs.
- **Given** a queued job older than the timeout, **when** `get_ocr_job` is called, **then** it reports `expired`, and the worker later skips it.

### R8 · Status shows state, step, progress and device

`get_ocr_job` must return the job's state; for a running job its step, its page number and total
once recognizing, and the seconds spent on the current page; the device once known; and the error
message of a failed job.
- **Given** a running job on page 3 of 12, **when** `get_ocr_job` is called, **then** it reports `running`, `recognizing`, page 3, total 12, the seconds on page 3 and the device.

### R9 · Waiting for a job is bounded

`get_ocr_job` with `wait_s` (0–60 s) returns as soon as the job reaches a final state, or when
`wait_s` has passed.
- **Given** a job that finishes after 1 s, **when** `get_ocr_job(wait_s=30)` is called, **then** it returns about 1 s later with the final state.

### R10 · Cancelling stops a job at its next check

`cancel_ocr_job` must make a queued job `cancelled` at once, and stop a running job at the next
of these points: after the engine loads, after the pre-check, before each page.
- **Given** a running job on page 3, **when** it is cancelled, **then** the engine sees no page after page 3 and the state becomes `cancelled`.
- **Given** a succeeded job, **when** it is cancelled, **then** the state stays `succeeded` and the reply says so.

### R11 · The engine is loaded once per language

The worker must load the engine only when the first job needs it, and load it again only when a
job's `lang` differs from the loaded engine's.
- **Given** two jobs with `lang: en`, **when** both run, **then** the engine factory is called once.

### R12 · A missing engine fails the job, not the server

If no OCR engine build is installed, the job fails with scanscribe's install message, and the
server keeps answering.
- **Given** an install without PaddlePaddle, **when** a job runs, **then** it is `failed` with the message naming `uv sync --extra gpu` and `--extra cpu`.

### R13 · The result comes back inline up to a limit

`get_ocr_result` must return the page-marked text inline when it fits in
`SCANSCRIBE_MCP_MAX_INLINE_CHARS` (default 50,000), and otherwise say how to get it whole.
`first_page` and `last_page` return only that range inline.
- **Given** a 300-page result, **when** `get_ocr_result` is called with no range, **then** no text is inline and the reply gives the page count and the ways to get the text.
- **Given** the same result, **when** it is called with pages 10 to 12, **then** exactly those three pages come back, with their `--- Page N ---` lines.

### R14 · Over stdio, a result can be written to a local file

With local paths allowed, `get_ocr_result(output_path=…)` writes the whole text to that file.
- **Given** a stdio server, **when** `output_path` is given, **then** the file holds exactly the job's text.

### R15 · Uploads only through upload links

Over HTTP, files reach the server only through an upload link: upload-only, valid for
`SCANSCRIBE_MCP_UPLOAD_LINK_TTL_S` (default 600 s), and closed after its `max_files`.
`max_files` defaults to 100 and is never above 200.
- **Given** an expired or used-up link, **when** a file is posted to it, **then** the server answers 404 and stores nothing.

### R16 · Upload sizes are limited

Each uploaded file must be at most `SCANSCRIBE_MCP_MAX_FILE_BYTES` (default 200 MB), and the files
of one link at most `SCANSCRIBE_MCP_MAX_UPLOAD_BYTES` (default 2 GB) in all.
- **Given** a 250 MB file, **when** it is posted, **then** the server answers 413 and stores nothing.

### R17 · A zip is expanded only safely

A zip input must hold only page images, at most the page limit of them, unpacking to at most
`SCANSCRIBE_MCP_MAX_UPLOAD_BYTES`, with no entry path that leaves the job folder.
- **Given** a zip with `../x.png`, `/x.png`, a symlink or a nested zip, **when** the job runs, **then** it fails before OCR and nothing is written outside the job folder.
- **Given** a zip with `a/1.png` and `b/1.png`, **when** the job runs, **then** it fails before OCR, naming the duplicate.
- **Given** a zip whose entries unpack past the limit, **when** the job runs, **then** it fails before OCR.

### R18 · The pages of an upload keep natural order

The images of one upload or zip must be OCR'd in scanscribe's natural file-name order: digit runs
compare as numbers.
- **Given** uploads `p10.png`, `p2.png`, `p1.png`, **when** the job runs, **then** the engine sees p1, p2, p10.

### R19 · Over HTTP, the MCP endpoint needs the bearer token

`/mcp` must reject requests without `SCANSCRIBE_MCP_TOKEN`, and the HTTP server refuses to start
without a token unless `--no-auth` is passed.
- **Given** a request without the token, **when** it reaches `/mcp`, **then** the server answers 401.
- **Given** HTTP with auth on and no token set, **when** the server starts, **then** it exits with a configuration error.

### R20 · Results are stored and expire

From phase 02, each result is stored with an id, and over HTTP a download URL; stored documents
older than `SCANSCRIBE_MCP_RETENTION_DAYS` (default 7) are deleted.
- **Given** a succeeded HTTP job, **when** `get_ocr_result` is called, **then** the reply carries an id and a URL that downloads exactly the text.
- **Given** a document older than the retention, **when** the hourly purge runs, **then** it is deleted unless a live job uses it.

### R21 · stdout carries only the MCP protocol

Only the MCP transport may write to the process's stdout; logs go to stderr.
- **Given** a stdio server running a job, **when** the client reads stdout, **then** every line is a valid MCP message.

### R22 · Logs never contain book material

Logs must never contain OCR text, input file names, upload tokens or error messages from jobs; they
name jobs by id, inputs by kind, size and page count, and errors by class.
- **Given** a job over `chapter-3.pdf` uploaded, run, failed and downloaded over HTTP, **when** logs are captured, **then** no line contains `chapter-3`, the link token or any recognized text.

### R23 · Tool errors never reveal server paths

A tool error may name the caller's own page (`p7.png`, `page 7`) but never a path on the server.
- **Given** an HTTP job whose uploaded `p7.png` is unreadable, **when** it fails, **then** the error names `p7.png` and contains neither the resolved `WORK_DIR` nor `OUTPUT_DIR`.

### R24 · Tests and CI never need PaddlePaddle or a GPU

The test suite must pass on the base install with the fake engine, and fail if `paddle` or
`paddleocr` is ever imported.
- **Given** CI's base install, **when** `uv run pytest` runs, **then** every test passes and neither module is in `sys.modules`.

### R25 · The Docker image uses the GPU and keeps its data

The Docker image must OCR on the GPU of a host with the NVIDIA container toolkit, and keep models
and documents on volumes.
- **Given** a GPU host, **when** a job runs in the container, **then** the device is `gpu:0`.
- **Given** the container is recreated, **when** the next job runs, **then** no model is downloaded again and earlier results still download.

### R26 · An unexpected error fails the job, not the worker

Any error while running a job must mark it `failed` with a message free of server paths, and the
worker must go on to the next job.
- **Given** a fake engine that raises `RuntimeError` on page 2, **when** that job and then another run, **then** the first is `failed` and the second `succeeded`.

### R27 · Oversized PDF pages are refused

A PDF page that would render above `SCANSCRIBE_MCP_MAX_PAGE_PIXELS` (default 100 million) at the
job's dpi must fail the job before the pre-check.
- **Given** a PDF with a 200 × 200 inch page and `dpi: 200`, **when** the job runs, **then** it fails naming the page, and nothing is rendered.

## Decisions

### D1 · Follow pandoc-mcp's layout on kit v0.2.1

`server.py` (instructions, auth), `service.py` (tool discovery, routes) and one
`features/<name>/tool.py` per tool. The logic lives in `ocr_service.py`, `jobs.py`,
`documents.py` and `uploads.py`, which never import MCP. Config is `AppConfig` = the kit's
`BaseServerConfig` plus `ScanscribeMcpConfig` (`SCANSCRIBE_MCP_*`). Rejected: a flat module (it
would break with the pattern the owner maintains in pandoc-mcp). Details: notes.md#d1

### D2 · One worker thread and a FIFO queue

A single daemon thread takes jobs from a `queue.Queue`, so OCR never runs twice at once (R5) and
never blocks the event loop. The job table, under a lock, is the truth: R6 counts its `queued`
jobs, and the worker skips cancelled or expired entries. Each job runs inside a catch-all (R26).
Rejected: `asyncio.to_thread` per job (needs its own lock to serialize); a process pool (a second
engine and GPU context per process).

### D3 · Engine from an injected factory, loaded lazily

`OcrService` takes an engine factory with `load_engine`'s signature; production passes
`scanscribe.load_engine`, and tests a fake (R24). The worker loads at the first job, and on a
language change drops the old engine before loading the new one (R11). After an engine error the
engine is dropped too. The stdio subprocess test uses `tests/stdio_launcher.py`, which builds the
server with the fake factory; production has no hook for it. Rejected: loading at start-up (every
stdio session would hold GPU memory and block on a model download).

### D4 · Cancel by raising from `on_page`

`cancel_ocr_job` sets a flag. The worker checks it after the engine loads and after the pre-check,
and `on_page` raises `JobCancelled` when it is set, so `ocr_source` stops before the next page
(R10). Rejected: killing the thread (Python can't, and pdfium would be left open).

### D5 · The worker opens the input and counts pages before OCR

The worker checks PDF page sizes (R27), calls `open_source`, checks `len(source)` against the page
limit (R4), then runs `ocr_source` and `format_pages`. Folders and zips are also counted from file
names at `start_ocr_job`. Rejected: `transcribe` (no hook between the pre-check and OCR).

### D6 · Results: in memory in phase 01, in the document store from phase 02

Phase 01 keeps each result's pages on the job. From phase 02 every result, on both transports, is
also saved as `ocr-<job id>.txt` in a pandoc-mcp-style `DocumentStore`, with options and page
count, never text, in `meta.json`. Over stdio the reply leaves out the URL, which nothing serves,
and points to slices and `output_path`. Purge runs hourly on a timer. Rejected: a database.

### D7 · Uploads: images, a PDF or a zip per link

A job from an `upload_id` reads that link's files: one PDF, one zip, or images used as a folder.
More than one PDF or zip, or a mix, is refused. Starting the job snapshots the document ids of the
files already received in full and closes the link. The worker builds the job folder, deleted when
the job ends; `WORK_DIR` is emptied at start-up. Rejected: zip only (hard in a browser); files
only (100 curl `-F` flags). Details: notes.md#d7

### D8 · Security follows pandoc-mcp's model

Static bearer token checked with `hmac.compare_digest` on `/mcp`; upload links with
`token_urlsafe(32)` kept as sha256 hashes in memory; `safe_filename` on every uploaded name;
random uuid4 ids for downloads; no client paths over HTTP; uvicorn's access log off, because paths
hold tokens and ids. Rejected: JWT (no identity provider here).

### D9 · Docker: Python slim image, the `gpu` extra, the NVIDIA toolkit

The image is `python:3.12-slim` with `uv sync --frozen --no-dev --extra gpu`; the cu126 wheels
bring their CUDA libraries, and the host's NVIDIA toolkit provides the driver. Compose requests the
GPU, sets a memory limit, and mounts `documents` at `/data` and `models` at `/cache`. A build
argument `ENGINE=cpu` exists but isn't checked. Rejected: an `nvidia/cuda` base (larger, and the
wheels carry CUDA). Details: notes.md#d9

### D10 · stdout safety relies on the transport, and a test checks it

While serving, fastmcp's stdio transport writes the protocol to its own copy of the original
stdout and points file descriptor 1 at stderr. So anything else that writes to stdout, including
the engine's swap of `sys.stdout`, lands on stderr. The server logs only to stderr. Task 01/4.2
checks it end to end (R21). Rejected: our own redirection. Details: notes.md#d10

## Assumptions

- scanscribe v0.2.0's API is enough; no new scanscribe tag is needed (notes.md#scanscribe-api).
- uv's `uv_build` backend accepts the Git dependencies on scanscribe and the kit.
- PaddleX keeps downloaded models under `PADDLE_PDX_CACHE_HOME` (default `~/.paddlex`), so the
  image can point it at a volume. Phase 03 verifies it.
- The PaddlePaddle cu126 wheels run with only the host driver mounted by the NVIDIA toolkit.
- Jobs and upload links live in memory; a restart forgets them, and agents start again.
- Finished jobs stay listed for `SCANSCRIBE_MCP_JOB_RETENTION_S` (default 24 h).
- `wait_s` polling every 0.5 s is cheap enough, as `check_upload` does in pandoc-mcp.

## Risks

- The container doesn't see the GPU, or the wheels need libraries the slim image lacks → the
  phase 03 manual check on the owner's RTX 3060; fall back to an `nvidia/cuda` runtime base.
- Zip bombs or path tricks in uploads → R17's checks, entry by entry while streaming, tested with
  hostile zips built in memory.
- A huge PDF page exhausts memory → R27's size check before rendering; compose's memory limit as
  the backstop for anything else.
- A page hangs in the engine or pdfium, so the worker never finishes it → cancelling can't help;
  R8's seconds-on-page shows it, and a restart recovers (compose `restart: unless-stopped`).
- Book material or server paths leak through logs or errors → R22, R23: the server swaps paths in
  scanscribe's messages for the caller's names. Logs hold only ids, counts and error classes.

## Rollout & rollback

Nothing is deployed yet. Each phase merges to `main` through its own pull request and leaves a
working server. After phase 03 the owner may tag `v0.1.0`. Rollback is reverting a phase's merge.
There is no data to migrate. After reverting phase 02, delete `data/documents` and `data/work`;
after reverting phase 03, `docker compose down -v` removes the volumes.

## Open questions

- None. The owner's answers of 2026-11-21 are recorded in D7, R3, R4, R6, R7, R9, R11, R13, R14
  and R16.

## Impact

- Packages / directories: `src/scanscribe_mcp/`, `tests/`, `pyproject.toml`, `uv.lock`,
  `README.md`, `docs/ARCHITECTURE.md`, `Dockerfile`, `docker-compose.yml`, `.env.example`,
  `.dockerignore`, `docs/demos/`, `docs/decision-log.md`, `AGENTS.md`.
- Data: the document store and job folders under `data/` (kept out of Git), the model cache volume.
- Jobs / APIs: six MCP tools; HTTP routes `/mcp`, `/upload/<token>`, `/documents/<id>/<name>`.

## Links

- scanscribe ADR-0001 — the engine sits behind a one-method `OcrEngine` protocol; Paddle is
  imported only inside `load_engine`.
- scanscribe ADR-0002 — the public API is exactly `scanscribe.__all__`, versioned with semver.
- scanscribe ADR-0003 — this server lives in its own repository, pins a scanscribe tag, copies the
  PaddlePaddle uv settings, and runs one job at a time.
- pandoc-mcp README and docs/ARCHITECTURE.md — the owner's document-conversion MCP server; its
  layout, upload links, document store and security model are copied here.
- mcp-service-kit v0.2.1 — HTTP refuses to start without an auth provider unless `--no-auth`.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | stdio server with jobs and a fake engine (R1–R14, R21, R22, R24, R26, R27) | draft | 0/15 |
| 02 | HTTP, token, uploads and the document store (R15–R20, R22, R23) | draft | 0/14 |
| 03 | Docker on the GPU and the manual GPU check (R25) | draft | 0/8 |

## Decision log

