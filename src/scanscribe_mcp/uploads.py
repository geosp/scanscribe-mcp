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
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from python_multipart import MultipartParser
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import parse_options_header

from .documents import DocumentStore, PendingDocument, StoredDocument

GRANT_RETENTION_S = 24 * 3600
FIELD_LIMIT = 64 * 1024
"""Bytes allowed in all non-file form fields of one request; they are read and dropped."""


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


class UploadError(Exception):
    """An upload refused with an HTTP status and a message for the uploader."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def is_hidden(filename: str) -> bool:
    """Whether the uploaded name, before `safe_filename`, was a hidden file (`.DS_Store`)."""
    return PurePosixPath(filename.replace("\\", "/")).name.startswith(".")


@dataclass
class _Part:
    filename: str | None
    pending: PendingDocument | None = None
    size: int = 0
    hidden: bool = False


class UploadReceiver:
    """Streams one multipart/form-data request into the store (R15, R16).

    Each part with a file name becomes a pending document, written chunk by chunk; the per-file
    and per-link limits are checked on every chunk, so an oversized stream stops early. The files
    are stored only when the whole request has arrived; if anything fails, none is (`abort`).
    Other form fields are read and dropped, up to FIELD_LIMIT bytes in all.
    """

    def __init__(
        self,
        links: UploadLinks,
        grant: Grant,
        store: DocumentStore,
        content_type: str,
        max_file_bytes: int,
    ) -> None:
        self.links = links
        self.grant = grant
        self.store = store
        self.max_file_bytes = max_file_bytes
        kind, params = parse_options_header(content_type)
        boundary = params.get(b"boundary")
        if kind != b"multipart/form-data" or not boundary:
            raise UploadError(400, "send the files as multipart/form-data, in field 'file'")
        self._parts: list[_Part] = []
        self._part: _Part | None = None
        self._header_name = b""
        self._header_value = b""
        self._headers: dict[bytes, bytes] = {}
        self._field_bytes = 0
        self._parser = MultipartParser(
            boundary,
            {
                "on_part_begin": self._on_part_begin,
                "on_header_field": self._on_header_field,
                "on_header_value": self._on_header_value,
                "on_header_end": self._on_header_end,
                "on_headers_finished": self._on_headers_finished,
                "on_part_data": self._on_part_data,
                "on_part_end": self._on_part_end,
            },
        )

    async def receive(self, chunks: AsyncIterator[bytes]) -> list[StoredDocument]:
        try:
            async for chunk in chunks:
                self._parser.write(chunk)
            self._parser.finalize()
            files = [part for part in self._parts if part.pending is not None]
            if not files:
                raise UploadError(400, "send the files as multipart/form-data, in field 'file'")
            return self._commit(files)
        except FormParserError as exc:
            self.abort()
            raise UploadError(400, "the upload is not valid multipart/form-data") from exc
        except BaseException:
            self.abort()
            raise

    def _commit(self, files: list[_Part]) -> list[StoredDocument]:
        stored = []
        for part in files:
            assert part.pending is not None
            document = part.pending.commit(
                {"kind": "upload", "upload_id": self.grant.upload_id, "hidden": part.hidden}
            )
            part.pending = None
            self.links.finish(self.grant, document.id)
            stored.append(document)
        return stored

    def abort(self) -> None:
        """Throw away every file of this request that isn't stored yet."""
        for part in self._parts:
            if part.pending is not None:
                part.pending.abort()
                part.pending = None
                self.links.abandon(self.grant, part.size)

    # --- parser callbacks ----------------------------------------------------------------------

    def _on_part_begin(self) -> None:
        self._headers = {}

    def _on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]

    def _on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def _on_header_end(self) -> None:
        self._headers[self._header_name.lower()] = self._header_value
        self._header_name = self._header_value = b""

    def _on_headers_finished(self) -> None:
        _, params = parse_options_header(self._headers.get(b"content-disposition"))
        raw = params.get(b"filename")
        filename = raw.decode("utf-8", "replace") if raw is not None else None
        part = _Part(filename)
        if filename is not None and params.get(b"name") == b"file":
            if self.grant.remaining <= 0:
                raise UploadError(
                    400, f"too many files: this link takes {self.grant.max_files} in all"
                )
            self.links.begin(self.grant)
            part.hidden = is_hidden(filename)
            part.pending = self.store.begin(filename or "upload")
        self._part = part
        self._parts.append(part)

    def _on_part_data(self, data: bytes, start: int, end: int) -> None:
        part = self._part
        assert part is not None
        count = end - start
        if part.pending is None:
            self._field_bytes += count
            if self._field_bytes > FIELD_LIMIT:
                raise UploadError(400, "send only files, in field 'file'")
            return
        if part.size + count > self.max_file_bytes:
            raise UploadError(413, f"each file must be at most {self.max_file_bytes} bytes")
        if not self.links.add_bytes(self.grant, count):
            raise UploadError(
                413, f"the files of one link must be at most {self.grant.max_bytes} bytes in all"
            )
        part.size += count
        part.pending.write(data[start:end])

    def _on_part_end(self) -> None:
        part = self._part
        if part is not None and part.pending is not None and part.size == 0:
            raise UploadError(400, "empty files are not accepted")
        self._part = None
