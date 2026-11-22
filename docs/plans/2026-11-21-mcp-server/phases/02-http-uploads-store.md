---
phase: 2
title: HTTP, token, uploads and the document store
status: draft
branch: null
base: null
delivers: [R15, R16, R17, R18, R19, R20, R22, R23]
design_review: { status: passed, rounds: 1, last: 2026-11-21 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · HTTP, token, uploads and the document store

## Goal

`scanscribe-mcp --mode http` serves all six tools behind a bearer token. A remote agent uploads
page images, a PDF or a zip through a link, starts a job from the `upload_id` or a stored
`document` id, and gets the text inline, in slices, or by download URL.

## Tasks

### 1. Authentication and logging

- [ ] 1.1 Add `auth.py` (`BearerTokenVerifier`) and the server's `create_auth_provider` and
  `validate_configuration` for `SCANSCRIBE_MCP_TOKEN` (D8, R19). Verify: HTTP tests through
  `httpx.ASGITransport`: no token and a wrong token get 401, the right one works; start-up with
  auth on and no token exits with a configuration error.
- [ ] 1.2 Turn off uvicorn's access log and check every log line of the HTTP flow (D8, R22).
  Verify: a test captures all log records while a file named `chapter-3.pdf` is uploaded, a job
  runs and fails, and a result is downloaded; no record contains `chapter-3`, the link token, a
  document id path or fake OCR text.

### 2. Document store

- [ ] 2.1 Add `documents.py` from pandoc-mcp (`DocumentStore`, `safe_filename`, purge) with the
  MIME types this server needs, and the `/documents/<id>/<filename>` route (D6, R20). Verify:
  unit tests for save, get, a wrong filename, a malformed id, and purge of an old document
  except one a live job uses.
- [ ] 2.2 Save each succeeded job's text as `ocr-<job id>.txt` on both transports, with options
  and page count in `meta.json`; return the id, and over HTTP the URL, from `get_ocr_result`;
  over stdio point to slices and `output_path` instead; run purge hourly on a timer (D6, R20).
  Verify: a client test downloads the URL and gets exactly the text; a stdio reply has an id and
  no URL; `meta.json` holds no recognized text; with an injected clock the timer purges while no
  job runs.

### 3. Uploads

- [ ] 3.1 Add `uploads.py` from pandoc-mcp with `max_files` defaulting to
  `UPLOAD_LINK_MAX_FILES` (100), never above 200, a per-grant byte total, and a `close()` used
  when a job starts (D7, R15, R16). Verify: unit tests with an injected clock for expiry,
  used-up and closed links, the active-link limit, the byte total, and start-up refusing
  `UPLOAD_LINK_MAX_FILES=201`.
- [ ] 3.2 Add the `/upload/<token>` GET form and POST route, with the per-file and per-link size
  checks done while streaming; a file is stored only after its last byte (R15, R16). Verify: HTTP
  tests for a good upload, an expired link (404), a 250 MB declared length and an over-limit
  stream (413, nothing stored), an empty file (400), and a name with `../` stored as a plain
  name.
- [ ] 3.3 Add `features/create_upload_link/tool.py` and `features/check_upload/tool.py`, with
  `wait_s` (D7, R15). Verify: client tests for the link, the curl command text, `check_upload`
  before and after an upload, and both tools over stdio returning "needs the HTTP server".

### 4. Jobs from uploads and documents

- [ ] 4.1 At `start_ocr_job`, snapshot the upload's finished files and close the link; in the
  worker, build `WORK_DIR/<job id>/pages/` from images or a zip, or use a stored PDF in place, and
  delete the folder when the job ends; empty `WORK_DIR` at start-up (D7, R18, notes.md#d7).
  Verify: unit tests for each upload kind; two PDFs, two zips or a mix refused at start; natural
  order (`p1`, `p2`, `p10`) seen by the fake engine; no job folder left after success, failure or
  cancel; a stale folder removed at start-up.
- [ ] 4.2 Add the zip checks and streaming extraction from notes.md#d7 (R17). Verify: tests that
  build zips in memory with `../x.png`, `/x.png`, a symlink entry, a nested zip, `a/1.png` with
  `b/1.png`, and a header that understates its size each fail before OCR with nothing outside the
  job folder; `chapter/p1.png` is accepted as `p1.png`; `__MACOSX/` entries are skipped.
- [ ] 4.3 Accept `upload_id` and `document` in `start_ocr_job`; a `document` must be an uploaded
  PDF or zip, and images and zips are counted at start (D5, D7, R1, R4). Verify: client tests for
  both inputs, an unknown id, a result `.txt` id refused, an upload with no files yet, and a
  501-entry zip refused at start.
- [ ] 4.4 Swap server paths in every job and tool error for the caller's own names (R23). Verify:
  a test with an unreadable uploaded `p7.png` checks that the error names `p7.png` and contains
  neither the resolved `WORK_DIR` nor the resolved `OUTPUT_DIR`; the job id itself may appear.

### 5. Documentation

- [ ] 5.1 Add the HTTP part to the README (running with `--mode http`, the token, uploads, routes,
  all limits) and the uploads, storage and security-model sections to `docs/ARCHITECTURE.md`,
  each attack mapped to its defence as in pandoc-mcp. Verify: every `SCANSCRIBE_MCP_*` variable
  in `config.py` appears in the README table.
- [ ] 5.2 Add `.env.example` with the token and URL variables. Verify: `gitleaks` in CI passes and
  `.env` stays ignored.
- [ ] 5.3 Run the HTTP server locally with `--extra gpu`, upload a self-made folder of images
  through the browser form and a zip with curl, and record the check in
  `docs/demos/<date>-http-check/README.md`. Verify: the record states the result, device, page
  counts and that no book material was used.
