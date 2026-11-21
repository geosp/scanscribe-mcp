---
title: A working scanscribe MCP server
status: draft
created: 2026-11-21
updated: 2026-11-21
design_review: { status: none, rounds: 0, last: null }
approved: null
adr_review: null
---

# A working scanscribe MCP server

## Summary

scanscribe-mcp becomes an MCP server that lets an agent OCR a scanned PDF or a set of page images
into page-marked text, through scanscribe's public API (scanscribe v0.2.0). An agent starts a
**job**, follows its progress page by page, can cancel it, and then fetches the text. One worker
thread loads the engine once and runs one job at a time from a queue (D2, D3), because the engine
and pdfium are not safe to run twice in one process. The server follows pandoc-mcp's layout and
security model (D1): stdio for local use with `input_path`, and HTTP with a bearer token, upload
links and a document store (D7, D8). It ships in three working slices: the stdio server,
then HTTP and uploads, then a Docker image for an NVIDIA GPU. The main risks are a Docker image
that fails to see the GPU (verified by a manual check in phase 03) and hostile uploads such as
zip bombs (R15, R16).

```text
agent ──start_ocr_job──▶ tool ──▶ OcrService ──queue──▶ worker thread ──▶ scanscribe
      ◀─get_ocr_job (page n/total, device)            (one engine, one job at a time)
      ◀─get_ocr_result (text, id, URL)  ◀── document store ◀──┘
```

## Why

scanscribe can already OCR a book chapter from the command line, and v0.2.0 added a library API
for exactly this server (ADR-0002, ADR-0003). Agents can't use the command well: a chapter of
20–100 pages takes minutes, longer than a tool call should block, and remote agents can't hand the
server a path. A job-based MCP server gives agents the OCR with progress, cancelling, uploads and
the GPU when the machine has one.

## What changes

- A new package `scanscribe_mcp` built on mcp-service-kit v0.2.1, laid out like pandoc-mcp.
- Six tools: `start_ocr_job`, `get_ocr_job`, `cancel_ocr_job`, `get_ocr_result`,
  `create_upload_link` and `check_upload`.
- A job queue with one worker thread, and a document store for results and uploads.
- `pyproject.toml` gains scanscribe and the kit, the `gpu` and `cpu` extras, and the PaddlePaddle
  uv settings copied from scanscribe.
- A Dockerfile, a compose file and `.env.example` for an NVIDIA GPU host.
- README and `docs/ARCHITECTURE.md` describe tools, configuration and the security model.

### Non-goals

- OCR engines other than scanscribe's, and any change to scanscribe itself (new needs go through a
  new scanscribe tag, ADR-0003).
- Several jobs at once, several GPUs, or jobs that survive a restart.
- Searching or editing the text; the agent does that with the text it gets back.
- A CPU-only Docker image as a supported target (the build argument exists, D9, but only the GPU
  image is checked).

## Terms

- **Job**: one OCR run over one input, with an id, a state and progress.
- **Job state**: `queued`, `running`, `succeeded`, `failed`, `cancelled` or `expired`.
- **Input**: what a job reads: an `upload_id`, a stored `document` id, or an `input_path`.
- **Page-marked text**: scanscribe's output, each page under a `--- Page N ---` line.
- **Engine**: the object `scanscribe.load_engine` returns; it OCRs one image at a time.
- **Device**: where the engine runs, as scanscribe reports it, for example `gpu:0` or `cpu`.
- **Fake engine**: a test class with scanscribe's one-method `OcrEngine` shape; no PaddlePaddle.
- **Local paths**: `input_path` and `output_path`; allowed only over stdio by default.
- **Upload link**: a short-lived, upload-only URL from `create_upload_link`, as in pandoc-mcp.
- **upload_id**: the non-secret handle the MCP caller gets with a link, to list what arrived.
- **Document store**: files under `SCANSCRIBE_MCP_OUTPUT_DIR`, one folder per random id.
- **Book material**: PDFs, page images and OCR text of books; never in Git, fixtures or logs.

## Requirements

### R1 · A job reads exactly one input

`start_ocr_job` must receive exactly one of `upload_id`, `document` or `input_path`.
- **Given** none, or two of them, **when** `start_ocr_job` is called, **then** it returns a tool error and no job is created.

### R2 · Local paths only where allowed

`input_path` and `output_path` are accepted only when local paths are allowed, which by default
means only over stdio.
- **Given** an HTTP server, **when** a call passes `input_path` or `output_path`, **then** it returns a tool error that names upload links instead.

