# Reviews · A working scanscribe MCP server

## 2026-11-21 · design-review · plan · round 1 · changes-requested
Commit: 95199061c16933d3b5fab00e355ada8a489365d9
Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅ · structure ✅
Raw reports: docs/reviews/2026-11-21-mcp-server/raw/design-review-01-{fresh-reader,codebase-fit,zoom-out}.md

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | fresh reader | Summary cites R15/R16 for zip bombs (R17) and D7/D8 for the store (D6), and omits the log/path leak risk | fixed: Summary |
| F2 | Major | codebase fit, fresh reader | scanscribe v0.2.0 API (names in `__all__`, `on_page` stop, `len(source)`, pre-check, install message) has no evidence in notes and no definition in Terms | fixed: Terms (scanscribe API, pre-check), notes.md#scanscribe-api |
| F3 | Major | codebase fit | notes.md#d7 name rule would accept `../x.png`, contradicting R17 and task 02/4.2 | fixed: R17, notes.md#d7 |
| F4 | Major | codebase fit | HTTP access logs would record upload tokens and `<input name>.txt` names (R22); no phase 02 log check | fixed: D6 (`ocr-<job id>.txt`), D8 (access log off), R22, phase 02 task 1.2 |
| F5 | Major | codebase fit | Task 01/4.2 Verify can't fail: a print while serving goes to stderr | fixed: phase 01 task 4.2, notes.md#d10 |
| F6 | Major | codebase fit, zoom out | No mechanism for the subprocess test's fake engine factory; an env import hook would load code in production | fixed: D3, phase 01 task 4.2 (`tests/stdio_launcher.py`) |
| F7 | Major | codebase fit | R2's refusal is never tested | fixed: phase 01 tasks 3.2, 3.5 |
| F8 | Major | codebase fit, zoom out | Cancelled or expired jobs still in `queue.Queue` count toward R6 | fixed: R6, R7, D2, phase 01 task 2.1 |
| F9 | Major | codebase fit, zoom out | Task 03/3.2 can't run tests in a `--no-dev` image; no command given | fixed: phase 03 task 3.2 |
| F10 | Major | zoom out | An unexpected error kills the worker thread; jobs then wait silently until expiry | fixed: R26, D2, D3, phase 01 task 2.2 |
| F11 | Major | zoom out | A hung page blocks the worker forever; engine load and pre-check can't be cancelled; not in Risks | fixed: R8, R10, D4, Risks, phase 01 tasks 2.2, 2.3 |
| F12 | Major | zoom out | The dpi cap doesn't bound memory for a huge PDF page | fixed: R27, D5, D9 (memory limit), notes.md#r27, Risks |
| F13 | Major | zoom out | Job folders left by a crash are never deleted | fixed: D7, phase 02 task 4.1 |
| F14 | Major | zoom out | When the job folder is built, how long an upload_id's files stay usable, and partial uploads are unstated; purge may delete an in-use PDF | fixed: D7, notes.md#d7, R20, phase 02 tasks 2.1, 3.1, 4.1 |
| F15 | Major | zoom out | Docker: OUTPUT_DIR/WORK_DIR/PUBLIC_BASE_URL not set to the `/data` volume | fixed: R25, D9, notes.md#d9, phase 03 tasks 1.1, 1.2, 3.1 |
| F16 | Major | fresh reader, zoom out | `checking pages` is used like a state but isn't one | fixed: Terms (Step), R8 |
| F17 | Major | fresh reader | The `document` input is unclear: which stored documents can be OCR'd | fixed: Terms (Document), phase 02 task 4.3 |
| F18 | Major | fresh reader | `create_upload_link` and `check_upload` are not described | fixed: What changes |
| F19 | Major | fresh reader | The setting that allows local paths isn't named | fixed: Terms (Local paths), R2 |
| F20 | Major | fresh reader | Whether stdio results go to the store from phase 02, and how stdio gets a large result, is unclear | fixed: D6, R20, phase 02 task 2.2 |
| F21 | Major | fresh reader | Phases table doesn't show which requirements each phase delivers | fixed: Phases table titles list the requirements |
| F22 | Major | fresh reader | D10's reasoning depends on notes.md | fixed: D10 |
| F23 | Major | fresh reader | R22 vs R23: whether job errors are logged is unstated | fixed: R22 |
| F24 | Major | fresh reader | Two PDFs or two zips in one upload aren't covered by D7 | fixed: D7, notes.md#d7, phase 02 task 4.1 |
| F25 | Nit | structure | plan.md 353 body lines, budget 250 | accepted: 25+ one-rule requirements; evidence already in notes.md |
| F26 | Nit | fresh reader | Several requirements hold more than one rule (R3, R8, R10, R13, R15–R17, R19, R20, R22, R25) | accepted: each covers one behavior of one tool; splitting adds ~40 lines |
| F27 | Nit | fresh reader | R3 columns, R19 refusal to start and R20 retention have no scenario | fixed: R3, R19, R20 scenarios |
| F28 | Nit | fresh reader | Summary omits the reload on language change, the inline limit and memory-then-store | fixed: Summary |
| F29 | Nit | fresh reader | Terms lack the kit, pdfium, PaddleX, fastmcp, `on_page`/`on_device` | fixed: Terms |
| F30 | Nit | fresh reader | R4 has two possible outcomes in one scenario | fixed: R4 |
| F31 | Nit | fresh reader, codebase fit | R15 `max_files` default and whether 200 is a hard cap; R16 "one upload" ambiguous | fixed: R15, R16, notes.md#configuration |
| F32 | Nit | fresh reader | D7's heading conflicts with its body | fixed: D7 heading |
| F33 | Nit | fresh reader | R17 scenario and the last Risks bullet run over 40 words | fixed: R17 split into scenarios, Risks |
| F34 | Nit | fresh reader | Decision log is empty | contested: the decision log is for changes after approval |
| F35 | Nit | fresh reader | Open questions doesn't mark which content came from the owner | accepted: the answers are listed by ID in Open questions |
| F36 | Nit | codebase fit | Task 01/4.1: the paddle-import check needs a stub in `sys.modules` to be shown failing | fixed: phase 01 task 4.1 |
| F37 | Nit | codebase fit | Task 03/1.1 Verify uses the system Python unless `.venv/bin` is on PATH | fixed: phase 03 task 1.1, notes.md#d9 |
| F38 | Nit | codebase fit | The stdout guarantee depends on fastmcp's version; no minimum is set | fixed: phase 01 task 1.1, notes.md#d10 |
| F39 | Nit | codebase fit, zoom out | Purge runs only during jobs, so an idle server never purges | fixed: D6, phase 02 task 2.2 |
| F40 | Nit | codebase fit | PUBLIC_BASE_URL default 8302 doesn't match the kit's default port outside Docker | fixed: notes.md#configuration |
| F41 | Nit | codebase fit | Task 02/4.4 Verify should name resolved paths and say whether the job id may appear | fixed: R23, phase 02 task 4.4 |
| F42 | Nit | codebase fit | D5's start-time page count arrives only in phase 02 | fixed: D5, phase 01 task 3.2 |
| F43 | Nit | codebase fit | No task updates the AGENTS.md Status line or the decision log for the new interface | fixed: phase 03 task 2.3 |
| F44 | Nit | codebase fit | The CI `licenses` allow-list may refuse PaddlePaddle's transitive licences | fixed: phase 01 task 1.1 |
| F45 | Nit | zoom out | Drop the old engine before loading a new language's | fixed: D3, phase 01 task 2.2 |
| F46 | Nit | zoom out | Rollback doesn't mention the named volumes or leftover data folders | fixed: Rollout & rollback |

