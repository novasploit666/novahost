from __future__ import annotations

import contextlib
import http.client
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import webbrowser
import zipfile
from pathlib import Path, PureWindowsPath
from unittest.mock import Mock, patch

import novahost.browser as browser_module
from novahost.cli import main
from novahost.core.models import RenderContext, is_path_within_root, quote_relative_url_path
from novahost.core.registry import classify, handler_for_extension, registered_handlers
from novahost.handlers.archive import ArchiveHandler
from novahost.handlers.data import DataHandler
from novahost.handlers.directory import DirectoryHandler
from novahost.handlers.image import ImageHandler
from novahost.handlers.markdown import MarkdownHandler
from novahost.handlers.media import AudioHandler, VideoHandler
from novahost.handlers.special import (
    DatabaseHandler,
    DocumentHandler,
    NotebookHandler,
    PresentationHandler,
    SpreadsheetHandler,
)
from novahost.handlers.text import CodeHandler
from novahost.server import create_server


def context(path: Path, root: Path | None = None, query: dict[str, str] | None = None) -> RenderContext:
    root = (root or path.parent).resolve()
    return RenderContext(root=root, path=path.resolve(), mime_type="application/octet-stream", detected_by="test", query=query)


class DetectionTests(unittest.TestCase):
    def test_directory_and_longest_extension_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(classify(root).handler.key, "directory")
            self.assertEqual(handler_for_extension("bundle.TAR.GZ").key, "archive")
            (root / "notes.md").write_text("# Test")
            self.assertEqual(classify(root / "notes.md").handler.key, "markdown")

    def test_unknown_type_does_not_assume_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "opaque.unknown"
            path.write_bytes(b"\x00\xff\x01")
            info = classify(path)
            self.assertEqual(info.handler.key, "unknown")
            html = info.handler.render(context(path))
            self.assertIn("Hex preview", html)
            self.assertIn("Open as text", html)

    def test_zip_and_office_container_detection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def write_zip(name: str, members: dict[str, str]) -> Path:
                path = root / name
                with zipfile.ZipFile(path, "w") as archive:
                    for member, content in members.items():
                        archive.writestr(member, content)
                return path

            generic = write_zip("generic", {"docs/readme.txt": "archive"})
            empty = write_zip("empty", {})
            damaged = root / "damaged"
            damaged.write_bytes(b"PK\x03\x04not-a-complete-zip")
            xlsx = write_zip(
                "xlsx-no-extension",
                {
                    "[Content_Types].xml": (
                        '<Types><Override PartName="/xl/workbook.xml" '
                        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                        "</Types>"
                    ),
                    "xl/workbook.xml": "<workbook/>",
                },
            )
            xlsm = write_zip(
                "xlsm-no-extension",
                {
                    "[Content_Types].xml": (
                        '<Types><Override PartName="/xl/workbook.xml" '
                        'ContentType="application/vnd.ms-excel.sheet.macroEnabled.main+xml"/>'
                        "</Types>"
                    ),
                    "xl/workbook.xml": "<workbook/>",
                },
            )
            ods = write_zip(
                "ods-no-extension",
                {
                    "mimetype": "application/vnd.oasis.opendocument.spreadsheet",
                    "content.xml": "<document-content/>",
                },
            )
            known_extension = write_zip("known.xlsx", {"notes.txt": "not an Office workbook"})
            oversized_content_types = write_zip(
                "oversized-office-container",
                {
                    "[Content_Types].xml": " " * (256 * 1024 + 1),
                    "xl/workbook.xml": "<workbook/>",
                },
            )
            unknown = root / "opaque.unknown"
            unknown.write_bytes(b"\x00\xff\x01not-a-container")

            self.assertEqual(classify(generic).handler.key, "archive")
            self.assertEqual(classify(empty).handler.key, "archive")
            self.assertEqual(classify(damaged).handler.key, "archive")
            self.assertEqual(classify(oversized_content_types).handler.key, "archive")
            self.assertEqual(classify(xlsx).handler.key, "spreadsheet")
            self.assertEqual(classify(xlsm).handler.key, "spreadsheet")
            self.assertEqual(classify(ods).handler.key, "spreadsheet")
            self.assertEqual(classify(known_extension).handler.key, "spreadsheet")
            self.assertEqual(classify(unknown).handler.key, "unknown")

    def test_registry_is_central_and_handlers_unique(self) -> None:
        keys = [handler.key for handler in registered_handlers()]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("markdown", keys)
        self.assertIn("binary", keys)


