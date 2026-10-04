"""Read-only inspectors for notebooks, office files, and SQLite databases."""

from __future__ import annotations

import json
import posixpath
import sqlite3
import zipfile
from pathlib import PurePosixPath
from urllib.parse import quote
from xml.etree import ElementTree as ET

from novahost.core.models import RenderContext
from novahost.handlers.base import Handler
from novahost.handlers.markdown import markdown_body
from novahost.ui.shell import esc, human_size, page

MAX_OFFICE_FILE = 64 * 1024 * 1024
MAX_PREVIEW_ROWS = 200


def _zip_xml(archive: zipfile.ZipFile, member: str) -> ET.Element:
    info = archive.getinfo(member)
    if info.file_size > MAX_OFFICE_FILE:
        raise ValueError(f"Document part is too large to preview: {member}")
    return ET.fromstring(archive.read(member))


def _tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _all_text(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def _sheet_cell(cell: ET.Element, shared: list[str]) -> object:
    kind = cell.attrib.get("t", "")
    value = cell.find("{*}v")
    if kind == "inlineStr":
        inline = cell.find("{*}is")
        return _all_text(inline) if inline is not None else ""
    if value is None:
        formula = cell.find("{*}f")
        return f"={_all_text(formula)}" if formula is not None else ""
    content = value.text or ""
    if kind == "s":
        try:
            return shared[int(content)]
        except (ValueError, IndexError):
            return content
    if kind == "b":
        return "TRUE" if content == "1" else "FALSE"
    return content


def _xlsx_sheets(archive: zipfile.ZipFile) -> list[tuple[str, list[list[object]]]]:
    workbook = _zip_xml(archive, "xl/workbook.xml")
    rel_root = _zip_xml(archive, "xl/_rels/workbook.xml.rels")
    rels = {el.attrib.get("Id", ""): el.attrib.get("Target", "") for el in rel_root}
    shared: list[str] = []
    if "xl/sharedStrings.xml" in archive.namelist():
        strings = _zip_xml(archive, "xl/sharedStrings.xml")
        shared = [_all_text(item) for item in strings if _tag_name(item.tag) == "si"]
    output = []
    sheets = next((el for el in workbook.iter() if _tag_name(el.tag) == "sheets"), None)
    if sheets is None:
        return output
    for sheet in list(sheets)[:40]:
        title = sheet.attrib.get("name", "Sheet")
        rel_id = next((value for key, value in sheet.attrib.items() if _tag_name(key) == "id"), "")
        target = rels.get(rel_id, "")
        member = posixpath.normpath(posixpath.join("xl", target))
        if member.startswith("../") or member not in archive.namelist():
            continue
        root = _zip_xml(archive, member)
        rows: list[list[object]] = []
        sheet_data = next((el for el in root.iter() if _tag_name(el.tag) == "sheetData"), None)
        if sheet_data is not None:
            for row in list(sheet_data)[:MAX_PREVIEW_ROWS + 1]:
                cells = []
                for cell in list(row)[:80]:
                    cells.append(_sheet_cell(cell, shared))
                rows.append(cells)
        output.append((title, rows))
    return output


def _ods_sheets(archive: zipfile.ZipFile) -> list[tuple[str, list[list[object]]]]:
    root = _zip_xml(archive, "content.xml")
    output = []
    for table in (el for el in root.iter() if _tag_name(el.tag) == "table"):
        title = next((v for k, v in table.attrib.items() if _tag_name(k) == "name"), "Sheet")
        rows: list[list[object]] = []
        for row in (el for el in table.iter() if _tag_name(el.tag) == "table-row"):
            cells: list[object] = []
            for cell in (el for el in row if _tag_name(el.tag) in {"table-cell", "covered-table-cell"}):
                value = next((v for k, v in cell.attrib.items() if _tag_name(k) == "value"), "")
                text = _all_text(cell)
                cells.append(text or value)
                repeat = next((v for k, v in cell.attrib.items() if _tag_name(k) == "number-columns-repeated"), "1")
                try:
                    cells.extend([""] * min(max(int(repeat) - 1, 0), 100))
                except ValueError:
                    pass
                if len(cells) >= 80:
                    break
            rows.append(cells[:80])
            if len(rows) >= MAX_PREVIEW_ROWS + 1:
                break
        output.append((title, rows))
        if len(output) >= 40:
            break
    return output


def _office_table(rows: list[list[object]]) -> str:
    if not rows:
        return '<div class="empty">No visible rows.</div>'
    columns = max((len(row) for row in rows), default=0)
    if not columns:
        return '<div class="empty">No visible cells.</div>'
    header = rows[0]
    th = "".join(f"<th>{esc(header[i] if i < len(header) else '')}</th>" for i in range(columns))
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(value)}</td>" for value in (row + [""] * columns)[:columns]) + "</tr>"
        for row in rows[1:MAX_PREVIEW_ROWS + 1]
    )
    return f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


