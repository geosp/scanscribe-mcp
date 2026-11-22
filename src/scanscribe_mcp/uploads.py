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

import fcntl
import hashlib
import os
import re
import secrets
import shutil
import stat
import sys
import time
import uuid
import zipfile
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import IO

from python_multipart import MultipartParser
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import parse_options_header
from scanscribe import IMAGE_EXTENSIONS

from .documents import ID_PATTERN, DocumentStore, PendingDocument, StoredDocument, safe_filename

GRANT_RETENTION_S = 24 * 3600
FIELD_LIMIT = 64 * 1024
"""Bytes allowed in one request beyond its files' data: every part's headers, and other form
fields, which are read and dropped (R16)."""


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
    """Files of uploads in progress, held against `max_files`."""
    requests: int = 0
    """Upload requests the route has taken and not answered yet, counted from their first byte,
    before any part header is parsed: a job may not start while one is open (R29)."""
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

    def open_request(self, grant: Grant) -> None:
        """An upload request reached the route: the link is busy until it is answered."""
        grant.requests += 1

    def end_request(self, grant: Grant) -> None:
        grant.requests -= 1

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
    ended: bool = False


class UploadReceiver:
    """Streams one multipart/form-data request into the store (R15, R16).

    Each part with a file name becomes a pending document, written chunk by chunk; the per-file
    and per-link limits are checked on every chunk, so an oversized stream stops early. The files
    are stored only when the whole request has arrived, up to its closing boundary (python-
    multipart's `finalize` doesn't check that, so `on_end` does); if anything fails, or the link
    was closed meanwhile, none is (`abort`). Part headers and other form fields count against
    FIELD_LIMIT; other fields are read and dropped.
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
        self._complete = False
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
                "on_end": self._on_end,
            },
        )

    async def receive(self, chunks: AsyncIterator[bytes]) -> list[StoredDocument]:
        try:
            async for chunk in chunks:
                self._parser.write(chunk)
            self._parser.finalize()
            if not self._complete or any(not part.ended for part in self._parts):
                raise UploadError(400, "the upload is incomplete: it ended before its last byte")
            files = [part for part in self._parts if part.pending is not None]
            if not files:
                raise UploadError(400, "send the files as multipart/form-data, in field 'file'")
            self._check_open()
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

    def _check_open(self) -> None:
        if self.grant.closed:
            raise UploadError(404, "this upload link is closed: a job has taken its files")

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

    def _count_extra(self, count: int) -> None:
        self._field_bytes += count
        if self._field_bytes > FIELD_LIMIT:
            raise UploadError(400, "send only files, in field 'file'")

    def _on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._count_extra(end - start)
        self._header_name += data[start:end]

    def _on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._count_extra(end - start)
        self._header_value += data[start:end]

    def _on_header_end(self) -> None:
        self._headers[self._header_name.lower()] = self._header_value
        self._header_name = self._header_value = b""

    def _on_headers_finished(self) -> None:
        _, params = parse_options_header(self._headers.get(b"content-disposition"))
        raw = params.get(b"filename")
        filename = raw.decode("utf-8", "replace") if raw is not None else None
        part = _Part(filename)
        self._part = part
        self._parts.append(part)
        if filename is not None and params.get(b"name") == b"file":
            self._check_open()
            if self.grant.remaining <= 0:
                raise UploadError(
                    400, f"too many files: this link takes {self.grant.max_files} in all"
                )
            part.hidden = is_hidden(filename)
            # The document first: if it can't be made, the link holds nothing for this part.
            part.pending = self.store.begin(filename or "upload")
            self.links.begin(self.grant)

    def _on_part_data(self, data: bytes, start: int, end: int) -> None:
        part = self._part
        assert part is not None
        count = end - start
        if part.pending is None:
            self._count_extra(count)
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
        if part is not None:
            part.ended = True
        self._part = None

    def _on_end(self) -> None:
        self._complete = True


# --- turning uploads into a scanscribe input (D7, D12, R17, R18, R29) -----------------------


class InputRefused(ValueError):
    """An upload or document that can't be a job's input; the message is safe for the caller."""


PDF, ZIP, IMAGES = "pdf", "zip", "images"


def file_kind(filename: str) -> str | None:
    """pdf, zip or images by suffix, in any case; None for any other file."""
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix == ".pdf":
        return PDF
    if suffix == ".zip":
        return ZIP
    if suffix in IMAGE_EXTENSIONS:
        return IMAGES
    return None


@dataclass(frozen=True)
class UploadPlan:
    """What a job reads from an upload: one PDF, one zip, or images used as a folder."""

    kind: str
    documents: tuple[StoredDocument, ...]


def plan_upload(documents: list[tuple[StoredDocument, bool]]) -> UploadPlan:
    """Choose the input from a link's (document, was hidden) pairs (D7, R29).

    Hidden files and files that are neither PDF, zip nor image are skipped. One PDF, one zip,
    or any number of images with distinct names is an input; anything else is refused.
    """
    by_kind: dict[str, list[StoredDocument]] = {PDF: [], ZIP: [], IMAGES: []}
    for document, hidden in documents:
        kind = file_kind(document.filename)
        if kind is not None and not hidden:
            by_kind[kind].append(document)
    present = [kind for kind in (PDF, ZIP, IMAGES) if by_kind[kind]]
    if not present:
        raise InputRefused("the upload holds no PDF, zip or page image")
    if len(present) > 1:
        raise InputRefused(
            f"the upload mixes {' and '.join(_counted(k, len(by_kind[k])) for k in present)}; a "
            "job reads one PDF, one zip, or page images. Upload them through separate links"
        )
    kind = present[0]
    chosen = by_kind[kind]
    if kind != IMAGES and len(chosen) > 1:
        raise InputRefused(
            f"the upload holds {_counted(kind, len(chosen))}; a job reads one. Upload each "
            "through its own link, or put the pages in one zip"
        )
    if kind == IMAGES:
        seen: set[str] = set()
        for document in chosen:
            if document.filename in seen:
                raise InputRefused(
                    f"two uploaded images are both named {document.filename!r}; give the pages "
                    "distinct names and upload them again through a new link"
                )
            seen.add(document.filename)
    return UploadPlan(kind, tuple(chosen))


def _counted(kind: str, count: int) -> str:
    if kind == IMAGES:
        return f"{count} page image(s)"
    return f"{count} {'PDF' if kind == PDF else 'zip'}{'s' if count > 1 else ''}"


def link_pages(documents: tuple[StoredDocument, ...], folder: Path) -> None:
    """Put uploaded images into the job folder under their names: hard links, or copies when
    the store is on another filesystem."""
    folder.mkdir(parents=True)
    for document in documents:
        target = folder / document.filename
        try:
            os.link(document.path, target)
        except OSError:
            shutil.copyfile(document.path, target)


# --- zips (R17, notes.md#d7) ----------------------------------------------------------------

DRIVE = re.compile(r"^[A-Za-z]:")
CHUNK = 1024 * 1024


def _parts(name: str) -> list[str]:
    return [part for part in re.split(r"[/\\]", name) if part]


def _skipped(info: zipfile.ZipInfo) -> bool:
    """Folders, hidden names and macOS metadata, as scanscribe skips hidden files."""
    parts = _parts(info.filename)
    return (
        info.is_dir()
        or not parts
        or parts[0] == "__MACOSX"
        or any(part.startswith(".") for part in parts)
    )


def zip_pages(path: Path, zip_name: str, max_pages: int, max_bytes: int) -> list[zipfile.ZipInfo]:
    """The page entries of a zip, checked from its central directory before anything is
    written: no path that leaves the folder, no symlink, only images, distinct base names, at
    most `max_pages` entries and `max_bytes` declared bytes."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise InputRefused(f"{zip_name} is not a readable zip file") from exc
    pages: list[zipfile.ZipInfo] = []
    names: set[str] = set()
    declared = 0
    for info in infos:
        name = info.filename
        if name.startswith(("/", "\\")) or DRIVE.match(name) or ".." in _parts(name):
            raise InputRefused(f"{zip_name}: the entry {name!r} points outside the zip's folder")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise InputRefused(f"{zip_name}: the entry {name!r} is a symbolic link")
        if _skipped(info):
            continue
        base = page_name(info)
        if file_kind(base) != IMAGES:
            raise InputRefused(
                f"{zip_name}: the entry {name!r} is not a page image; a zip may hold only "
                f"{', '.join(sorted(IMAGE_EXTENSIONS))} files"
            )
        if base in names:
            raise InputRefused(
                f"{zip_name}: two entries are named {base!r}; give the pages distinct names"
            )
        if info.flag_bits & 0x1:
            raise InputRefused(f"{zip_name}: the entry {name!r} is encrypted")
        names.add(base)
        declared += info.file_size
        pages.append(info)
        if len(pages) > max_pages:
            raise InputRefused(
                f"{zip_name} has more than {max_pages} pages; this server takes at most "
                f"{max_pages} per job (SCANSCRIBE_MCP_MAX_PAGES). Split it into smaller jobs"
            )
        if declared > max_bytes:
            raise InputRefused(
                f"{zip_name} unpacks to more than {max_bytes} bytes "
                "(SCANSCRIBE_MCP_MAX_UPLOAD_BYTES)"
            )
    return pages


