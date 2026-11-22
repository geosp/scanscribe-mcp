## Phase 01 implementation review, contract lens (diff 34a1a04..d79c2fc)

I found no Blockers, 2 Majors and 14 Nits. Most promises are kept and have a test that would fail without them. The two Majors are an R28 watchdog gap that the tests can't see, and an R22 log leak through a path that no log test exercises.

### Major

**M1 · R28 / D2: no watchdog during page 1's render or during the pre-check**
- **Location:** `/home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/ocr_service.py:400-402` and `:480`.
- **What happens:** `page_started` is set only inside `on_page`, and `check_watchdog` returns False while `page_started is None`.
- **What scanscribe does:** in its installed `scanscribe/api.py:31-33`, `ocr_source` renders each page through `source.images()` before it calls `on_page(number, total)`. Before that, the pre-check (`scanscribe/pages.py` `ImageFolderSource.__init__`, which calls `image.load()` on every image) runs during `checking pages`, and `_watch` ignores that step.
- **Failure scenario:**
  - Take a PDF whose first page hangs pdfium in `page.render`, or a folder whose image hangs PIL's decode in the pre-check, with `PAGE_TIMEOUT_S=600`.
  - The job stays `running` for ever. The service never becomes stuck, so `start_ocr_job` keeps accepting jobs that will never run; they wait an hour and expire instead of failing with "restart the server".
  - A hang rendering page n+1 (n ≥ 1) is caught, but blamed on page n.
- **Contract:** R28: "A page that takes longer than `SCANSCRIBE_MCP_PAGE_TIMEOUT_S` (default 600 s) must fail its job". Plan Risks: "A page hangs in the engine or pdfium … R28's watchdog fails the job".
- **Observability:** `tests/test_watchdog.py` blocks only inside `FakeEngine.recognize` on page 2. `test_watchdog_ignores_a_job_that_is_not_recognizing` (`:53-72`) asserts the gap as intended behaviour.
- **Test that would expose it:** give `running_service` an `open_source` whose `images()` blocks before yielding page 1 (and one whose pre-check blocks), advance the FakeClock past the timeout, and assert `failed` plus `service.stuck`.

