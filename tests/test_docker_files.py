"""The Docker image and compose file keep their promises (phase 03; R25, D9, R28).

These read docker-compose.yml, the Dockerfile and .dockerignore; the compose tests also run
`docker compose config`, which needs Docker but no GPU and no image, and skip without it.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
SERVICE = COMPOSE["services"]["scanscribe"]
DOCKERFILE = (ROOT / "Dockerfile").read_text()

needs_docker = pytest.mark.skipif(shutil.which("docker") is None, reason="docker is not installed")


def image_env() -> dict[str, str]:
    """The ENV settings of the Dockerfile's final image."""
    env: dict[str, str] = {}
    for block in re.findall(r"^ENV (.*?)(?<!\\)$", DOCKERFILE, re.M | re.S):
        for key, value in re.findall(r'(\w+)=("[^"]*"|\S+)', block):
            env[key] = value.strip('"')
    return env


def compose_config(**env: str) -> dict[str, Any]:
    """`docker compose config` as the service sees it, with `env` as the only settings."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("SCANSCRIBE_MCP_", "MCP_"))}
    done = subprocess.run(
        ["docker", "compose", "--env-file", os.devnull, "config", "--format", "json"],
        cwd=ROOT,
        env={**clean, "SCANSCRIBE_MCP_TOKEN": "not-a-secret", **env},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    service: dict[str, Any] = json.loads(done.stdout)["services"]["scanscribe"]
    return service


@needs_docker
def test_links_follow_the_host_port() -> None:
    """M1: with only the host port changed, upload links and download URLs use it."""
    environment = compose_config(SCANSCRIBE_MCP_HOST_PORT="9000")["environment"]
    assert environment["SCANSCRIBE_MCP_PUBLIC_BASE_URL"] == "http://localhost:9000"
    default = compose_config()["environment"]
    assert default["SCANSCRIBE_MCP_PUBLIC_BASE_URL"] == "http://localhost:8302"
    named = compose_config(SCANSCRIBE_MCP_PUBLIC_BASE_URL="https://ocr.example.org")
    assert named["environment"]["SCANSCRIBE_MCP_PUBLIC_BASE_URL"] == "https://ocr.example.org"


@needs_docker
def test_the_device_is_the_gpu_unless_set() -> None:
    """N1, R25: a container that can't see the GPU fails its jobs instead of using the CPU."""
    assert compose_config()["environment"]["SCANSCRIBE_MCP_DEVICE"] == "gpu:0"
    chosen = compose_config(SCANSCRIBE_MCP_DEVICE="cpu")
    assert chosen["environment"]["SCANSCRIBE_MCP_DEVICE"] == "cpu"


@needs_docker
@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SCANSCRIBE_MCP_PAGE_TIMEOUT_S", "900"),
        ("SCANSCRIBE_MCP_RETENTION_DAYS", "3"),
        ("SCANSCRIBE_MCP_MAX_PAGES", "800"),
        ("SCANSCRIBE_MCP_LANGS", "en,fr"),
    ],
)
def test_documented_settings_reach_the_container(name: str, value: str) -> None:
    """N2: the settings the README lists for Docker are passed through when set."""
    assert compose_config(**{name: value})["environment"][name] == value
    readme = (ROOT / "README.md").read_text()
    docker_section = readme[readme.index("## Run it in Docker") : readme.index("## Tools")]
    assert f"`{name}`" in docker_section


def run_healthcheck(status: int) -> int:
    """Run the compose healthcheck's script against a server that answers `status`."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(status)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        test = SERVICE["healthcheck"]["test"]
        assert test[:3] == ["CMD", "python", "-c"]
        script = test[3].replace("127.0.0.1:8302", f"127.0.0.1:{server.server_port}")
        return subprocess.run([sys.executable, "-c", script], timeout=30).returncode
    finally:
        server.shutdown()


def test_the_healthcheck_wants_the_expected_404() -> None:
    """N3: up means the server answers its 404 page; a 5xx is unhealthy."""
    assert run_healthcheck(404) == 0
    assert run_healthcheck(500) != 0
    assert run_healthcheck(200) != 0


def test_data_and_models_live_on_the_volumes() -> None:
    """N7, R25: documents, job folders and the model cache are on the named volumes, so a
    recreated container keeps them; the server listens on the port compose maps."""
    mounts = dict(volume.split(":")[::-1] for volume in SERVICE["volumes"])
    assert mounts == {"/data": "documents", "/cache": "models"}
    assert set(COMPOSE["volumes"]) == {"documents", "models"}
    env = image_env()
    assert env["SCANSCRIBE_MCP_OUTPUT_DIR"].startswith("/data/")
    assert env["SCANSCRIBE_MCP_WORK_DIR"].startswith("/data/")  # one filesystem: hard links
    assert env["PADDLE_PDX_CACHE_HOME"].startswith("/cache/")
    assert SERVICE["ports"][0].endswith(f":{env['MCP_PORT']}")
    assert SERVICE["restart"] == "unless-stopped"  # R28: an exit 70 comes back
    assert "--extra gpu" in DOCKERFILE and re.search(r"^USER scanscribe$", DOCKERFILE, re.M)


def test_the_build_context_is_an_allow_list() -> None:
    """N8, D9: everything is ignored but the four inputs the image copies."""
    lines = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert lines[0] == "*"
    assert sorted(lines[1:]) == ["!README.md", "!pyproject.toml", "!src/", "!uv.lock"]
    copied = re.findall(r"^COPY (?!--from)(.+) \S+$", DOCKERFILE, re.M)
    assert sorted(" ".join(copied).split()) == ["README.md", "pyproject.toml", "src/", "uv.lock"]
