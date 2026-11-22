Review of /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server: plan.md, phases 01–03 and notes.md.

**Verdict:** 0 Blockers, 6 Majors, 7 Nits. The plan does fix the cause given under Why: OCR takes minutes, longer than a tool call should block, and remote agents can't hand over a path. Jobs plus upload links address both. Code placement copies pandoc-mcp's layout (D1), so it is consistent.

**What I could not check:** the repository is still a scaffold. `src/scanscribe_mcp/__init__.py` holds only `__version__`, and `pyproject.toml` has `dependencies = []`. The claims about scanscribe, the kit, pandoc-mcp and fastmcp point to code outside the repository, and I stayed inside it.

## Major

**M1. The plan is marked "passed", but a second review round found Majors that are still open.**
- **Where:** plan.md frontmatter `design_review: { status: passed, rounds: 1 }`; reviews.md.
- **What is wrong:** reviews.md records only round 1, which ends "Status: passed".
  - Round-2 raw reports exist: `docs/reviews/2026-11-21-mcp-server/raw/design-review-02-codebase-fit.md` (5 Majors) and `design-review-02-fresh-reader.md` (several Majors).
  - The plan text has not changed in response. For example, Terms still says local paths are allowed "when `SCANSCRIBE_MCP_ALLOW_LOCAL_PATHS` is true; unset, it is true over stdio and false over HTTP".
  - Round-2 M5 still stands as well. Phase 03 task 3.2 mounts only `tests/`, but `tests/test_ci_gate.py:11` does `import ci_gate` from `.github/scripts`, and lines 16–17 read `.github/workflows/ci.yml`. Neither is in the image.
- **Fix:** log round 2 in reviews.md and resolve its findings before approval. M2–M4 below confirm three of them on their own.

**M2. Over HTTP, setting one variable lets clients pass server paths.**
- **Where:** plan.md › Terms "Local paths", R2; phase 01 task 1.2 (tests the variable "set"); notes.md#configuration `ALLOW_LOCAL_PATHS`.
- **What is wrong:** the variable can be set to true on an HTTP server, which would then accept `input_path` and `output_path`.
- **Evidence:** AGENTS.md hard constraint: "Over HTTP: no client-supplied paths". D8 also says "no client paths over HTTP".
- **Fix:** HTTP refuses local paths whatever the variable says.

**M3. The worker's order is not stated, so refused inputs may still load the engine.**
- **Where:** plan.md › D3, D4, D5, R4; Terms "Step"; phase 01 tasks 2.2 and 2.3.
- **What the plan says:**
  - The steps are listed as "`loading engine`, `checking pages` or `recognizing`".
  - D4: the worker checks the cancel flag "after the engine loads and after the pre-check".
  - Task 2.3: "a cancel during a slow fake engine load stops before the pre-check".
  - All of that puts the load first.
- **The conflict:** R4 says a 501-page PDF "never reaches the engine", and task 2.2 says it "fails ... without the engine".
- **Cost:** if the load comes first, every refused input pays for it: a first-run model download and GPU memory, which D3 exists to avoid. That covers a 501-page PDF, an oversized page and an unreadable page.
- **Fix:** state the order once in D5: size check, pre-check, page limit, then engine load. Say whether "without the engine" means the factory is never called.

**M4. A default data folder that depends on the current folder, wiped at start-up and shared between processes, can destroy files and running jobs.**
- **Where:** notes.md#configuration (`OUTPUT_DIR` `data/documents`, `WORK_DIR` `data/work`); D6; D7 ("`WORK_DIR` is emptied at start-up"); phase 02 tasks 2.2 and 4.1.
- **One user, one session:**
  - D6 saves every result "on both transports", so each stdio session started by `claude mcp add` creates `./data/` in whatever project it was started from.
  - Start-up then empties any `./data/work` it finds there.
- **Two sessions at once:** two Claude Code windows in the same project, or stdio next to a local HTTP server, share the folders.
  - The second start-up deletes the first one's running job folder.
  - Purge in one process deletes documents a job in the other is using. Purge only skips "documents a live job uses" in its own job table (R20).
