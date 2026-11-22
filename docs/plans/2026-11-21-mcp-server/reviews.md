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
