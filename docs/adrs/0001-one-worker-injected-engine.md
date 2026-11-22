---
status: accepted
date: 2026-11-22
supersedes: null
plan: docs/plans/2026-11-21-mcp-server
---

# ADR-0001: One OCR worker per process, with an injected engine

## Context

scanscribe's OCR engine swaps the process-wide `sys.stdout` while it recognizes a page, and pdfium, which renders PDFs, isn't thread safe. Two jobs at once in one process would corrupt each other's output and could crash the renderer. Over stdio, stdout also carries the MCP protocol, so a stray write breaks the session. A chapter takes minutes, longer than a tool call should block, and a page can hang inside the engine where no cancel reaches it.

Rejected: a thread per job with `asyncio.to_thread` (it needs its own lock to serialize, so it gains nothing); a process pool (a second engine and GPU context per process, and models loaded twice); loading the engine at start-up (every stdio session would hold GPU memory and block on a model download).

## Decision

We will run OCR on exactly one worker thread per process, taking jobs from a FIFO queue, with a watchdog that fails a job whose page passes `SCANSCRIBE_MCP_PAGE_TIMEOUT_S` and, over HTTP, ends the process with code 70 so its supervisor restarts it. The engine comes from an injected factory with `scanscribe.load_engine`'s signature, loaded at the first job and again only when the language changes; each job runs with `sys.stdout` redirected to stderr.

## Consequences

- Jobs queue: throughput is one job at a time per process, and scaling means more processes or containers, each with its own engine and GPU memory.
- Tests use a fake engine through the factory, so the suite and CI never need PaddlePaddle or a GPU, and a guard fails the session if `paddle` is imported.
- A hung page costs a restart over HTTP, which forgets in-memory jobs and upload links; over stdio the server refuses new jobs until restarted.
- Alternating languages reload the engine for every job; that cost was accepted.
- Any new code that runs OCR must go through the worker; nothing else may call the engine or pdfium.