class SpreadsheetHandler(Handler):
    key = "spreadsheet"
    label = "Spreadsheet"

    def render(self, context: RenderContext) -> str:
        suffix = context.path.suffix.lower()
        message = ""
        try:
            if context.size > MAX_OFFICE_FILE:
                raise ValueError("File exceeds the 64 MiB preview limit.")
            if suffix == ".xls":
                raise ValueError("Legacy .xls files need an external converter; NovaHost will not claim a preview it cannot render.")
            with zipfile.ZipFile(context.path) as archive:
                sheets = _ods_sheets(archive) if suffix == ".ods" else _xlsx_sheets(archive)
            sheet_html = "".join(
                f'<section style="margin:20px 0"><h2>{esc(name)}</h2>{_office_table(rows)}</section>'
                for name, rows in sheets
            )
            if not sheets:
                message = "No supported worksheets were found."
            body = f'<section class="surface surface-pad">{sheet_html or f"<div class=notice>{esc(message)}</div>"}<div class="notice">Read-only preview · formulas are shown as stored, not recalculated.</div></section>'
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as error:
            body = f'<section class="surface surface-pad"><div class="notice error">{esc(error)}</div><a class="button" href="{context.file_url(context.path)}" download>Download original</a></section>'
        return page(context, context.label, "Spreadsheet", body, subtitle="Office rendering is best-effort and read-only.")


