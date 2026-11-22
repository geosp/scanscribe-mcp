# Manual check · Docker on the GPU · 2026-11-22

Phase 03, tasks 3.1 and 3.2 of [the plan](../../plans/2026-11-21-mcp-server/phases/03-docker-gpu.md): run the stack on the owner's GPU host with `SCANSCRIBE_MCP_LANGS=en,fr`, OCR a self-made PDF, recreate the container and OCR it again, switch languages, and run the test suite inside the image (R25, R11).

> [!NOTE]
> Run by an agent (Claude Code in VS Code) on the owner's machine; the owner delegated the run. The stack ran as a separate compose project (`-p scanscribe-check`), so it started from fresh, empty volumes. The token was a throwaway random value passed through the environment; no `.env` was written.

- **Result:** pass. Every job ran on `gpu:0`, the second run downloaded nothing, the first result still downloaded after the container was recreated, and the text of every run was identical to what was drawn. GPU memory stayed flat across language switches. The test suite passed inside the image: 259 passed, 3 skipped.
- **Machine:** AMD Ryzen 9 8945HS, NVIDIA GeForce RTX 3060 12 GB (driver 610.43.03), NVIDIA Container Toolkit 1.19.1, Docker 29.6.2 with Compose 5.3.1, Fedora Linux 44 (kernel 7.1.7)
- **Versions:** image built from commit 41a9f0e (`Dockerfile`, `src/`, `pyproject.toml`, `uv.lock` unchanged since), image `sha256:991d7d575d58…`; scanscribe 0.2.0, mcp-service-kit 0.2.1, fastmcp 4.2.4, paddlepaddle-gpu 3.3.1, paddleocr 3.7.0, paddlex 3.7.2
- **Who ran it:** an agent, delegated by the owner (see the note above)
- **Input:** two PDFs drawn by [make_pdfs.py](make_pdfs.py) at 200 dpi in Liberation Sans: 10 English pages and 2 French pages with accented letters, all sentences written for this check. No book material was used.

## Commands

```bash
cd /path/to/scanscribe-mcp
uv run python docs/demos/2026-11-22-docker-gpu-check/make_pdfs.py /tmp/docker-gpu-check
openssl rand -hex 32 > /tmp/docker-gpu-check/token     # a throwaway token
export SCANSCRIBE_MCP_TOKEN="$(cat /tmp/docker-gpu-check/token)" SCANSCRIBE_MCP_LANGS=en,fr
export TOKEN_FILE=/tmp/docker-gpu-check/token
C="docker compose --env-file /dev/null -p scanscribe-check"
$C up -d --build
run() {   # <name> <lang>: one job through an upload link, from the host
  uv run python docs/demos/2026-11-22-docker-gpu-check/check_client.py \
    /tmp/docker-gpu-check/$2.pdf /tmp/docker-gpu-check/$1.txt $2
}

run run1 en                         # cold model cache
$C up -d --force-recreate           # a new container on the same volumes
curl -sS "<run1's download URL>"    # the first result still downloads
run run2 en
run run3 fr                         # switch the engine to French
run run4 en                         # and back
nvidia-smi --query-compute-apps=pid,used_memory --format=csv   # after each job

diff /tmp/docker-gpu-check/en.expected.txt /tmp/docker-gpu-check/run1.txt
diff /tmp/docker-gpu-check/fr.expected.txt /tmp/docker-gpu-check/run3.txt

$C down                             # afterwards: remove the containers; add -v to delete the volumes too
```

[check_client.py](check_client.py) uploads the PDF through `create_upload_link`, starts the job with `start_ocr_job(upload_id=...)`, follows it with `get_ocr_job(wait_s=60)`, saves the text from `get_ocr_result`, and prints one JSON line.

The test suite inside the image (task 3.2), with `docs/` mounted as well because `tests/test_docs.py` reads the decision log, and `:z` on each mount for SELinux:

```bash
docker run --rm --user 0 -v $PWD/tests:/app/tests:ro,z -v $PWD/.github:/app/.github:ro,z \
  -v $PWD/docs:/app/docs:ro,z scanscribe-mcp:dev \
  sh -c 'uv sync --frozen --extra gpu -q && uv run --frozen pytest -q -p no:cacheprovider -rs'
```

## Observations

