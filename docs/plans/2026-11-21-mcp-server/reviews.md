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