def page_name(info: zipfile.ZipInfo) -> str:
    """The page's file name: the entry's base name, made plain like any uploaded name (D8)."""
    return safe_filename(_parts(info.filename)[-1])


def count_zip_pages(path: Path, zip_name: str, max_bytes: int) -> int:
    """The number of pages a zip would give, for the check at start_ocr_job (R4). It applies
    every rule of `zip_pages` from the central directory but the page limit, which the caller
    checks so its message gives the count. The worker checks them all again."""
    return len(zip_pages(path, zip_name, sys.maxsize, max_bytes))


def extract_zip(path: Path, zip_name: str, folder: Path, max_pages: int, max_bytes: int) -> int:
    """Unpack a zip's pages flat into `folder`, under their base names (R17).

    The bytes written are counted as they stream, so an entry whose header understates its size
    can't pass `max_bytes`; zipfile's CRC check catches a damaged entry. Returns the page count.
    """
    pages = zip_pages(path, zip_name, max_pages, max_bytes)
    folder.mkdir(parents=True)
    written = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for info in pages:
                target = folder / page_name(info)
                with archive.open(info) as source, open(target, "xb") as sink:
                    while chunk := source.read(CHUNK):
                        written += len(chunk)
                        if written > max_bytes:
                            raise InputRefused(
                                f"{zip_name} unpacks to more than {max_bytes} bytes "
                                "(SCANSCRIBE_MCP_MAX_UPLOAD_BYTES)"
                            )
                        sink.write(chunk)
    except (zipfile.BadZipFile, EOFError, RuntimeError, NotImplementedError) as exc:
        raise InputRefused(f"{zip_name} is damaged or uses an unsupported format") from exc
    return len(pages)


# --- the work folder (D12) ------------------------------------------------------------------

LOCK_FILE = ".scanscribe-mcp.lock"


class WorkDir:
    """WORK_DIR, held by one HTTP server through an exclusive lock file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock: IO[str] | None = None

    def acquire(self) -> int:
        """Take the lock, or refuse to start; then delete leftover job folders, which no job
        survives a restart to use. Returns how many were deleted."""
        self.path.mkdir(parents=True, exist_ok=True)
        handle = open(self.path / LOCK_FILE, "a")  # noqa: SIM115
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise ValueError(
                f"another scanscribe-mcp server is using SCANSCRIBE_MCP_WORK_DIR ({self.path}); "
                "give each server its own"
            ) from None
        self._lock = handle
        removed = 0
        for entry in self.path.iterdir():
            if not ID_PATTERN.match(entry.name):
                continue
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
            removed += 1
        return removed

    def release(self) -> None:
        if self._lock is not None:
            self._lock.close()  # closing the file drops the lock
            self._lock = None

    def job_folder(self, job_id: str) -> Path:
        return self.path / job_id

    def remove(self, job_id: str) -> None:
        shutil.rmtree(self.job_folder(job_id), ignore_errors=True)
