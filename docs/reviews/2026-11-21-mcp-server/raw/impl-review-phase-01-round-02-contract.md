I found no Blockers and no Majors. Every delivered requirement has code that enforces it and a test that would fail without it, except where a Nit below says otherwise. The fixes for I1 (R28: the watchdog now times page 1's render and the pre-check) and I2 (R22: unexpected tool exceptions now become class-only tool errors) are in place and tested. I ran nothing: this is a read-only review of 34a1a04..045e804.

## Promise map (enforcing code → test that would fail)

Paths are under /home/geo/develop/projects/scanscribe-mcp.

- **R1:** src/scanscribe_mcp/ocr_service.py:180-193 → tests/test_tools.py:91.
- **R2:** ocr_service.py:178-179, 235-246, 249, 336; features/get_ocr_result/tool.py:42-44; config.py:103-107 → test_tools.py:171, 178, 406, 480, 494 and test_config.py:71-93.
- **R3:** ocr_service.py:219-233 → test_tools.py:106, 119.
- **R4:**
  - Folder at start: ocr_service.py:255-258 → test_tools.py:130.
  - PDF after the pre-check: ocr_service.py:401-402 → test_worker.py:60 (checks the factory is never called).
- **R5:** jobs.py:119, 134, 171-190 and the single worker at ocr_service.py:146-147, 354-359 → test_jobs.py:210; test_tools.py:155 shows B stays queued while A runs.
- **R6:** jobs.py:125-131, with `_refresh` applied first → test_jobs.py:220, 229, 236; test_tools.py:155.
- **R7:** jobs.py:262-271 (expiry on read) and 184-187 (worker skips) → test_jobs.py:245, 257.
- **R8:** results.py:278-305; ocr_service.py:396-411, 461-463 → test_tools.py:230, 199, 257.
- **R9:** features/get_ocr_job/tool.py:22-46 → test_tools.py:199, 214.
- **R10 / D4:** jobs.py:143-159; ocr_service.py:400, 406, 410 → tests/test_cancel.py (all five) and test_tools.py:268.
- **R11 / D3:** ocr_service.py:453-476 → test_worker.py:40, 49 (weakref `alive_at_load`); a start-up load would break test_worker.py:67.
- **R12:** ocr_service.py:376-377 → test_worker.py:87, 143 (the real `load_engine`).
- **R13:** ocr_service.py:288-331; features/get_ocr_result/tool.py:56-95 → test_tools.py:319-459.
- **R14:** ocr_service.py:333-350, 547-557 → test_tools.py:380, 393.
- **R21 / D10:** ocr_service.py:368; the kit's stderr logging at mcp_service_kit/server.py:478 → test_stdio.py:214, 228.
- **R22 / D11:** ocr_service.py:207-216, 389, 506-514, 532-544; results.py:273-275 → test_messages_and_logs.py:27, 52; test_tools.py:462.
  - fastmcp logs a `ToolError` with `exc_info=False` and no message (fastmcp/server/server.py:1684-1688), so caller-facing messages stay out of logs.
- **R24:** tests/paddle_guard.py:180-190 → test_paddle_guard.py:118, 141.
- **R26:** ocr_service.py:365-381 → test_worker.py:105; test_messages_and_logs.py:68, 79.
- **R27 / D5:** ocr_service.py:397-398, 428-451, which run before `_open_source` → test_worker.py:70 (spy confirms `open_source` is never called and the factory is never called).
- **R28 / D2:**
  - Timing: ocr_service.py:396 (checking step), 404 (engine load not timed), 407 (page 1 render), 411 (each page).
  - Watchdog: ocr_service.py:484-517. Admission lock: ocr_service.py:203-206.
  - Tests: test_watchdog.py:21, 57, 96, 116, 148.
  - The universal "every page / the checking step" claim holds at every point in `_process`. Even pdfium's close after the last page is still timed under that page.
- **Universal claims checked:**
  - pdfium runs only on the worker thread: the R27 check and the `PdfSource`.
  - Every local-path entry point calls `check_local_paths`.
  - Every queue count runs after `_refresh`.
  - Every finish goes through a guarded `table.finish`.
  - No `logger` call takes a name, a message or any text.

## Findings (all Nit)

1. **D3 (src/scanscribe_mcp/ocr_service.py:413-418, 470-476): after an engine error, the old engine may not be freed before the next load.**
   - `_drop_engine` runs `gc.collect()` while the exception's traceback still references `_TrackedEngine` and the engine.
   - The next job's `_engine_for` calls `_drop_engine`, which returns early because `_engine is None`, so nothing collects before the new load.
   - A real engine held in reference cycles would keep its GPU memory through the reload.
   - test_worker.py:105 checks only that the factory is called twice, not `alive_at_load == [[], [False]]`.

2. **R10 (ocr_service.py:406): the "after the engine loads" check isn't observable.**
   - If line 406 were deleted, test_cancel.py:210 would still pass, because `on_page(1)` raises before page 1 is recognized (`engine.seen == []`). The only difference would be that page 1 gets rendered.
   - A test would need to assert that page 1 is never rendered, or that the step never reaches `recognizing`.

3. **R22 (tests/test_messages_and_logs.py:27): the task 2.4 log capture bypasses the MCP layer.**
   - It drives `OcrService` directly, so the log lines fastmcp and the kit write during the failing job's tool calls are never captured.
   - For example, `get_ocr_result` on a failed job raises a `ToolError` that carries `job.error`.
   - That is safe today only because of fastmcp's `exc_info=False` logging, which no test pins down. A `fastmcp.Client` variant at DEBUG level would observe it.

4. **R24 (tests/paddle_guard.py:180): the guard can't fully observe "ever imported".**
   - It reads `sys.modules` once, at session end. A module imported and then removed, for example by `monkeypatch.setitem` cleanup, passes unnoticed.
   - A `sys.meta_path` blocker would catch every import. This is a different point from the accepted I16.

5. **R24 / AGENTS (tests/test_worker.py:143): the real-`load_engine` test misbehaves when the `gpu` extra is installed.**
   - Task 4.4 has the owner run `uv sync --extra gpu`. `uv run pytest` does not remove extras, so the test would then import paddle and load the real engine.
   - The job would succeed, so the assertion fails, and the guard fires too.
   - The documented `uv sync --locked` resets to the base install, which is why this is a Nit. A skip when `find_spec("paddle")` finds paddle would remove the trap.

6. **R28 (src/scanscribe_mcp/service.py:209-214): over HTTP the process doesn't exit when the watchdog fires.**
   - `on_stuck` isn't wired, so a phase 01 server started with `--mode http --no-auth` stays up refusing jobs instead of exiting.
   - Phase 02 task 4.5 covers this, so it is a Nit.

7. **R2 (ocr_service.py:239-243): the HTTP refusal for `output_path` gives the wrong advice.**
   - It says "the server can't read your files … pass the upload_id". That fits `input_path`, not a result destination.
   - It also names `create_upload_link`, which phase 01 doesn't offer. It satisfies R2's wording ("names upload links").

8. **R8 (src/scanscribe_mcp/results.py:294): `page_seconds` is missing for parts the watchdog times.**
   - It is reported only once `job.page` is set. The checking step and page 1's render are timed by the watchdog but show no seconds.
   - An agent can't see how close those parts are to the timeout.

9. **D1 (ocr_service.py:33 → config.py:12): `ocr_service.py` imports MCP transitively.**
   - D1 says it "never imports MCP". Its config import pulls in `mcp_service_kit`, which imports `fastmcp` (mcp_service_kit/server.py:16-18).
   - docs/ARCHITECTURE.md:20 says config.py doesn't import MCP, which is wrong.

10. **R28 / D2 docs (docs/ARCHITECTURE.md, "The watchdog" section): the description is stale after I1.**
    - It still says the watchdog checks "the running job's current page" only. It doesn't mention the checking step or page 1's render.

11. **D5 (ocr_service.py:414): `format_pages` is never called in the worker.**
    - D5 lists it as the worker's last step. The worker stores the pages and `format_pages` runs at result time in the event loop.
    - The result is the same; the stated order isn't followed.

12. **R1 / R2 (ocr_service.py:250-252): an empty `input_path` OCRs the server's working directory.**
    - `input_path=""` counts as the one input. `Path("").resolve()` gives the server's cwd, and that folder is queued as a job.

13. **R1 (tests/test_tools.py:91): "no job is created" is never asserted.**
    - The code raises before `submit`, but no test checks the table's counts after the error.

14. **R5 / R7 (tests/test_jobs.py): parts are tested only at `JobTable` level.**
    - R7's expiry through `get_ocr_job` and R5's "B starts next" in the running service are covered only by table tests.
    - `ScanscribeMCPService` can't take a clock, so the tool tests can't observe expiry.

15. **Previously accepted mismatches, still present.** You decide again:
    - I3 (R26): `except Exception` lets `SystemExit` / `KeyboardInterrupt` end the worker. Their traceback goes to stderr through `threading.excepthook`, which would also break R22.
    - I5, I6, I7, I10 (`~/out.txt` accepted at ocr_service.py:337), I11, I15.
