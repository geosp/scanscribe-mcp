## Review: 2026-11-21-mcp-server (round 3, after the D10/R28 change)

I checked the plan, all three phases and the notes against the code on `docs/plan-mcp-server` (HEAD c3643fd, plus the untracked `tests/stdio_launcher.py` and `tests/test_stdio.py`) and against the installed packages in `.venv`: mcp 2.3.0, fastmcp 4.2.4, scanscribe 0.2.0 and mcp-service-kit 0.2.1. Most claims hold:

- **Transport:** `_claim_fd` and `_is_backed_by_fd` in `mcp/server/stdio.py` point fd 1 at stderr while serving and write the wire through a private duplicate, as the notes say.
- **scanscribe:** its engine wraps its calls in `redirect_stdout(sys.stderr)` (`scanscribe/paddle_engine.py:47,53`).
- **Logging:** the kit logs to stderr (`mcp_service_kit/server.py:478`).
- **R28:** `JobTable.fail_queued` and the `on_stuck` hook exist (`jobs.py:234`, `ocr_service.py:485-494`), and `tests/test_watchdog.py:32-44` checks that queued jobs fail with "restart the server".
- **Pre-existing setup:** `pyproject.toml` already has the extras, the conflicts rule, the cu126 index and its source. `ci.yml` has the `licenses` job.

There is one Major finding and four Nits.

### Major

**M1 · Phase 01 has no task that adds D10's per-job stdout redirect** (`phases/01-stdio-server.md` › Tasks 2.2 and 4.2; `plan.md` › Decisions › D10)
- **What D10 now requires:** "So the worker also runs each job inside `contextlib.redirect_stdout(sys.stderr)`… Task 01/4.2 checks it end to end (R21)."
- **What the tasks say:** task 4.2 only says "Add `tests/stdio_launcher.py` … and a subprocess test that runs a job through it". Task 2.2, which defines the worker, is already ticked and doesn't mention the redirect. No other task covers it.
- **In the code:** the redirect isn't there. `grep redirect_stdout src/` finds nothing, and `OcrService._run` / `_process` (`src/scanscribe_mcp/ocr_service.py:354-405`) call `_process` with no redirect.
- **Effect:** `tests/test_stdio.py::test_stdout_carries_only_mcp`, which asserts that `"fake engine stray output, page 3"` appears on stderr, can't pass as the plan is written. This is the failure notes.md#d10 itself records.
- **Fix:** add the code change to a task. Either extend task 4.2 with "wrap `_run`'s whole body, page check included, in `redirect_stdout(sys.stderr)`", or add a task 2.6. Also tick or update task 2.2 so it doesn't read as complete without it.

### Nits

- **N1 · Task verifies lag behind changed text.** `phases/01-stdio-server.md` › Task 2.5's Verify still checks only "the job becomes `failed` … and a new start is refused". R28 now also requires queued jobs to fail asking for a restart. The test covers it (`tests/test_watchdog.py:42-44`), but the Verify line should say so.
  - The same applies to Task 3.5 and the new Assumptions (`output_path` refuses `first_page`/`last_page`; a page longer than `MAX_INLINE_CHARS` returns no text). The code implements both (`features/get_ocr_result/tool.py:42-46` and `:74-81`), but neither the Verify nor any test in `tests/test_tools.py` covers them. AGENTS.md says "Never claim an untested capability works."
- **N2 · Phases table progress is stale.** `plan.md` › Phases shows phase 01 as "0/16", but 12 of the 16 tasks are ticked in `phases/01-stdio-server.md`.
- **N3 · Phase 01 branch name breaks the naming rule.** `phases/01-stdio-server.md` frontmatter has `branch: docs/plan-mcp-server`. AGENTS.md requires `<type>/<issue>-<short-slug>`. This name has no issue number, and it is a `docs/` branch carrying feature code (commits 58e2608, eac4daa).
- **N4 · notes.md misattributes the fd-1 diversion.** notes.md › D10 says "fastmcp 4.2.4 … serves stdio through `mcp.server.stdio.stdio_server`" and that pinning `fastmcp>=4.2.4` keeps the behaviour. The diversion is actually in the `mcp` package (2.3.0 here). The pin still works, because fastmcp 4.2.4 requires `mcp>=2.3.0` (its METADATA). The note should name `mcp>=2.3.0` as the version the behaviour was read at.

### Other checks
- **ADRs:** none were given and `docs/adrs/` holds only a README, so there were no ADR conflicts to check.
- **Phases 02 and 03:** the D10 and R28 changes don't affect them. Phase 02 › 4.5's HTTP exit uses the existing `on_stuck` hook.

Files referenced:
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/plan.md
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/phases/01-stdio-server.md
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/notes.md
- /home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/ocr_service.py
- /home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/features/get_ocr_result/tool.py
- /home/geo/develop/projects/scanscribe-mcp/tests/test_stdio.py
- /home/geo/develop/projects/scanscribe-mcp/tests/test_watchdog.py
- /home/geo/develop/projects/scanscribe-mcp/tests/test_tools.py
- /home/geo/develop/projects/scanscribe-mcp/.venv/lib/python3.12/site-packages/mcp/server/stdio.py
