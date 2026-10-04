"""Read-only archive inventory; archives are never extracted to disk."""

from __future__ import annotations

import gzip
import tarfile
import zipfile

from novahost.core.models import RenderContext
from novahost.handlers.base import Handler
from novahost.ui.shell import esc, human_size, page

MAX_MEMBERS = 5000
MAX_UNPACKED_BYTES = 512 * 1024 * 1024


class ArchiveHandler(Handler):
    key = "archive"
    label = "Archive"

    def render(self, context: RenderContext) -> str:
        items: list[tuple[str, int, str]] = []
        warning = ""
        try:
            if zipfile.is_zipfile(context.path):
                with zipfile.ZipFile(context.path) as archive:
                    for member in archive.infolist()[:MAX_MEMBERS]:
                        if member.is_dir():
                            kind = "Folder"
                        else:
                            kind = "File"
                        items.append((member.filename, member.file_size, kind))
            elif tarfile.is_tarfile(context.path):
                with tarfile.open(context.path, mode="r:*") as archive:
                    total = 0
                    for member in archive:
                        if len(items) >= MAX_MEMBERS:
                            break
                        if member.isfile():
                            total += member.size
                            if total > MAX_UNPACKED_BYTES:
                                warning = "Listing stopped at the 512 MiB expanded-size safety limit."
                                break
                        items.append((member.name, member.size, "Folder" if member.isdir() else "File" if member.isfile() else "Link/special file"))
            elif context.path.suffix.lower() == ".gz":
                with gzip.open(context.path, "rb") as source:
                    preview = source.read(4096)
                items.append((context.path.stem, len(preview), "Compressed stream (previewed first 4 KiB)"))
            else:
                warning = "This archive format needs an external reader. NovaHost does not extract or execute it."
        except (OSError, tarfile.TarError, zipfile.BadZipFile, EOFError) as error:
            warning = f"Could not read archive index: {error}"
        rows = "".join(
            f'<div class="file-row"><span class="file-name">{esc(name)}</span><span class="pill">{esc(kind)}</span><span class="file-size">{human_size(size)}</span></div>'
            for name, size, kind in items
        )
        empty = '<div class="empty">No readable entries found.</div>'
        warning_html = f'<div class="notice">{esc(warning)}</div>' if warning else ""
        body = f'<section class="surface"><div class="toolbar"><span class="pill">{len(items)} listed entries</span><span class="muted">Read-only · no extraction</span></div>{warning_html}<div>{rows or empty}</div></section>'
        return page(context, context.label, "Archive", body, subtitle="Archive listing is bounded and nothing inside is executed.")
