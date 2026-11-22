"""Upload links (task 02/3.1).

D7, R15, R16.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scanscribe_mcp.config import ScanscribeMcpConfig
from scanscribe_mcp.uploads import GRANT_RETENTION_S, UploadLinks

from .fakes import FakeClock


def links(clock: FakeClock, max_links: int = 3, max_bytes: int = 100) -> UploadLinks:
    return UploadLinks(ttl_s=600, max_links=max_links, max_bytes=max_bytes, clock=clock)


def test_a_link_works_until_it_expires() -> None:
    clock = FakeClock()
    uploads = links(clock)
    token, grant = uploads.create(max_files=2)
    assert uploads.for_token(token) is grant and uploads.open(grant)
    assert uploads.for_token(token + "x") is None
    clock.advance(599)
    assert uploads.for_token(token) is grant
    clock.advance(1)
    assert uploads.for_token(token) is None and uploads.expired(grant)
    assert uploads.get(grant.upload_id) is grant  # still listed for check_upload
    clock.advance(GRANT_RETENTION_S)
    assert uploads.get(grant.upload_id) is None


def test_a_link_is_used_up_by_stored_and_running_uploads() -> None:
    uploads = links(FakeClock())
    token, grant = uploads.create(max_files=2)
    uploads.begin(grant)
    uploads.finish(grant, "a" * 32)
    uploads.begin(grant)
    assert grant.remaining == 0 and uploads.for_token(token) is None
    uploads.abandon(grant, 0)
    assert grant.remaining == 1 and uploads.for_token(token) is grant
    uploads.begin(grant)
    uploads.finish(grant, "b" * 32)
    assert uploads.for_token(token) is None and grant.files == ["a" * 32, "b" * 32]


def test_a_closed_link_takes_nothing() -> None:
    uploads = links(FakeClock())
    token, grant = uploads.create(max_files=5)
    uploads.close(grant)
    assert uploads.for_token(token) is None and not uploads.open(grant)
    assert uploads.get(grant.upload_id) is grant
    uploads.create(max_files=1)
    uploads.create(max_files=1)
    uploads.create(max_files=1)  # the closed link no longer counts as open


def test_open_links_are_limited() -> None:
    clock = FakeClock()
    uploads = links(clock, max_links=2)
    uploads.create(1)
    uploads.create(1)
    with pytest.raises(ValueError, match="too many open upload links"):
        uploads.create(1)
    clock.advance(600)
    uploads.create(1)  # the first two expired


def test_bytes_are_counted_per_link() -> None:
    uploads = links(FakeClock(), max_bytes=100)
    _, grant = uploads.create(max_files=5)
    uploads.begin(grant)
    uploads.begin(grant)
    assert uploads.add_bytes(grant, 60)
    assert not uploads.add_bytes(grant, 41)  # two uploads share the total
    assert uploads.add_bytes(grant, 40) and grant.remaining_bytes == 0
    uploads.abandon(grant, 40)
    assert grant.bytes == 60 and grant.remaining_bytes == 40


def test_tokens_are_long_and_kept_only_hashed() -> None:
    uploads = links(FakeClock())
    token, grant = uploads.create(1)
    assert len(token) >= 43 and grant.upload_id not in token
    assert token not in uploads._by_token


def test_max_files_setting_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCANSCRIBE_MCP_UPLOAD_LINK_MAX_FILES", "200")
    assert ScanscribeMcpConfig().upload_link_max_files == 200
    monkeypatch.setenv("SCANSCRIBE_MCP_UPLOAD_LINK_MAX_FILES", "201")
    with pytest.raises(ValidationError, match="upload_link_max_files"):
        ScanscribeMcpConfig()
