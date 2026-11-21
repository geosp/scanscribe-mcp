---
phase: 3
title: Docker on the GPU and the manual GPU check
status: draft
branch: null
base: null
delivers: [R25]
design_review: { status: changes-requested, rounds: 1, last: 2026-11-21 }
impl_review: { status: none, rounds: 0, last: null }
approved: null
---

# Phase 03 · Docker on the GPU and the manual GPU check

## Goal

`docker compose up -d --build` runs the HTTP server on an NVIDIA GPU host, OCRs on `gpu:0`, and
keeps the PaddleOCR models on a volume across restarts. A manual check records it.

## Tasks

### 1. Image and compose

- [ ] 1.1 Add the `Dockerfile` from notes.md#d9: `python:3.12-slim`, `git`, pinned uv,
  `uv sync --frozen --no-dev --extra ${ENGINE}` (default `gpu`), an unprivileged user,
  `PADDLE_PDX_CACHE_HOME=/cache/paddlex`, `MCP_PORT=8302`, `--mode http` (D9). Verify:
  `docker build .` succeeds, and `docker run --rm <image> python -c "import scanscribe_mcp"`
  exits 0.
- [ ] 1.2 Add `docker-compose.yml` with the GPU reservation, the `documents` and `models`
  volumes, the token from `.env` (required), and the port; and `.dockerignore` that keeps `in/`,
  `out/`, `data/`, `.env` and `.git` out of the build context (D9, R25). Verify:
  `docker compose config` is valid and fails without `SCANSCRIBE_MCP_TOKEN`; the build context
  listing contains none of the ignored paths.
- [ ] 1.3 Check that PaddleX writes its models under `PADDLE_PDX_CACHE_HOME` (assumption in
  plan.md). Verify: after the first job, `/cache/paddlex` in the volume holds the models and
  `~/.paddlex` in the container is empty or absent. If not, switch to the variable PaddleX
  actually reads and log a Decision log line.

### 2. Documentation

- [ ] 2.1 Add the Docker section to the README: the NVIDIA container toolkit prerequisite,
  `cp .env.example .env`, `docker compose up -d --build`, `claude mcp add --transport http`, and
  what the volumes hold. Verify: the link checker passes; the commands match the compose file.
- [ ] 2.2 Update the architecture diagram in `docs/ARCHITECTURE.md` with the container, the two
  volumes and the GPU. Verify: the Mermaid block renders on GitHub.

### 3. Manual GPU check

- [ ] 3.1 On the owner's GPU host, start the stack, upload a self-made PDF of about 10 pages,
  run a job, then restart the container and run it again (R25). Record device, first-run and
  second-run times, whether a download happened on the second run, and the result in
  `docs/demos/<date>-docker-gpu-check/README.md`. Verify: the record shows `gpu:0`, no second
  download, and identical text on both runs.
- [ ] 3.2 Run the test suite inside the image as in pandoc-mcp's README (tests mounted read-only)
  to show the image's environment passes too. Verify: the command and its pass count are in the
  check record.
