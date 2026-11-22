"""The document store: uploads and results over HTTP (D6), after pandoc-mcp's.

Each document lives in its own folder, `<output_dir>/<id>/`, holding the file under a plain name
and `meta.json` with how it was made: options and counts, never text (R22). `<id>` is a random
uuid4 hex string and is the unguessable part of its URL, `<base_url>/documents/<id>/<filename>`.
An upload is written as a hidden part file and renamed when its last byte has arrived, so a
reader never sees half a file. Nothing here uses MCP's API.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import time
import uuid
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any
from urllib.parse import quote

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")
METADATA_FILE = "meta.json"
PART_FILE = ".upload.part"

MIME_TYPES = {
    "txt": "text/plain; charset=utf-8",
    "pdf": "application/pdf",
    "zip": "application/zip",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "bmp": "image/bmp",
    "webp": "image/webp",
}


def mime_type_for(extension: str) -> str:
    return MIME_TYPES.get(extension.lower(), "application/octet-stream")


@dataclass(frozen=True)
class StoredDocument:
    id: str
    path: Path
    url: str
    filename: str
    size: int

    @property
    def extension(self) -> str:
        return self.path.suffix.removeprefix(".").lower()

    @property
    def mime_type(self) -> str:
        return mime_type_for(self.extension)


def safe_filename(name: str, default: str = "document") -> str:
    """A plain file name: no folders, no unusual characters, not hidden."""
    name = UNSAFE_CHARS.sub("_", Path(name.replace("\\", "/")).name).strip(" .")
    return name[:120] or default


class PendingDocument:
    """A document being written chunk by chunk; `commit` stores it, `abort` throws it away."""

    def __init__(self, store: DocumentStore, doc_id: str, folder: Path, filename: str) -> None:
        self._store = store
        self.id = doc_id
        self.folder = folder
        self.filename = filename
        self.size = 0
        self._file: IO[bytes] | None = open(folder / PART_FILE, "xb")  # noqa: SIM115

    def write(self, data: bytes) -> None:
        assert self._file is not None
        self._file.write(data)
        self.size += len(data)

    def commit(self, metadata: dict[str, Any] | None = None) -> StoredDocument:
        assert self._file is not None
        self._file.close()
        self._file = None
        path = self.folder / self.filename
        os.replace(self.folder / PART_FILE, path)
        self._store._write_metadata(self.folder, metadata)
        return self._store._document(self.id, path)

    def abort(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        shutil.rmtree(self.folder, ignore_errors=True)


class DocumentStore:
    def __init__(
        self, directory: Path, base_url: str, clock: Callable[[], float] = time.time
    ) -> None:
        self.directory = directory
        self.base_url = base_url.rstrip("/")
        self.clock = clock

    def ensure_directory(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(
        self, data: bytes, filename: str, metadata: dict[str, Any] | None = None
    ) -> StoredDocument:
        pending = self.begin(filename)
        try:
            pending.write(data)
            return pending.commit(metadata)
        except BaseException:
            pending.abort()
            raise

    def begin(self, filename: str) -> PendingDocument:
        """Start a document whose bytes arrive in chunks."""
        doc_id = uuid.uuid4().hex
        folder = self.directory / doc_id
        folder.mkdir(parents=True)
        return PendingDocument(self, doc_id, folder, safe_filename(filename))

    def get(self, doc_id: str) -> StoredDocument | None:
        folder = self._folder(doc_id)
        if folder is None:
            return None
        files = [
            p
            for p in folder.iterdir()
            if p.is_file() and p.name != METADATA_FILE and not p.name.startswith(".")
        ]
        return self._document(doc_id, files[0]) if files else None

    def path_for(self, doc_id: str, filename: str) -> Path | None:
        """The stored file for a download URL, or None."""
        document = self.get(doc_id)
        return document.path if document and document.filename == filename else None

    def metadata(self, document: StoredDocument) -> dict[str, Any]:
        try:
            data = json.loads((document.path.parent / METADATA_FILE).read_text())
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def delete(self, doc_id: str) -> None:
        folder = self._folder(doc_id)
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)

    def purge(self, older_than_days: float, keep: Collection[str] = ()) -> int:
        """Delete documents older than the retention, except those in `keep` (ids a live job
        uses); return how many were deleted (R20)."""
        if not self.directory.is_dir():
            return 0
        cutoff = self.clock() - older_than_days * 86400
        removed = 0
        for folder in self.directory.iterdir():
            if not ID_PATTERN.match(folder.name) or folder.name in keep:
                continue
            with contextlib.suppress(OSError):
                if folder.stat().st_mtime < cutoff:
                    shutil.rmtree(folder, ignore_errors=True)
                    removed += 1
        return removed

    def _folder(self, doc_id: str) -> Path | None:
        if not ID_PATTERN.match(doc_id):
            return None
        folder = self.directory / doc_id
        return folder if folder.is_dir() else None

    def _write_metadata(self, folder: Path, metadata: dict[str, Any] | None) -> None:
        created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock()))
        meta = {"created": created, **(metadata or {})}
        (folder / METADATA_FILE).write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    def _document(self, doc_id: str, path: Path) -> StoredDocument:
        url = f"{self.base_url}/documents/{doc_id}/{quote(path.name)}"
        return StoredDocument(doc_id, path, url, path.name, path.stat().st_size)
