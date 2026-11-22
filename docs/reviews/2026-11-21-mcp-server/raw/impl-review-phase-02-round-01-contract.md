<!-- Re-typed by the coordinator: save-report refused twice, because the reviewer delivered its
report as a hand-back message rather than as its final result, so the transcript held no report
to copy. The text below is the reviewer's report as delivered, unedited. -->

## Review of phase 02 (diff 872ec10..925f427), contract lens

I read the diff, the plan, phase 02 and notes.md, and checked the installed python_multipart and fastmcp source where the code depends on them. I ran nothing that writes files.

Most promises have code that enforces them and a test that would fail without that code:

- R19: auth and the start-up check (test_http_auth.py).
- R15: expiry, used-up links and an upload that finishes after expiry (test_upload_routes.py).
- R16: the declared-length and streaming 413s.
- R17: every hostile-zip case, plus a streaming-count test (test_zips.py).
- R18: natural order with the fake engine and with real curl.
- R20: result storage, the exact download, the purge timer that spares a live job (test_results_store.py), and the document route (test_documents.py).
- R23: test_http_messages.py.
- R28 over HTTP: exit code 70 (test_http_process.py).
- D12: the lock and the stale-folder clean-up.
- D8: the access log is off (a real-process check in test_http_logs.py).
- R29: duplicate names and refusals that leave the link open.

These are the gaps.

### Major

**M1 · A cut-off multipart body is stored as a complete file (R15, R29; task 3.2 says "a file is stored only after its last byte").**
- Location: /home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/uploads.py:225-231 and :308-312.
- Cause: `receive()` relies on `self._parser.finalize()` to reject an unfinished body, but python_multipart's `MultipartParser.finalize` does nothing (`.venv/.../python_multipart/multipart.py:1621-1630`: "TODO: verify that we're in the state MultipartState.END … pass").
- Scenario: a POST whose body ends without the closing boundary, either with a Content-Length that matches the cut body or a chunked stream that ends cleanly. For example, the headers of `name="file"; filename="p1.png"` followed by half the PNG bytes.
- Wrong outcome: `_on_part_end` never runs, yet `_commit` still stores the half file and the route answers 200. A part that has headers and no data at all is stored as a 0-byte file, which also skips the 400 for empty files.
- Fix: track whether each part reached `on_part_end`, or whether the parser got to its end state.
- Test that would expose it: in test_upload_routes.py, post `multipart(("p1.png", png()))` with its final `--boundary--` line removed, then expect 400 and `stored_count == 0`.

**M2 · An upload that has started but whose part headers haven't arrived yet doesn't count as in progress, so it lands on a closed link (R29, D7, R15).**
- Location: /home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/uploads.py:279-284 and :119-122; /home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/service.py:165-187; /home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/ocr_service.py:255-258.
- Cause: `links.begin(grant)` runs only when a part's headers have been parsed. The route checks the grant before the body arrives, then awaits `request.stream()`. `_on_headers_finished` checks `grant.remaining` but not `grant.closed`, and `finish()` appends to `grant.files` unconditionally.
- Scenario: request B passes `for_token`, and `start_ocr_job(upload_id)` runs on the event loop before B's first body chunk is parsed. At that moment `in_progress == 0` and `files` is non-empty, so the job takes a snapshot and closes the link. B's file is then stored and appended to a closed grant.
- Wrong outcome: the uploader gets 200, but the page is not in the job. R29 says the start "must refuse while a file is still arriving", and D7 says starting a job closes the link.
- Related mismatch: docs/ARCHITECTURE.md:84 claims the start and the upload route "never interleave", which is wrong at the route's await points.
- Observability: test_upload_jobs.py:293 fakes the in-progress state by calling `uploads.begin(grant)` directly. No test runs a real request in flight while the job starts.
- Fix: call `begin` per request at route entry, or refuse parts once `grant.closed` is set.
- Test that would expose it: stream a body with `chunked(..., between=...)` that calls `start_ocr_job` before the first chunk, then expect either a refusal or the upload not being stored.