### R3 · Options are checked before a job is queued

`lang` must be one of `SCANSCRIBE_MCP_LANGS`, `dpi` must be 72–400, and `columns` must be 1–8.
- **Given** `lang: "xx"` with `SCANSCRIBE_MCP_LANGS=en`, **when** a job is started, **then** it returns a tool error listing the allowed languages.
- **Given** `dpi: 600`, **when** a job is started, **then** it returns a tool error.

### R4 · A job has at most the page limit

A job whose input has more than `SCANSCRIBE_MCP_MAX_PAGES` pages (default 500) fails before any
page is OCR'd.
- **Given** a folder of 501 images, **when** a job is started, **then** it returns a tool error, or the job fails with a message naming the limit, and the engine never runs.

### R5 · One job runs at a time, in order

Only one job may run at a time; queued jobs start in the order they were started.
- **Given** jobs A then B, **when** both are queued, **then** B stays `queued` until A is no longer `running`, and B starts next.

### R6 · The queue has a length limit

At most `SCANSCRIBE_MCP_MAX_QUEUED` jobs (default 20) may wait at once.
- **Given** 20 queued jobs, **when** another job is started, **then** it returns a tool error and no job is created.

### R7 · A job that waits too long expires

A queued job that hasn't started within `SCANSCRIBE_MCP_QUEUE_TIMEOUT_S` (default 3600 s) becomes
`expired` and never runs.
- **Given** a queued job older than the timeout, **when** the worker reaches it, **then** its state is `expired` and the engine never sees it.

### R8 · Status shows state, progress and device

`get_ocr_job` must return the job's state, its page number and page total once OCR has started,
the device once the engine is loaded, and an error message for a failed job.
- **Given** a running job on page 3 of 12, **when** `get_ocr_job` is called, **then** it reports `running`, page 3, total 12 and the device.

### R9 · Waiting for a job is bounded

`get_ocr_job` with `wait_s` (0–60 s) returns as soon as the job reaches a final state, or when
`wait_s` has passed.
- **Given** a job that finishes after 1 s, **when** `get_ocr_job(wait_s=30)` is called, **then** it returns about 1 s later with the final state.

### R10 · Cancelling stops a job before its next page

`cancel_ocr_job` must make a queued job `cancelled` at once, and stop a running job before its next
page. A finished job is unchanged.
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
`SCANSCRIBE_MCP_UPLOAD_LINK_TTL_S` (default 600 s), and closed after its `max_files` (at most 200).
- **Given** an expired or used-up link, **when** a file is posted to it, **then** the server answers 404 and stores nothing.

### R16 · Upload sizes are limited

Each uploaded file must be at most `SCANSCRIBE_MCP_MAX_FILE_BYTES` (default 200 MB), and one
upload at most `SCANSCRIBE_MCP_MAX_UPLOAD_BYTES` (default 2 GB) in all.
- **Given** a 250 MB file, **when** it is posted, **then** the server answers 413 and stores nothing.

### R17 · A zip is expanded only safely

A zip input must contain only page images, stored under plain, unique file names, with an unpacked
total within `SCANSCRIBE_MCP_MAX_UPLOAD_BYTES` and at most the page limit of entries.
- **Given** a zip with `../x.png`, a symlink, a nested zip, two entries named `1.png`, or entries that unpack past the limit, **when** a job is started from it, **then** the job fails before OCR and nothing is written outside the job's folder.

### R18 · The pages of an upload keep natural order

The images of one upload or zip must be OCR'd in scanscribe's natural file-name order.
- **Given** uploads `p10.png`, `p2.png`, `p1.png`, **when** the job runs, **then** the engine sees p1, p2, p10.

### R19 · Over HTTP, the MCP endpoint needs the bearer token

`/mcp` must reject requests without `SCANSCRIBE_MCP_TOKEN`, and the HTTP server refuses to start
without a token unless `--no-auth` is passed.
- **Given** a request without the token, **when** it reaches `/mcp`, **then** the server answers 401.

### R20 · Results are stored and expire

Over HTTP, each result is stored with an id and a download URL, and stored documents older than
`SCANSCRIBE_MCP_RETENTION_DAYS` (default 7) are deleted.
- **Given** a succeeded job, **when** `get_ocr_result` is called, **then** the reply carries an id and a URL that downloads exactly the text.

### R21 · stdout carries only the MCP protocol