Fixes applied 2026-11-21: every Major fixed; F25, F26, F35 accepted, F34 contested. Status: passed (review profile `small`: no Major is open, so no further round is required).

## 2026-11-21 · design-review · plan · round 2 · changes-requested
Commit: 706ae73 (plan under review)
Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅ (not independent: it read the two committed round-2 reports; its M1 comes from them, and its M2–M3 repeat codebase-fit findings)
Raw reports: docs/reviews/2026-11-21-mcp-server/raw/design-review-02-{fresh-reader,codebase-fit,zoom-out}.md

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| G1 | Major | codebase fit, zoom out | `ALLOW_LOCAL_PATHS=true` would let the HTTP server take client paths, against AGENTS.md | fixed: Terms (Local paths), R2, notes.md#configuration, tasks 01/1.2, 02/1.1 |
| G2 | Major | fresh reader, codebase fit, zoom out | Worker order unstated; the engine may load (and download models) for inputs that are then refused; conflicts with R4 and task 01/2.2 | fixed: D5, Terms (Step), R4, R10, D4, tasks 01/2.2, 01/2.3 |
| G3 | Major | codebase fit, zoom out | Relative `data/` defaults over stdio create folders in the user's project; emptying `WORK_DIR` at start-up and purge can hit other processes' files | fixed: D6, D12, Terms, R20, notes.md#d7, tasks 02/2.2, 02/4.1 |
| G4 | Major | fresh reader, codebase fit | Two uploaded images with the same name collide in the job folder | fixed: R29, D7, notes.md#d7, task 02/4.1 |
| G5 | Major | codebase fit | Task 03/3.2: the image has no `.github/` or `README.md`, so the suite can't pass | fixed: tasks 03/1.1, 03/3.2, notes.md#d9 |
| G6 | Major | zoom out | A hung page leaves the process alive, so `restart: unless-stopped` never recovers it | fixed: R28, D2, D9, Risks, tasks 01/2.5, 02/4.5, 03/1.2 |
| F14 | Major | zoom out | Reopened: a file still uploading at `start_ocr_job` is silently left out; a second start on a closed `upload_id` is undefined | fixed: R29, D7, notes.md#d7, tasks 02/3.2, 02/4.1 |
| G7 | Major | fresh reader | With local paths off over stdio, the R2 error points to upload links, which stdio doesn't have | fixed: R2, task 01/3.2 |
| G8 | Major | fresh reader, zoom out | R13: a page range longer than the inline limit is undefined | fixed: R13, task 01/3.5 |
| G9 | Major | fresh reader, codebase fit | The path-swapping mechanism sits only in Risks; R26 in phase 01 needs path-free messages but nothing checks it there | fixed: D11, task 01/2.4 |
| G10 | Major | fresh reader, zoom out | Whether a job past its queue timeout counts toward R6 is unstated | fixed: R6 |
| G11 | Major | fresh reader | Summary ties the store to HTTP and leaves out the hung-page risk | fixed: Summary |
| G12 | Major | zoom out | Frontmatter said `passed` while round 2 had open Majors | accepted: round 2 is logged and the status reset |
| G13 | Nit | codebase fit | notes.md#r27 says pypdfium2 is already in the lock; true only after task 01/1.1 | fixed: notes.md#r27 |
| G14 | Nit | codebase fit | The config table doesn't mark phases; no phase 02 task adds the phase 02 variables | fixed: notes.md#configuration (Phase column), task 02/1.1 |
| G15 | Nit | codebase fit | Default `dpi` and `columns` are not given | fixed: R3, notes.md#configuration |
| G16 | Nit | codebase fit | R15's used-up link has no HTTP test | fixed: R15, task 02/3.2 |
| G17 | Nit | codebase fit | Interface changes reach the decision log only in phase 03 | fixed: tasks 01/4.3, 02/5.1, 03/2.3 |
| G18 | Nit | codebase fit | `.DS_Store`/`Thumbs.db` in a browser upload refuse the job; `.dockerignore` lacks `.venv`, `.env.*` | fixed: D7, notes.md#d7, notes.md#d9, task 03/1.2 |
| G19 | Nit | zoom out | Rollback's `down -v` deletes results and models | fixed: Rollout & rollback |
| G20 | Nit | zoom out | Alternating languages reload every job; dropping the reference may not free GPU memory | fixed: D3 (accepted cost), Risks, task 03/3.1 |
| G21 | Nit | zoom out | `ENGINE=cpu` build argument serves no stated need | fixed: D9 |
| G22 | Nit | zoom out | Whether an upload running at link expiry may finish is unstated | fixed: R15, task 02/3.2 |
| G23 | Nit | fresh reader | `safe_filename` undefined | fixed: Terms |
| G24 | Nit | fresh reader | R14: relative path, missing parent, existing file not covered | fixed: R14, task 01/3.5 |
| G25 | Nit | fresh reader | Whether a rejected start closes the link is unstated | fixed: D7, notes.md#d7 |
| G26 | Nit | fresh reader | Whether R26's page-2 `RuntimeError` counts as an engine error is unclear | fixed: D3 (any error while recognizing) |