- **Simplicity point:** storing stdio results buys nothing. Over stdio there is no URL, and result `.txt` ids are refused as input (Terms "Document"). The phase 01 in-memory pages plus `output_path` already cover stdio.
- **Fix:**
  - Store results only over HTTP, or give each process its own folder.
  - At start-up, delete only entries named like job ids, and lock the folder per process.
  - Add a test that a non-job entry survives start-up.

**M5. The mitigation for a hung page does not work.**
- **Where:** plan.md › Risks, bullet 4: "a restart recovers (compose `restart: unless-stopped`)"; phase 03 task 2.1 ("how a restart recovers a hung job").
- **What is wrong:** `restart: unless-stopped` only acts when the process exits. A worker thread stuck in pdfium or Paddle leaves the process, and its HTTP endpoint, alive. Docker never restarts it, and every queued job sits until it expires under R7.
  - Over stdio there is no supervisor at all.
  - A manual restart also drops every in-memory job and upload link (Assumptions).
  - So the "mitigation" amounts to "an operator notices and restarts".
- **Fix:** either add a per-page watchdog, e.g. `SCANSCRIBE_MCP_PAGE_TIMEOUT_S`, that fails the job and calls `os._exit` so compose restarts the container, plus a compose healthcheck. Or state honestly that recovery is manual.

**M6. Starting a job while files are still uploading silently leaves pages out.**
- **Where:** plan.md › D7 ("snapshots the document ids of the files already received in full and closes the link"); notes.md#d7 ("a partial file is never in the snapshot").
- **What is wrong:** a file still streaming when `start_ocr_job` is called is left out of the job, and the link is closed.
  - The plan doesn't say whether that in-flight file is then rejected or stored as an orphan.
  - The job runs on fewer pages and reports success. For a chapter that is a wrong result with no error, which is not a safe failure.
  - A repeated `start_ocr_job` on the same, now closed, `upload_id` has no stated reply.
- **Fix:**
  - Refuse to start while the link has uploads in progress, or make the reply list the file names and count taken.
  - Define the reply for a closed or already-used `upload_id`.
  - Add a test for each.

## Nits

- **Rollout & rollback:** "after reverting phase 03, `docker compose down -v` removes the volumes". That also deletes every stored result and the model cache. Say `down`, and keep or export the volumes unless the owner wants the data gone.
- **Rollout & rollback:** after reverting phase 02 it says "delete `data/documents` and `data/work`". Because of M4, those folders may be scattered across every folder a stdio session was started in. Name where they are.
- **D3, R11:** with FIFO and `MAX_QUEUED` 20, alternating `en`/`fr` jobs reload the engine for every job. Also, dropping the Python reference doesn't guarantee Paddle frees GPU memory. Note both as known costs, or test that memory is freed in the phase 03 GPU check.
- **R13:** the reply for a `first_page`–`last_page` range longer than `MAX_INLINE_CHARS` is undefined (round-2 fresh reader raised it too).
- **R6/R7, phase 01 task 2.1:** say that R6's count of `queued` jobs uses the same derived state as the expiry check, so a job past its timeout but not yet skipped by the worker doesn't fill the queue.
- **D9:** "A build argument `ENGINE=cpu` exists but isn't checked". It is built for a need nobody stated, and Non-goals excludes a CPU image. Drop it.
- **R15/R16, phase 02 task 3.2:** it isn't said whether a stream already running when the 600 s link expires may finish. 2 GB in 600 s needs about 3.4 MB/s, so slow links will hit this.

## Relevant files

- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/plan.md
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/notes.md
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/phases/01-stdio-server.md
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/phases/02-http-uploads-store.md
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/phases/03-docker-gpu.md
- /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/reviews.md
- /home/geo/develop/projects/scanscribe-mcp/docs/reviews/2026-11-21-mcp-server/raw/design-review-02-codebase-fit.md
- /home/geo/develop/projects/scanscribe-mcp/docs/reviews/2026-11-21-mcp-server/raw/design-review-02-fresh-reader.md
- /home/geo/develop/projects/scanscribe-mcp/AGENTS.md
- /home/geo/develop/projects/scanscribe-mcp/tests/test_ci_gate.py
