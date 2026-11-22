# Architecture

scanscribe-mcp wraps [scanscribe](https://github.com/geosp/scanscribe)'s public library API (`scanscribe.__all__`, pinned at a Git tag) in an MCP server built on mcp-service-kit. The layout follows the owner's pandoc-mcp. Decisions and their reasons are in [the plan](plans/2026-11-21-mcp-server/plan.md) (D1-D12).

## Layers

```text
MCP client ──▶ FastMCP (kit) ──▶ features/<tool>/tool.py ──▶ OcrService ──▶ JobTable
                                                                  │
                                                     worker thread ┴─▶ scanscribe
                                                     watchdog thread
```

| Module | Role | Imports MCP? |
| --- | --- | --- |
| `server.py` | `ScanscribeMCPServer`: instructions sent to clients; `main()` from the kit's `create_main_with_modes` | yes |
| `service.py` | `ScanscribeMCPService`: builds `OcrService` and starts its threads in `initialize()`, stops them in `cleanup()`, registers every `features/*/tool.py` | yes |
| `features/<tool>/tool.py` | One MCP tool each: arguments, reply text and structured content | yes |
| `results.py` | `tool_errors()` turns a `ValueError` into a tool error; job status fields and replies | yes |
| `config.py` | `AppConfig`: the kit's `BaseServerConfig` (`MCP_*`) and `ScanscribeMcpConfig` (`SCANSCRIBE_MCP_*`) | no |
| `ocr_service.py` | `OcrService`: input and option checks, the worker, the engine cache, the watchdog, results | no |
| `jobs.py` | `Job`, `JobTable` (the job table under a lock) and the FIFO queue | no |

Callers' mistakes are raised as `ValueError` with a message meant for the caller. The tools wrap them in `tool_errors()`, so they reach the client as tool errors.

## One job at a time

scanscribe's engine swaps the process-wide `sys.stdout` while it runs, and pdfium isn't thread safe. So exactly one daemon thread, the worker, runs OCR, taking job ids from a `queue.Queue` in order. The tools run in the event loop and only read and change the job table, which guards every job with one lock and hands out copies.

The engine comes from an injected factory with `scanscribe.load_engine`'s signature. Production passes `load_engine`, and the tests pass a fake. The worker keeps one engine:

- it loads the engine at the first job;
- it drops the engine before loading one for another language;
- it drops the engine after any error raised inside it.

## A job, step by step

1. **`start_ocr_job`** checks that exactly one input was given, that local paths are allowed, and that `lang`, `dpi` and `columns` are within the configured limits. It checks that `input_path` exists. For a folder, it counts the page images and refuses more than `MAX_PAGES`. It also refuses the job if the queue is full or the server is stuck. Then the job is `queued`.
2. **The worker** takes the next queued job, skipping cancelled and expired ones, and marks it `running`. Everything below runs inside `redirect_stdout(sys.stderr)` and a catch-all.
3. **`checking pages`:**
   - For a PDF, the worker reads every page's size and refuses a page larger than `MAX_PAGE_PIXELS` at the job's dpi, before anything is rendered.
   - Then `scanscribe.open_source` runs its pre-check, which reads every page once.
   - A source with more than `MAX_PAGES` pages fails here, so a refused input never loads the engine.
4. **`loading engine`:** the engine is reused, or loaded through the factory, which reports the device.
5. **`recognizing`:** `scanscribe.ocr_source` calls `on_page(n, total)` before each page. The worker records the page and its start time there, and raises to stop when the job was cancelled.
6. **The end:** the pages are kept on the job, and `get_ocr_result` formats them as scanscribe's `format_pages` does.
   - An error from scanscribe fails the job with its message, after the input's server path is replaced by the caller's own name for it.
   - Any other error fails it with `OCR failed (<error class>)`.
   - Either way, the worker goes on to the next job.

Cancelling sets a flag on the job. The worker checks it after the pre-check, after the engine loads, and before each page.

## The watchdog

A second thread checks the running job's current page every second. When the page passes `PAGE_TIMEOUT_S`, the watchdog:

- fails the job, naming the timeout;
- fails every queued job with a request to restart the server;
- marks the service stuck, so `start_ocr_job` refuses new jobs until the server restarts.

The worker can't be killed, and the engine may still be busy with the page. If it returns late, its results are ignored. Over HTTP (phase 02) the process will exit instead, so that its supervisor restarts it.

## stdout and logs

Over stdio, stdout carries the MCP protocol. Two things keep other writes off it:

- **The transport:** while serving, it points file descriptor 1 at stderr and writes the protocol through its own copy of the original descriptor.
- **The worker's per-job redirect:** a buffered `print()` would otherwise be written at exit, after the transport has handed descriptor 1 back.

The kit configures logging to stderr. Logs carry job ids, input kinds, sizes, page counts and error classes, never file names, recognized text or error messages. `tests/test_stdio.py` runs the real server in a subprocess, with a fake engine that prints, and checks that every stdout line is an MCP message.

## Tests

Every test runs on the base install: no GPU and no PaddlePaddle.

- **Fakes:** `tests/fakes.py` holds the fake engine and factory, a clock that moves only when a test says so, and builders for small images and PDFs. No book material is used.
- **Tools:** tool tests use a real `fastmcp.Client` against the in-process server.
- **Engine guard:** `tests/paddle_guard.py` fails the session if `paddle` or `paddleocr` was imported.
