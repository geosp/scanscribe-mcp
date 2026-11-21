Review of /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server (plan.md, phases/01-03, notes.md). The repository has no server code yet: src/scanscribe_mcp/__init__.py only sets `__version__`, and pyproject.toml has `dependencies = []`. So I checked the plan against its own text, against AGENTS.md and against CI (.github/workflows/ci.yml). I could not check claims about scanscribe, pandoc-mcp or fastmcp, because their code is outside this repository.

**Overall:** The plan fixes the real cause in Why: blocking CLI runs, and remote agents can't pass a path. The jobs, queue and upload design is a sound way to do that, and its layout follows the pattern it names. I found no Blockers, six Majors and six Nits. The Majors are about what happens when a step fails, hangs or crashes, and about disk and memory limits over HTTP.

## Major

**M1. If the worker thread hits an unexpected error, the thread can die and the server stops running jobs without saying so.**
- Where: plan.md › Decisions › D2, D3; phase 01 › Tasks 2.2 and 2.4.
- What's wrong: only three named errors are covered: "`EngineMissingError` makes the job `failed` and the next job still runs" (2.2), and "Map scanscribe's `UsageError` and `InputError`" (2.4). Nothing covers other errors from `ocr_source` or the engine, such as a Paddle runtime error, CUDA out of memory, a pdfium error or a Pillow `DecompressionBombError`. Nothing covers an error inside the worker's own code either.
- What follows: D2's "single daemon thread" exits on an uncaught exception. The MCP tools keep answering, but every queued job stays `queued` until it expires (R7), and nothing reports it.
- Needed: a catch-all per job that marks the job `failed` with a path-free generic message and keeps the loop alive. Also a test where the fake engine raises `RuntimeError` and the next job still succeeds. If the engine raised, it should probably be dropped so the next job reloads it.

**M2. There is no limit on how long a running job can take, and cancelling can't stop a page that hangs.**
- Where: plan.md › Risks; Decisions › D4; R10.
- What's wrong: cancelling only works at page boundaries ("`on_page` callback raises `JobCancelled`", D4), and D4 itself rejects killing the thread. If the engine or pdfium hangs on one page (a GPU hang, a pathological PDF page), the single worker is blocked forever. Every later job then expires after `QUEUE_TIMEOUT_S`, and only a restart helps.
- Also: a job that is loading the engine (the first model download in Docker takes minutes) or running `open_source` can't be cancelled until that step ends. D4 only says "The flag is also checked after the pre-check."
- The Risks section doesn't mention any of this.
- Needed at minimum: a Risk entry that names the outcome and the recovery (restart the process or container; Compose `restart: unless-stopped`). Optionally, `get_ocr_job` could report how long the current page has been running, so an operator can see a hang.

**M3. A huge PDF page can exhaust memory, and the dpi cap doesn't prevent it.**
- Where: plan.md › Risks, item 3; Assumptions › "scanscribe v0.2.0's API is enough".
- What's wrong: the mitigation is "→ the dpi cap (R3); pdfium's limits are scanscribe's concern". Memory depends on page size × dpi. A hostile PDF uploaded over HTTP with, say, a 200-inch page at 400 dpi renders to about 80,000 × 80,000 pixels, many GB, before OCR starts. The plan treats hostile uploads as a main risk ("hostile uploads such as zip bombs", Summary), but for PDFs this mitigation does nothing.
- The server can't fix this itself. AGENTS.md says "use only names in `scanscribe.__all__`", so the check (a pixel cap per rendered page) has to come from scanscribe.
- Needed: either a new scanscribe tag (which contradicts the Assumption, so it should be listed as a dependency), or an explicit accepted risk with the container memory limit as the backstop. The plan should not present the dpi cap as the mitigation.

**M4. Job folders left behind by a crash or restart are never deleted.**
- Where: phase 02 › Task 4.1; notes.md › D7.
- What's wrong: 4.1 says "delete the folder when the job ends". Non-goals says jobs don't survive a restart. A crash, an OOM kill (see M3) or `docker compose down` during a job leaves `WORK_DIR/<job id>/` on disk. Extracted zips can be up to `MAX_UPLOAD_BYTES` (2 GB) per job, and nothing ever deletes them.
- Needed: clear `WORK_DIR` at start-up, which is safe because no job survives a restart. Add a test for it.

