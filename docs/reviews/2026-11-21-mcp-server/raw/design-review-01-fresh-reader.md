Plan reviewed: /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/plan.md. I read only this file and opened nothing it links to (no notes.md, no ADRs).

## From the Summary
The change turns scanscribe-mcp into an MCP server that lets an agent OCR a scanned PDF or a set of page images into text marked by page, using scanscribe v0.2.0's library API. Work runs as jobs: the agent starts one, polls its progress, can cancel it, and fetches the text. A single worker thread holds the engine and runs jobs one at a time from a queue, because the engine and pdfium can't safely run twice in one process. It copies pandoc-mcp's layout: stdio for local paths, and HTTP with a token, upload links and a document store. It ships in three slices: stdio, then HTTP, then a GPU Docker image. The main risks are a container that can't see the GPU and hostile uploads such as zip bombs.

## From the whole plan
The plan adds a new `scanscribe_mcp` package on mcp-service-kit v0.2.1 with six tools: start, status, cancel and result for jobs, plus creating and checking upload links. A FIFO queue feeds one daemon worker thread. That thread loads the engine lazily, through an injected factory, once per language. It opens the input, enforces a page limit, OCRs page by page with callbacks for progress and cancelling, and keeps the result in memory (phase 01) or in a file-based document store (phase 02). The reason is that OCRing a chapter takes minutes, so a blocking command-line call is too slow, and remote agents can't hand the server a path. Jobs with progress, cancelling, uploads and GPU support fix both. There are many safety rules: input validation, queue and size limits, safe zip expansion, a bearer token, no server paths or book material in logs or errors, and a clean stdout. Tests use a fake engine so CI never needs PaddlePaddle or a GPU.

## How the existing system works, per this plan
scanscribe is a separate library and command-line tool that can already OCR a book chapter. v0.2.0 added a public API (`scanscribe.__all__`) for this server. As far as the plan shows, that API includes `load_engine`, `open_source`, `ocr_source`, `format_pages`, `transcribe`, an `OcrEngine` protocol with one method, and `on_page`/`on_device` callbacks. Paddle is imported only inside `load_engine`, and its output is text with a `--- Page N ---` line before each page. scanscribe-mcp itself has nothing working yet ("Nothing is deployed yet"). pandoc-mcp, a sibling project by the same owner, provides the layout, upload links, document store and security model being copied. mcp-service-kit provides the base config, stderr logging and the rule that HTTP won't start without auth.

## Summary vs plan
- Major, Summary: it cites R15 and R16 for zip bombs, but the zip rules are in R17. R15 covers upload links and R16 covers sizes.
- Major, Summary: it leaves out the risk of book material or server paths leaking through logs and errors (Risks, R22, R23). That is a large part of the plan's design.
- Nit, Summary: "loads the engine once" leaves out the reload when a job's language changes (R11, D3).
- Nit, Summary: it cites the document store as "(D7, D8)", but the store is decided in D6.
- Nit, Summary: "then fetches the text" hides that text over 50,000 chars isn't returned inline (R13), and that stdio can write it to `output_path` (R14).
- Nit, Summary: it says nothing about results being held in memory in phase 01 and in the store only from phase 02 (D6).
- Nit, Summary: it doesn't mention the queue limits or expiry (R6, R7). This is acceptable for a summary.

## Sections I couldn't paraphrase (Blockers)
No Blockers. Every section could be paraphrased at least roughly. D10 comes closest: "the engine's swap of `sys.stdout`" and how fastmcp "points [fd 1] at stderr" only make full sense with notes.md#d10. I list it as Major under item 6.

## Project-specific terms used but never explained
- Major, D4, D5, Risks: "pre-check" is never defined. It seems to be something `open_source` does, maybe a check that every page is readable, but the plan doesn't say.
- Major, D5, D4: the scanscribe API functions `open_source`, `ocr_source`, `format_pages` and `transcribe` are never described. Their signatures, return values and what "closes the source" means are missing.
- Major, R1, Terms: the `document` input ("a stored document id") is unclear. Stored documents are OCR results and uploads, so it isn't clear what OCRing a stored document means, or how it differs from `upload_id`.
- Major, What changes, Terms: `check_upload` is named but not described beyond "to list what arrived". `create_upload_link` has no parameters listed apart from an implied `max_files`.
- Nit, Summary, D1, Links: pandoc-mcp is only explained indirectly, as the owner's other project.
- Nit, D1, D10, Links: "the kit", mcp-service-kit, `BaseServerConfig` and the kit's "auth provider".
- Nit, Summary, D4: pdfium.
- Nit, D3, D4: the `on_page` and `on_device` callbacks, and `JobCancelled`.
- Nit, D6, D8: `DocumentStore` and `safe_filename`, both assumed known from pandoc-mcp.
- Nit, What changes, D9: the "PaddlePaddle uv settings", the `gpu`/`cpu` extras and the cu126 wheels.
- Nit, Assumptions: PaddleX (as distinct from PaddlePaddle) and `PADDLE_PDX_CACHE_HOME`.
- Nit, Assumptions: the `uv_build` backend.
- Nit, D10: fastmcp.
- Nit, D10: "the engine's swap of `sys.stdout`".
- Nit, R18: "scanscribe's natural file-name order". The example helps, but the rule isn't stated.
- Nit, R3: the default of `SCANSCRIBE_MCP_LANGS` isn't given.
- Nit, Risks, D9, Rollout: "the owner" (who that is, and their RTX 3060).
- Nit, Why, Non-goals, Links: ADR-0001/2/3. The Links section summarises them in one line each, which is just enough.

