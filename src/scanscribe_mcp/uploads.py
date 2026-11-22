"""Short-lived upload links (D7, D8, R15, R16, R29), after pandoc-mcp's.

An authenticated MCP caller asks for a link with create_upload_link. The link carries a random
token that allows uploading up to `max_files` files, `max_bytes` bytes in all, for a few minutes,
and nothing else. The caller also gets a non-secret upload_id, the only handle that lists what
arrived (check_upload) and starts a job from it (start_ocr_job), so whoever uploads never learns
the stored document ids.

Tokens are kept only as sha256 hashes, in memory: a restart invalidates every link. A link is
checked when an upload starts, so an upload that began in time may finish after expiry; uploads
in progress count against the link's files and bytes. Starting a job closes the link. Grants
stay readable by upload_id for a day after the link expires. Every method runs on the event
loop, so no lock is needed. Nothing here uses MCP's API.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

GRANT_RETENTION_S = 24 * 3600


@dataclass
class Grant:
    upload_id: str
    expires_at: float
    max_files: int
    max_bytes: int
    files: list[str] = field(default_factory=list)
    """Document ids of the files stored, in order of arrival."""
    bytes: int = 0
    """Bytes stored plus bytes of uploads in progress."""
    in_progress: int = 0
    closed: bool = False
    snapshot: tuple[str, ...] | None = None
    """The document ids a job took from this link; later starts reuse them (D7)."""

    @property
    def remaining(self) -> int:
        """Files the link still takes, counting uploads in progress."""
        return max(self.max_files - len(self.files) - self.in_progress, 0)

    @property
    def remaining_bytes(self) -> int:
        return max(self.max_bytes - self.bytes, 0)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class UploadLinks:
    def __init__(
        self,
        ttl_s: float,
        max_links: int,
        max_bytes: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_s = ttl_s
        self.max_links = max_links
        self.max_bytes = max_bytes
        self.clock = clock
        self._by_token: dict[str, Grant] = {}
        self._by_id: dict[str, Grant] = {}

    def create(self, max_files: int) -> tuple[str, Grant]:
        self._purge()
        if len(self._by_token) >= self.max_links:
            raise ValueError("too many open upload links; wait for some to expire")
        token = secrets.token_urlsafe(32)
        grant = Grant(uuid.uuid4().hex, self.clock() + self.ttl_s, max_files, self.max_bytes)
        self._by_token[_hash(token)] = grant
        self._by_id[grant.upload_id] = grant
        return token, grant

    def for_token(self, token: str) -> Grant | None:
        """The grant of a usable link: unknown, expired, closed and used-up links give None."""
        self._purge()
        grant = self._by_token.get(_hash(token))
        if grant is None or grant.closed or grant.remaining <= 0:
            return None
        return grant

    def begin(self, grant: Grant) -> None:
        """An upload starts: it holds one of the link's files until it ends."""
        grant.in_progress += 1

    def add_bytes(self, grant: Grant, count: int) -> bool:
        """Count bytes of an upload in progress; False, counting nothing, past the link's total
        (R16)."""
        if grant.bytes + count > grant.max_bytes:
            return False
        grant.bytes += count
        return True

    def finish(self, grant: Grant, doc_id: str) -> None:
        """The upload is stored: it becomes one of the link's files."""
        grant.in_progress -= 1
        grant.files.append(doc_id)

    def abandon(self, grant: Grant, counted_bytes: int) -> None:
        """The upload failed: give back its file and the bytes it counted."""
        grant.in_progress -= 1
        grant.bytes -= counted_bytes

    def close(self, grant: Grant) -> None:
        """No more uploads: a job took the files (D7)."""
        grant.closed = True
        for key, value in list(self._by_token.items()):
            if value is grant:
                del self._by_token[key]

    def get(self, upload_id: str) -> Grant | None:
        self._purge()
        return self._by_id.get(upload_id)

    def expired(self, grant: Grant) -> bool:
        return self.clock() >= grant.expires_at

    def open(self, grant: Grant) -> bool:
        """Whether the link still takes new uploads."""
        return not grant.closed and not self.expired(grant) and grant.remaining > 0

    def _purge(self) -> None:
        now = self.clock()
        for key, grant in list(self._by_token.items()):
            if now >= grant.expires_at:
                del self._by_token[key]
        for key, grant in list(self._by_id.items()):
            if now >= grant.expires_at + GRANT_RETENTION_S:
                del self._by_id[key]