**M5. The plan doesn't say when the job folder is built or how long an `upload_id` stays valid.**
- Where: phase 02 › Tasks 4.1 and 4.3; notes.md › D7; Assumptions › "Jobs and upload links live in memory".
- What's wrong: three things depend on this choice, and the plan settles none of them.
  - Built at `start_ocr_job`: zip extraction of up to 2 GB runs inside the async tool handler and blocks the event loop. Up to `MAX_QUEUED` = 20 waiting jobs could each hold a 2 GB folder, about 40 GB of disk.
  - Built when the worker starts the job: the job needs the upload's file list long after the link's 600 s TTL. An in-memory grant that is purged at TTL would make every job queued for more than 10 minutes fail.
  - Built at start but deleted only "when the job ends": it's unclear whether that includes queued jobs that are cancelled or expired.
  - R17's wording ("the job fails before OCR") points to the worker, but 4.3 does the page-count check at start.
- Also: the plan doesn't say whether a job started while a file is still streaming into the link can see a partial file, or whether starting a job closes the link.
- Needed: state the build time (in the worker is the better fit), how long upload_ids live (tied to document retention, not link TTL), and what happens to files that are still arriving.

**M6. In the Docker image, documents and job folders don't go to the `documents` volume.**
- Where: phase 03 › Task 1.1; notes.md › D9, notes.md › Configuration.
- What's wrong: the defaults are relative: `OUTPUT_DIR` = `data/documents` and `WORK_DIR` = `data/work`. D9 mounts the volume at `/data`. Task 1.1's environment list sets only `PADDLE_PDX_CACHE_HOME=/cache/paddlex` and `MCP_PORT=8302`, not `SCANSCRIBE_MCP_OUTPUT_DIR`, `SCANSCRIBE_MCP_WORK_DIR` or `PUBLIC_BASE_URL`.
- What follows: as written, results are written under the image's working directory, not to the volume. They are lost when the container is recreated, and the unprivileged uid 1000 may not be able to write there at all. This breaks D9's "mounts two volumes: documents and the model cache" and R20's retention.
- Also: if the upload store and `WORK_DIR` end up on different filesystems, D7's hard links silently fall back to copies.
- Needed: set both variables to paths under `/data` in the Dockerfile or compose file, and add a check in 3.1 that a result survives `docker compose up --force-recreate`.

## Nits

- plan.md › Risks, item 4 and phase 01 › Task 2.2: `checking pages` is reported like a state, but Terms › Job state lists only six states. Say whether it is a state or a field.
- plan.md › R6 and D2: if cancelled or expired jobs stay inside the `queue.Queue` until the worker reaches them, they still count toward `MAX_QUEUED`. A 21st valid job could then be refused while fewer than 20 are really waiting. Count only live jobs.
- plan.md › R11 and D3: on a language change, drop the old engine before loading the new one. Otherwise two models sit in GPU memory on the 12 GB RTX 3060.
- phase 01 › Task 4.2: the plan doesn't say how the subprocess gets the "test-only engine factory". If it's an environment variable or import hook in production code, that is a code-loading path in the shipped server. A test-only wrapper entry point that calls `main()` with the factory avoids this.
- phase 02 › Task 2.2: the hourly purge can delete a stored PDF that is used "in place" (notes.md › D7) by a queued or running job. Skip documents in use, or copy the PDF into the job folder.
- phase 03 › Task 3.2: the image is built with `--no-dev` (Task 1.1), so pytest isn't installed. Running the tests needs a dev sync, which downloads into the image. Say which command is meant.
- plan.md › Rollout & rollback: no deploy order or migration is needed, which is fine. Rolling back phase 03 should also mention removing the named `models` and `documents` volumes (`docker compose down -v`). After a phase 02 revert, `data/documents` and `data/work` stay on disk.

## Points checked and found sound

- Root cause: the plan fixes the cause in Why, not a symptom.
- Simplicity: the zip path (R17) is the largest attack surface, but notes.md › D7 says the owner chose it, so I raise no simplicity finding.
- Placement: it follows pandoc-mcp as D1 states.
- R21 / D10: the stdout claim has a real end-to-end test (Task 4.2), so that mitigation works.
- R24: it is checked at the end of the test session.