Only the MCP transport may write to the process's stdout; logs go to stderr.
- **Given** a stdio server running a job, **when** the client reads stdout, **then** every line is a valid MCP message.

### R22 · Logs never contain book material

Logs must never contain OCR text or input file names; they name jobs by id and inputs by kind,
size and page count.
- **Given** a job over a file `chapter-3.pdf`, **when** it runs and fails, **then** no log line contains `chapter-3` or any recognized text.

### R23 · Tool errors never reveal server paths

A tool error may name the caller's own page (`p7.png`, `page 7`) but never a path on the server.
- **Given** an HTTP job whose uploaded `p7.png` is unreadable, **when** it fails, **then** the error names `p7.png` and contains no part of the server's job folder path.

### R24 · Tests and CI never need PaddlePaddle or a GPU

The test suite must pass on the base install with the fake engine, and fail if `paddle` or
`paddleocr` is ever imported.
- **Given** CI's base install, **when** `uv run pytest` runs, **then** every test passes and neither module is in `sys.modules`.

### R25 · The Docker image uses the GPU and keeps its models

The Docker image must OCR on the GPU of a host with the NVIDIA container toolkit, and keep the
downloaded models on a volume.
- **Given** a GPU host, **when** a job runs in the container, **then** the device is `gpu:0`.
- **Given** a second container start, **when** the first job runs, **then** no model is downloaded again.

## Decisions

### D1 · Follow pandoc-mcp's layout on kit v0.2.1

`server.py` (instructions, auth), `service.py` (tool discovery, routes) and one
`features/<name>/tool.py` per tool. The logic lives in `ocr_service.py`, `jobs.py`,
`documents.py` and `uploads.py`, which never import MCP. Config is `AppConfig` = the kit's
`BaseServerConfig` plus `ScanscribeMcpConfig` (`SCANSCRIBE_MCP_*`). Rejected: a flat module (it
would break with the pattern the owner maintains in pandoc-mcp). Details: notes.md#d1

### D2 · One worker thread and a FIFO queue

A single daemon thread takes jobs from a `queue.Queue`, so OCR never runs twice at once (R5) and
never blocks the event loop. Job state sits in a dict guarded by a lock; async tools read it and
poll for `wait_s`. Rejected: `asyncio.to_thread` per job (needs its own lock to serialize, and
cancelling is no easier); a process pool (a second engine and GPU context per process).

### D3 · Engine from an injected factory, loaded lazily

`OcrService` takes an engine factory with `load_engine`'s signature; production passes
`scanscribe.load_engine` with `on_device` saving the device, and tests pass a fake engine (R24).
The worker loads the engine at the first job and reloads it on a language change (R11). Rejected:
loading at start-up (every stdio session would hold GPU memory, and start-up would block on a
model download).

### D4 · Cancel by raising from `on_page`

`cancel_ocr_job` sets a flag; the job's `on_page` callback raises `JobCancelled` when it is set,
so `ocr_source` stops before the next page and closes the source (R10). The flag is also checked
after the pre-check. Rejected: killing the thread (Python can't, and pdfium would be left open).

### D5 · The worker opens the input and counts pages before OCR

The worker calls `open_source(path, dpi, columns)`, checks `len(source)` against the page limit
(R4), then runs `ocr_source` and `format_pages`. For folders and zips the count is also checked
from file names when the job is started, so most over-limit inputs are refused at once. Rejected:
`transcribe` (no hook between the pre-check and the OCR to apply the limit).

### D6 · Results: text in memory in phase 01, document store from phase 02

Phase 01 keeps each result's pages on the job, so slices (R13) need no re-parsing. Phase 02 saves
the text as `<input name>.txt` in a pandoc-mcp-style `DocumentStore`, with options and page count,
never text, in `meta.json`. Rejected: a database (more than a file per id needs).

### D7 · Uploads: many files, one PDF or one zip per link

A link accepts up to 200 files. A job from an `upload_id` reads all of its files: one PDF, one zip
of images, or several images used as a folder. Mixed sets are refused. Zips are expanded by the
server into the job's folder under R17's rules. Rejected: zip only (browsers can't make one
easily); many files only (curl with 100 `-F` flags is clumsy for agents). Details: notes.md#d7

### D8 · Security follows pandoc-mcp's model

Static bearer token checked with `hmac.compare_digest` on `/mcp`; upload links with
`token_urlsafe(32)` kept as sha256 hashes in memory; `safe_filename` on every uploaded name;
random uuid4 ids for downloads; no client paths over HTTP. Rejected: JWT (no identity provider
here).

### D9 · Docker: Python slim image, the `gpu` extra, the NVIDIA toolkit

The image is `python:3.12-slim` with `uv sync --frozen --extra gpu`; the PaddlePaddle cu126 wheels
bring their CUDA libraries, and the host's NVIDIA container toolkit provides the driver. Compose
requests the GPU and mounts two volumes: documents and the model cache. A build argument
`ENGINE=cpu` exists but isn't a checked target. Rejected: an `nvidia/cuda` base image (larger, and
the wheels already carry CUDA). Details: notes.md#d9

