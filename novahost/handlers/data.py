"""Bounded CSV, TSV, JSON, and line-delimited JSON inspection."""

from __future__ import annotations

import csv
import json
from itertools import islice

from novahost.core.models import RenderContext
from novahost.handlers.base import Handler
from novahost.ui.shell import esc, page

MAX_DATA_BYTES = 32 * 1024 * 1024
MAX_PREVIEW_ROWS = 200


def _table(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(f'<th data-sort-column title="Sort by {esc(value)}">{esc(value)} ↕</th>' for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody id="data-rows">{body}</tbody></table></div>'


class DataHandler(Handler):
    key = "data"
    label = "Dataset"

    def render(self, context: RenderContext) -> str:
        suffix = context.path.suffix.lower()
        if suffix in {".parquet", ".feather", ".avro"}:
            body = f"""
<section class="surface surface-pad"><div class="notice">This is a {esc(suffix.lstrip('.').upper())} dataset. NovaHost does not bundle a format-specific decoder, so it will not guess at the file contents.</div>
<div class="kv"><div><small>File size</small><strong>{context.size:,} bytes</strong></div><div><small>MIME</small><strong>{esc(context.mime_type)}</strong></div></div>
<a class="button" href="{context.file_url(context.path)}" download>Download original</a></section>"""
            return page(context, context.label, "Dataset · inspection only", body, subtitle="No decoder is installed for this columnar/binary format.")
        if context.size > MAX_DATA_BYTES:
            body = f'<section class="surface surface-pad"><div class="notice">This file is {context.size:,} bytes. The interactive preview is limited to {MAX_DATA_BYTES:,} bytes to avoid loading a large dataset into memory.</div><a class="button" href="{context.file_url(context.path)}" download>Download original</a></section>'
            return page(context, context.label, "Dataset", body, subtitle="Large dataset preview is disabled.")
        try:
            if suffix in {".jsonl", ".ndjson"}:
                data_rows = []
                with context.path.open(encoding="utf-8") as source:
                    for line in islice(source, 5001):
                        if line.strip():
                            data_rows.append(json.loads(line))
                preview = data_rows[:MAX_PREVIEW_ROWS]
                if preview and isinstance(preview[0], dict):
                    headers = list(dict.fromkeys(key for row in preview if isinstance(row, dict) for key in row))
                    rows = [[row.get(key, "") if isinstance(row, dict) else row for key in headers] for row in preview]
                else:
                    headers, rows = ["JSON value"], [[json.dumps(row, ensure_ascii=False)] for row in preview]
                count_note = "at least 5,001" if len(data_rows) > 5000 else str(len(data_rows))
            elif suffix == ".json":
                value = json.loads(context.path.read_text(encoding="utf-8"))
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    preview = value[:MAX_PREVIEW_ROWS]
                    headers = list(dict.fromkeys(key for row in preview if isinstance(row, dict) for key in row))
                    rows = [[row.get(key, "") if isinstance(row, dict) else row for key in headers] for row in preview]
                    count_note = str(len(value))
                else:
                    headers, rows = ["JSON"], [[json.dumps(value, ensure_ascii=False, indent=2)]]
                    count_note = "1 document"
            else:
                delimiter = "\t" if suffix == ".tsv" else ","
                with context.path.open(encoding="utf-8-sig", newline="") as source:
                    reader = csv.reader(source, delimiter=delimiter)
                    headers = next(reader, [])
                    rows = list(islice(reader, MAX_PREVIEW_ROWS + 1))
                count_note = "first 201 rows" if len(rows) > MAX_PREVIEW_ROWS else f"{len(rows)} rows"
                rows = rows[:MAX_PREVIEW_ROWS]
            nulls = [sum(1 for row in rows if index >= len(row) or row[index] in (None, "")) for index in range(len(headers))]
            types = []
            for index in range(len(headers)):
                values = [row[index] for row in rows if index < len(row) and row[index] not in ("", None)]
                types.append("number" if values and all(_is_number(value) for value in values) else "text")
            table = _table(headers, rows) if headers else '<div class="empty">No rows to display.</div>'
            info = "".join(
                f'<div class="tile"><strong>{esc(headers[index])}</strong><p>{esc(types[index])} · {nulls[index]} empty in preview</p></div>'
                for index in range(min(len(headers), 40))
            )
            body = f"""
<section class="surface"><div class="toolbar"><input class="search" type="search" data-filter="#data-rows tr" placeholder="Search preview rows" aria-label="Search rows">
<span class="pill">{len(headers)} columns</span><span class="pill">{esc(count_note)}</span></div><div class="content">{table}
<div class="kv">{info}</div></div></section>"""
        except (OSError, UnicodeError, csv.Error, json.JSONDecodeError, ValueError) as error:
            body = f'<section class="surface surface-pad"><div class="notice error">Could not read this dataset: {esc(error)}</div><a class="button" href="{context.file_url(context.path)}" download>Download original</a></section>'
        return page(context, context.label, "Dataset", body, subtitle="Interactive preview is bounded; the original data is never modified.")


def _is_number(value: object) -> bool:
    try:
        float(str(value))
        return True
    except (TypeError, ValueError):
        return False