class CrossPlatformPathTests(unittest.TestCase):
    def test_windows_path_containment_and_url_encoding(self) -> None:
        root = PureWindowsPath(r"C:\Users\Example\NovaHost")
        file_path = root / "Folder Name" / "report (draft) #50%+ ü.md"
        self.assertTrue(is_path_within_root(file_path, root))
        self.assertTrue(is_path_within_root(PureWindowsPath(r"c:\users\example\novahost\file.md"), root))
        self.assertFalse(is_path_within_root(PureWindowsPath(r"C:\Users\Example\NovaHost-old\file.md"), root))
        self.assertEqual(
            quote_relative_url_path(file_path.relative_to(root)),
            "Folder%20Name/report%20%28draft%29%20%2350%25%2B%20%C3%BC.md",
        )

    def test_render_context_quotes_special_local_names_and_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "folder space" / "café (draft) #50%+.txt"
            path.parent.mkdir()
            path.write_text("local")
            render_context = context(path, root)
            expected = "folder%20space/caf%C3%A9%20%28draft%29%20%2350%25%2B.txt"
            self.assertEqual(render_context.file_url(path), "/__asset__/" + expected)
            self.assertEqual(render_context.view_url(path), "/__view__/" + expected)
            self.assertEqual(render_context.raw_url(path), "/__raw__/" + expected)
            with self.assertRaises(ValueError):
                render_context.file_url(root.parent / "outside.txt")


class BrowserTests(unittest.TestCase):
    def test_uses_platform_default_browser_and_fails_gracefully(self) -> None:
        with patch("novahost.browser.sys.platform", "linux"), patch.object(
            browser_module.webbrowser,
            "open_new_tab",
            return_value=True,
        ) as open_tab:
            self.assertTrue(browser_module.open_browser("http://127.0.0.1:5000/"))
        open_tab.assert_called_once_with("http://127.0.0.1:5000/")

        with patch("novahost.browser.sys.platform", "win32"), patch.object(
            browser_module.os,
            "startfile",
            create=True,
        ) as startfile:
            self.assertTrue(browser_module.open_browser("http://127.0.0.1:5000/"))
        startfile.assert_called_once_with("http://127.0.0.1:5000/")

        with patch("novahost.browser.webbrowser.open_new_tab", side_effect=webbrowser.Error("unavailable")):
            self.assertFalse(browser_module.open_browser("http://127.0.0.1:5000/"))


