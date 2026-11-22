# scanscribe-mcp over HTTP on an NVIDIA GPU (plan D9). Needs the NVIDIA container toolkit on the
# host; the cu126 PaddlePaddle wheels bring their own CUDA libraries, the host brings the driver.
#
#   docker compose up -d --build        (see docker-compose.yml and the README)
#
# Base images are pinned by digest; bump them by hand with the tag in the comment.

# ghcr.io/astral-sh/uv:0.13.5, the uv version CI pins (UV_VERSION in .github/workflows/ci.yml)
FROM ghcr.io/astral-sh/uv@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv

# python:3.12-slim
FROM python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# git fetches the Git dependencies (scanscribe, mcp-service-kit) at their pinned tags. The slim
# image lacks three runtime libraries the OCR engine loads: libgomp1 (OpenMP, for PaddlePaddle),
# and libgl1 and libglib2.0-0 (for the OpenCV that PaddleX imports).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, so a change to src/ doesn't download PaddlePaddle again.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra gpu --no-install-project

COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra gpu

# An unprivileged user owns the two volumes' mount points: /data (documents and job folders,
# one filesystem so uploads are hard-linked into job folders) and /cache (the OCR models).
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin scanscribe \
    && mkdir -p /data/documents /data/work /cache/paddlex \
    && chown -R scanscribe:scanscribe /data /cache

ENV PATH="/app/.venv/bin:$PATH" \
    PADDLE_PDX_CACHE_HOME=/cache/paddlex \
    SCANSCRIBE_MCP_OUTPUT_DIR=/data/documents \
    SCANSCRIBE_MCP_WORK_DIR=/data/work \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8302 \
    FASTMCP_SHOW_SERVER_BANNER=false

USER scanscribe
VOLUME ["/data", "/cache"]
EXPOSE 8302

CMD ["scanscribe-mcp", "--mode", "http"]