class PresentationHandler(Handler):
    key = "presentation"
    label = "Presentation"

    def render(self, context: RenderContext) -> str:
        suffix = context.path.suffix.lower()
        try:
            if context.size > MAX_OFFICE_FILE:
                raise ValueError("File exceeds the 64 MiB preview limit.")
            if suffix != ".pptx":
                raise ValueError(f"{suffix.upper()} slides are not decoded by NovaHost. Download the original for a faithful presentation.")
            with zipfile.ZipFile(context.path) as archive:
                members = sorted(
                    (name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")),
                    key=lambda name: int("".join(c for c in PurePosixPath(name).stem if c.isdigit()) or 0),
                )[:500]
                slides = []
                for number, member in enumerate(members, 1):
                    root = _zip_xml(archive, member)
                    text = [_all_text(el) for el in root.iter() if _tag_name(el.tag) == "t"]
                    title = text[0] if text else f"Slide {number}"
                    paragraphs = "".join(f"<p>{esc(value)}</p>" for value in text[1:] if value)
                    slides.append(f'<article class="surface slide" data-slide><div class="eyebrow">Slide {number}</div><h2>{esc(title)}</h2>{paragraphs}</article>')
            body = f"""
<section class="surface" data-slideshow><div class="content">{''.join(slides) or '<div class="empty">No slides found.</div>'}</div>
<div class="toolbar"><button type="button" data-prev>Previous</button><span class="pill" data-slide-count></span><button type="button" data-next>Next</button><span class="muted">Use ← / → keys</span></div>
<div class="media-meta">Text-only extraction from PPTX. Layout, charts, animations, and embedded media are not reproduced.</div></section>"""
        except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as error:
            body = f'<section class="surface surface-pad"><div class="notice error">{esc(error)}</div><a class="button" href="{context.file_url(context.path)}" download>Download original</a></section>'
        return page(context, context.label, "Presentation", body, subtitle="Best-effort offline text slideshow; not a pixel-faithful Office renderer.")


class DocumentHandler(Handler):
    key = "document"
    label = "Document"

    def render(self, context: RenderContext) -> str:
        suffix = context.path.suffix.lower()
        try:
            if context.size > MAX_OFFICE_FILE:
                raise ValueError("File exceeds the 64 MiB preview limit.")
            if suffix == ".doc":
                raise ValueError("Legacy .doc files need an external converter; the original is available to download.")
            member = "content.xml" if suffix == ".odt" else "word/document.xml"
            with zipfile.ZipFile(context.path) as archive:
                root = _zip_xml(archive, member)
            blocks = []
            for element in root.iter():
                kind = _tag_name(element.tag)
                if kind in {"p", "h"}:
                    text = _all_text(element)
                    if text:
                        blocks.append(f"<p>{esc(text)}</p>")
                elif kind == "table":
                    rows = []
                    for row in element.iter():
                        if _tag_name(row.tag) in {"tr", "table-row"}:
                            cells = [_all_text(cell) for cell in row if _tag_name(cell.tag) in {"tc", "table-cell"}]
                            if cells:
                                rows.append(cells)
                    if rows:
                        blocks.append(_office_table(rows))
            content = "".join(blocks) or '<div class="empty">No readable text was found.</div>'
            body = f'<article class="surface surface-pad markdown">{content}</article><div class="actions" style="margin-top:12px"><a class="button" href="{context.file_url(context.path)}" download>Download original</a><button type="button" onclick="window.print()">Print</button></div>'
        except (OSError, ValueError, zipfile.BadZipFile, KeyError, ET.ParseError) as error:
            body = f'<section class="surface surface-pad"><div class="notice error">{esc(error)}</div><a class="button" href="{context.file_url(context.path)}" download>Download original</a></section>'
        return page(context, context.label, "Document", body, subtitle="Text and simple tables are extracted; pagination and advanced formatting may differ.")


class NotebookHandler(Handler):
    key = "notebook"
    label = "Jupyter notebook"

    def render(self, context: RenderContext) -> str:
        try:
            if context.size > 32 * 1024 * 1024:
                raise ValueError("Notebook exceeds the 32 MiB preview limit.")
            notebook = json.loads(context.path.read_text(encoding="utf-8"))
            cells = notebook.get("cells", [])
            rendered_cells = []
            for index, cell in enumerate(cells[:1000], 1):
                kind = cell.get("cell_type", "raw")
                source = cell.get("source", "")
                source = "".join(source) if isinstance(source, list) else str(source)
                if kind == "markdown":
                    cell_body = f'<div class="markdown">{markdown_body(source, context)}</div>'
                else:
                    cell_body = f'<div class="code-frame"><pre>{esc(source)}</pre></div>'
                execution = cell.get("execution_count")
                rendered_cells.append(f'<section class="surface notebook-cell"><div class="cell-label">In [{esc(execution if execution is not None else " ")}] · {esc(kind)} · cell {index}</div><div class="cell-body">{cell_body}</div>')
                outputs = cell.get("outputs", [])
                for output in outputs[:100]:
                    data = output.get("data", {})
                    if "text/plain" in data:
                        value = data["text/plain"]
                        value = "".join(value) if isinstance(value, list) else str(value)
                        rendered_cells.append(f'<div class="cell-body"><div class="cell-label">Saved output</div><pre>{esc(value[:100_000])}</pre></div>')
                    elif "image/png" in data:
                        encoded = data["image/png"]
                        encoded = "".join(encoded) if isinstance(encoded, list) else str(encoded)
                        if len(encoded) <= 4_000_000:
                            rendered_cells.append(f'<div class="cell-body"><img alt="Saved notebook output" style="max-width:100%" src="data:image/png;base64,{esc(encoded)}"></div>')
                    elif "text/html" in data:
                        value = data["text/html"]
                        value = "".join(value) if isinstance(value, list) else str(value)
                        rendered_cells.append(f'<div class="cell-body"><details><summary>Saved HTML output (shown as text for safety)</summary><pre>{esc(value[:100_000])}</pre></details></div>')
                rendered_cells.append("</section>")
            body = "".join(rendered_cells) or '<section class="surface empty">This notebook has no cells.</section>'
            warning = '<div class="notice">Notebook cells are read-only. Code is never executed. Rich HTML outputs are shown as text to prevent active content.</div>'
            body = warning + body
        except (OSError, ValueError, json.JSONDecodeError) as error:
            body = f'<section class="surface surface-pad"><div class="notice error">Could not parse notebook: {esc(error)}</div><a class="button" href="{context.file_url(context.path)}" download>Download original</a></section>'
        return page(context, context.label, "Notebook", body, subtitle="Saved cells and outputs · read-only · no kernel is started.")


class DatabaseHandler(Handler):
    key = "database"
    label = "SQLite database"

    def render(self, context: RenderContext) -> str:
        if context.path.suffix.lower() == ".sql":
            from novahost.handlers.text import CodeHandler

            return CodeHandler().render(context)
        try:
            uri = context.path.as_uri() + "?mode=ro&immutable=1"
            with sqlite3.connect(uri, uri=True, timeout=2) as connection:
                connection.execute("PRAGMA query_only = ON")
                tables = [
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                    )
                ]
                query = context.query or {}
                selected = query.get("table", "")
                table_links = "".join(
                    f'<a class="button" href="{context.view_url(context.path)}?table={quote(name)}">{esc(name)}</a>'
                    for name in tables
                )
                body = f'<section class="surface surface-pad"><h2>Tables</h2><div class="actions">{table_links or "<span class=muted>No user tables</span>"}</div>'
                if selected in tables:
                    safe_name = selected.replace('"', '""')
                    page_num = max(0, min(int(query.get("page", "0")), 100_000))
                    columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{safe_name}")')]
                    total = connection.execute(f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0]
                    rows = connection.execute(f'SELECT * FROM "{safe_name}" LIMIT 100 OFFSET ?', (page_num * 100,)).fetchall()
                    header = "".join(f"<th>{esc(name)}</th>" for name in columns)
                    table_rows = "".join("<tr>" + "".join(f"<td>{esc(value)}</td>" for value in row) + "</tr>" for row in rows)
                    previous = max(0, page_num - 1)
                    next_page = page_num + 1
                    controls = f'<div class="pagination"><a class="button" href="{context.view_url(context.path)}?table={quote(selected)}&page={previous}">Previous</a><span>{page_num * 100 + 1 if total else 0}–{min((page_num + 1) * 100, total)} of {total}</span><a class="button" href="{context.view_url(context.path)}?table={quote(selected)}&page={next_page}">Next</a></div>'
                    body += f'<h2>{esc(selected)}</h2><p class="muted">{len(columns)} columns · {total} rows</p><div class="table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{table_rows}</tbody></table></div>{controls}'
                body += '<div class="notice">Opened in immutable read-only mode. No SQL statements from the file or user are executed.</div></section>'
        except (OSError, sqlite3.Error, ValueError) as error:
            body = f'<section class="surface surface-pad"><div class="notice error">Could not open SQLite database read-only: {esc(error)}</div><a class="button" href="{context.file_url(context.path)}" download>Download original</a></section>'
        return page(context, context.label, "SQLite", body, subtitle="Read-only tables, schemas, row counts, and paginated samples.")
