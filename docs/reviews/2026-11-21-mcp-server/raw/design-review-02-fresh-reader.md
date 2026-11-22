File read: /home/geo/develop/projects/scanscribe-mcp/docs/plans/2026-11-21-mcp-server/plan.md (read once; I opened no other files).

## From the Summary

The change turns scanscribe-mcp into an MCP server that lets an agent OCR a scanned PDF or a set of page images into text with page markers, using scanscribe v0.2.0's library API. The work is organised as jobs: the agent starts one, polls its progress, can cancel it, and then fetches the text in one of four ways (inline, page slices, a download URL, or a local file). A single worker thread runs jobs one at a time, because the engine and pdfium can't safely run twice in one process. The plan copies pandoc-mcp's layout and security model and ships in three slices: stdio, then HTTP with uploads, then a GPU Docker image. The main risks are hostile uploads (zip bombs, huge PDF pages), book content or server paths leaking into logs and errors, and a container that can't see the GPU.

## From the whole plan

The plan adds a Python package `scanscribe_mcp`, built on the owner's mcp-service-kit, with six tools. Four are job tools: start, status (with a bounded wait), cancel and result. Two are upload tools that work only over HTTP: create link and check upload. Behind the tools sit a FIFO queue, one worker thread, an engine that loads on the first job and reloads only when the language changes, and from phase 02 a document store for uploads and results that is purged after a retention period. The reason is that OCR of a 20–100 page chapter takes minutes, too long for one tool call to block, and remote agents can't hand the server a file path. Jobs, upload links and a GPU-capable Docker image fix that. Many requirements are defensive: input and option limits, safe zip unpacking, a bearer token, logs free of book content, errors free of server paths, and tests that never import Paddle.

## How the existing system works, per this plan

scanscribe is a separate library and command-line tool. It can already OCR a chapter from the command line, and v0.2.0 exposes a public API: `load_engine`, `open_source` (which runs a pre-check that reads every page and reports no progress), `ocr_source` with an `on_page(n, total)` callback that can stop the run by raising, and `format_pages`. Its output is text with a `--- Page N ---` line before each page, and its files are ordered by natural file-name order. It renders PDFs with pdfium, imports Paddle only inside `load_engine`, and prints an install message naming `uv sync --extra gpu/cpu` when no engine is installed. scanscribe-mcp itself is not deployed yet and seems to be close to empty. The plan names pandoc-mcp, a sister server, as the source of its layout, upload links, document store and security model.

## Summary vs plan

- Major · Summary / D6, R20: The Summary ties the document store to HTTP ("or HTTP with a bearer token, upload links and a document store"). D6 and R20 say every result is stored on both transports from phase 02. Only the download URL is HTTP-only.
- Major · Summary / Risks: The Summary leaves out the risk that a page hangs in the engine or pdfium. Cancelling can't stop such a job, and only a restart recovers. This is a real operational limit of the one-worker design.
- Nit · Summary / D6: The diagram and the text imply results always come from the document store. In phase 01 they are kept in memory on the job.
- Nit · Summary / R13: "Inline up to 50,000 characters" is a configurable default (`SCANSCRIBE_MCP_MAX_INLINE_CHARS`), not a fixed limit.
- Nit · Summary / D3: The engine is also dropped after an engine error, not only reloaded when the language changes.
- Nit · Summary / Terms, D7: Inputs are described as "a scanned PDF or a set of page images", but a zip upload and a stored document id are also inputs.
- Nit · Summary: The claim that "the engine and pdfium aren't safe to run twice in one process" isn't backed up anywhere else. D2's reasons are a FIFO order and avoiding a second GPU context.

## Sections I couldn't paraphrase

No Blockers. I could paraphrase every section. "Decision log" is empty. "Phases" gives task counts (0/15, 0/14, 0/8) for tasks that aren't in this file, but that doesn't stop me paraphrasing it.

## Unexplained project-specific terms

- Nit · Summary: "pandoc-mcp" is used from the first paragraph but explained only in Links.
- Nit · D8: `safe_filename` is never defined. Its source, and whether it changes names in a way that affects R18 ordering, is unknown.
- Nit · D6: "pandoc-mcp-style `DocumentStore`" is defined only as "one folder per random id".
- Nit · D5: `transcribe` is a scanscribe function that doesn't appear in the Terms list of the API.
- Nit · D1: `AppConfig`, `BaseServerConfig`: which settings the kit supplies is never stated.
- Nit · What changes: the `gpu` and `cpu` extras and "the PaddlePaddle uv settings copied from scanscribe" are not explained.
- Nit · D10: "Task 01/4.2" points to a task list that isn't in the plan.
- Nit · Rollout: `data/documents` and `data/work` appear to be the defaults for `OUTPUT_DIR` and `WORK_DIR`, but the plan never says so.
- Nit · Impact: `docs/demos/`, `docs/decision-log.md` and `AGENTS.md` are listed as touched but are never mentioned in What changes or any phase.
- Nit · R17: "page images" never says which file types count.
- Nit · Throughout: "the owner" is never identified.

