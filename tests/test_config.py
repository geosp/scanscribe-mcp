"""ScanscribeMcpConfig and AppConfig (task 01/1.2)."""

from __future__ import annotations

import pytest
from mcp_service_kit import BaseServerConfig
from pydantic import ValidationError

from scanscribe_mcp.config import AppConfig, ScanscribeMcpConfig


def test_defaults() -> None:
    config = ScanscribeMcpConfig()
    assert config.langs == ["en"]
    assert config.lang == "en"
    assert (config.default_dpi, config.default_columns) == (200, 1)
    assert config.device is None
    assert (config.min_dpi, config.max_dpi, config.max_columns) == (72, 400, 8)
    assert config.max_pages == 500
    assert config.max_page_pixels == 100_000_000
    assert config.page_timeout_s == 600
    assert config.max_queued == 20
    assert config.queue_timeout_s == 3600
    assert config.job_retention_s == 86400
    assert config.max_inline_chars == 50_000
    assert config.allow_local_paths is True


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCANSCRIBE_MCP_MAX_PAGES", "12")
    monkeypatch.setenv("SCANSCRIBE_MCP_DEVICE", "cpu")
    monkeypatch.setenv("SCANSCRIBE_MCP_MAX_INLINE_CHARS", "100")
    monkeypatch.setenv("SCANSCRIBE_MCP_PAGE_TIMEOUT_S", "5")
    config = ScanscribeMcpConfig()
    assert (config.max_pages, config.device, config.max_inline_chars) == (12, "cpu", 100)
    assert config.page_timeout_s == 5


def test_langs_are_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCANSCRIBE_MCP_LANGS", " en, fr ,,es")
    config = ScanscribeMcpConfig()
    assert config.langs == ["en", "fr", "es"]
    assert config.lang == "en"


def test_default_lang_must_be_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCANSCRIBE_MCP_LANGS", "en,fr")
    monkeypatch.setenv("SCANSCRIBE_MCP_DEFAULT_LANG", "fr")
    assert ScanscribeMcpConfig().lang == "fr"
    monkeypatch.setenv("SCANSCRIBE_MCP_DEFAULT_LANG", "de")
    with pytest.raises(ValidationError, match="not in SCANSCRIBE_MCP_LANGS"):
        ScanscribeMcpConfig()


def test_empty_langs_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCANSCRIBE_MCP_LANGS", " , ")
    with pytest.raises(ValidationError, match="at least one language"):
        ScanscribeMcpConfig()


def test_default_dpi_within_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCANSCRIBE_MCP_DEFAULT_DPI", "600")
    with pytest.raises(ValidationError, match="DEFAULT_DPI"):
        ScanscribeMcpConfig()


def app(transport: str) -> AppConfig:
    return AppConfig(server=BaseServerConfig(transport=transport))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("transport", "variable", "allowed"),
    [
        ("stdio", None, True),
        ("stdio", "true", True),
        ("stdio", "false", False),
        ("http", None, False),
        ("http", "true", False),
        ("http", "false", False),
    ],
)
def test_local_paths_allowed(
    monkeypatch: pytest.MonkeyPatch, transport: str, variable: str | None, allowed: bool
) -> None:
    if variable is not None:
        monkeypatch.setenv("SCANSCRIBE_MCP_ALLOW_LOCAL_PATHS", variable)
    assert app(transport).local_paths_allowed is allowed


def test_transport_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("SCANSCRIBE_MCP_ALLOW_LOCAL_PATHS", "true")
    assert AppConfig().local_paths_allowed is False


def test_http_defaults() -> None:
    config = ScanscribeMcpConfig()
    assert config.token is None and config.public_base_url is None
    assert (str(config.output_dir), str(config.work_dir)) == ("data/documents", "data/work")
    assert config.retention_days == 7
    assert config.max_file_bytes == 200 * 1024**2
    assert config.max_upload_bytes == 2 * 1024**3
    assert config.upload_link_ttl_s == 600
    assert (config.upload_link_max_files, config.upload_link_max_active) == (100, 100)


def test_token_is_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCANSCRIBE_MCP_TOKEN", "s3cret")
    config = ScanscribeMcpConfig()
    assert config.token is not None and config.token.get_secret_value() == "s3cret"
    assert "s3cret" not in repr(config)


def test_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_PORT", "8302")
    assert AppConfig().base_url == "http://localhost:8302"
    monkeypatch.setenv("SCANSCRIBE_MCP_PUBLIC_BASE_URL", "https://ocr.example.org/")
    assert AppConfig().base_url == "https://ocr.example.org"
