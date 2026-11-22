---
phase: 3
title: Docker on the GPU and the manual GPU check
status: approved
branch: null
base: null
delivers: [R25]
design_review: { status: passed, rounds: 3, last: 2026-11-21 }
impl_review: { status: none, rounds: 0, last: null }
approved: 2026-11-21
---

# Phase 03 · Docker on the GPU and the manual GPU check

## Goal

`docker compose up -d --build` runs the HTTP server on an NVIDIA GPU host, OCRs on `gpu:0`, and
keeps the models and documents on volumes across restarts and recreation. A manual check records
it.

## Tasks

### 1. Image and compose

- [ ] 1.1 Add the `Dockerfile` from notes.md#d9: `python:3.12-slim`, `git`, pinned uv, copying
  only `pyproject.toml`, `uv.lock`, `README.md` and `src/`, `uv sync --frozen --no-dev --extra
  gpu`, an unprivileged user,
  `PATH=/app/.venv/bin:$PATH`, `PADDLE_PDX_CACHE_HOME=/cache/paddlex`,
  `SCANSCRIBE_MCP_OUTPUT_DIR=/data/documents`, `SCANSCRIBE_MCP_WORK_DIR=/data/work`,
  `MCP_PORT=8302`, `--mode http` (D9). Verify: `docker build .` succeeds, and
  `docker run --rm <image> python -c "import scanscribe_mcp, sys; print(sys.prefix)"` prints
  `/app/.venv`.
- [ ] 1.2 Add `docker-compose.yml` with the GPU reservation, `mem_limit`, `restart:
  unless-stopped`, a healthcheck on the HTTP port, the `documents` volume at `/data` and `models`
  at `/cache`, the token from `.env` (required), `SCANSCRIBE_MCP_PUBLIC_BASE_URL` and the port;
  and `.dockerignore` keeping `in/`, `out/`, `data/`, `.env`, `.env.*`, `.venv` and `.git` out of
  the build context (D9, R25, R28). Verify:
  `docker compose config` is valid and fails without `SCANSCRIBE_MCP_TOKEN`; the build context
  contains none of the ignored paths.
- [ ] 1.3 Check that PaddleX writes its models under `PADDLE_PDX_CACHE_HOME` (assumption in
  plan.md). Verify: after the first job, `/cache/paddlex` in the volume holds the models and
  `~/.paddlex` in the container is empty or absent. If not, switch to the variable PaddleX
  actually reads and log a Decision log line.

### 2. Documentation and project records

- [ ] 2.1 Add the Docker section to the README: the NVIDIA container toolkit prerequisite,
  `cp .env.example .env`, `docker compose up -d --build`, `claude mcp add --transport http`, what
  the volumes hold, and how a restart recovers a hung job. Verify: the link checker passes; the
  commands match the compose file.
- [ ] 2.2 Update the architecture diagram in `docs/ARCHITECTURE.md` with the container, the two
  volumes and the GPU. Verify: the Mermaid block renders on GitHub.
- [ ] 2.3 Add the Docker interface to `docs/decision-log.md` (image, port 8302, volumes) and
  leave the AGENTS.md Status line for `impl-plan close` to update. Verify: the decision log lists
  them; `uv run .agents/sync_agents.py --check` passes.

### 3. Manual GPU check

- [ ] 3.1 On the owner's GPU host, with `SCANSCRIBE_MCP_LANGS=en,fr`, start the stack, upload a
  self-made PDF of about 10 pages, run a job, then `docker compose up -d --force-recreate` and
  run it again; then run one `fr` job and one `en` job (R25, R11). Record the device, run times,
  whether a download happened on the second run, whether the first result still downloads, GPU
  memory (`nvidia-smi`) after each language switch, and the result, in
  `docs/demos/<date>-docker-gpu-check/README.md`.
  Verify: the record shows `gpu:0`, no second download, the first result still downloadable,
  and identical text on both runs.
- [ ] 3.2 Run the test suite inside the image with dev dependencies, in a throwaway container:
  `docker run --rm --user 0 -v $PWD/tests:/app/tests:ro -v $PWD/.github:/app/.github:ro <image>
  sh -c 'uv sync --frozen --extra gpu -q && uv run --frozen pytest -q -p no:cacheprovider'`. Here PaddlePaddle is installed, so
  R24's no-import check is meaningful. Verify: the command and its pass count are in the check
  record.