Fixes applied 2026-11-21: every Major fixed or accepted (G12). Status: passed. The design-review skill stops after round 2; nothing is open. Structure warnings: plan.md 442 body lines and phase 01 108 lines over budget, accepted as in F25.

## 2026-11-21 · approved · plan and phases 01–03
Approved by the owner after design review round 2 passed.

## 2026-11-21 · design-review · plan · round 3 · changes-requested
Commit: c3643fd. Scope: the D10 / R28 / D2 update made during phase 01's apply. Lenses: codebase fit only (owner's choice).
Reviewers: codebase fit ✅ (raw: docs/reviews/2026-11-21-mcp-server/raw/design-review-03-codebase-fit.md)

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| H1 | Major | codebase fit | No phase 01 task adds D10's per-job `redirect_stdout`; task 2.2 is ticked without it | fixed: task 01/4.2 |
| H2 | Nit | codebase fit | Task 2.5 and 3.5 Verify lines don't cover queued jobs failing, `output_path` with a range, or a page over the inline limit; no tests for the last two | fixed: tasks 01/2.5, 01/3.5 (3.5 unticked until its tests pass) |
| H3 | Nit | codebase fit | Phases table shows phase 01 as 0/16 | fixed: Phases table |
| H4 | Nit | codebase fit | Phase 01 branch `docs/plan-mcp-server` doesn't follow `<type>/<issue>-<slug>` | accepted: owner's choice at `start` |
| H5 | Nit | codebase fit | notes.md#d10 credits fastmcp with the fd-1 diversion; it is in `mcp` (2.3.0) | fixed: notes.md#d10 |

