---
phase: 2
title: HTTP, token, uploads and the document store
status: in-progress
branch: feat/5-http-uploads-store
base: 872ec10bba4784363a1b1802fd3bd3fdf591b36e
delivers: [R2, R15, R16, R17, R18, R19, R20, R22, R23, R28, R29]
design_review: { status: passed, rounds: 3, last: 2026-11-21 }
impl_review: { status: none, rounds: 0, last: null }
approved: 2026-11-21
---

# Phase 02 · HTTP, token, uploads and the document store

## Goal

`scanscribe-mcp --mode http` serves all six tools behind a bearer token. A remote agent uploads
page images, a PDF or a zip through a link, starts a job from the `upload_id` or a stored
`document` id, and gets the text inline, in slices, or by download URL.

## Tasks

### 1. Authentication and logging

- [x] 1.1 Add the variables marked phase 02 in notes.md#configuration, `auth.py`
  (`BearerTokenVerifier`), and the server's `create_auth_provider` and `validate_configuration`
  for `SCANSCRIBE_MCP_TOKEN` (D8, R2, R19). Verify: HTTP tests through `httpx.ASGITransport`: no
  token and a wrong token get 401, the right one works; start-up with auth on and no token exits
  with a configuration error; with `ALLOW_LOCAL_PATHS=true`, `input_path` and `output_path` are
  still refused with an error naming upload links.
- [x] 1.2 Turn off uvicorn's access log and check every log line of the HTTP flow (D8, R22).
  Verify: a test captures all log records while a file named `chapter-3.pdf` is uploaded, a job
  runs and fails, and a result is downloaded; no record contains `chapter-3`, the link token, a
  document id path or fake OCR text.

### 2. Document store

- [x] 2.1 Add `documents.py` from pandoc-mcp (`DocumentStore`, `safe_filename`, purge) with the
  MIME types this server needs, and the `/documents/<id>/<filename>` route (D6, R20). Verify:
  unit tests for save, get, a wrong filename, a malformed id, and purge of an old document
  except one a live job uses.
- [x] 2.2 Over HTTP, save each succeeded job's text as `ocr-<job id>.txt`, with options and page
  count in `meta.json`, and return the id and URL from `get_ocr_result`; run purge hourly on a
  timer (D6, R20). Verify: a client test downloads the URL and gets exactly the text; a stdio
  server creates no `OUTPUT_DIR` or `WORK_DIR`; `meta.json` holds no recognized text; with an
  injected clock the timer purges while no job runs.

### 3. Uploads

- [x] 3.1 Add `uploads.py` from pandoc-mcp with `max_files` defaulting to
  `UPLOAD_LINK_MAX_FILES` (100), never above 200, a per-grant byte total, and a `close()` used
  when a job starts (D7, R15, R16). Verify: unit tests with an injected clock for expiry,
  used-up and closed links, the active-link limit, the byte total, and start-up refusing
  `UPLOAD_LINK_MAX_FILES=201`.
- [x] 3.2 Add the `/upload/<token>` GET form and POST route, with the per-file and per-link size
  checks done while streaming; a file is stored only after its last byte, and the grant counts
  uploads in progress; the link is checked when a request starts, so a running upload may finish
  past expiry (R15, R16, R29). Verify: HTTP tests for a good upload, an expired and a used-up link
  (404), a 250 MB declared length and an over-limit stream (413, nothing stored), an empty file
  (400), a name with `../` stored as a plain name, and an upload that began before expiry
  finishing after it.
- [x] 3.3 Add `features/create_upload_link/tool.py` and `features/check_upload/tool.py`, with
  `wait_s` (D7, R15). Verify: client tests for the link, the curl command text, `check_upload`
  before and after an upload, and both tools over stdio returning "needs the HTTP server".

### 4. Jobs from uploads and documents

- [x] 4.1 At `start_ocr_job`, refuse while an upload is in progress or when two images reduce to
  one name; once the job is created, snapshot the files and close the link. In the worker, build
  `WORK_DIR/<job id>/pages/` from images or a zip, or use a stored PDF in place, and delete the
  folder when the job ends. At start-up, take the `WORK_DIR` lock and delete only entries named
  like job ids (D7, D12, R18, R29, notes.md#d7). Verify: unit tests for each upload kind;
  `.DS_Store` and `Thumbs.db` skipped; two PDFs, two zips, a mix, an in-progress upload and
  `a/p1.png` with `b/p1.png` refused at start, each leaving the link open; a second start on the
  same `upload_id` reusing the snapshot; natural order (`p1`, `p2`, `p10`) seen by the fake
  engine; no job folder left after success, failure or cancel; a stale job-id folder removed and
  a non-job file kept at start-up; a second server on the same `WORK_DIR` refusing to start.
- [x] 4.2 Add the zip checks and streaming extraction from notes.md#d7 (R17). Verify: tests that
  build zips in memory with `../x.png`, `/x.png`, a symlink entry, a nested zip, `a/1.png` with
  `b/1.png`, and a header that understates its size each fail before OCR with nothing outside the
  job folder; `chapter/p1.png` is accepted as `p1.png`; `__MACOSX/` entries are skipped.
- [x] 4.3 Accept `upload_id` and `document` in `start_ocr_job`; a `document` must be an uploaded
  PDF or zip, and images and zips are counted at start (D5, D7, R1, R4). Verify: client tests for
  both inputs, an unknown id, a result `.txt` id refused, an upload with no files yet, and a
  501-entry zip refused at start.
- [x] 4.4 Swap server paths in every job and tool error for the caller's own names (R23). Verify:
  a test with an unreadable uploaded `p7.png` checks that the error names `p7.png` and contains
  neither the resolved `WORK_DIR` nor the resolved `OUTPUT_DIR`; the job id itself may appear.
- [x] 4.5 Over HTTP, make R28's watchdog exit the process with a non-zero code after it marks the
  job failed and logs the job id (R28). Verify: a subprocess test starts the HTTP server with a
  fake engine that blocks past a 2 s timeout and sees the process exit non-zero.

### 5. Documentation

- [ ] 5.1 Add the HTTP part to the README (running with `--mode http`, the token, uploads, routes,
  all limits) and the uploads, storage and security-model sections to `docs/ARCHITECTURE.md`,
  each attack mapped to its defence as in pandoc-mcp; add the upload tools, the routes and the
  phase 02 variables to `docs/decision-log.md`. Verify: every `SCANSCRIBE_MCP_*` variable in
  `config.py` appears in the README table and the decision log.
- [ ] 5.2 Add `.env.example` with the token and URL variables. Verify: `gitleaks` in CI passes and
  `.env` stays ignored.
- [ ] 5.3 Run the HTTP server locally with `--extra gpu`, upload a self-made folder of images
  through the browser form and a zip with curl, and record the check in
  `docs/demos/<date>-http-check/README.md`. Verify: the record states the result, device, page
  counts and that no book material was used.
