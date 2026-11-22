Review of /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server (plan.md, phases 01–03, notes.md), checked against the repository and /home/geo/develop/projects/scanscribe-mcp/AGENTS.md.

**Limits of this review.** The repository has no code of its own yet. `src/scanscribe_mcp/__init__.py` holds only `__version__`. There is no `.venv`. `uv.lock` lists only dev tools (mypy, pytest, ruff, pyyaml and their dependencies). So none of the outside claims could be checked from inside the repo: the scanscribe API, pandoc-mcp, mcp-service-kit and the fastmcp/mcp stdio behaviour. Every file the plan names is marked as new, so nothing it names is missing. No ADRs were given; the scanscribe ADRs it cites live in another repository.

## Blockers

None.

## Major

**M1 · Notes (the whole file), and the tasks in Phase 01 that use scanscribe (2.2, 2.4).** The scanscribe API the plan depends on has no evidence anywhere.
- AGENTS.md has two hard rules here: "use only names in `scanscribe.__all__`" and "Verify library and API behavior against current docs or installed source before relying on it".
- The notes give a pinned read for pandoc-mcp (`cbe8023`), the kit (v0.2.1) and fastmcp (4.2.4), but nothing for scanscribe v0.2.0.
- The plan relies on these names: `load_engine` (its signature and an `on_device` hook), `open_source(path, dpi, columns)`, `len(source)`, `ocr_source` with `on_page`, `format_pages`, `EngineMissingError`, `UsageError`, `InputError`, and `IMAGE_EXTENSIONS` (notes.md#d7, "every other entry must have an `IMAGE_EXTENSIONS` suffix").
- The plan never shows that these names are in `__all__`, or that they behave as D4 and D5 assume. D4 assumes a raise from `on_page` stops before the next page and closes the source. D5 assumes the source can be counted with `len()` before OCR starts.
- R12's scenario also depends on the exact install message ("naming `uv sync --extra gpu` and `--extra cpu`").
- Fix: add a scanscribe section to notes.md, read at the v0.2.0 tag.

**M2 · notes.md#d7 (the zip rules) against plan.md R17.** The notes contradict R17's scenario.
- R17: "Given a zip with `../x.png` … then the job fails before OCR".
- notes.md#d7: "the name is reduced with `safe_filename`; an entry whose reduced name differs from its base name only by case or is a duplicate is refused".
- Under that rule, `../x.png` reduces to `x.png`, which equals its base name, so it would be accepted and not refused.
- Phase 02 task 4.2 tests `../x.png` and an absolute name and expects "each fails before OCR". The rule in the notes would not make that test pass.
- The sentence about case is also hard to follow: refusing "only by case" when there is no case-insensitive duplicate seems unintended.
- Fix: state plainly that an entry is refused when its name has a directory part, `..`, a leading `/` or a drive letter, or when its reduced name differs from the original at all.

**M3 · plan.md D6 and Impact, against R22 and AGENTS.md ("Never commit or log secrets").** The HTTP routes put book-identifying names and secrets in URL paths, and no task deals with access logs.
- D6 saves results as "`<input name>.txt`", and the Impact section lists the routes "`/upload/<token>`, `/documents/<id>/<name>`".
- An HTTP access log (uvicorn logs request paths at INFO by default) would therefore record the input file name, which breaks R22. It would also record the upload-link token, which is a secret.
- Phase 02 has no task that re-checks R22 for the HTTP routes, the upload handlers or the code copied from pandoc-mcp. R22 is checked only once, in Phase 01 task 2.4, for a stdio job.
- Fix: add a Phase 02 task that turns off or scrubs access logging, plus a log-capture test over an upload, a download and a zip job. Or name stored files by job id instead of input name.

**M4 · Phase 01 › 4.2, Verify.** As written, this check cannot fail.
- The Verify says the test "fails if the server is changed to `print()` a line to stdout".
- But D10 and notes.md#d10 say that while the server runs, "fd 1 at stderr, so handlers and children … stray output misses the wire". A `print()` in the server would go to stderr, and the test would still pass.
- The check only works if the `print()` runs before the transport takes fd 1, for example at import or in `main()`.
- Fix: name where the injected `print` goes, or test a print before start-up and a print while serving separately.

**M5 · Phase 01 › 4.2 ("a test-only engine factory") with D3.** Getting a fake engine into a real subprocess needs a way in through production code, and the plan doesn't name one.
- D3 injects the factory in-process. A subprocess started through the real entry point can only receive a different factory through an environment variable, a CLI flag or a plugin hook.
- No such setting is in notes.md#configuration.
- If it ends up as an env var that imports any `module:callable`, the shipped server can be made to import arbitrary code.
- Fix: decide the mechanism, for example a separate test launcher script under `tests/` that builds the server with the fake factory and calls the kit's run. Record it in D3.

**M6 · Phase 01 › 3.2 against R2 (delivered in phase 01).** R2's scenario is never tested.
- R2: "Given an HTTP server, when a call passes `input_path` or `output_path`, then it returns a tool error that names upload links instead."
- Task 3.2 verifies only "no input, two inputs, a bad lang, `dpi: 600`, `columns: 9`, and a full queue". Task 3.5 tests `output_path` only with local paths allowed. Task 1.2 tests only the config default.
- No task checks the refusal or its wording, and HTTP doesn't exist until phase 02.
- Fix: add client tests with `local_paths_allowed=False` for both parameters, checking that the error names upload links.

**M7 · D2 and Phase 01 › 2.1, against R6 and R10.** The plan doesn't say what happens to the queue limit when queued jobs are cancelled or expire.
- D2 uses a `queue.Queue`. R10 makes a queued job "`cancelled` at once", but the item stays in the queue until the worker reaches it.
- R7 says expiry happens only "when the worker reaches it".
- If the R6 limit is `Queue(maxsize)` or `qsize()`, then 20 cancelled or timed-out jobs behind a long job would refuse new work for as long as that job runs.
- Fix: count only jobs in the `queued` state, from the job table, and add that case to 2.1's tests.

**M8 · Phase 03 › 3.2 against 1.1.** The test suite cannot run in the image as built.
- Task 1.1 builds with `uv sync --frozen --no-dev --extra ${ENGINE}`, so pytest, pytest-asyncio and httpx are not in the image.
- Task 3.2 says "Run the test suite inside the image … Verify: the command and its pass count are in the check record."
- Fix: give the exact command, for example `uv sync --frozen --extra gpu` with dev deps in a throwaway container, or `uv run --group dev`. Also note that R24's "paddle never imported" check now runs with paddle installed, which is the case it was written to catch.

## Nits

- Phase 01 › 4.1 Verify: on the base install `import paddle` raises ModuleNotFoundError and never reaches `sys.modules`, so "fails when a test imports `paddle` on purpose" needs a stub put into `sys.modules`. Say so.
- Phase 03 › 1.1 Verify: `docker run … python -c "import scanscribe_mcp"` uses the system Python, not uv's `.venv`, unless the Dockerfile puts `/app/.venv/bin` on PATH. Use `uv run python -c …` or state the PATH.
- notes.md#d10: the stdout guarantee depends on the fastmcp/mcp version ("the version the kit's `fastmcp>=4.1.3` resolves to today"). Phase 01 task 1.1 should keep it in the lock or set a minimum version, so a re-resolve can't silently drop it.
- Phase 02 › 2.2 ("purge at most once an hour during a job"): an HTTP server with no jobs never purges, so R20's 7-day retention isn't enforced when idle.
- notes.md#configuration: R15 says `max_files` is "at most 200", but `UPLOAD_LINK_MAX_FILES` is configurable with no stated cap. Say whether 200 is a hard ceiling.
- notes.md#configuration: the `PUBLIC_BASE_URL` default `http://localhost:8302` only matches if `MCP_PORT` is 8302, which Phase 03 › 1.1 sets only in Docker. A local `--mode http` run (Phase 02 › 5.3) on the kit's default port would hand out broken links. Set the port default alongside it.
- Phase 02 › 4.4 Verify: "contains neither `WORK_DIR` nor `OUTPUT_DIR`" should say it means the resolved values, and whether the job id (part of `WORK_DIR/<job id>`) is allowed, since R23 bans "any part of the server's job folder path".
- plan.md D5 against Phase 01: D5's check of folder page counts from file names at start-up only arrives in Phase 02 › 4.3. In phase 01 an `input_path` folder is checked only by the worker. That still meets R4, but D5 reads as if it applies from phase 01.
- AGENTS.md "Status" line ("Update this line whenever a plan closes") and the decision-log rule for new interfaces: no Phase 03 task updates the status line or adds the six tools and the `SCANSCRIBE_MCP_*` interface to docs/decision-log.md.
- Phase 01 › 1.1: the lock will now include the PaddlePaddle/PaddleOCR dependency tree (all extras are locked). The PR-only `licenses` job in /home/geo/develop/projects/scanscribe-mcp/.github/workflows/ci.yml uses a fixed allow-list and may refuse some of those transitive licenses. Worth a step that runs the job and records any additions.

## Reuse

There is nothing in this repository to reuse yet. The plan already reuses pandoc-mcp's modules, which fits AGENTS.md's "pandoc-mcp's model".

## Tasks and order

The task order builds in each phase: config, then jobs and worker, then tools, then end-to-end tests. Each phase's `delivers` list is covered by its tasks, except R2, which is never verified (M6). The task counts match the plan's table (15, 13 and 7).
