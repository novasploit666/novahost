"""Shared application shell and document helpers."""

from __future__ import annotations

import html
from pathlib import Path

from novahost.core.models import RenderContext
from novahost.ui.assets import ENHANCEMENTS, SCRIPT, STYLES


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def page(
    context: RenderContext,
    title: str,
    category: str,
    body: str,
    *,
    subtitle: str | None = None,
    actions: str = "",
    extra_head: str = "",
) -> str:
    """Wrap viewer content with NovaHost's shared responsive shell."""
    safe_title = esc(title)
    safe_label = esc(context.label)
    theme = "light" if context.light else "dark"
    parent = context.relative_path.as_posix()
    return f"""<!doctype html>
<html lang="en" data-theme="{theme}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light"><title>{safe_title} · NovaHost</title>
<style>{STYLES}</style>{extra_head}
</head>
<body>
<header class="topbar"><a class="brand" href="/"><span class="brand-mark" aria-hidden="true">n</span>NovaHost</a>
<span class="crumb" title="{esc(parent)}">{safe_label}</span><div class="top-actions">
<button type="button" data-theme-toggle aria-label="Toggle light or dark theme">◐ Theme</button></div></header>
<main class="page">
<section class="heading"><div><div class="eyebrow">{esc(category)}</div><h1>{safe_title}</h1>
{f'<p class="subtitle">{esc(subtitle)}</p>' if subtitle else ""}</div><div class="actions">{actions}</div></section>
{body}
</main>
<footer class="footer"><span>Served locally by NovaHost</span><span>{human_size(context.size)} · {esc(context.mime_type)}</span></footer>
<script>{SCRIPT}</script><script>{ENHANCEMENTS}</script>
</body></html>"""


def card(title: str, body: str, *, icon: str = "•") -> str:
    return f'<article class="tile"><strong><span class="file-icon">{esc(icon)}</span>{esc(title)}</strong><p>{body}</p></article>'


def file_icon(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".md": "M", ".py": "Py", ".js": "JS", ".ts": "TS", ".json": "{ }",
        ".csv": "▦", ".png": "▧", ".jpg": "▧", ".mp4": "▶", ".mp3": "♫",
        ".pdf": "PDF", ".zip": "ZIP",
    }.get(suffix, "•")
