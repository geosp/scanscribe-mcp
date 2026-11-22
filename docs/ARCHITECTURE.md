# Architecture

scanscribe-mcp wraps [scanscribe](https://github.com/geosp/scanscribe)'s public library API (`scanscribe.__all__`, pinned at a Git tag) in an MCP server built on mcp-service-kit. The layout follows the owner's pandoc-mcp. Decisions and their reasons are in [the plan](plans/2026-11-21-mcp-server/plan.md) (D1-D12).

## Layers

```text
MCP client ──▶ FastMCP (kit) ──▶ features/<tool>/tool.py ──▶ OcrService ──▶ JobTable
   (bearer token on /mcp over HTTP)                               │
                                                     worker thread ┼─▶ scanscribe
                                                     watchdog thread
uploader ──▶ /upload/<token> ──▶ UploadReceiver ──▶ DocumentStore ◀── purge thread (HTTP)
downloader ──▶ /documents/<id>/<name> ─────────────────┘
```

| Module | Role | Uses MCP? |
| --- | --- | --- |
| `server.py` | `ScanscribeMCPServer`: instructions sent to clients (one text per transport), the bearer-token provider, the token check at start-up, uvicorn's access log off; `main()` from the kit's `create_main_with_modes` | yes |
| `service.py` | `ScanscribeMCPService`: builds `OcrService` and starts its threads in `initialize()`, stops them in `cleanup()`, registers every `features/*/tool.py`. Over HTTP it also takes the `WORK_DIR` lock, builds the document store and upload links, and serves `/upload/<token>` and `/documents/<id>/<filename>` | yes |
| `auth.py` | `BearerTokenVerifier`: one static token, compared in constant time | yes |
| `features/<tool>/tool.py` | One MCP tool each: arguments, reply text and structured content | yes |
| `results.py` | `tool_errors()` turns a `ValueError` into a tool error; job status fields and replies | yes |
| `config.py` | `AppConfig`: the kit's `BaseServerConfig` (`MCP_*`) and `ScanscribeMcpConfig` (`SCANSCRIBE_MCP_*`) | no, but importing the kit loads fastmcp |
| `ocr_service.py` | `OcrService`: input and option checks, the worker, the engine cache, the watchdog, results | no (it imports `config.py`) |
| `jobs.py` | `Job`, `JobTable` (the job table under a lock) and the FIFO queue | no |
| `documents.py` | `DocumentStore`: one folder per random id, `meta.json`, streamed writes, purge; `safe_filename` | no |
| `uploads.py` | `UploadLinks` and `Grant`; `UploadReceiver`, the streaming multipart reader; what an upload becomes as a job input; zip checks and extraction; `WorkDir`, the locked work folder | no |

Callers' mistakes are raised as `ValueError` with a message meant for the caller. The tools wrap them in `tool_errors()`, so they reach the client as tool errors.

## One job at a time

scanscribe's engine swaps the process-wide `sys.stdout` while it runs, and pdfium isn't thread safe. So exactly one daemon thread, the worker, runs OCR, taking job ids from a `queue.Queue` in order. The tools run in the event loop and only read and change the job table, which guards every job with one lock and hands out copies.

The engine comes from an injected factory with `scanscribe.load_engine`'s signature. Production passes `load_engine`, and the tests pass a fake. The worker keeps one engine:

- it loads the engine at the first job;
- it drops the engine before loading one for another language;
- it drops the engine after any error raised inside it.

## A job, step by step

1. **`start_ocr_job`** checks that exactly one input was given, that local paths are allowed, and that `lang`, `dpi` and `columns` are within the configured limits. It checks that `input_path` exists. For a folder, it counts the page images and refuses more than `MAX_PAGES`. It also refuses the job if the queue is full or the server is stuck. Then the job is `queued`.
2. **The worker** takes the next queued job, skipping cancelled and expired ones, and marks it `running`. Everything below runs inside `redirect_stdout(sys.stderr)` and a catch-all.
3. **`checking pages`:**
   - For a PDF, the worker reads every page's size and refuses a page larger than `MAX_PAGE_PIXELS` at the job's dpi, before anything is rendered.
   - Then `scanscribe.open_source` runs its pre-check, which reads every page once.
   - A source with more than `MAX_PAGES` pages fails here, so a refused input never loads the engine.
4. **`loading engine`:** the engine is reused, or loaded through the factory, which reports the device.
5. **`recognizing`:** `scanscribe.ocr_source` calls `on_page(n, total)` before each page. The worker records the page and its start time there, and raises to stop when the job was cancelled.
6. **The end:** the pages are kept on the job, and `get_ocr_result` formats them as scanscribe's `format_pages` does.
   - An error from scanscribe fails the job with its message, after the input's server path is replaced by the caller's own name for it.
   - Any other error fails it with `OCR failed (<error class>)`.
   - Either way, the worker goes on to the next job.

Cancelling sets a flag on the job. The worker checks it after the pre-check, after the engine loads, and before each page.

## The watchdog

A second thread checks the running job every second. It times the `checking pages` step, and then each page from when the job reaches it until the next page is ready, which covers page 1's render. It doesn't time the engine load, because a first run downloads models. When one of these passes `PAGE_TIMEOUT_S`, the watchdog:

- fails the job, naming the timeout;
- fails every queued job with a request to restart the server;
- marks the service stuck, so `start_ocr_job` refuses new jobs until the server restarts.

The worker can't be killed, and the engine may still be busy with the page. If it returns late, its results are ignored. Over HTTP the process then exits with code 70 (`os._exit`, after flushing the logs: a graceful shutdown could wait for ever on the stuck worker), so its supervisor restarts it. A restart forgets the jobs and links in memory, and the next start-up deletes the job's leftover folder.

## Uploads

```text
agent ──create_upload_link──▶ server        (over /mcp, with the bearer token)
      ◀── /upload/<token> link, upload_id
user or shell ──POST /upload/<token>──▶ server ──▶ document store
              ◀── names, sizes, remaining (no ids)
agent ──check_upload(upload_id) / start_ocr_job(upload_id)──▶ server
```

The link is the only upload credential: `secrets.token_urlsafe(32)`, kept as a sha256 hash in memory. It takes `max_files` files (at most 200) and `MAX_UPLOAD_BYTES` in all, and accepts new uploads for `UPLOAD_LINK_TTL_S`. The link is checked when an upload starts, so an upload that began in time may end later; uploads in progress count against the link's files and bytes. The non-secret `upload_id`, which only the MCP caller gets, lists the files and starts the job, so an uploader never learns the document ids. A restart closes every link.

`UploadReceiver` feeds the request body to python-multipart's streaming parser. Each file part goes straight to a hidden part file in a new document folder, and the per-file and per-link limits are checked on every chunk, so an oversized stream stops early with 413. A request's files are stored (renamed into place, with `meta.json`) only once the whole request has arrived; on any error none of them is. Names go through `safe_filename`; a name that was hidden (`.DS_Store`) is marked in `meta.json`.

### From an upload to a job

`start_ocr_job(upload_id=...)` runs in the event loop, like the upload route, so the two never interleave. It refuses while an upload is arriving, then decides what the link's files are: one PDF, one zip, or page images with distinct names. Hidden files and other files are skipped; anything else is refused and the link stays open. Images and zip entries are counted against `MAX_PAGES` here. Once the job is created it keeps the document ids, the link closes, and a later start on the same `upload_id` reuses those ids. `start_ocr_job(document=...)` takes one uploaded PDF or zip; result `.txt` documents and images are refused.

In the worker, during `checking pages`:

| Input | What the worker reads |
| --- | --- |
| a PDF | the stored file, in place |
| images | `WORK_DIR/<job id>/pages/`, hard links to the stored images (copies across filesystems) |
| a zip | `WORK_DIR/<job id>/pages/`, the zip's pages unpacked flat |

The job folder is deleted when the job ends, whatever the end. Pages then go through `open_source` like any folder, so they keep scanscribe's natural order.

A zip is checked from its central directory before anything is written. Its entries must not start with `/` or `\` or a drive letter, or contain `..`, and must not be symbolic links. Folders, hidden names and `__MACOSX/` are skipped. Every other entry must be a page image, so a nested zip is refused. Base names must be distinct, because the folders are dropped. There may be at most `MAX_PAGES` entries and `MAX_UPLOAD_BYTES` declared bytes. Extraction counts the bytes it writes as they stream, and `zipfile`'s CRC check catches an entry whose header lies about its size.

### The work folder

`WORK_DIR` belongs to one HTTP server. At start-up the server takes an exclusive `flock` on `WORK_DIR/.scanscribe-mcp.lock`, refusing to start if another process holds it. Then it deletes the entries named like job ids (32 hex characters), which no job survives a restart to use, and nothing else.

## Storage

```text
OUTPUT_DIR/<uuid4 hex>/<filename>   an upload, or a result ocr-<job id>.txt
OUTPUT_DIR/<uuid4 hex>/meta.json    kind, created, and for a result: job id, options, page count
```

Over HTTP the worker saves each succeeded job's text as `ocr-<job id>.txt` before it marks the job succeeded; `get_ocr_result` returns the document id and URL. `meta.json` never holds text. A purge thread deletes documents older than `RETENTION_DAYS` once an hour, also while no job runs, except documents a queued or running job reads. Over stdio there is no store: results stay in memory and nothing is written but `output_path`.

## Security model

Over HTTP the threat is an untrusted client or uploader, and uploaded files built to break the server. Each defence maps to an attack that a test tries:

| Attack | Defence |
| --- | --- |
| Using the tools without the token | Bearer token on `/mcp`, compared in constant time; HTTP refuses to start without one unless `--no-auth` |
| Reading or writing server files through `input_path` or `output_path` | Never accepted over HTTP, whatever `ALLOW_LOCAL_PATHS` says |
| Handing the server token to users or shells to upload | Upload links: upload-only, minutes, `max_files`, a byte total, hashed in memory |
| Reusing an expired, used-up or closed link | 404, nothing stored |
| A huge upload filling the disk | `MAX_FILE_BYTES` per file and `MAX_UPLOAD_BYTES` per link, checked on the declared length and on every streamed chunk |
| Path traversal in an uploaded name | `safe_filename` keeps only a plain name |
| Zip slip: `../x.png`, `/x.png`, `C:/x.png`, a symlink entry | Refused from the central directory before anything is written |
| Zip bomb, or a header that understates an entry's size | Declared total checked first, then a running count while streaming, and the CRC check |
| A nested zip, or two pages that collapse to one name | Only page images, distinct base names |
| A PDF page that renders to gigapixels | `MAX_PAGE_PIXELS` checked from the page sizes before anything is rendered |
| Too many pages or jobs | `MAX_PAGES` at start and after the pre-check; `MAX_QUEUED`; `UPLOAD_LINK_MAX_ACTIVE` |
| A page that hangs the engine | The watchdog fails the job and the process exits, so its supervisor restarts it |
| Guessing download URLs | Random uuid4 ids; the file name must match too |
| Server paths, book text or tokens leaking through errors and logs | Errors name the caller's own files; every server folder is scrubbed; logs carry ids, kinds, sizes, counts and error classes; uvicorn's access log is off |
| Two servers sharing `WORK_DIR` and deleting each other's job folders | The `flock` on `WORK_DIR` |

Accepted risks: a download URL is a shared secret, and anyone holding one can fetch that document until it is purged; an upload link shows up in transcripts, which is acceptable because it is useless once spent, closed or expired; jobs and links live in memory, so a restart forgets them.

## stdout and logs

Over stdio, stdout carries the MCP protocol. Two things keep other writes off it:

- **The transport:** while serving, it points file descriptor 1 at stderr and writes the protocol through its own copy of the original descriptor.
- **The worker's per-job redirect:** a buffered `print()` would otherwise be written at exit, after the transport has handed descriptor 1 back.

The kit configures logging to stderr. Logs carry job ids, input kinds, sizes, page counts and error classes, never file names, recognized text, error messages or upload tokens. Over HTTP, uvicorn's access log is off, because request paths hold upload tokens and document ids. `tests/test_stdio.py` runs the real server in a subprocess, with a fake engine that prints, and checks that every stdout line is an MCP message.

## Tests

Every test runs on the base install: no GPU and no PaddlePaddle.

- **Fakes:** `tests/fakes.py` holds the fake engine and factory, a clock that moves only when a test says so, and builders for small images and PDFs. No book material is used.
- **Tools:** tool tests use a real `fastmcp.Client` against the in-process server.
- **HTTP:** `tests/http_helpers.py` runs the HTTP server's ASGI app in process, with an MCP client and an `httpx` client; multipart bodies are built by hand so a test can send them in chunks. `tests/http_launcher.py` runs the real server in a subprocess, for the watchdog's exit and the access-log check. Zips, PDFs and images are built by the tests.
- **Engine guard:** `tests/paddle_guard.py` fails the session if `paddle` or `paddleocr` was imported.
