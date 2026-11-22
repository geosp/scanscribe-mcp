## Phase 02 implementation review: contract lens (diff 872ec10b..beb0ef1c)

I found one Major mismatch and a set of Nits. Every other promise I traced has enforcing code and a test that would fail without it.

### Findings

**F1 · Major · D7 (and R29's "refusal leaves the link open" flow) · `src/scanscribe_mcp/documents.py:99-101`, `:147`; `src/scanscribe_mcp/ocr_service.py:344-347`**
- **Problem:** an uploaded file named `meta.json` overwrites, and is overwritten by, the store's own metadata file. That makes the whole link unusable.
- **Scenario:** a user uploads `p1.png`, `p2.png` and a stray `meta.json` (for example from a scanner app or a folder drop) through one link, then calls `start_ocr_job(upload_id=…)`.
  - `safe_filename("meta.json")` keeps the name.
  - `PendingDocument.commit` does `os.replace(part, folder/"meta.json")`, then `_write_metadata` writes over that same file.
  - `DocumentStore.get` leaves out `METADATA_FILE` (line 147), finds no file and returns None.
  - `_upload_input` then raises "the files of this upload are no longer stored; upload them again" (ocr_service.py:346-347).
- **Wrong outcome:** D7 says "hidden and non-image files are skipped", so the job should start from the two PNGs. Instead it is refused on every attempt. `check_upload` also silently drops the file. The user is told the files expired, which is false. Uploading a name that reduces to `meta.json` (such as `../meta.json`) has the same effect.
- **Test that would expose it:** upload `("p1.png", png()), ("meta.json", b"{}")` and assert that `start_ocr_job` succeeds with `files == ["p1.png"]`.
- **Fix direction:** reserve the name in `safe_filename`/`begin` (for example by renaming it), or keep the metadata under a hidden name.

### Nits
- `tests/test_zips.py:73-89`, R17: R17's Given/When/Then says "when the job runs, then it fails before OCR". The code refuses hostile zips earlier, at `start_ocr_job` (`count_zip_pages`, ocr_service.py:380). The test accepts either outcome (`try/except Exception`), so no test pins which one happens, and none checks that the link stays open after a zip refusal (D7). Refusing earlier is stricter, so the outcome is acceptable.
- `src/scanscribe_mcp/config.py:83-90`, R16: the defaults are 200 MiB and 2 GiB, not the 200 MB and 2 GB the plan states. The test name says 200 MiB, so this looks deliberate. It is worth one line in the README.
- `tests/test_results_store.py:94`, task 2.2 ("the timer purges while no job runs"): the test sees the hourly purge only while a job is running, page 1 blocked. The idle purge at start-up has nothing to delete, so "purges while idle" is never observed despite the test's name.
- `src/scanscribe_mcp/uploads.py:426-435`, D7 / notes "copies if on another filesystem": the `shutil.copyfile` fallback after `os.link` fails never runs in tests, because tmp_path is one filesystem. Making `os.link` raise `OSError` in a test would cover it.
- `tests/test_http_curl.py:22`, R18 / task 5.3: the only zip test with a `p10` entry (natural order inside a zip) is skipped when `curl` is missing. `test_a_zip_is_unpacked` uses only p1 and p2, where alphabetical and natural order are the same. Add `p10.png` there so the zip order is covered without curl.
- `src/scanscribe_mcp/ocr_service.py:352-364`, D7: a `document=` start doesn't check the `hidden` metadata flag, so a hidden `.x.pdf` that `upload_id` would skip can still be OCR'd by its id. This is harmless; noted for consistency.
- `src/scanscribe_mcp/ocr_service.py:351-354` vs the purge thread (`ocr_service.py:577-583`), R20: purge reads `live_documents()` on another thread. A `document=` start can check the document at line 355 and then be queued just after purge has taken its keep set. If the document is just past retention it is then deleted under a queued job. The job fails cleanly ("no longer stored", or the PDF path is missing, in which case the R27 check is skipped and `open_source` reports it). Only inputs already past retention are affected.
- `src/scanscribe_mcp/uploads.py:260-270`, R16 / "stores nothing": if `commit` fails on the second file of a multi-file request, the first file stays stored and counted while the route answers 500. The plan promises nothing for store errors; noted because 500 differs from the request's all-or-nothing rule.
- `src/scanscribe_mcp/upload_page.html:51-67`, R29: the browser form sends one request per file in sequence, so `grant.requests` drops to 0 between files. A `start_ocr_job` in that gap takes a partial snapshot and closes the link. R29 only promises a refusal while a file is arriving, so this is a usability risk, not a contract break.
- `src/scanscribe_mcp/ocr_service.py:600-601`, R28: building the job folder, which includes unpacking a zip of up to `MAX_UPLOAD_BYTES`, is timed as part of `checking pages`. A very slow disk could hit the page timeout during unpacking and exit the HTTP process. This is consistent with the wording "checking pages step"; noted.
- `src/scanscribe_mcp/ocr_service.py:781-784` / `public_message`, R23: if scanscribe printed the job folder through a symlinked current folder in `Path.absolute()` form, `public_message` would not match it. `scrub` would then show `<server folder>/<id>/pages/p7.png` instead of `p7.png`. No server path leaks; noted only because I can't fully verify how scanscribe spells paths.
- `tests/test_upload_jobs.py:109-123`, task 4.1: the in-progress refusal test doesn't assert `closed is False` right after the refusal. The later real-upload test implies it, because the link still takes and uses the second file.

### Promises traced (enforcing code → test that would fail)
- **R2:**
  - Over HTTP, local paths are always refused: `config.py:145-148`, `ocr_service.py:287-305`, and the `output_path` check in `get_ocr_result/tool.py:199-201`. Test: `test_http_auth.py:61`.
  - The stdio `=false` case is from phase 01.
- **R15:**
  - Links expire, close after a job and get used up: `uploads.py:105-111`, `:142-147`, `:160-167`.
  - `max_files` is capped at 200 in `create_upload_link/tool.py:108-115` and `config.py:94-99`.
  - An upload that began in time may finish after expiry, because only `closed` is checked later: `uploads.py:272-274`.
  - Tests: `test_upload_routes.py:70`, `:151`; `test_uploads.py:21-91`.
- **R16:**
  - Declared length is checked in `service.py:367-379`; per-file and per-link bytes while streaming in `uploads.py:331-336`.
  - Tests: `test_upload_routes.py:86`, `:95`, `:109`, `:212`.
- **R17:**
  - Each zip rule is enforced in `uploads.py:459-504`; extraction counts bytes as they stream in `:519-543`.
  - Tests: `test_zips.py`.
- **R18:**
  - Order comes from `open_source` on the job folder.
  - Tests: `test_upload_jobs.py:50`; zips only in `test_http_curl.py` (see the Nit).
- **R19:**
  - `server.py:91-119`, `auth.py`.
  - Tests: `test_http_auth.py:23`, `:37`.
- **R20:**
  - The result is stored in `ocr_service.py:528-549` and the URL returned in `get_ocr_result/tool.py:229-233`.
  - Purge runs hourly and keeps live jobs' documents: `ocr_service.py:567-588`, `jobs.py` `live_documents`.
  - Tests: `test_results_store.py:34`, `:94`; `test_documents.py:61`.
- **R22:**
  - Every new logger call logs only ids, counts and exception classes; the access log is off (`server.py:96-108`).
  - fastmcp logs a ToolError without its message, and logs validation errors without input values (I checked its source in `.venv`).
  - Tests: `test_http_logs.py:52`, `:76`.
- **R23:**
  - `public_message` and `scrub`: `ocr_service.py:551-555`, `:590-593`, `:763-784`.
  - Tests: `test_http_messages.py`.
- **R28 (HTTP exit):**
  - `service.py:249-258`, `:297`.
  - Test: `test_http_process.py:19`.
- **R29:**
  - `requests` is counted from the moment the route takes a request (`service.py:382`); refusals happen in `ocr_service.py:332-336`; duplicate names are caught in `uploads.py:408-416`.
  - Tests: `test_upload_jobs.py:96`, `:109`, `:195`, `:222`.
- **D6:**
  - Over stdio nothing reaches disk: `service.py:278` (HTTP-only store). Test: `test_results_store.py:78`.
  - `meta.json` holds no text: `ocr_service.py:534-546`.
- **D7:** snapshot and close happen at `ocr_service.py:255-258`. Test: `test_upload_jobs.py:126`.
- **D8:** the hash, `token_urlsafe(32)`, `safe_filename` on every name including zip entries, and uuid4 ids are all in place.
- **D12:** lock and clean-up in `uploads.py:558-581`. Tests: `test_upload_jobs.py:168`, `:185`.
