"""The one registration point for supported extensions and viewer handlers."""

from __future__ import annotations

import mimetypes
import zipfile
from pathlib import Path

from novahost.core.models import FileInfo
from novahost.handlers.archive import ArchiveHandler
from novahost.handlers.base import Handler
from novahost.handlers.binary import BinaryHandler, CryptoHandler
from novahost.handlers.data import DataHandler
from novahost.handlers.directory import DirectoryHandler
from novahost.handlers.image import ImageHandler
from novahost.handlers.markdown import MarkdownHandler
from novahost.handlers.media import AudioHandler, VideoHandler
from novahost.handlers.native import NativeHandler
from novahost.handlers.special import (
    DatabaseHandler,
    DocumentHandler,
    NotebookHandler,
    PresentationHandler,
    SpreadsheetHandler,
)
from novahost.handlers.text import CodeHandler, TextHandler


DIRECTORY_HANDLER = DirectoryHandler()
UNKNOWN_HANDLER = BinaryHandler(key="unknown", label="Unknown file")

# Add an extension to a handler here. Keep all extension routing centralized.
HANDLER_REGISTRATIONS: tuple[tuple[Handler, tuple[str, ...]], ...] = (
    (MarkdownHandler(), (".markdown", ".mdown", ".mkdn", ".mkd", ".md")),
    (
        NotebookHandler(),
        (".ipynb",),
    ),
    (
        SpreadsheetHandler(),
        (".xlsx", ".xlsm", ".ods", ".xls"),
    ),
    (
        PresentationHandler(),
        (".pptx", ".odp", ".ppt"),
    ),
    (
        DocumentHandler(),
        (".docx", ".odt", ".doc"),
    ),
    (DatabaseHandler(), (".sqlite3", ".sqlite", ".db")),
    (CodeHandler(), (
        ".py", ".pyw", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".java",
        ".kt", ".kts", ".rs", ".go", ".cs", ".php", ".rb", ".pl", ".swift",
        ".dart", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue",
        ".svelte", ".r", ".jl", ".sh", ".bash", ".zsh", ".fish", ".ps1",
        ".bat", ".cmd", ".sql", ".toml", ".ini", ".cfg", ".yaml", ".yml",
        ".xml", ".graphql", ".gql", ".dockerfile", ".makefile", ".diff",
    )),
    (
        TextHandler(),
        (".txt", ".text", ".log", ".nfo", ".rst", ".adoc", ".conf", ".env.example"),
    ),
    (ImageHandler(), (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif", ".svg")),
    (AudioHandler(), (".mp3", ".wav", ".ogg", ".opus", ".m4a", ".aac", ".flac")),
    (VideoHandler(), (".mp4", ".webm", ".mkv", ".mov", ".m4v", ".ogv", ".avi")),
    (ArchiveHandler(), (
        ".tar.gz", ".tar.xz", ".tar.bz2", ".tgz", ".zip", ".tar", ".7z",
        ".rar", ".gz", ".bz2", ".xz",
    )),
    (DataHandler(), (
        ".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".parquet", ".feather",
        ".avro",
    )),
    (CryptoHandler(), (".pem", ".crt", ".cer", ".der", ".key", ".pub", ".asc", ".gpg")),
    (
        BinaryHandler(),
        (".bin", ".exe", ".dll", ".so", ".a", ".out", ".h5", ".hdf5", ".mat",
         ".fits", ".nc", ".pt", ".pth", ".ckpt", ".safetensors", ".onnx"),
    ),
    (
        NativeHandler(),
        (".html", ".htm", ".xhtml", ".css", ".webmanifest", ".pdf", ".ttf",
         ".otf", ".woff", ".woff2"),
    ),
)

HANDLERS_BY_KEY: dict[str, Handler] = {}
EXTENSION_MAP: dict[str, Handler] = {}
for _handler, _extensions in HANDLER_REGISTRATIONS:
    HANDLERS_BY_KEY[_handler.key] = _handler
    for _extension in _extensions:
        EXTENSION_MAP[_extension] = _handler
HANDLERS_BY_KEY[UNKNOWN_HANDLER.key] = UNKNOWN_HANDLER
HANDLERS_BY_KEY[DIRECTORY_HANDLER.key] = DIRECTORY_HANDLER

MIME_MAP: dict[str, Handler] = {
    "text/markdown": next(handler for handler, _ in HANDLER_REGISTRATIONS if handler.key == "markdown"),
    "text/plain": next(handler for handler, _ in HANDLER_REGISTRATIONS if handler.key == "text"),
    "image/png": next(handler for handler, _ in HANDLER_REGISTRATIONS if handler.key == "image"),
    "image/jpeg": next(handler for handler, _ in HANDLER_REGISTRATIONS if handler.key == "image"),
    "image/gif": next(handler for handler, _ in HANDLER_REGISTRATIONS if handler.key == "image"),
    "image/webp": next(handler for handler, _ in HANDLER_REGISTRATIONS if handler.key == "image"),
    "audio/mpeg": next(handler for handler, _ in HANDLER_REGISTRATIONS if handler.key == "audio"),
    "video/mp4": next(handler for handler, _ in HANDLER_REGISTRATIONS if handler.key == "video"),
}

_ARCHIVE_HANDLER = HANDLERS_BY_KEY["archive"]
_SPREADSHEET_HANDLER = HANDLERS_BY_KEY["spreadsheet"]
_MAX_ZIP_DETECTION_BYTES = 16 * 1024 * 1024
_MAX_ZIP_MEMBERS = 10_000
_MAX_CONTENT_TYPES_BYTES = 256 * 1024


def registered_handlers() -> tuple[Handler, ...]:
    """Return unique handlers in registration order."""
    return tuple(dict.fromkeys(handler for handler, _ in HANDLER_REGISTRATIONS))


def handler_for_extension(name: str) -> Handler | None:
    """Find the registered handler using the longest matching extension."""
    lowered = name.lower()
    for extension in sorted(EXTENSION_MAP, key=len, reverse=True):
        if lowered.endswith(extension):
            return EXTENSION_MAP[extension]
    return None


def _read_zip_member_limited(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    limit: int,
) -> bytes | None:
    if member.file_size > limit:
        return None
    with archive.open(member) as file:
        content = file.read(limit + 1)
    return content if len(content) <= limit else None


def _zip_container_handler(path: Path) -> Handler:
    """Identify a few Office ZIP containers without extracting their contents."""
    try:
        if path.stat().st_size > _MAX_ZIP_DETECTION_BYTES:
            return _ARCHIVE_HANDLER
        with zipfile.ZipFile(path, "r") as archive:
            members = archive.infolist()
            if len(members) > _MAX_ZIP_MEMBERS:
                return _ARCHIVE_HANDLER
            names = {member.filename for member in members}

            if "mimetype" in names and "content.xml" in names:
                mime_member = archive.getinfo("mimetype")
                mime = _read_zip_member_limited(archive, mime_member, 128)
                if mime == b"application/vnd.oasis.opendocument.spreadsheet":
                    return _SPREADSHEET_HANDLER

            if "[Content_Types].xml" in names and "xl/workbook.xml" in names:
                types_member = archive.getinfo("[Content_Types].xml")
                content_types = _read_zip_member_limited(
                    archive,
                    types_member,
                    _MAX_CONTENT_TYPES_BYTES,
                )
                if content_types is not None:
                    lowered = content_types.lower()
                    if (
                        b"application/vnd.ms-excel.sheet.macroenabled.main+xml" in lowered
                        or b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml" in lowered
                    ):
                        return _SPREADSHEET_HANDLER
    except (
        OSError,
        RuntimeError,
        EOFError,
        ValueError,
        NotImplementedError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ):
        # PK signatures still identify a ZIP-like archive, even when damaged.
        pass
    return _ARCHIVE_HANDLER


def classify(path: Path, forced_handler: str | None = None) -> FileInfo:
    """Detect a file type by directory, registered suffix, MIME, then signature."""
    path = path.expanduser().resolve()
    mime_type, _ = mimetypes.guess_type(path.name)
    mime_type = mime_type or "application/octet-stream"

    if path.is_dir():
        return FileInfo(path, DIRECTORY_HANDLER, "inode/directory", "directory")

    if forced_handler:
        handler = HANDLERS_BY_KEY.get(forced_handler)
        if handler is None:
            raise ValueError(f"Unknown handler {forced_handler!r}. Use --list-handlers to see available handlers.")
        return FileInfo(path, handler, mime_type, "forced")

    handler = handler_for_extension(path.name)
    if handler:
        return FileInfo(path, handler, mime_type, "extension")

    handler = MIME_MAP.get(mime_type)
    if handler:
        return FileInfo(path, handler, mime_type, "mime")

    try:
        with path.open("rb") as file:
            signature = file.read(16)
    except OSError:
        signature = b""

    if signature.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"RIFF")):
        image_handler = next(handler for handler, _ in HANDLER_REGISTRATIONS if handler.key == "image")
        return FileInfo(path, image_handler, mime_type, "signature")
    if signature.startswith(b"%PDF-"):
        native_handler = next(handler for handler, _ in HANDLER_REGISTRATIONS if handler.key == "native")
        return FileInfo(path, native_handler, "application/pdf", "signature")
    if signature.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return FileInfo(path, _zip_container_handler(path), mime_type, "signature")
    return FileInfo(path, UNKNOWN_HANDLER, mime_type, "fallback")
