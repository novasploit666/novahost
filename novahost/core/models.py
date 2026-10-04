"""Shared types passed between detection, handlers, and the local server."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from novahost.handlers.base import Handler


def is_path_within_root(path: PurePath, root: PurePath) -> bool:
    """Compare path components using the path flavour's native semantics."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def quote_relative_url_path(path: PurePath) -> str:
    """Encode a relative filesystem path as a URL path with forward slashes."""
    if path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise ValueError("URL paths must be relative to the serving root.")
    return quote(path.as_posix(), safe="/")


@dataclass(frozen=True)
class FileInfo:
    """A classified local filesystem target."""

    path: Path
    handler: Handler
    mime_type: str
    detected_by: str


@dataclass
class RenderContext:
    """Context required to render a target without granting access outside root."""

    root: Path
    path: Path
    mime_type: str
    detected_by: str
    light: bool = False
    query: dict[str, str] | None = None
    forced_text: bool = False
    forced_hex: bool = False

    @property
    def relative_path(self) -> Path:
        return self.path.relative_to(self.root)

    @property
    def label(self) -> str:
        return self.path.name or self.path.as_posix()

    @property
    def size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def file_url(self, path: Path | str) -> str:
        """Return a safe URL for a file under the served root."""
        return self._url_for(path, "/__asset__/")

    def view_url(self, path: Path | str) -> str:
        """Return a URL that opens another file in its appropriate viewer."""
        return self._url_for(path, "/__view__/")

    def raw_url(self, path: Path | str) -> str:
        """Return a URL to serve a native document and its relative resources."""
        return self._url_for(path, "/__raw__/")

    def _url_for(self, path: Path | str, prefix: str) -> str:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.path.parent / candidate
        resolved = candidate.resolve()
        if not is_path_within_root(resolved, self.root):
            raise ValueError("Local links must stay within the served root.")
        relative = resolved.relative_to(self.root)
        return prefix + quote_relative_url_path(relative)