## Places where the parts don't connect

- Major · R2 / Terms "Local paths" / R15: Local paths can be turned off over stdio with `SCANSCRIBE_MCP_ALLOW_LOCAL_PATHS=false`, and the R2 error then "names upload links instead". But upload tools are HTTP-only, so a stdio server with local paths off has no way to receive input, and the error points to a feature that doesn't exist there.
- Major · D4 / D5 / R4 / R27 / Terms "Step": The order of engine loading against input checks is never stated. D5 lists the page-size check, `open_source` and the page count but doesn't say where the engine loads. D4 checks cancel "after the engine loads and after the pre-check", and the Step order (loading engine, checking pages, recognizing) suggests the engine loads first. If so, a 501-page PDF, a hostile zip or an oversized page would still trigger a model download and GPU load before failing.
- Major · R18 / R17 / D7: Duplicate names are handled for zips only (R17). An upload of images that are stored one per random-id folder could contain two `p1.png` files, or names that `safe_filename` changes into the same name. The plan doesn't say how the job folder is laid out or how such a clash is handled, and R18's order depends on those names.
- Major · R13: The plan doesn't say what happens when a requested page range is itself longer than the inline limit.
- Major · Risks (last bullet) / R23 / R26: The way paths are kept out of errors ("the server swaps paths in scanscribe's messages for the caller's names") appears only in Risks, with no Decision behind it. R26 (phase 01) already needs path-free messages, while R23 belongs to phase 02.
- Major · R6 / R7: It's unclear whether a job past the queue timeout but not yet marked `expired` counts toward the 20-job queue limit. It's also unclear who marks it expired: a lazy check on read, the worker, or a timer.
- Nit · D3 / R26: "After an engine error the engine is dropped". It isn't clear whether R26's `RuntimeError` on page 2 counts as an engine error.
- Nit · D7: Starting a job "snapshots files already received in full". Files still uploading are silently left out, and the plan doesn't say whether a rejected start (R1, R3, R6) still closes the link.
- Nit · R14: The plan doesn't cover an existing file, a relative path or a missing parent folder.
- Nit · Terms "Document": a `document` id input is useful only for HTTP uploads. It's unclear whether a single uploaded image can be a `document` input.
- Nit · R24: there's no mechanism for "fail if paddle is ever imported" (for example a test guard).
- Nit · Open questions: it says the owner's answers are "recorded in D7, R3 …", but those sections don't mark which parts are the answers.
- Nit · D9: "ENGINE=cpu exists but isn't checked": unclear whether "checked" means validated or tested.
- Nit · D1, D7, D9, D10, Terms: these point to notes.md for details. Each still reads on its own, so this is not a gap.

## Readability

- Nit · Summary: "The layout and security model are pandoc-mcp's (D1, D8): stdio with `input_path`, or HTTP with …". I had to reread it; the colon makes the transports read as the security model.
- Nit · Summary: "An agent starts a job, follows its progress … or into a local file over stdio" is about 40 words with a nested list.
- Nit · R8: the single sentence with semicolons packs in five conditional fields. I had to reread it.
- Nit · D2: "The job table, under a lock, is the truth" needed a reread.
- Nit · D6: "with options and page count, never text, in `meta.json`" needed a reread.
- Nit · R15 holds five rules: upload-only, TTL, closing after `max_files`, the default of 100 and the cap of 200.
- Nit · R17 holds four rules: images only, page limit, unpacked size, and paths staying inside the job folder.
- Nit · R22 holds two rules: what is forbidden in logs and how things are named instead.
- Nit · R10, R19, R20 and R25 each hold two rules.
- Nit · R4 and R17: the page limit is stated twice.
- Nit · R16 and R17: `SCANSCRIBE_MCP_MAX_UPLOAD_BYTES` serves as two different limits (total per link and unpacked zip size), which is easy to misread.
- Nit · R23, R26 and Risks: "no server paths" is stated three times in different words.
- Nit · R22 and Risks: the log rules are repeated.
- Nit · Terms "Local paths", R2 and R14: the local-path rule is stated three times.
- Nit · Non-goals and Links (ADR-0003): "one job at a time / own repository" is repeated.