Fixes applied 2026-11-21 (owner's choice): H1 fixed, H4 accepted, the other Nits fixed. Every reviewer completed and no Major is open. Status: passed.

## 2026-11-21 · approved · plan and phases 01–03 (after round 3)
Re-approved by the owner after the D10 / R28 update passed design review round 3.

## 2026-11-21 · impl-review · phase 01 · round 1 · changes-requested
Diff: 34a1a04..d79c2fc (frozen). Profile `small`: contract lens only.
Reviewers: contract ✅ (raw: docs/reviews/2026-11-21-mcp-server/raw/impl-review-phase-01-round-01-contract.md)

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| I1 | Major | contract | R28: no watchdog while page 1 renders or during the pre-check; a hang there never fails the job | fixed: test_a_hung_first_render_trips_the_watchdog, test_a_hung_pre_check_trips_the_watchdog (tests/test_watchdog.py); ocr_service.py; R28, D2 updated |
| I2 | Major | contract | R22: a symlink-loop `input_path` raises RuntimeError past `tool_errors()`; fastmcp logs the path in a traceback | fixed: test_unexpected_tool_error_hides_the_path_from_logs_and_client (tests/test_tools.py); results.py tool_errors |
| I3 | Nit | contract | R26: catch-all is `except Exception`; SystemExit/KeyboardInterrupt in the engine ends the worker | accepted: Paddle doesn't raise SystemExit or KeyboardInterrupt in a worker thread |
| I4 | Nit | contract | R28: race between the stuck check in `start_job` and the watchdog's `fail_queued` | fixed: test_a_start_racing_the_watchdog_never_leaves_a_job_queued (tests/test_watchdog.py); admission lock in ocr_service.py |
| I5 | Nit | contract | D11: only the input path is rewritten; other server paths in scanscribe errors pass through (phase 02 R23) | accepted: phase 02's R23 covers other server paths |
| I6 | Nit | contract | R27: size check only when `is_file()`; a FIFO/device is read as PDF unchecked | accepted: a FIFO or device as input_path is the local caller's own choice over stdio |
| I7 | Nit | contract | R27/D5: size loop walks every page before the R4 count check | accepted: R4 and D5 put the page count after the pre-check |
| I8 | Nit | contract | R2: some errors (bad lang, two inputs, output_path with a range) come before the local-path error | fixed: test_local_path_errors_come_first (tests/test_tools.py); local-path checks first |
| I9 | Nit | contract | R2: `output_path` over HTTP not tested | fixed: test_output_path_never_over_http (tests/test_tools.py) |
| I10 | Nit | contract | R14: `~/out.txt` accepted via expanduser though the path "must be absolute" | accepted: `~` is the caller's own home over stdio; README asks for absolute paths |
| I11 | Nit | contract | D6: `write_replacing` leaves a transient temp file next to `output_path` | accepted: the temp file exists only during the write and is removed on failure |
| I12 | Nit | contract | R10: cancel during the last page ends `succeeded` although the reply said it would stop | fixed: test_cancel_reply_promises_only_the_next_page (tests/test_tools.py); cancel_ocr_job reply |
| I13 | Nit | contract | R12: test uses a hand-written EngineMissingError, not `scanscribe.load_engine` | fixed: test_real_load_engine_without_paddle_fails_the_job (tests/test_worker.py) |
| I14 | Nit | contract | R21: stdio test doesn't join the stdout reader before asserting | fixed: StdioSession.close joins the pipe readers (tests/test_stdio.py) |
| I15 | Nit | contract | R21: launcher runs `server.run()`, not the production `main()` | accepted: the kit's main only adds argument parsing and stderr logging around the same run() |
| I16 | Nit | contract | R24: guard checks only the parent session at its end | accepted: subprocess sessions run the fake engine only; the parent guard covers the suite |
| I17 | Nit | contract | 4.4: `expected.txt` ends with a newline, `check.txt` doesn't; `diff` never reads identical | fixed: make_pdf.py writes expected.txt without a final newline |

Fixes applied 2026-11-21 (owner's choice): both Majors fixed test first; Nits fixed or accepted. Round 2 (contract lens) re-checks I1, I2 and the changed R28.

## 2026-11-21 · impl-review · phase 01 · round 2 · passed
Diff: 34a1a04..045e804 (frozen). Profile `small`: contract lens only; also the one-lens re-check of the changed R28.
Reviewers: contract ✅ (raw: docs/reviews/2026-11-21-mcp-server/raw/impl-review-phase-01-round-02-contract.md). I1 and I2 confirmed fixed; I3, I5-I7, I10, I11, I15 stay accepted.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| J1 | Nit | contract | D3: after an engine error, `gc.collect()` runs while the traceback still holds the engine; the next load may not free it | fixed: gc.collect() before every engine load (ocr_service.py); alive_at_load asserted in test_engine_error_fails_the_job_and_drops_the_engine, which the fake engine (no cycles) can't pin |
| J2 | Nit | contract | R10: the "after the engine loads" cancel check isn't observable by the tests | accepted: cancel before page 1 is covered; the extra check only saves rendering page 1 |
| J3 | Nit | contract | R22: the task 2.4 log capture bypasses the MCP layer | accepted: fastmcp logs ToolErrors without their message; test_unexpected_tool_error_hides_the_path_from_logs_and_client covers the tool layer |
| J4 | Nit | contract | R24: the guard reads `sys.modules` once at session end; an import later removed passes | accepted: no test removes engine modules; a meta_path blocker can come later if needed |
| J5 | Nit | contract | R24: the real `load_engine` test fails (and trips the guard) after `uv sync --extra gpu` | fixed: test_real_load_engine_without_paddle_fails_the_job skips when paddle is installed |
| J6 | Nit | contract | R28: over HTTP the process doesn't exit when stuck (phase 02 task 4.5) | accepted: phase 02 task 4.5 wires on_stuck to exit over HTTP |
| J7 | Nit | contract | R2: the HTTP refusal for `output_path` gives `input_path` advice | fixed: separate output_path message over HTTP; test_output_path_never_over_http |
| J8 | Nit | contract | R8: no seconds shown for the checking step or page 1's render | accepted: page_seconds stays per page, as R8 says |
| J9 | Nit | contract | D1: `ocr_service.py` imports MCP through `config.py` → the kit; ARCHITECTURE.md says config.py doesn't | fixed: plan.md D1 wording, docs/ARCHITECTURE.md module table, ocr_service.py docstring |
| J10 | Nit | contract | ARCHITECTURE.md's watchdog section is stale after I1 | fixed: docs/ARCHITECTURE.md watchdog section |
| J11 | Nit | contract | D5: `format_pages` runs at result time, not in the worker | accepted: D6 keeps pages on the job; formatting at result time gives the same text |
| J12 | Nit | contract | R1: `input_path=""` OCRs the server's working directory | fixed: empty input_path refused; test_empty_input_path_is_refused_and_creates_no_job |
| J13 | Nit | contract | R1: "no job is created" is never asserted | fixed: same test asserts the table holds no job |
| J14 | Nit | contract | R5/R7: parts tested only at `JobTable` level | accepted: the tool tests cover queue order and full queue; expiry needs an injected clock in the service, not worth it now |

Fixes applied 2026-11-21 (owner's choice): J1, J5, J7, J9, J10, J12, J13 fixed; the rest accepted. The review stays passed; nothing is open.

## 2026-11-21 · note · phase 01 · manual check finding
Task 4.4 showed that Claude Code gives the model only a tool's `structuredContent`, so `get_ocr_result`'s inline text never reached the agent (R13). Fixed test first: every reply carries its summary as `message`, and `get_ocr_result` its text as `text`, in structured content (test_small_result_inline, test_large_result_not_inline, test_page_slice_with_markers). Owner's choice; the manual check reruns the inline call.

## 2026-11-21 · impl-review · phase 02 · round 1 · changes-requested
Diff base: 872ec10 · reviewed commit: 925f427 · profile `small` (contract lens only)
Reviewers: contract ✅ (a first attempt on e48c71e stopped at the usage limit with no report; a fresh reviewer ran on 925f427)
Raw report: `docs/reviews/2026-11-21-mcp-server/raw/impl-review-phase-02-round-01-contract.md` (re-typed: `save-report` refused twice, because the reviewer handed its report back as a message, not as its final result)

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| M1 | Major | contract | A body cut off before its closing boundary is stored as a whole file: python-multipart's `finalize()` is a no-op (R15, R29, task 3.2) | fixed: `on_end` and per-part `ended` in `UploadReceiver` (uploads.py); test_upload_routes.py::test_a_body_cut_before_its_closing_boundary_stores_nothing |
| M2 | Major | contract | An upload whose part headers haven't arrived isn't counted as in progress, so a job can start and close the link, and the late file is stored on the closed link outside the job (R29, D7) | fixed: the route counts each request (`Grant.requests`) from entry and `start_ocr_job` refuses while one is open; parts and the commit refuse a closed link (uploads.py, service.py, ocr_service.py); test_upload_jobs.py::test_a_start_during_a_real_upload_is_refused_and_the_upload_lands, ::test_no_file_is_stored_on_a_link_closed_mid_request |
| M3 | Major | contract | Part header bytes count against no limit; a chunked request skips the declared-length check (R16) | fixed: part headers and other fields share the 64 KiB `FIELD_LIMIT` per request (uploads.py). One huge header was already refused by python-multipart (8 lines of 4,224 bytes per part); the unbounded case was endless empty field parts; test_upload_routes.py::test_header_and_part_counts_are_limited |
| M4 | Major | contract | The log line "result stored as document <id>" plus the job id rebuilds the token-free download URL (D8, R22) | fixed: the log line names the job and size, not the document id (ocr_service.py); test_http_logs.py forbids the id |
| M5 | Major | contract | Over HTTP the `output_path` error doesn't name upload links, as R2's Then says | fixed: the message names the download URL and upload links (ocr_service.py); test_http_auth.py::test_local_paths_refused_over_http_even_when_allowed |
| N1 | Nit | contract | `safe_filename`'s 120-character cut can drop the extension, so a long-named page is skipped silently | fixed: `safe_filename` cuts before the suffix (documents.py); test_documents.py::test_a_long_name_keeps_its_extension |
| N2 | Nit | contract | Zip entries are written under raw base names, not through `safe_filename` (D8) | fixed: `page_name` puts zip entries through `safe_filename`, duplicates checked after (uploads.py); test_zips.py::test_zip_entries_get_plain_names, ::test_names_equal_after_cleaning_are_duplicates |
| N3 | Nit | contract | If `store.begin` raises after `links.begin`, `in_progress` is never given back and the OSError reaches uvicorn | fixed: the document is made before the link counts the part; the route answers 500 and logs the class only (uploads.py, service.py); test_upload_routes.py::test_a_store_error_gives_back_the_upload_and_hides_its_text |
| N4 | Nit | contract | `count_zip_pages` ignores `max_pages` and counts non-image entries, so the start-time message can mislead | fixed: `count_zip_pages` applies every `zip_pages` rule but the page limit (uploads.py); test_zips.py::test_a_non_image_entry_is_named_at_start |
| N5 | Nit | contract | A document at the retention age can be purged between `store.get` and `submit`; the job then fails at run time | accepted: a tiny window, only for a document at the retention age; the job then fails cleanly at run time |
| N6 | Nit | contract | Zip extraction runs inside the timed `checking pages` step; a slow 2 GB unpack could trip the watchdog | accepted: R28 times the `checking pages` step, which includes the unpack; 600 s is ample for 2 GB |
| N7 | Nit | contract | `scrub` replaces the relative "data/work" anywhere in an error, including the caller's own names | fixed: `scrub` uses absolute spellings only (ocr_service.py); test_http_messages.py::test_scrub_leaves_the_callers_own_names_alone |
| N8 | Nit | contract | The declared-length 413 is tested only with `max_files=1`, not at R16's defaults | fixed: test only, the behaviour was right; test_upload_routes.py::test_a_250_mb_file_answers_413_at_the_default_limits |
| N9 | Nit | contract | ARCHITECTURE.md says the start and the upload route "never interleave"; untrue at await points | fixed: docs/ARCHITECTURE.md now says the two interleave and how the route guards it |

Fixes in 9f9df6c, owner-approved (all Majors; N1-N4, N7-N9; N5 and N6 accepted). Each test failed before its fix and fails again when the fix is reverted.

## 2026-11-21 · impl-review · phase 02 · round 2 · changes-requested
Diff base: 872ec10 · reviewed commit: beb0ef1 · profile `small` (contract lens), owner-requested after round 1's Majors were fixed
Reviewers: contract ✅
Raw report: `docs/reviews/2026-11-21-mcp-server/raw/impl-review-phase-02-round-02-contract.md` (saved by `save-report`). Correction to round 1's note: a hand-back report saves fine, so round 1's refusals were most likely the coordinator's snippets, not the hand-back.
No round 1 finding came back.

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | contract | An upload named `meta.json` (or `../meta.json`) collides with the store's metadata file; `get()` then finds no file and every start on that link is refused as "no longer stored" (D7, R29) | fixed: `DocumentStore.begin` stores an upload named `meta.json` as `meta_.json` (documents.py); test_upload_jobs.py::test_an_upload_named_like_the_metadata_file_is_kept_apart |
| N10 | Nit | contract | R17's test accepts a refusal at start or a failure at run time; neither is pinned, and the link staying open after a zip refusal isn't checked | fixed: test pins the refusal at start with the link left open, and the run-time failure for the understated size; the worker re-checks every hostile zip (test_zips.py) |
| N11 | Nit | contract | Defaults are 200 MiB and 2 GiB where the plan says 200 MB and 2 GB | accepted: the README gives the limits in MiB and GiB; only the plan says "MB" loosely |
| N12 | Nit | contract | The purge test sees the hourly purge only while a job runs; "while idle" is never observed | fixed: test_results_store.py::test_the_timer_purges_while_no_job_runs |
| N13 | Nit | contract | The copy fallback when `os.link` fails is never exercised | fixed: test_upload_jobs.py::test_images_are_copied_when_they_cant_be_linked |
| N14 | Nit | contract | Natural order inside a zip (with `p10`) is tested only in the curl test, which is skipped without curl | fixed: test_upload_jobs.py::test_a_zip_is_unpacked now has p10 |
| N15 | Nit | contract | `document=` doesn't honour the `hidden` flag that `upload_id` skips | fixed: `document=` refuses a hidden upload (ocr_service.py); test_upload_jobs.py::test_a_hidden_upload_is_no_input_by_id_either |
| N16 | Nit | contract | A `document=` start can race the purge thread's keep set for a document already past retention; the job then fails cleanly | accepted: the same tiny window as round 1 N5, and the job fails cleanly |
| N17 | Nit | contract | If `commit` fails on the second file of a request, the first stays stored while the route answers 500 | fixed: `_commit` removes the request's stored files if one fails (uploads.py); test_upload_routes.py::test_a_failed_store_keeps_none_of_the_requests_files |
| N18 | Nit | contract | The browser form sends one request per file, so a start between two files takes a partial snapshot and closes the link | fixed: the form sends every chosen file in one request (upload_page.html); test_http_curl.py pins it |
| N19 | Nit | contract | Unpacking a zip is timed as part of `checking pages` (same as round 1's N6) | accepted: round 1, N6 |
| N20 | Nit | contract | `public_message` may miss a job-folder path spelled through a symlinked working folder; `scrub` still hides it | accepted: no server path leaks either way; `scrub` still hides it |
| N21 | Nit | contract | The in-progress refusal test doesn't assert the link is still open right after the refusal | fixed: test_upload_jobs.py asserts the link is open after the refusal |

Fixes in 932fb34, owner-approved (F1; N10, N12-N15, N17, N18, N21; N11, N16, N20 accepted). Each code fix's test fails when the fix is reverted; N10, N12-N14 and N21 added coverage for behaviour that was already right. Review rounds stop here, as the impl-review skill says.

## 2026-11-21 · done · phase 02
Gate passed: 15/15 tasks, impl review passed (round 2). Checks from a clean clone of 4e7c493: ruff, format, mypy, 262 tests, agent sync, gitleaks. No manual-check record: task 5.3 became an automated curl test (owner's decision, plan Decision log).

## 2026-11-22 · impl-review · phase 03 · round 1 · changes-requested
Diff base: 8831461 · reviewed commit: 94c9b6f · profile `small` (contract lens)
Reviewers: contract ✅
Raw report: `docs/reviews/2026-11-21-mcp-server/raw/impl-review-phase-03-round-01-contract.md` (saved by `save-report`)

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| M1 | Major | contract | With `SCANSCRIBE_MCP_HOST_PORT` set and `PUBLIC_BASE_URL` unset, upload links and download URLs still point at port 8302 (R25, D9) | fixed: the default URL is `http://localhost:${SCANSCRIBE_MCP_HOST_PORT:-8302}` (docker-compose.yml); test_docker_files.py::test_links_follow_the_host_port; a live job through port 9000 in the record |
| N1 | Nit | contract | Compose doesn't pin the device, so a container that loses the GPU falls back to the CPU silently (R25) | fixed: compose sets `SCANSCRIBE_MCP_DEVICE` to `gpu:0` unless set; test_docker_files.py::test_the_device_is_the_gpu_unless_set |
| N2 | Nit | contract | Only three `SCANSCRIBE_MCP_*` variables reach the container; others in `.env` are ignored silently, and the docs don't say so | fixed: compose passes eight more settings when set, and the README and `.env.example` say which reach the container; test_docker_files.py::test_documented_settings_reach_the_container |
| N3 | Nit | contract | The healthcheck treats any HTTP error, a 5xx included, as healthy | fixed: the healthcheck passes only on the 404 page; test_docker_files.py::test_the_healthcheck_wants_the_expected_404 runs its script against 404, 500 and 200 |
| N4 | Nit | contract | plan.md's Phases table still shows phase 03 as approved, 0/8 | fixed: Phases table updated |
| N5 | Nit | contract | The record's test-suite command differs from task 3.2's (docs mount, `:z`, `-rs`, the `:dev` tag); disclosed | accepted: the differences are disclosed in the record and justified (docs mount for test_docs.py, `:z` for SELinux, `-rs`, an image built from the same commit) |
| N6 | Nit | contract | The record lacks evidence for tasks 1.1 and 1.2's verifies, the token read from a real `.env`, and a restart in the container | fixed: the record now shows tasks 1.1 and 1.2 checks, a real `.env` file, host port 9000, the build context, and a restart in the container (SIGTERM; a real exit 70 needs a hung page) |
| N7 | Nit | contract | No automated test pins the Dockerfile and compose invariants (volume paths, cache location) | fixed: test_docker_files.py::test_data_and_models_live_on_the_volumes |
| N8 | Nit | contract | `.dockerignore` ignores only top-level `in/`, `out/`, `data/`; stray PDFs elsewhere reach the build context | fixed: `.dockerignore` is an allow-list of the four inputs; test_docker_files.py::test_the_build_context_is_an_allow_list, and the record lists the context |

Fixes in e727b93, owner-approved (M1; N1-N4, N6-N8; N5 accepted). Each test failed before its fix and fails again when the fix is reverted. Found while fixing: on cancel and failure the worker marked the job final before removing its job folder, so a caller could briefly see the folder after a final state (a flaky test showed it); the folder is now removed first, pinned by test_upload_jobs.py::test_the_job_folder_is_gone_before_the_job_ends.
