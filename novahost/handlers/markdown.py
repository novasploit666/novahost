"""Offline Markdown rendering with safe local asset routing."""

from __future__ import annotations

import re
from html import escape
from urllib.parse import urlsplit

from novahost.core.models import RenderContext
from novahost.handlers.base import Handler
from novahost.ui.shell import page


def markdown_body(text: str, context: RenderContext) -> str:
    """Render Markdown without allowing raw HTML or remote rendering services."""
    from markdown_it import MarkdownIt
    from mdit_py_plugins.anchors import anchors_plugin
    from mdit_py_plugins.footnote import footnote_plugin
    from mdit_py_plugins.tasklists import tasklists_plugin

    md = MarkdownIt("gfm-like", {"html": False, "linkify": False, "typographer": True})
    md.use(tasklists_plugin, enabled=True)
    md.use(footnote_plugin)
    md.use(anchors_plugin, min_level=1, max_level=6, permalink=False)
    try:
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import get_lexer_by_name
        from pygments.util import ClassNotFound

        formatter = HtmlFormatter(nowrap=True, style="native")

        def highlighter(code: str, language: str | None, _attrs: str) -> str:
            if not language:
                return ""
            try:
                lexer = get_lexer_by_name(language, stripall=False)
            except ClassNotFound:
                return ""
            safe_language = escape(language, quote=True)
            return f'<pre class="highlight"><code class="language-{safe_language}">{highlight(code, lexer, formatter)}</code></pre>'

        md.options["highlight"] = highlighter
        pygments_css = f"<style>{formatter.get_style_defs('.markdown')}</style>"
    except ImportError:
        pygments_css = ""

    default_link = md.renderer.rules.get("link_open")
    if default_link is None:
        default_link = lambda tokens, index, options, env: md.renderer.renderToken(tokens, index, options, env)
    default_image = md.renderer.rules["image"]

    def local_link(tokens: list, index: int, options: dict, env: dict) -> str:
        token = tokens[index]
        href = token.attrGet("href") or ""
        split = urlsplit(href)
        if href and not split.scheme and not split.netloc and not href.startswith("//") and not href.startswith("#"):
            try:
                token.attrSet("href", context.view_url(split.path) + (f"?{split.query}" if split.query else "") + (f"#{split.fragment}" if split.fragment else ""))
            except (ValueError, OSError):
                token.attrSet("href", "#")
        return default_link(tokens, index, options, env)

    def local_image(tokens: list, index: int, options: dict, env: dict) -> str:
        token = tokens[index]
        src = token.attrGet("src") or ""
        split = urlsplit(src)
        if src and not split.scheme and not split.netloc and not src.startswith("//"):
            try:
                token.attrSet("src", context.file_url(split.path))
            except (ValueError, OSError):
                token.attrSet("src", "")
        return default_image(tokens, index, options, env)

    md.renderer.rules["link_open"] = local_link
    md.renderer.rules["image"] = local_image
    tokens = md.parse(text)
    rendered = md.renderer.render(tokens, md.options, {})
    headings: list[tuple[int, str, str]] = []
    for index, token in enumerate(tokens[:-1]):
        if token.type == "heading_open":
            inline = tokens[index + 1]
            anchor = token.attrGet("id")
            if anchor:
                headings.append((int(token.tag[1:]), str(anchor), inline.content))
    toc = ""
    if len(headings) >= 2:
        items = "".join(
            f'<li class="toc-level-{level}"><a href="#{anchor}">{_escape_heading(label)}</a></li>'
            for level, anchor, label in headings
        )
        toc = f'<nav class="toc" aria-label="Table of contents"><strong>On this page</strong><ol>{items}</ol></nav>'
    code_index = 0

    def add_copy(match: re.Match[str]) -> str:
        nonlocal code_index
        code_index += 1
        attrs, content = match.group(1), match.group(2)
        return f'<pre id="md-code-{code_index}"{attrs}>{content}</pre><button type="button" data-copy="#md-code-{code_index}">Copy code</button>'

    rendered = re.sub(r"<pre([^>]*)>(.*?)</pre>", add_copy, rendered, flags=re.DOTALL)
    rendered = toc + rendered
    return pygments_css + rendered


def _escape_heading(value: str) -> str:
    from html import escape

    return escape(value, quote=True)


class MarkdownHandler(Handler):
    key = "markdown"
    label = "Markdown"

    def render(self, context: RenderContext) -> str:
        try:
            if context.size > 4 * 1024 * 1024:
                raise ValueError("Markdown preview is limited to 4 MiB.")
            source = context.path.read_text(encoding="utf-8", errors="replace")
            rendered = markdown_body(source, context)
            body = f'<article class="surface surface-pad markdown">{rendered}</article>'
        except Exception as error:
            source = locals().get("source", "")
            body = (
                f'<section class="surface surface-pad"><div class="notice error">Could not render this Markdown file: '
                f'{escape(f"{type(error).__name__}: {error}", quote=True)}</div>'
                f'<pre>{escape(source, quote=True)}</pre>'
                f'<a class="button" href="{context.file_url(context.path)}" download>Download original</a></section>'
            )
        return page(context, context.label, "Markdown", body, subtitle="Offline document view · local links and assets stay on this machine.")