| Run | Container | Lang | Pages | Device | `run_seconds` | Model download | Text |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | first | en | 10 | `gpu:0` | 37.9 | yes: `/cache/paddlex` went from empty to 133 MB (`PP-OCRv6_medium_det`, `PP-OCRv6_medium_rec`) | identical to `en.expected.txt` |
| 2 | recreated | en | 10 | `gpu:0` | 5.1 | none: PaddleX logged "Model files already exist. Using cached files" for both models; the cache stayed 133 MB | identical to run 1 |
| 3 | recreated | fr | 2 | `gpu:0` | 1.3 | none: the French engine uses the same two models | identical to `fr.expected.txt`, accents included |
| 4 | recreated | en | 10 | `gpu:0` | 3.4 | none | identical to run 1 |

- **The first result after recreating the container:** its download URL answered 200, and the file was identical to run 1's text.
- **Engine loads:** the server logged "engine loaded" for `en` before run 2, `fr` before run 3, and `en` before run 4, so each language switch reloaded the engine (R11). Run 1's time includes the model download and the first engine load.
- **GPU memory** (`nvidia-smi`, the server's process): 2,248 MiB after run 1, after run 2, after the switch to `fr`, and after the switch back to `en`. The switch frees the old engine's memory, or reuses it; it doesn't grow. The rest of the 3,031 MiB in use was the desktop (746 MiB, already there before the stack started).
- **Healthcheck:** the container reported `healthy` within seconds of each start.
- **Test suite in the image (task 3.2):** 259 passed, 3 skipped. Two curl tests skip because the image has no `curl`; one worker test skips because it needs the base install. PaddlePaddle and PaddleOCR are installed in the image, so the session guard that fails if a test imports them was meaningful, and it passed (R24).

### Found while preparing the check

- **Three libraries missing from `python:3.12-slim`.** PaddlePaddle failed to import without `libgomp1`, and the first job failed with `OCR failed (ImportError)` until `libgl1` and `libglib2.0-0` were installed, which the OpenCV that PaddleX imports needs. The Dockerfile installs all three, and D9's slim base stands (plan Decision log, 2026-11-22).
- **A first try at the French PDF** used Pillow's built-in font, which has no accented letters: it drew empty boxes, and the OCR read them as `ø` or dropped them. With Liberation Sans the accents are drawn, and the OCR reads them all. That was the input, not the server.

### Rechecked after the implementation review

After the review's fixes (commit e727b93: links follow the host port, `SCANSCRIBE_MCP_DEVICE` defaults to `gpu:0`, more settings passed through, a stricter healthcheck, an allow-list `.dockerignore`), the image was rebuilt and these were run on the same host. The stack ran on the `scanscribe-check` volumes, whose model cache already held the English models.

- **Task 1.1:** `docker run --rm scanscribe-mcp:latest python -c "import scanscribe_mcp, sys; print(sys.prefix)"` printed `/app/.venv`; the image runs as `uid=1000(scanscribe)`.
- **Task 1.2, the token:** `docker compose --env-file /dev/null config -q` exits 1 without `SCANSCRIBE_MCP_TOKEN` ("required variable SCANSCRIBE_MCP_TOKEN is missing a value") and 0 with it.
- **Task 1.2, a real `.env` file:** a scratch env file outside the repository, holding the token, `SCANSCRIBE_MCP_HOST_PORT=9000`, `SCANSCRIBE_MCP_LANGS=en,fr` and `SCANSCRIBE_MCP_PAGE_TIMEOUT_S=900`, was passed with `--env-file`. Inside the container `env` showed `SCANSCRIBE_MCP_DEVICE=gpu:0`, `SCANSCRIBE_MCP_LANGS=en,fr`, `SCANSCRIBE_MCP_PAGE_TIMEOUT_S=900` and `SCANSCRIBE_MCP_PUBLIC_BASE_URL=http://localhost:9000`.
- **Host port 9000:** the 10-page English job, uploaded and started through `http://localhost:9000`, ran on `gpu:0` in 5.7 s with text identical to `en.expected.txt`, and its download URL was on port 9000.
- **Task 1.2, the build context:** a throwaway image that copied the whole context held only `README.md`, `pyproject.toml`, `src` and `uv.lock`.
- **A restart in the container:** SIGTERM to the server process (PID 1) ended it; `restart: unless-stopped` started it again within seconds (restart count 0 to 1, a new start time), and the healthcheck reported `healthy`. A real exit 70 needs a page that hangs in the engine, which this check can't produce; `tests/test_http_process.py` shows the server exits with 70 when a page hangs, and the restart policy applies to any exit.
