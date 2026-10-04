"""Safe local directory explorer."""

from __future__ import annotations

from datetime import datetime
from itertools import islice
from urllib.parse import quote

from novahost.core.models import RenderContext, is_path_within_root
from novahost.handlers.base import Handler
from novahost.ui.shell import esc, file_icon, human_size, page


class DirectoryHandler(Handler):
    key = "directory"
    label = "Folder"

    def render(self, context: RenderContext) -> str:
        current = context.path.resolve()
        root = context.root.resolve()
        parent_rel = current.relative_to(root)
        breadcrumbs = ['<a href="/">Root</a>']
        crumb_path = root
        for part in parent_rel.parts:
            crumb_path /= part
            rel = crumb_path.relative_to(root).as_posix()
            breadcrumbs.append(f'<a href="/__view__/{quote(rel, safe="/")}">{esc(part)}</a>')
        rows: list[str] = []
        try:
            entries = list(islice(current.iterdir(), 2001))
            entries.sort(key=lambda item: (not item.is_dir(), item.name.casefold()))
        except OSError as error:
            entries = []
            error_html = f'<div class="notice error">Could not list this folder: {esc(error)}</div>'
        else:
            error_html = ""
        visible_count = 0
        for entry in entries:
            try:
                resolved = entry.resolve()
                if not is_path_within_root(resolved, root):
                    continue
                stat = entry.stat()
            except OSError:
                continue
            relative = resolved.relative_to(root).as_posix()
            is_dir = entry.is_dir()
            href = "/" if is_dir and resolved == root else f'/__view__/{quote(relative, safe="/")}'
            icon = "▰" if is_dir else file_icon(entry)
            kind = "Folder" if is_dir else (entry.suffix.lstrip(".").upper() or "File")
            size = "—" if is_dir else human_size(stat.st_size)
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            rows.append(
                f'<a class="file-row directory-row" data-directory-row href="{href}" '
                f'data-name="{esc(entry.name.casefold())}" data-kind="{esc(kind.casefold())}" '
                f'data-size="{stat.st_size}" data-modified="{stat.st_mtime}" data-is-dir="{int(is_dir)}">'
                f'<span class="file-name"><span class="file-icon">{esc(icon)}</span>{esc(entry.name)}</span>'
                f'<span class="pill">{esc(kind)}</span><span class="file-size">{esc(size)} · {esc(modified)}</span></a>'
            )
            visible_count += 1
            if visible_count >= 2000:
                break
        listing = "".join(rows) or '<div class="empty">This folder is empty.</div>'
        cap_note = '<div class="notice">Showing up to the first 2,000 entries. Open a subfolder to narrow the listing.</div>' if len(entries) > 2000 else ""
        body = f"""
<section class="surface">
  <div class="toolbar"><div class="crumb">{" / ".join(breadcrumbs)}</div>
    <input class="search" type="search" data-filter="[data-directory-row]" placeholder="Filter this folder" aria-label="Filter folder">
    <select data-directory-sort aria-label="Sort files"><option value="folders">Folders first</option><option value="name-desc">Name Z–A</option><option value="kind">Type</option><option value="size">Size</option><option value="modified">Modified</option></select>
    <button type="button" onclick="document.querySelector('.directory-list').classList.toggle('directory-compact')">Grid / list</button>
  </div>{error_html}{cap_note}
  <div class="directory-list">{listing}</div>
  <div class="media-meta">{visible_count:,} entries · Folders stay inside the selected root.</div>
</section>"""
        return page(context, current.name or "Files", "Folder", body, subtitle=f"Browsing {' / '.join(parent_rel.parts) if parent_rel.parts else 'the selected root'}")
