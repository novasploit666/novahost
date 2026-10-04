"""Plain-text and syntax-highlighted source viewers."""

from __future__ import annotations

from pathlib import Path

from novahost.core.models import RenderContext
from novahost.handlers.base import Handler
from novahost.ui.shell import esc, human_size, page


class TextHandler(Handler):
    key = "text"
    label = "Text"

    def render(self, context: RenderContext) -> str:
        if context.forced_hex:
            from novahost.handlers.binary import render_hex

            return render_hex(context)
        try:
            with context.path.open(encoding="utf-8", errors="replace") as file:
                text = file.read(2_000_001)
        except OSError as error:
            text = f"Could not read {context.label}: {error}"
        truncated = len(text) > 2_000_000
        text = text[:2_000_000]
        body = f"""
<section class="surface">
  <div class="toolbar">
    <input class="search" type="search" data-filter="#text-content" placeholder="Search this file" aria-label="Search text">
    <button type="button" data-copy="#text-content">Copy</button>
    <span class="pill">{len(text.splitlines()):,} lines</span>
    <span class="pill">{human_size(context.size)}</span>
  </div>
  {f'<div class="notice">Large text file shortened to the first 2 MB. Download the original for the complete file.</div>' if truncated else ""}
  <div class="content"><pre id="text-content" style="white-space:pre-wrap;overflow-wrap:anywhere;margin:0;font:13px/1.75 ui-monospace,SFMono-Regular,Consolas,monospace">{esc(text)}</pre></div>
</section>"""
        return page(context, context.label, "Text file", body, subtitle="Readable, searchable, and never executed.")


_LANGUAGE_NAMES = {
    ".py": "Python", ".pyw": "Python", ".js": "JavaScript", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TSX", ".jsx": "JSX",
    ".html": "HTML", ".css": "CSS", ".json": "JSON", ".yml": "YAML",
    ".yaml": "YAML", ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell",
    ".ps1": "PowerShell", ".rs": "Rust", ".go": "Go", ".java": "Java",
    ".kt": "Kotlin", ".c": "C", ".h": "C/C++", ".cpp": "C++",
    ".cc": "C++", ".cs": "C#", ".php": "PHP", ".rb": "Ruby",
    ".swift": "Swift", ".sql": "SQL", ".r": "R", ".jl": "Julia",
}


class CodeHandler(Handler):
    key = "code"
    label = "Source code"

    def render(self, context: RenderContext) -> str:
        if context.forced_text:
            return TextHandler().render(context)
        try:
            with context.path.open(encoding="utf-8", errors="replace") as file:
                source = file.read(2_000_001)
        except OSError as error:
            source = f"Could not read {context.label}: {error}"
        truncated = len(source) > 2_000_000
        source = source[:2_000_000]
        escaped_source = esc(source)
        language = _LANGUAGE_NAMES.get(context.path.suffix.lower(), context.path.suffix.lstrip(".").upper() or "Text")
        highlighted: list[str] = []
        try:
            from pygments.formatters import HtmlFormatter
            from pygments.lexers import get_lexer_for_filename
            from pygments.util import ClassNotFound

            try:
                lexer = get_lexer_for_filename(context.path.name, stripnl=False, ensurenl=False)
            except ClassNotFound:
                lexer = None
            if lexer is None:
                highlighted = [esc(line) for line in source.splitlines()]
            else:
                formatter = HtmlFormatter(nowrap=True)
                # Feed the complete document to the lexer so multiline strings
                # and comments retain their state across line boundaries.
                highlighted = [
                    rendered.rstrip("\n")
                    for _, rendered in formatter._format_lines(lexer.get_tokens(source))
                ]
        except ImportError:
            highlighted = [esc(line) for line in source.splitlines()]
        if source and not highlighted:
            highlighted = [esc(source)]
        rows = "".join(
            f'<div class="code-line" id="L{number}"><a class="line-no" href="#L{number}" aria-label="Line {number}">{number}</a>'
            f'<span class="line-src">{line or " "}</span></div>'
            for number, line in enumerate(highlighted, 1)
        )
        css = ""
        try:
            from pygments.formatters import HtmlFormatter
            from pygments.styles import get_style_by_name

            css = "<style>" + HtmlFormatter(style=get_style_by_name("native")).get_style_defs(".code-frame") + "</style>"
        except (ImportError, OSError):
            pass
        body = f"""
<section class="surface">
  <div class="toolbar">
    <input class="search" type="search" data-search-code placeholder="Find in source" aria-label="Find in source">
    <div class="code-tools"><button type="button" data-copy="#source">Copy all</button>
      <button type="button" onclick="document.querySelector('.code-frame').classList.toggle('wrap')">Toggle wrapping</button>
      <span class="badge">{esc(language)}</span><span class="pill">{len(highlighted):,} lines</span>
      <span class="pill">{human_size(context.size)}</span></div>
  </div>
  {f'<div class="notice">Large source file shortened to the first 2 MB for preview. Download the original for the full file.</div>' if truncated else ""}
  <div class="code-frame"><pre id="source">{rows}</pre></div>
</section>"""
        return page(context, context.label, "Code", body, subtitle="Read-only source view · scripts are never run.", extra_head=css)
