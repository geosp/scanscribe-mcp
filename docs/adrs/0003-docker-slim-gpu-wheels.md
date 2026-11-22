---
status: accepted
date: 2026-11-22
supersedes: null
plan: docs/plans/2026-11-21-mcp-server
---

# ADR-0003: Docker on `python:3.12-slim` with the GPU wheels

## Context

The server is meant to run as a service on an NVIDIA GPU host, restarted when a page hangs (ADR-0001), keeping its documents and the OCR models across container restarts and rebuilds. The PaddlePaddle cu126 wheels bring their own CUDA libraries, so the image needs only the host's driver, which the NVIDIA Container Toolkit mounts. The slim image lacks three runtime libraries the engine loads, found during the manual check.

Rejected: an `nvidia/cuda` base image (larger, and the wheels already carry CUDA; kept as the fallback if a future wheel needs more than the driver); a CPU image (no stated need, and not a supported target); one volume for everything, or bind mounts (job folders and uploads must share a filesystem for hard links, and models are a separate, reusable cache).

## Decision

We will build the image from `python:3.12-slim` and uv, both pinned by digest, installing the `gpu` extra with `uv sync --frozen --no-dev` plus Debian's `git`, `libgomp1`, `libgl1` and `libglib2.0-0`, and run it as uid 1000 on port 8302. Compose reserves one GPU, defaults the device to `gpu:0` so a container that can't see the GPU fails instead of using the CPU, keeps documents and job folders on the `documents` volume at `/data` and PaddleX's models on the `models` volume at `/cache`, and restarts the container `unless-stopped`.

## Consequences

- The image is about 7.5 GB, almost all PaddlePaddle and CUDA wheels; a dependency-layer cache keeps rebuilds fast.
- Hosts need Docker, an NVIDIA driver and the NVIDIA Container Toolkit; the GPU check on such a host is the only test of R25.
- A base-image or wheel bump can drop a library; the `gpu:0` default turns that into failed jobs rather than silent CPU runs, and the manual check catches it.
- Only the settings compose names reach the container; storage paths and the port are fixed in the image, so a local `.env` can't move data off the volumes.
- `docker compose down -v` deletes every stored document and the model cache.
