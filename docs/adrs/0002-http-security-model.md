---
status: accepted
date: 2026-11-22
supersedes: null
plan: docs/plans/2026-11-21-mcp-server
---

# ADR-0002: The HTTP security model

## Context

Over HTTP the server is reachable by remote agents, and the files it handles are scanned books: material that must not leak through paths, logs or links. Remote agents can't hand the server a path, and handing users or shells the server's token to upload would give them every tool. Uploaded files may be built to break the server: zip path tricks, zip bombs, huge files, cut-off streams. The owner's pandoc-mcp already solved the same problem, and following it keeps one model across the owner's servers.

Rejected: JWT or OAuth (there is no identity provider here); accepting client paths over HTTP (the server would read and write the caller's choice of files); uploads authorized by the server's token (the token would spread to every uploader); zip-only or files-only uploads (hard in a browser, or a hundred curl flags).

## Decision

We will guard `/mcp` with one static bearer token, compared in constant time, and refuse to start HTTP without it unless `--no-auth`. Over HTTP the server never accepts a client path: files arrive only through short-lived, upload-only links whose tokens are kept as sha256 hashes in memory, with per-file, per-link, page and zip limits checked while streaming. Results and uploads live in a document store under random uuid4 ids, downloadable without the token by whoever holds the URL. Logs carry ids, kinds, sizes, counts and error classes, never file names, recognized text, tokens or error messages, and uvicorn's access log is off.

## Consequences

- A download URL is a shared secret until its document is purged after `SCANSCRIBE_MCP_RETENTION_DAYS`.
- Upload links appear in transcripts; that is acceptable because they are useless once spent, closed or expired.
- Links and jobs live in memory, so a restart forgets them and agents start again.
- Every new route or tool must keep these rules: no client paths over HTTP, nothing book-derived in logs or errors, limits on every input. `docs/ARCHITECTURE.md` maps each attack to its defence, and tests try each one.
