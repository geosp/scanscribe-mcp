# Reviews · A working scanscribe MCP server

## 2026-11-21 · design-review · plan · round 1 · changes-requested
Commit: 95199061c16933d3b5fab00e355ada8a489365d9
Reviewers: fresh reader ✅ · codebase fit ✅ · zoom out ✅ · structure ✅
Raw reports: docs/reviews/2026-11-21-mcp-server/raw/design-review-01-{fresh-reader,codebase-fit,zoom-out}.md

| ID | Sev | Lens | Finding | Resolution |
| --- | --- | --- | --- | --- |
| F1 | Major | fresh reader | Summary cites R15/R16 for zip bombs (R17) and D7/D8 for the store (D6), and omits the log/path leak risk | open |
| F2 | Major | codebase fit, fresh reader | scanscribe v0.2.0 API (names in `__all__`, `on_page` stop, `len(source)`, pre-check, install message) has no evidence in notes and no definition in Terms | open |
| F3 | Major | codebase fit | notes.md#d7 name rule would accept `../x.png`, contradicting R17 and task 02/4.2 | open |
| F4 | Major | codebase fit | HTTP access logs would record upload tokens and `<input name>.txt` names (R22); no phase 02 log check | open |
| F5 | Major | codebase fit | Task 01/4.2 Verify can't fail: a print while serving goes to stderr | open |
| F6 | Major | codebase fit, zoom out | No mechanism for the subprocess test's fake engine factory; an env import hook would load code in production | open |
| F7 | Major | codebase fit | R2's refusal is never tested | open |
| F8 | Major | codebase fit, zoom out | Cancelled or expired jobs still in `queue.Queue` count toward R6 | open |
| F9 | Major | codebase fit, zoom out | Task 03/3.2 can't run tests in a `--no-dev` image; no command given | open |
| F10 | Major | zoom out | An unexpected error kills the worker thread; jobs then wait silently until expiry | open |
| F11 | Major | zoom out | A hung page blocks the worker forever; engine load and pre-check can't be cancelled; not in Risks | open |
| F12 | Major | zoom out | The dpi cap doesn't bound memory for a huge PDF page | open |
| F13 | Major | zoom out | Job folders left by a crash are never deleted | open |
| F14 | Major | zoom out | When the job folder is built, how long an upload_id's files stay usable, and partial uploads are unstated; purge may delete an in-use PDF | open |
| F15 | Major | zoom out | Docker: OUTPUT_DIR/WORK_DIR/PUBLIC_BASE_URL not set to the `/data` volume | open |
| F16 | Major | fresh reader, zoom out | `checking pages` is used like a state but isn't one | open |
| F17 | Major | fresh reader | The `document` input is unclear: which stored documents can be OCR'd | open |
| F18 | Major | fresh reader | `create_upload_link` and `check_upload` are not described | open |
| F19 | Major | fresh reader | The setting that allows local paths isn't named | open |
| F20 | Major | fresh reader | Whether stdio results go to the store from phase 02, and how stdio gets a large result, is unclear | open |
| F21 | Major | fresh reader | Phases table doesn't show which requirements each phase delivers | open |
| F22 | Major | fresh reader | D10's reasoning depends on notes.md | open |
| F23 | Major | fresh reader | R22 vs R23: whether job errors are logged is unstated | open |
| F24 | Major | fresh reader | Two PDFs or two zips in one upload aren't covered by D7 | open |
| F25 | Nit | structure | plan.md 353 body lines, budget 250 | open |
| F26 | Nit | fresh reader | Several requirements hold more than one rule (R3, R8, R10, R13, R15–R17, R19, R20, R22, R25) | open |
| F27 | Nit | fresh reader | R3 columns, R19 refusal to start and R20 retention have no scenario | open |
| F28 | Nit | fresh reader | Summary omits the reload on language change, the inline limit and memory-then-store | open |
| F29 | Nit | fresh reader | Terms lack the kit, pdfium, PaddleX, fastmcp, `on_page`/`on_device` | open |
| F30 | Nit | fresh reader | R4 has two possible outcomes in one scenario | open |
| F31 | Nit | fresh reader, codebase fit | R15 `max_files` default and whether 200 is a hard cap; R16 "one upload" ambiguous | open |
| F32 | Nit | fresh reader | D7's heading conflicts with its body | open |
| F33 | Nit | fresh reader | R17 scenario and the last Risks bullet run over 40 words | open |
| F34 | Nit | fresh reader | Decision log is empty | open |
| F35 | Nit | fresh reader | Open questions doesn't mark which content came from the owner | open |
| F36 | Nit | codebase fit | Task 01/4.1: the paddle-import check needs a stub in `sys.modules` to be shown failing | open |
| F37 | Nit | codebase fit | Task 03/1.1 Verify uses the system Python unless `.venv/bin` is on PATH | open |
| F38 | Nit | codebase fit | The stdout guarantee depends on fastmcp's version; no minimum is set | open |
| F39 | Nit | codebase fit, zoom out | Purge runs only during jobs, so an idle server never purges | open |
| F40 | Nit | codebase fit | PUBLIC_BASE_URL default 8302 doesn't match the kit's default port outside Docker | open |
| F41 | Nit | codebase fit | Task 02/4.4 Verify should name resolved paths and say whether the job id may appear | open |
| F42 | Nit | codebase fit | D5's start-time page count arrives only in phase 02 | open |
| F43 | Nit | codebase fit | No task updates the AGENTS.md Status line or the decision log for the new interface | open |
| F44 | Nit | codebase fit | The CI `licenses` allow-list may refuse PaddlePaddle's transitive licences | open |
| F45 | Nit | zoom out | Drop the old engine before loading a new language's | open |
| F46 | Nit | zoom out | Rollback doesn't mention the named volumes or leftover data folders | open |