## Places where the parts don't connect
- Major, Risks (pre-check bullet) vs Terms and R8: `get_ocr_job` reports `checking pages`, but that isn't one of the six job states. It's unclear whether it's a state, a sub-status or a progress field.
- Major, R2, Terms: local paths are allowed over stdio "by default", but the setting that changes this, and what it does over HTTP, is never named.
- Major, D6, R13, R20: over stdio from phase 02 on, it's unclear whether results also go to the document store or stay in memory. R13's "say how to get it whole" has no stated mechanism for stdio in phase 01, other than `output_path`.
- Major, Phases: the phase table has task counts but doesn't link to phase files or map requirements to phases. It's unclear which of R1–R25 phase 01 must meet, for example whether R14 and R24 fall in 01 or later.
- Major, D10, D1, D7, D9: these defer details to notes.md. D10's reasoning depends on them; D1, D7 and D9 mostly stand alone.
- Major, R22 vs R23: errors may name `p7.png`, but logs must never contain input file names. The plan doesn't say whether failed-job error messages are logged, or how they're scrubbed if so.
- Major, D7: two PDFs, or two zips, in one upload aren't covered. "Mixed sets are refused" doesn't settle it.
- Nit, R4: the outcome is "a tool error, or the job fails". D5 explains why both can happen, but the requirement alone isn't a single testable outcome.
- Nit, R7, R6: a timed-out job is only marked `expired` "when the worker reaches it". It's unclear what `get_ocr_job` reports before then, and whether it still counts toward the queue limit.
- Nit, R15: who sets `max_files`, and what its default is, isn't stated.
- Nit, R16: "one upload" is ambiguous: one link, one request or one file.
- Nit, R20: there is no mechanism or timing for deleting documents past retention.
- Nit, Assumptions: finished jobs stay listed for 24 h, but no requirement or setting backs this, and the phase 01 in-memory result vanishes with the job.
- Nit, Open questions: it says the answers are "recorded in D7, R3, …", but those sections don't mark which content came from the owner's answers.
- Nit, Decision log: the section is empty.
- Nit, R8: the device the fake engine reports isn't defined.

## Readability
- Nit, Summary: I had to reread "The server follows pandoc-mcp's layout and security model (D1): stdio … and HTTP with a bearer token, upload links and a document store (D7, D8)." The colon list mixes layout, transport and storage.
- Nit, D10: I had to reread "claims file descriptor 1 at start and points it at stderr". It's unclear which stream carries the protocol afterwards.
- Nit, D7: the heading "one PDF or one zip per link" conflicts with the body's "several images used as a folder".
- Nit, R17: the Given/When/Then line is about 45 words.
- Nit, Risks (last bullet): about 45 words.
- Nit, Repetition: "one job at a time" appears in the Summary, R5, D2 and Links (ADR-0003).
- Nit, Repetition: "local paths only over stdio" appears in Terms and R2.
- Nit, Repetition: "CPU image not checked" appears in Non-goals and D9.
- Nit, Multi-rule requirements: R3 has three rules (lang, dpi, columns).
- Nit, Multi-rule requirements: R8 has four (state, page/total, device, error).
- Nit, Multi-rule requirements: R10 has three (queued, running, finished).
- Nit, Multi-rule requirements: R13 has two (inline limit, page range).
- Nit, Multi-rule requirements: R15 has three (upload-only, TTL, max_files).
- Nit, Multi-rule requirements: R16 has two (per-file, total).
- Nit, Multi-rule requirements: R17 has four (images only, plain names, unique names, size and entry limits).
- Nit, Multi-rule requirements: R19 has two (401, refuse to start).
- Nit, Multi-rule requirements: R20 has two (store with id and URL, retention).
- Nit, Multi-rule requirements: R22 has two (no text, no file names).
- Nit, Multi-rule requirements: R25 has two (GPU, model cache).
- Nit, Untested rules: R3's `columns` range, R19's refusal to start and R20's retention have no Given/When/Then.