### D10 · stdout safety relies on the transport, and a test checks it

fastmcp's stdio transport claims file descriptor 1 at start and points it at stderr, so the
engine's swap of `sys.stdout` can't reach the wire. The server itself only logs to stderr, through
the kit. A subprocess test runs a job over real stdio and parses every stdout line (R21). Rejected:
our own redirection (it would fight the engine's). Details: notes.md#d10

## Assumptions

- scanscribe v0.2.0's API is enough; no new scanscribe tag is needed.
- uv's `uv_build` backend accepts the Git dependencies on scanscribe and the kit.
- PaddleX keeps downloaded models under `PADDLE_PDX_CACHE_HOME` (default `~/.paddlex`), so the
  image can point it at a volume. Phase 03 verifies it.
- The PaddlePaddle cu126 wheels run with only the host driver mounted by the NVIDIA toolkit.
- Jobs and upload links live in memory; a restart forgets them, and agents start again.
- Finished jobs stay listed for 24 h; their stored results follow R20's retention.
- `wait_s` polling every 0.5 s is cheap enough, as `check_upload` does in pandoc-mcp.

## Risks

- The container doesn't see the GPU, or the wheels need libraries the slim image lacks → the
  phase 03 manual check runs on the owner's RTX 3060; fall back to an `nvidia/cuda` runtime base.
- Zip bombs or path tricks in uploads → R17's checks before extraction, entry by entry, with
  tests that build hostile zips in memory.
- A huge PDF page at 400 dpi uses a lot of memory → the dpi cap (R3); pdfium's limits are
  scanscribe's concern, noted for a later tag if it shows up.
- The pre-check of 500 images takes a while with no progress → `get_ocr_job` reports
  `checking pages` while `open_source` runs.
- Book material or server paths leak through logs or error text (scanscribe's messages contain
  paths) → R22, R23: the server replaces the job folder in scanscribe's messages before
  returning them, logs only ids and counts, and a test scans captured logs.

## Rollout & rollback

Nothing is deployed yet. Each phase merges to `main` through its own pull request and leaves a
working server. After phase 03 the owner may tag `v0.1.0`. Rollback is reverting a phase's merge;
there is no data to migrate, and stored documents are disposable.

## Open questions

- None. The owner's answers of 2026-11-21 are recorded in D7, R3, R4, R6, R7, R9, R11, R13, R14
  and R16.

## Impact

- Packages / directories: `src/scanscribe_mcp/`, `tests/`, `pyproject.toml`, `uv.lock`,
  `README.md`, `docs/ARCHITECTURE.md`, `Dockerfile`, `docker-compose.yml`, `.env.example`,
  `.dockerignore`, `docs/demos/`.
- Data: the document store under `data/documents` (kept out of Git), the model cache volume.
- Jobs / APIs: six MCP tools; HTTP routes `/mcp`, `/upload/<token>`, `/documents/<id>/<name>`.

## Links

- scanscribe ADR-0001 — the engine sits behind a one-method `OcrEngine` protocol; Paddle is
  imported only inside `load_engine`.
- scanscribe ADR-0002 — the public API is exactly `scanscribe.__all__`, versioned with semver.
- scanscribe ADR-0003 — this server lives in its own repository, pins a scanscribe tag, copies the
  PaddlePaddle uv settings, and runs one job at a time.
- pandoc-mcp README and docs/ARCHITECTURE.md — the layout, upload links, document store and
  security model copied here.
- mcp-service-kit v0.2.1 — HTTP refuses to start without an auth provider unless `--no-auth`.

## Phases

| Phase | Title | Status | Tasks |
| --- | --- | --- | --- |
| 01 | stdio server with jobs and a fake engine | draft | 0/15 |
| 02 | HTTP, token, uploads and the document store | draft | 0/13 |
| 03 | Docker on the GPU and the manual GPU check | draft | 0/7 |

## Decision log