class RenderingTests(unittest.TestCase):
    def test_markdown_local_image_and_unsafe_html(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "images").mkdir()
            (root / "images" / "chart.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            path = root / "README.md"
            path.write_text("# Hello\n\n## Details\n\n[Read more](details.md)\n\n```python\nprint('safe')\n```\n\n![chart](images/chart.png)\n\n<script>alert(1)</script>\n\n| a | b |\n|---|---|\n| 1 | 2 |")
            html = MarkdownHandler().render(context(path, root))
            self.assertIn('/__asset__/images/chart.png', html)
            self.assertIn('/__view__/details.md', html)
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertIn("<table>", html)
            self.assertIn('aria-label="Table of contents"', html)
            self.assertIn("Copy code", html)
            self.assertIn('class="language-python"', html)

    def test_markdown_error_fallback_escapes_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.md"
            path.write_text("<script>alert('xss')</script>")
            with patch("novahost.handlers.markdown.markdown_body", side_effect=RuntimeError("<failed>")):
                html = MarkdownHandler().render(context(path))
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>alert", html)

    def test_source_highlight_has_line_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "example.py"
            path.write_text("def greet(name):\n    return f'Hi {name}'\n")
            html = CodeHandler().render(context(path))
            self.assertIn("line-no", html)
            self.assertIn("Python", html)
            self.assertIn("scripts are never run", html)
            self.assertIn("def", html)

    def test_source_highlighting_preserves_multiline_lexer_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "multiline.py"
            path.write_text(
                'message = """first line\nsecond line\nthird line"""\n'
                "# outside the string\nvalue = 2\n"
            )
            html = CodeHandler().render(context(path))
            self.assertIn('id="L2"', html)
            self.assertIn('<span class="s2">second line</span>', html)
            self.assertIn('<span class="s2">third line"""</span>', html)
            self.assertIn('<span class="c1"># outside the string</span>', html)

    def test_media_viewers_use_browser_native_elements(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "voice.mp3"
            video = root / "clip.mp4"
            audio.write_bytes(b"")
            video.write_bytes(b"")
            self.assertIn("<audio", AudioHandler().render(context(audio)))
            video_html = VideoHandler().render(context(video))
            self.assertIn("<video", video_html)
            self.assertIn("codec support varies", video_html.lower())

    def test_image_viewer_controls_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cover.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n")
            html = ImageHandler().render(context(path))
            for control in ('data-image-action="fit"', 'data-image-action="actual"', 'data-image-action="rotate"', 'data-image-action="reset"', "Fullscreen"):
                self.assertIn(control, html)
            self.assertIn("data-image-dimensions", html)

    def test_dataset_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.csv"
            path.write_text("name,count\nalpha,3\nbeta,5\n")
            html = DataHandler().render(context(path))
            self.assertIn("2 columns", html)
            self.assertIn("alpha", html)
            self.assertIn("number", html)
            self.assertIn("data-sort-column", html)

    def test_directory_navigation_search_and_sort_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "folder").mkdir()
            (root / "a.txt").write_text("first")
            html = DirectoryHandler().render(context(root, root))
            self.assertIn("folder", html)
            self.assertIn("a.txt", html)
            self.assertIn("data-directory-sort", html)
            self.assertIn("data-filter", html)
            self.assertIn('class="file-row directory-row"', html)

    def test_archive_index_without_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bundle.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("docs/readme.txt", "hello")
            html = ArchiveHandler().render(context(path))
            self.assertIn("docs/readme.txt", html)
            self.assertIn("no extraction", html.lower())
            self.assertFalse((Path(temporary) / "docs").exists())

    def test_sqlite_is_read_only_and_paginated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "records.sqlite"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE records (id INTEGER, name TEXT)")
                connection.execute("INSERT INTO records VALUES (1, 'Nova')")
            html = DatabaseHandler().render(context(path, query={"table": "records"}))
            self.assertIn("Nova", html)
            self.assertIn("Previous", html)
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM records").fetchone()[0], 1)

    def test_notebook_displays_saved_text_without_executing_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.ipynb"
            path.write_text(json.dumps({
                "cells": [
                    {"cell_type": "code", "source": ["print('never run')"], "execution_count": None,
                     "outputs": [{"data": {"text/plain": ["saved value"]}}]},
                    {"cell_type": "markdown", "source": ["# Notes"]},
                ]
            }))
            html = NotebookHandler().render(context(path))
            self.assertIn("never run", html)
            self.assertIn("saved value", html)
            self.assertIn("never executed", html)

    def test_spreadsheet_document_and_presentation_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            xlsx = root / "table.xlsx"
            with zipfile.ZipFile(xlsx, "w") as archive:
                archive.writestr("xl/workbook.xml", '<workbook xmlns:r="urn:r"><sheets><sheet name="Sheet1" r:id="rId1"/></sheets></workbook>')
                archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
                archive.writestr("xl/worksheets/sheet1.xml", '<worksheet><sheetData><row><c r="A1" t="inlineStr"><is><t>Name</t></is></c></row><row><c r="A2" t="inlineStr"><is><t>Nova</t></is></c></row></sheetData></worksheet>')
            self.assertIn("Nova", SpreadsheetHandler().render(context(xlsx)))

            docx = root / "note.docx"
            with zipfile.ZipFile(docx, "w") as archive:
                archive.writestr("word/document.xml", '<document xmlns:w="urn:w"><body><p><r><t>Hello document</t></r></p></body></document>')
            self.assertIn("Hello document", DocumentHandler().render(context(docx)))

            pptx = root / "slides.pptx"
            with zipfile.ZipFile(pptx, "w") as archive:
                archive.writestr("ppt/slides/slide1.xml", '<sld xmlns:a="urn:a"><a:t>Title</a:t><a:t>Summary</a:t></sld>')
            presentation = PresentationHandler().render(context(pptx))
            self.assertIn("Title", presentation)
            self.assertIn("text-only", presentation.lower())


class CliAndServerTests(unittest.TestCase):
    def test_cli_help_version_and_info(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as help_exit:
                main(["--help"])
        self.assertEqual(help_exit.exception.code, 0)
        self.assertIn("no-browser", output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as version_exit:
                main(["--version"])
        self.assertEqual(version_exit.exception.code, 0)
        self.assertIn("novahost", output.getvalue().lower())
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--info"]), 0)
        self.assertIn("Python", output.getvalue())

    def test_cli_list_handlers_invalid_target_and_root_boundary(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--list-handlers"]), 0)
        self.assertIn("spreadsheet", output.getvalue())
        self.assertIn("archive", output.getvalue())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "sample.txt"
            target.write_text("local")
            with patch("novahost.cli.create_server") as create:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main([str(root / "missing.txt")]), 2)
                    self.assertEqual(main([str(target), "--root", str(root / "other")]), 2)
            create.assert_not_called()

    def test_cli_default_port_and_info_with_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "sample.md"
            target.write_text("# Local")
            server = Mock()
            server.server_address = ("127.0.0.1", 5000)
            server.serve_forever.side_effect = KeyboardInterrupt
            with patch("novahost.cli.create_server", return_value=server) as create:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main(["--info", str(target), "--no-browser"]), 0)
            self.assertEqual(create.call_args.args[3], 5000)
            self.assertIn("Python", output.getvalue())
            self.assertIn("http://127.0.0.1:5000/", output.getvalue())

    def test_no_browser_light_and_port_zero_options(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "sample.md"
            target.write_text("# Local")
            server = Mock()
            server.server_address = ("127.0.0.1", 43210)
            server.serve_forever.side_effect = KeyboardInterrupt
            with patch("novahost.cli.create_server", return_value=server) as create:
                with patch("novahost.cli.open_browser") as browser:
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(main([str(target), "--no-browser", "--light", "--host", "127.0.0.1", "--port", "0"]), 0)
            create.assert_called_once()
            self.assertTrue(create.call_args.kwargs["light"])
            self.assertEqual(create.call_args.args[2], "127.0.0.1")
            self.assertEqual(create.call_args.args[3], 0)
            browser.assert_not_called()
            server.shutdown.assert_called_once()
            server.server_close.assert_called_once()
            self.assertIn("http://127.0.0.1:43210/", output.getvalue())

    def test_server_local_assets_range_security_and_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            root = temporary_path / "served"
            root.mkdir()
            target = root / "index.html"
            target.write_text('<html><link rel="stylesheet" href="site.css"><link rel="icon" href="/site.css"><script src="/site.js"></script><body>local</body></html>')
            (root / "site.css").write_text("body { color: green; }")
            (root / "site.js").write_text("window.loaded = true;")
            special_file = root / "folder space" / "café (draft) #50%+.txt"
            special_file.parent.mkdir()
            special_file.write_text("encoded name")
            asset = root / "clip.mp4"
            asset.write_bytes(b"0123456789")
            (root / "document.pdf").write_bytes(b"%PDF-1.4\n% test")
            secret = temporary_path / "secret.txt"
            secret.write_text("outside root")
            try:
                (root / "leak.txt").symlink_to(secret)
            except OSError:
                pass
            with self.assertRaises(ValueError):
                create_server(root, secret, "127.0.0.1", 0)
            server = create_server(root, target, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.server_address[1]
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request("GET", "/")
                response = connection.getresponse()
                self.assertEqual(response.status, 302)
                raw_location = response.getheader("Location")
                response.read()
                connection.request("GET", raw_location)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn(b"site.css", response.read())

                connection.request("GET", "/__raw__/site.css")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"body { color: green; }")
                connection.request("GET", "/site.css")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"body { color: green; }")
                connection.request("GET", "/site.js")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"window.loaded = true;")

                special_url = context(special_file, root).file_url(special_file)
                connection.request("GET", special_url)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"encoded name")

                connection.request("GET", "/__view__/document.pdf")
                response = connection.getresponse()
                self.assertEqual(response.status, 302)
                pdf_location = response.getheader("Location")
                response.read()
                connection.request("GET", pdf_location)
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader("Content-Type"), "application/pdf")
                self.assertTrue(response.read().startswith(b"%PDF"))

                connection.request("GET", "/__asset__/clip.mp4", headers={"Range": "bytes=2-5"})
                response = connection.getresponse()
                self.assertEqual(response.status, 206)
                self.assertEqual(response.read(), b"2345")

                connection.request("GET", "/__asset__/%2e%2e/etc/passwd")
                response = connection.getresponse()
                self.assertEqual(response.status, 404)
                response.read()
                connection.request("GET", "/__asset__/folder%5C..%5Csecret.txt")
                response = connection.getresponse()
                self.assertEqual(response.status, 404)
                response.read()
                connection.request("GET", "/__asset__/C%3A/Windows/win.ini")
                response = connection.getresponse()
                self.assertEqual(response.status, 404)
                response.read()
                if (root / "leak.txt").is_symlink():
                    connection.request("GET", "/__asset__/leak.txt")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 404)
                    response.read()
                connection.close()
            finally:
                server.shutdown()
                thread.join(timeout=3)
                server.server_close()
            self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