**M2 · R22: a symlink loop puts the input path in the logs**
- **Location:** `/home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/ocr_service.py:244-256`.
- **What happens:**
  - `path.resolve()` sits in a `try` that catches only `OSError`. On Python 3.12 (the venv's 3.12.12), pathlib's `resolve` turns ELOOP into `RuntimeError("Symlink loop from %r" % e.filename)`; this is pathlib.py:1234-1237 in the venv.
  - That isn't a `ValueError`, so `tool_errors()` (`results.py:23-26`) doesn't catch it.
  - fastmcp then logs it at `logger.error(f"Error calling tool {name!r}", exc_info=True)` (`fastmcp/server/server.py:1722-1724`), and the traceback carries the full path.
  - The client gets the unmasked `Error calling tool 'start_ocr_job': Symlink loop from '…'`.
- **Failure scenario:** `start_ocr_job(input_path="/home/u/books/chapter-3.pdf")`, where that name is a self-referencing symlink. stderr then holds `chapter-3`.
- **Contract:** R22: "Logs must never contain … input file names". scanscribe itself catches `RuntimeError` for exactly this case (`pages.py` `_input_is_dir`).
- **Observability:** `tests/test_messages_and_logs.py` captures logs only from `OcrService` called directly. No test captures logs through the fastmcp tool layer, so nothing fastmcp logs is ever checked.
- **Test that would expose it:** a `fastmcp.Client` test with caplog, starting a job on a symlink loop named `chapter-3.pdf`, asserting a ToolError and no `chapter-3` in any record's message or `exc_text`.

### Nits
- `ocr_service.py:373`, R26/D2: the catch-all is `except Exception`. A `SystemExit` or `KeyboardInterrupt` raised in the engine ends the worker thread, and later jobs wait until they expire. Unlikely from Paddle, so noted only.
- `ocr_service.py:192-200` against `:486-489`, R28: there is a race between checking and setting the stuck flag. `start_job` can read `_stuck` as False, the watchdog then sets it and runs `fail_queued`, and `submit` adds a job that is never run. That job expires after `QUEUE_TIMEOUT_S` instead of failing with the restart message. The window is tiny.
- `ocr_service.py:370-371`, R26/D11: `public_message` rewrites only the input's path. A `ScanscribeError` from the engine load or a model download that names other server paths, such as the cache, passes through. That's harmless over stdio and matters for phase 02's R23.
- `ocr_service.py:388`, R27: the PDF size check runs only when `is_file()` is true. `open_source` reads any other non-folder (a FIFO or device) as a PDF without the size check. This is an edge case.
- `ocr_service.py:429`, R27/D5: the size loop walks every page before R4's page-count check. A PDF with a million pages walks them all, with no watchdog. D5 orders it this way; checking `len(document)` first would be cheap.
- `features/get_ocr_result/tool.py:42-46` and `ocr_service.py:186-191`, R2: some errors come before the local-path check, so they don't name upload links (HTTP) or `ALLOW_LOCAL_PATHS=false` (stdio). The cases are `output_path` with `first_page`, `input_path` with a bad `lang`, and `input_path` with a second input. R2 says such a call's error names them. This is minor.
- `tests/test_tools.py:177-181`, R2: `output_path` over HTTP is never tested; only `input_path` is. The code path (`write_result` → `check_local_paths`) exists.
- `ocr_service.py:331`, R14: `expanduser()` runs before the `is_absolute()` check, so `~/out.txt` is accepted although "the path must be absolute". It's probably intended; the contract doesn't say.
- `ocr_service.py:531-535`, D6: `write_replacing` puts a transient `.name.hex.tmp` next to `output_path`. D6 says "nothing is written to disk except `output_path`". It's acceptable, but the plan doesn't record it.
- `ocr_service.py:400-405`, R10: a cancel sent while the last page is being recognized has no later check, so the job ends `succeeded`. The reply had said it "will stop at its next check". This matches R10's wording; flagged for the reply text.
- `tests/test_worker.py:84-99`, R12: the test raises a hand-written `EngineMissingError`, not the real one. The base test environment has no Paddle, so calling `scanscribe.load_engine` there would check the real install message end to end. The hand-written text matches `ENGINE_MISSING_MESSAGE` today.
- `tests/test_stdio.py:537-544, 589`, R21: `close()` waits for the process but doesn't join the stdout reader thread. Lines flushed at exit, the case D10 is about, may not be in `session.lines` yet when the assertion runs. The `stderr` assertion at `:591` still catches a removed redirect, so this is a Nit.
- `tests/stdio_launcher.py:278-285`, R21: the subprocess test runs `ScanscribeMCPServer(...).run()`, not the production `main()` from `create_main_with_modes`. Anything the real entry point writes to stdout is not observed. The kit's main logs to stderr (`mcp_service_kit/server.py:478`).
- `tests/paddle_guard.py:180`, R24: the check runs only at session end in the parent process. A test that imports and then removes `paddle` passes, and subprocess sessions (the stdio launcher, pytester) are never checked.
- `docs/demos/2026-11-21-stdio-check/make_pdf.py:51`, task 4.4 (not ticked): `expected.txt` ends with `"\n"`, but `format_pages` output (`check.txt`) doesn't. The README's `diff` will always print "No newline at end of file", so the record can't say "identical".

### Promises checked and held
- **R1:** `ocr_service.py:177-190`; `test_start_needs_exactly_one_input`.
- **R2:** `config.py:379-382`, `ocr_service.py:229-240, 243, 330`; `test_local_paths_allowed`, `test_local_paths_turned_off_over_stdio`, `test_local_paths_never_over_http`, `test_output_path_refused_with_local_paths_off`.
- **R3:** `ocr_service.py:213-227`; `test_bad_options_are_refused`, `test_defaults_are_200_dpi_and_one_column`.
- **R4:** `:250-252` and `:392-393`; `test_folder_over_the_page_limit_is_refused`, `test_too_many_pdf_pages_fails_before_the_engine`.
- **R5 / D2:** one worker thread and a FIFO `queue.Queue` (`ocr_service.py:145-150`, `jobs.py:123-190`); `test_jobs_run_in_order`.
- **R6:** `jobs.py:126-131`, applied after `_refresh`; `test_twenty_first_job_refused`, `test_cancelled_jobs_do_not_count`, `test_expired_jobs_do_not_count`.
- **R7:** `jobs.py:262-271`, and `next_job` refreshes before it picks; `test_expiry_on_read`, `test_worker_skips_cancelled_and_expired`.
- **R8:** `results.py:29-56`; `test_running_job_reports_step_page_and_seconds`, `test_failed_job_reports_its_error`.
- **R9:** `get_ocr_job/tool.py:38-46`; `test_wait_returns_when_the_job_ends`, `test_wait_is_bounded`.
- **R10 / D4:** `:391`, `:397`, `:401`; `tests/test_cancel.py` (all five tests).
- **R11 / D3:** `:444-467`, with `_TrackedEngine` dropping the engine after a recognize error; `test_engine_loaded_once_per_language`, `test_language_change_releases_the_old_engine_first`, `test_engine_error_fails_the_job_and_drops_the_engine`.
- **R12:** `EngineMissingError` is a `ScanscribeError` subclass, so its message passes through `public_message`; `test_missing_engine_fails_the_job_not_the_server`.
- **R13:** `ocr_service.py:282-325`. Its blocks match `format_pages` (`scanscribe/output.py:18-20`). Covered by the five 3.5 slice and inline tests.
- **R14:** `:327-344`; the three `output_path` tests.
- **R21 / D10:** `:362`; `test_stdout_carries_only_mcp`, `test_the_check_catches_output_before_the_server_starts`.
- **R22:** every `logger` call in the diff logs only ids, kinds, sizes, counts, language, device and error class. fastmcp logs a `ToolError` without its message (`exc_info=False`, `server.py:1684-1687`), and its validation log omits inputs. The one leak is M2.
- **R24:** `tests/paddle_guard.py`; `test_paddle_guard.py`.
- **R26:** `:359-379`; `test_engine_error_fails_the_job_and_drops_the_engine`, `test_unexpected_error_text_is_hidden`.
- **R27:** `:419-442`, run before `open_source`; `test_huge_pdf_page_fails_before_anything_is_rendered`, which spies on `open_source`.
- **R28 (OCR pages):** `:475-499`, `jobs.py:234-242`; `test_a_hung_page_fails_the_job_and_refuses_new_ones`. The gaps are M1.
- **D1:** layout as specified; `jobs.py` and `ocr_service.py` don't import MCP. Every scanscribe name used is in `scanscribe.__all__`.
- **D5:** the worker follows D5's order, with `format_pages` run when the result is read (D6).
- **D11:** `public_message` and "OCR failed (<class>)".
- **Task 4.3:** every variable and tool is in the README and `docs/decision-log.md`.
