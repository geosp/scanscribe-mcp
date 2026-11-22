Review of /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server (plan.md, the three phase files, notes.md), checked against the repository and against AGENTS.md / CLAUDE.md.

I found 5 Majors and 7 Nits. No Blockers. The most serious problem is that one setting lets the HTTP server accept client paths, which the project's hard rules forbid.

**What I could not check.** The repository is still a scaffold. `src/scanscribe_mcp/__init__.py` holds only `__version__`, `pyproject.toml` has `dependencies = []`, and `uv.lock` has no scanscribe, kit, fastmcp or pypdfium2. Every file and module the plan names (config.py, jobs.py, ocr_service.py, server.py, features/*, documents.py, uploads.py, auth.py, Dockerfile and so on) is marked as to be created, which is fine. The claims about scanscribe v0.2.0, pandoc-mcp `cbe8023`, mcp-service-kit v0.2.1 and fastmcp 4.2.4 are all about code outside this repository. I stayed inside the repository, so I could not confirm them. There are no ADRs in this repo (`docs/adrs/README.md`: "There are no ADRs yet"); the plan cites only scanscribe's ADRs, which are external. So there is nothing to check under item 4.

## Major

**M1. Turning on local paths over HTTP breaks a hard constraint.**
- Where: plan.md › Terms ("Local paths"), R2, D8; phase 01 task 1.2; notes.md#configuration (`ALLOW_LOCAL_PATHS`).
- What is wrong: the plan says "allowed when `SCANSCRIBE_MCP_ALLOW_LOCAL_PATHS` is true; unset, it is true over stdio and false over HTTP". Task 1.2 also tests the case where the variable is "set". So an operator can set it to true and the HTTP server will accept `input_path` and `output_path`.
- Evidence: AGENTS.md, Hard constraints: "Over HTTP: no client-supplied paths". D8 says the same thing ("no client paths over HTTP"). Open questions says "None", so the conflict is never raised.
- Fix: make HTTP always refuse local paths whatever the variable says. Or ask the owner and record the exception in the decision log.

**M2. Relative data folders, plus wiping WORK_DIR at start-up, can delete files in the user's project over stdio.**
- Where: notes.md#configuration (`OUTPUT_DIR` = `data/documents`, `WORK_DIR` = `data/work`); D6, D7; phase 02 tasks 2.2 and 4.1.
- What is wrong: D6 says results go to the store "on both transports". Task 4.1 says to "empty `WORK_DIR` at start-up" and doesn't limit that to HTTP. A stdio server started with `claude mcp add` runs in whatever directory the client was started from. So every stdio session would create `./data/documents` in the user's own project, and would empty any `./data/work` it finds there.
- Fix: resolve the defaults against a fixed base, such as a per-user data folder. Only delete entries named like job ids. Or don't empty the folder over stdio. Add a test for a non-job entry in WORK_DIR surviving start-up.

**M3. The order of engine loading and page checks is unclear, and the task 01/2.2 tests depend on it.**
- Where: plan.md › Terms (Step), R4, R10, D3, D4, D5; phase 01 tasks 2.2 and 2.3.
- The order as written:
  - The steps are listed as `loading engine`, `checking pages`, `recognizing`.
  - D4 and R10 check for a cancel "after the engine loads and after the pre-check".
  - Task 2.3 says "a cancel during a slow fake engine load stops before the pre-check".
  - All of that puts the load before the page checks.
- The conflict: R4 says a 501-page PDF "never reaches the engine", and task 2.2's Verify says it "fails after the pre-check without the engine". Under the order above, the factory would already have been called.
- Cost: with the load first, every input that will be refused (a 501-page PDF, an R27-oversized page, an unreadable page) first pays for an engine load. That can include a first-run model download and holding GPU memory, which D3 was written to avoid.
- Fix: state the order once in D5. My recommendation is size check, then pre-check, then page limit, then load, then OCR. Then say exactly what "without the engine" means in the Verify (factory not called, or engine not called).

**M4. Images from one upload link with the same name collide in the job folder.**
- Where: D7; notes.md#d7 (table row "1–200 images | hard links ... into `<job>/pages/`"); phase 02 task 4.1.
- What is wrong: each upload is stored under its own id and run through `safe_filename`. Two files that end up as `p1.png` are therefore both kept. Examples: a browser folder upload of `a/p1.png` and `b/p1.png`, or curl `-F` sending the same name twice. Hard-linking both into one `pages/` folder fails.
- Evidence: the zip path has an explicit rule ("two entries with the same base name are refused"). The images path has none. So this case would surface as R26's generic "unexpected error" at run time instead of a clear tool error at start.
- This matters because D7 keeps image uploads precisely for the browser ("Rejected: zip only (hard in a browser)").
- Fix: refuse duplicates at `start_ocr_job`, naming the file, and add a test to task 4.1.

**M5. The in-image test run (task 03/3.2) can't pass as written.**
- Where: phase 03 task 3.2.
- What is wrong: the command mounts only `tests/` (`-v $PWD/tests:/app/tests:ro`).
- Evidence:
  - `tests/test_ci_gate.py:11` does `import ci_gate`, found through `pyproject.toml` `pythonpath = [".github/scripts"]`.
  - `tests/test_ci_gate.py:16-17` reads `.github/scripts/ci_gate.py` and `.github/workflows/ci.yml` from the repo root.
  - Neither task 1.1 nor notes.md#d9 says the image copies `.github/`. An image that has only the app wouldn't have it.
  - Building the project with `uv sync` also needs `README.md`, because pyproject sets `readme = "README.md"`, and the Dockerfile description doesn't list what gets copied.
- Fix: list the files the Dockerfile copies. Then either mount `.github` too, or deselect `test_ci_gate.py` in the 3.2 command.

## Nits

- **notes.md#r27:** "pypdfium2 is already in the lock through scanscribe" is false today; `uv.lock` has neither. It only becomes true after task 01/1.1, so reword it.
- **Phase 01 task 1.2:** "the phase 01 variables from notes.md#configuration" can't be followed, because the table doesn't mark phases. No phase 02 task says to add the rest (`TOKEN`, `OUTPUT_DIR`, `WORK_DIR`, `UPLOAD_*`, …), even though task 02/3.1 relies on start-up validation of `UPLOAD_LINK_MAX_FILES`.
- **plan.md › R3 / notes.md#configuration:** the defaults for `dpi` and `columns` are never given (there is no `DEFAULT_DPI` / `DEFAULT_COLUMNS`), yet `open_source(path, dpi, columns)` needs both.
- **plan.md › R15 vs phase 02 task 3.2:** R15's scenario says a used-up link gets 404 over HTTP, but the HTTP tests cover only the expired link; used-up is tested only in `UploadLinks` unit tests (3.1).
- **plan.md › R26 vs phase 01:** phase 01 delivers R26 ("a message free of server paths"), but no phase 01 Verify checks the message; the path-stripping test comes only in task 02/4.4.
- **notes.md#d7 (images row) and phase 03 task 1.2:**
  - A browser folder upload that carries `.DS_Store` or `Thumbs.db` falls under "anything else ... tool error" and refuses the whole job. Skip hidden and non-image names, the way zips do.
  - `.dockerignore` leaves out `.venv` and `.env.*`. If the Dockerfile copies the whole repo, a host `.venv` could replace `/app/.venv`.
- **Phase 03 task 2.3 vs AGENTS.md "Record changes to ... interfaces ... in docs/decision-log.md":** phases 01 and 02 each merge new tools and variables, but the decision log gets the interface only at the end of phase 03. Record it in each phase's PR instead.

## Tasks and coverage

- Each phase's `delivers` list is covered by its tasks, apart from the gaps above (M3, M4, and the R15 and R26 Nits).
- The task counts match the Phases table (15, 14 and 8).
- The task order builds, apart from the config gap in the second Nit.

Relevant files:
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/plan.md
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/notes.md
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/phases/01-stdio-server.md
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/phases/02-http-uploads-store.md
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/phases/03-docker-gpu.md
- /home/geo/develop/projects/scanscribe-mcp/AGENTS.md
- /home/geo/develop/projects/scanscribe-mcp/pyproject.toml
- /home/geo/develop/projects/scanscribe-mcp/uv.lock
- /home/geo/develop/projects/scanscribe-mcp/tests/test_ci_gate.py
- /home/geo/develop/projects/scanscribe-mcp/docs/decision-log.md
