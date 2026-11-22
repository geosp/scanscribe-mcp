---
phase: 1
title: stdio server with jobs and a fake engine
status: done
branch: docs/plan-mcp-server
base: 34a1a04be3f342a60a2ab38e6dccad3b6c06cbac
delivers: [R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R21, R22, R24, R26, R27, R28]
design_review: { status: passed, rounds: 3, last: 2026-11-21 }
impl_review: { status: passed, rounds: 2, last: 2026-11-21 }
approved: 2026-11-21
---

# Phase 01 · stdio server with jobs and a fake engine

## Goal

`uv run scanscribe-mcp` serves the four job tools over stdio. An agent can OCR a local PDF or
image folder through `input_path`, follow progress, cancel, and read the text inline, in page
slices or into a local file. Every test runs on the base install with a fake engine.

## Tasks

### 1. Project and configuration

- [x] 1.1 Add the dependencies to `pyproject.toml`: scanscribe at tag v0.2.0 and the kit at
  v0.2.1 as Git dependencies, `fastmcp>=4.2.4` and `pypdfium2` directly (notes.md#d10,
  notes.md#r27); the `gpu` and `cpu` extras pulling `scanscribe[gpu]` / `scanscribe[cpu]`;
  scanscribe's `[tool.uv] conflicts`, `paddlepaddle-cu126` index and `[tool.uv.sources]` entry;
  the `scanscribe-mcp` script; dev deps `pytest-asyncio` and `httpx`; mypy overrides for untyped
  modules. Relock with CI's uv (D1, D9). Verify: `uv sync --locked` on the base install and
  `uv lock --check` with CI's uv pass; `uv sync --extra gpu --dry-run` resolves
  `paddlepaddle-gpu` from the cu126 index; the PR's `licenses` job passes, and any licence added
  to its allow-list gets a line in `docs/decision-log.md`.
- [x] 1.2 Add `config.py`: `ScanscribeMcpConfig` with the variables marked phase 01 in
  [notes.md#configuration](../notes.md#configuration) and `AppConfig` with
  `local_paths_allowed` (D1, R2, R3). Verify: unit tests for defaults, env overrides, `LANGS`
  parsing, and `local_paths_allowed`: true over stdio unless the variable is `false`, and always
  false over HTTP, even with the variable `true`.

### 2. Jobs and the worker

- [x] 2.1 Add `jobs.py`: the `Job` record (id, state, step, input kind, options, page, total,
  page start time, device, error, pages, timestamps), the job table under a lock, and the FIFO
  queue; R6 counts `queued` jobs in the table, and a queued job past the timeout reads as
  `expired` (D2, R5, R6, R7). Verify: unit tests with an injected clock for order, the 21st job
  refused, 20 cancelled jobs not counted, expiry on read, the worker skipping cancelled and
  expired entries, and purge of finished jobs after `JOB_RETENTION_S`.
- [x] 2.2 Add the worker thread to `ocr_service.py`, in D5's order: PDF page sizes (R27,
  notes.md#r27), `open_source`, the page limit, then the engine through the injected factory
  (loaded at the first job, dropped before a language change and after any error while it was
  recognizing), then `ocr_source` and `format_pages`; record the step, page progress and final
  state; run each job in a catch-all (D2, D3, D5, R4, R8, R11, R12, R26, R27). Verify:
  fake-engine tests: one factory call for two `en` jobs, two for `en` then `fr` with the first
  engine released before the second load; a 501-page PDF and a 200 × 200 inch page each fail with
  the factory never called; `EngineMissingError` and a `RuntimeError` on page 2 each fail the job
  and the next job succeeds.
- [x] 2.3 Add cancelling: a per-job flag checked after the pre-check and after the engine loads,
  `on_page` raising `JobCancelled`, and queued jobs cancelled without running (D4, R10). Verify:
  a fake engine that blocks on page 3 until released sees no page 4 and the state is
  `cancelled`; a cancel during a slow pre-check stops before the factory is called; a cancel
  during a slow fake engine load stops before page 1; cancelling a succeeded job leaves it
  `succeeded`.
- [x] 2.4 Rewrite error messages as D11 says, and log only job ids, input kinds, sizes, page
  counts and error classes (D11, R22, R26). Verify: a test captures every log record of a failing
  job over a file named `chapter-3.pdf` and finds neither the name, the error message nor any fake
  OCR text; an unreadable page's error names the page as the caller gave it; a fake
  `RuntimeError` whose text holds a temp path gives "OCR failed (RuntimeError)".
- [x] 2.5 Add the page watchdog: a thread that fails the job when the current page (from when
  the job reaches it until the next page is ready) or the `checking pages` step passes
  `PAGE_TIMEOUT_S`, then puts the service in a stuck state in which `start_ocr_job` returns
  "restart the server" (D2, R28). Verify: with an injected clock and a fake engine that blocks
  on page 2, a page 1 render that blocks, or a pre-check that blocks, the job becomes `failed`
  naming the timeout, a queued job becomes `failed` asking
  for a restart, and a new start is refused.

### 3. Tools

- [x] 3.1 Add `server.py`, `service.py` and `results.py` on the kit: instructions text, tool
  discovery from `features/*/tool.py`, worker start in `initialize()` and stop in `cleanup()`,
  `tool_errors()` (D1). Verify: a `fastmcp.Client` test lists exactly the phase 01 tools and
  reads the instructions.
- [x] 3.2 Add `features/start_ocr_job/tool.py`: exactly one input (only `input_path` works in this
  phase; the others return "needs the HTTP server"), `lang`, `dpi`, `columns`, option checks, an
  `input_path` folder counted from file names, and the job id and state in the reply (R1, R2,
  R3, R4, R6, D5). Verify: client tests for no input, two inputs, a bad lang, `dpi: 600`,
  `columns: 9`, the 200 dpi and 1 column defaults, a 501-image folder, a full queue, and
  `input_path` with `ALLOW_LOCAL_PATHS=false` returning an error that names that setting.
- [x] 3.3 Add `features/get_ocr_job/tool.py` with `wait_s` 0–60 polling every 0.5 s (R8, R9).
  Verify: a client test where a fake job finishes after ~1 s and `wait_s=30` returns in under
  3 s with `succeeded`, page total and device; a running job reports its step and seconds on
  the current page; an unknown id is a tool error.
- [x] 3.4 Add `features/cancel_ocr_job/tool.py` (R10). Verify: client tests for queued, running
  and finished jobs.
- [x] 3.5 Add `features/get_ocr_result/tool.py`: inline text up to `MAX_INLINE_CHARS`,
  `first_page` / `last_page` slices, and `output_path` when local paths are allowed (R2, R13,
  R14). Verify: client tests for a small result inline, a large one not inline with a page
  count, a slice of pages 10–12 with their markers, a slice longer than the limit cut at a page
  with the next `first_page` named, an out-of-range slice as a tool error, an absolute
  `output_path` writing the exact text, a relative path and a missing parent refused, and
  `output_path` with local paths turned off refused; `output_path` with `first_page` or
  `last_page` refused, and a slice whose first page alone exceeds the limit returning no text
  (Assumptions).

### 4. End to end and documentation

- [x] 4.1 Add a test fixture module with the fake engine and a session-end check that `paddle`
  and `paddleocr` were never imported; generate small fixture images and PDFs in the tests (no
  book material) (R24). Verify: `uv run pytest` passes on the base install, and the check fails
  when a test puts a stub module named `paddle` into `sys.modules` on purpose.
- [x] 4.2 Run each job in the worker inside `contextlib.redirect_stdout(sys.stderr)` (D10). Add
  `tests/stdio_launcher.py`, which builds the server with the fake engine factory and runs it over
  stdio, and a subprocess test that runs a job through it and parses every stdout
  line as MCP; the fake engine prints to stdout while recognizing (D3, D10, R21). Verify: the
  test passes, and a variant of the launcher that prints one line before the server starts
  makes it fail.
- [x] 4.3 Write the README (tools, stdio setup with `claude mcp add`, configuration, the
  one-job-at-a-time limit) and `docs/ARCHITECTURE.md` (layers, a job step by step), and update
  the AGENTS.md checks if they change; add the four job tools and the phase 01 variables to
  `docs/decision-log.md`. Verify: the link checker in CI passes; every tool and variable in the
  code is in the README and the decision log.
- [x] 4.4 With `uv sync --extra gpu`, register the server with Claude Code over stdio and OCR a
  self-made PDF of a few pages through `input_path`; record the check in
  `docs/demos/<date>-stdio-check/README.md`. Verify: the record states the result, device, page
  count and time, and that no book material was used.