**M3 · The size of part headers has no limit, and chunked requests skip the declared-length check (R16; the AGENTS.md hard constraint "size and page limits on every input").**
- Location: /home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/uploads.py:264-272 (`_header_name +=`, `_header_value +=`, `_headers` dict); /home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/service.py:171-176 (`declared = int(... or 0)`).
- Cause: only part data is counted. File data counts against the per-file and per-link limits, and other fields count against FIELD_LIMIT, but header bytes count against nothing.
- Scenario: anyone with a valid link sends a chunked POST (no Content-Length) whose single part carries a `Content-Disposition` value, or many header lines, of several GB.
- Wrong outcome: memory grows without bound until compose's memory limit kills the process. Phase 02 has no compose file, so on a bare host nothing stops it.
- Test that would expose it: stream an 80 KB header value in chunks and expect 400 or 413.

**M4 · The download capability ends up in the logs (D8, R22; task 1.2 says "no record contains … a document id path").**
- Location: /home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/ocr_service.py:545, `logger.info("job %s: result stored as document %s", job.id, document.id)`.
- Cause: the URL is `/documents/<document id>/ocr-<job id>.txt`, and the route needs no token. This one line holds both parts, so anyone who can read the logs can rebuild the URL and download the OCR text.
- Evidence: D8 turns the access log off "because paths hold tokens and ids", and ARCHITECTURE.md calls a download URL a "shared secret".
- Observability: test_http_logs.py:71 only forbids the full path `s.path(url)`, so it passes.
- Fix: drop the document id from the log line.
- Test that would expose it: also forbid `result.structured_content["document"]` in the logs.

**M5 · Over HTTP, the error for `output_path` doesn't name upload links (R2).**
- Location: /home/geo/develop/projects/scanscribe-mcp/src/scanscribe_mcp/ocr_service.py:291-295.
- Contract: R2 says that over HTTP, "a call passes `input_path` or `output_path`, then it returns a tool error that names upload links", and task 1.1 says the same.
- Actual: the message is "output_path is not accepted over HTTP … Get the text inline or in page ranges". It names neither upload links nor the download URL, which is the obvious alternative over HTTP.
- Observability: test_http_auth.py:67 matches only "output_path is not accepted over HTTP".
- Rated Major because it's a literal unmet Then clause. The better fix may be to reword R2 for `output_path` so the message points at the URL, but that's the engineer's call.

### Nits

- **N1** · documents.py:68: `safe_filename` cuts names to 120 characters, which can drop the extension. `plan_upload` then skips that image as "not an image", so a page with a very long name goes missing from the job with no error (R18, D7).
- **N2** · uploads.py:492: zip entries are written under their raw base names, not through `safe_filename`. D8 says "`safe_filename` on every uploaded name". Traversal is blocked, but control characters or names over 255 bytes reach the filesystem and the error text.
- **N3** · uploads.py:284-286: if `store.begin` raises after `links.begin`, the part was never added to `_parts`. So `abort` never gives back its `in_progress`, and every later start on that link is refused with "still arriving". The OSError also goes unhandled to uvicorn, whose traceback can include a stored path with the uploaded file name (from `commit`'s `os.replace`), which R22 forbids.
- **N4** · uploads.py:470-475: `count_zip_pages` never uses its `max_pages` argument, and it counts non-image entries. A zip of 500 images plus `readme.txt` is refused at start as "501 pages" rather than "not a page image".
- **N5** · ocr_service.py:255 vs `JobTable.live_documents`: a document can be purged between `store.get` in `_document_input` and `table.submit`. Only a document right at the retention age is affected, and the job then fails at run time. It is a tiny window (R20).
- **N6** · ocr_service.py:598: zip extraction of up to 2 GB runs inside the timed `checking pages` step. On a slow disk the watchdog can fire and exit the HTTP process. That is consistent with R28's wording but may not be intended.
- **N7** · ocr_service.py `scrub` and `_folder_spellings`: with the default relative `data/work` and `data/documents`, the bare string "data/work" is replaced anywhere in an error, including in the caller's own names (R23).
- **N8** · test_upload_routes.py:93-99: the 250 MB declared-length 413 is tested only with `max_files=1`. With a default link (100 files), the declared check allows 250 MB and only the streaming check refuses it. That path is tested at small limits, not at R16's defaults. The behaviour is correct; only the coverage differs.
- **N9** · docs/ARCHITECTURE.md:84: the "never interleave" claim is inaccurate (see M2).
