---
phase: 1
title: stdio server with jobs and a fake engine
status: draft
branch: null
base: null
delivers: [R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R21, R22, R24]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-21 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 01 · stdio server with jobs and a fake engine

## Goal

`uv run scanscribe-mcp` serves the four job tools over stdio. An agent can OCR a local PDF or
image folder through `input_path`, follow progress, cancel, and read the text inline, in page
slices or into a local file. Every test runs on the base install with a fake engine.

## Tasks

### 1. Project and configuration

- [ ] 1.1 Add the dependencies to `pyproject.toml`: scanscribe at tag v0.2.0 and mcp-service-kit
  at v0.2.1 as Git dependencies; the `gpu` and `cpu` extras pulling `scanscribe[gpu]` /
  `scanscribe[cpu]`; scanscribe's `[tool.uv] conflicts`, `paddlepaddle-cu126` index and
  `[tool.uv.sources]` entry; the `scanscribe-mcp` script; dev deps `pytest-asyncio` and `httpx`;
  mypy overrides for untyped modules. Relock with CI's uv (D1, D9). Verify: `uv sync --locked`
  on the base install, and `uv lock --check` with CI's uv version, both pass;
  `uv sync --extra gpu --dry-run` resolves `paddlepaddle-gpu` from the cu126 index.
- [ ] 1.2 Add `config.py`: `ScanscribeMcpConfig` with the phase 01 variables from
  [notes.md#configuration](../notes.md#configuration) and `AppConfig` with
  `local_paths_allowed` (D1, R2, R3). Verify: unit tests for defaults, env overrides, `LANGS`
  parsing and the stdio-only default for local paths.

### 2. Jobs and the worker

- [ ] 2.1 Add `jobs.py`: the `Job` record (id, state, input kind, options, page, total, device,
  error, pages, timestamps), the job table with its lock, and the FIFO queue with the length
  limit and queue timeout (D2, R5, R6, R7). Verify: unit tests with an injected clock for order,
  the 21st job refused, expiry, and purge of finished jobs after `JOB_RETENTION_S`.
- [ ] 2.2 Add the worker thread to `ocr_service.py`: it loads the engine through the injected
  factory on the first job and on a language change, reporting the device through `on_device`;
  runs `open_source`, the page-limit check, `ocr_source` and `format_pages`; and records
  `checking pages`, page progress and the final state (D3, D5, R4, R8, R11, R12). Verify: unit
  tests with a fake engine and fake factory: one factory call for two `en` jobs, two calls for
  `en` then `fr`, a 501-page folder fails before the engine runs, `EngineMissingError` makes the
  job `failed` and the next job still runs.
- [ ] 2.3 Add cancelling: a per-job flag, `on_page` raising `JobCancelled`, a check after the
  pre-check, and queued jobs cancelled without running (D4, R10). Verify: a fake engine that
  blocks on page 3 until released; after cancel, it sees no page 4 and the state is `cancelled`;
  cancelling a succeeded job leaves it `succeeded`.
- [ ] 2.4 Map scanscribe's `UsageError` and `InputError` to job errors and tool errors, and log
  only job ids, kinds, sizes and page counts (R22). Verify: a test captures all log records of a
  failing job over `chapter-3.pdf` and finds neither the name nor any fake OCR text.

### 3. Tools

- [ ] 3.1 Add `server.py`, `service.py` and `results.py` on the kit: instructions text, tool
  discovery from `features/*/tool.py`, worker start in `initialize()` and stop in `cleanup()`,
  `tool_errors()` (D1). Verify: a `fastmcp.Client` test lists exactly the phase 01 tools and
  reads the instructions.
- [ ] 3.2 Add `features/start_ocr_job/tool.py`: exactly one input (only `input_path` works in this
  phase; the others return "needs the HTTP server"), `lang`, `dpi`, `columns`, option checks,
  returns the job id and state (R1, R2, R3, R6). Verify: client tests for no input, two inputs,
  a bad lang, `dpi: 600`, `columns: 9`, and a full queue.
- [ ] 3.3 Add `features/get_ocr_job/tool.py` with `wait_s` 0–60 polling every 0.5 s (R8, R9).
  Verify: a client test where a fake job finishes after ~1 s and `wait_s=30` returns in under
  3 s with `succeeded`, page total and device; an unknown id is a tool error.
- [ ] 3.4 Add `features/cancel_ocr_job/tool.py` (R10). Verify: client tests for queued, running
  and finished jobs.
- [ ] 3.5 Add `features/get_ocr_result/tool.py`: inline text up to `MAX_INLINE_CHARS`,
  `first_page` / `last_page` slices, and `output_path` when local paths are allowed (R13, R14).
  Verify: client tests for a small result inline, a large one not inline with a page count,
  a slice of pages 10–12 with their markers, an out-of-range slice as a tool error, and
  `output_path` writing the exact text.

### 4. End to end and documentation

- [ ] 4.1 Add a test fixture module with the fake engine and a session-end check that `paddle`
  and `paddleocr` were never imported, and generate small fixture images and a two-page PDF in
  the tests (no book material) (R24). Verify: `uv run pytest` passes on the base install and the
  check fails when a test imports `paddle` on purpose.
- [ ] 4.2 Add a subprocess test that starts the server over real stdio with a test-only engine
  factory whose engine prints to stdout, runs a job through `input_path`, and parses every
  stdout line as MCP (D10, R21). Verify: the test passes, and fails if the server is changed to
  `print()` a line to stdout.
- [ ] 4.3 Write the README (tools, stdio setup with `claude mcp add`, configuration, the
  one-job-at-a-time limit) and `docs/ARCHITECTURE.md` (layers, a job step by step), and update
  the AGENTS.md checks if they change. Verify: the link checker in CI passes; every tool and
  variable in the code is in the README.
- [ ] 4.4 With `uv sync --extra gpu`, register the server with Claude Code over stdio and OCR a
  self-made PDF of a few pages through `input_path`; record the check in
  `docs/demos/<date>-stdio-check/README.md`. Verify: the record states the result, device, page
  count and time, and that no book material was used.
