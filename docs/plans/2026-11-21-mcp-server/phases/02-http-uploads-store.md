---
phase: 2
title: HTTP, token, uploads and the document store
status: draft
branch: null
base: null
delivers: [R15, R16, R17, R18, R19, R20, R23]
design_review: { status: none, rounds: 0, last: null }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 02 · HTTP, token, uploads and the document store

## Goal

`scanscribe-mcp --mode http` serves all six tools behind a bearer token. A remote agent uploads
page images, a PDF or a zip through a link, starts a job from the `upload_id` or a stored
`document` id, and gets the text inline, in slices, or by download URL.

## Tasks

### 1. Authentication

- [ ] 1.1 Add `auth.py` (`BearerTokenVerifier`) and the server's `create_auth_provider` and
  `validate_configuration` for `SCANSCRIBE_MCP_TOKEN` (D8, R19). Verify: HTTP tests through
  `httpx.ASGITransport`: no token and a wrong token get 401, the right one works; start-up
  without a token fails unless auth is off.

### 2. Document store

- [ ] 2.1 Add `documents.py` from pandoc-mcp (`DocumentStore`, `safe_filename`, purge) with the
  MIME types this server needs, and the `/documents/<id>/<filename>` route (D6, R20). Verify:
  unit tests for save, get, a wrong filename, a malformed id, and purge with an old mtime.
- [ ] 2.2 Save each succeeded job's text as `<input name>.txt` with options and page count in
  `meta.json`, keep the pages for slices, and return the id and URL from `get_ocr_result`; purge
  at most once an hour during a job (D6, R20). Verify: a client test downloads the URL and gets
  exactly the result text; `meta.json` contains no recognized text.

### 3. Uploads

- [ ] 3.1 Add `uploads.py` from pandoc-mcp with `max_files` up to 200 and a per-grant byte total
  (D7, R15, R16). Verify: unit tests with an injected clock for expiry, used-up links, the active
  link limit and the byte total.
- [ ] 3.2 Add the `/upload/<token>` GET form and POST route, with the per-file and per-upload size
  checks done while streaming (R15, R16). Verify: HTTP tests for a good upload, an expired link
  (404), a 250 MB declared length and an over-limit stream (413), an empty file (400), and a
  name with `../` stored as a plain name.
- [ ] 3.3 Add `features/create_upload_link/tool.py` and `features/check_upload/tool.py`, with
  `wait_s` (D7, R15). Verify: client tests for the link, the curl command text, `check_upload`
  before and after an upload, and both tools over stdio returning "needs the HTTP server".

### 4. Jobs from uploads and documents

- [ ] 4.1 Add the job folder: build `WORK_DIR/<job id>/pages/` from an upload's images or a zip,
  or use a stored PDF in place, and delete the folder when the job ends (D7, R18). Verify: unit
  tests for each upload kind, a refused mix, and natural order (`p1`, `p2`, `p10`) seen by the
  fake engine.
- [ ] 4.2 Add the zip checks and streaming extraction from notes.md#d7 (R17). Verify: tests that
  build zips in memory with `../x.png`, an absolute name, a symlink entry, a nested zip, a
  duplicate name, `__MACOSX` entries, and a header that understates its size; each fails before
  OCR, or is skipped for hidden names, and nothing appears outside the job folder.
- [ ] 4.3 Accept `upload_id` and `document` in `start_ocr_job`, with the page-count check from file
  names at start (D5, R1, R4). Verify: client tests for both inputs, an unknown id, an upload
  with no files yet, and a 501-entry zip refused at start.
- [ ] 4.4 Strip server paths from every job and tool error: replace the job folder and store
  paths in scanscribe's messages with the caller's own names (R23). Verify: a test with an
  unreadable uploaded `p7.png` checks that the error names `p7.png` and contains neither
  `WORK_DIR` nor `OUTPUT_DIR`.

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
