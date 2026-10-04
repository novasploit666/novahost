"""Threaded localhost server with bounded filesystem routing and range support."""

from __future__ import annotations

import mimetypes
import socket
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PureWindowsPath
from urllib.parse import parse_qs, unquote, urlsplit

from novahost.core.models import RenderContext, is_path_within_root
from novahost.core.registry import classify


@dataclass(frozen=True)
class ServerConfig:
    root: Path
    target: Path
    light: bool = False
    forced_handler: str | None = None
    verbose: bool = False


class NovaHTTPServer(ThreadingHTTPServer):
    """Thread-per-request server so streamed media does not block viewers."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], config: ServerConfig):
        self.config = config
        if ":" in address[0]:
            self.address_family = socket.AF_INET6
        super().__init__(address, NovaRequestHandler)


class NovaRequestHandler(BaseHTTPRequestHandler):
    server: NovaHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        if self.server.config.verbose:
            sys.stderr.write(f"[novahost] {self.address_string()} - {format % args}\n")

    def do_GET(self) -> None:
        self._dispatch(send_body=True)

    def do_HEAD(self) -> None:
        self._dispatch(send_body=False)

    def _dispatch(self, *, send_body: bool) -> None:
        parsed = urlsplit(self.path)
        route = parsed.path
        try:
            if route == "/":
                path = self.server.config.target
                self._serve_view(path, {}, send_body)
                return
            if route.startswith("/__asset__/"):
                path = self._resolve(route[len("/__asset__/"):])
                self._send_file(path, send_body=send_body)
                return
            if route.startswith("/__raw__/"):
                path = self._resolve(route[len("/__raw__/"):])
                if not path.is_file():
                    self._not_found(send_body)
                    return
                self._send_file(path, send_body=send_body)
                return
            if route.startswith("/__view__/"):
                path = self._resolve(route[len("/__view__/"):])
                self._serve_view(path, parse_qs(parsed.query), send_body)
                return
            # Preserve root-relative assets in native HTML/CSS projects.
            if route != "/":
                path = self._resolve(route.lstrip("/"))
                if path.is_file():
                    self._send_file(path, send_body=send_body)
                    return
            self._not_found(send_body)
        except (ValueError, OSError, PermissionError):
            self._not_found(send_body)
        except Exception as error:
            if self.server.config.verbose:
                sys.stderr.write(f"[novahost] render error for {self.path}: {type(error).__name__}: {error}\n")
            self._send_html(
                "<!doctype html><meta charset=utf-8><title>Preview error</title>"
                "<main style='font:16px system-ui;max-width:640px;margin:15vh auto;padding:24px'>"
                "<h1>This file could not be previewed</h1><p>Try downloading the original or opening it as text.</p></main>",
                status=500,
                send_body=send_body,
            )

    def _resolve(self, encoded: str) -> Path:
        """Resolve a URL path only when the final path remains inside the root."""
        try:
            decoded = unquote(encoded, errors="strict")
        except UnicodeDecodeError as error:
            raise ValueError("Invalid URL encoding") from error
        parts = decoded.split("/")
        windows_path = PureWindowsPath(decoded)
        if (
            not decoded
            or "\x00" in decoded
            or "\\" in decoded
            or decoded.startswith("/")
            or windows_path.drive
            or windows_path.root
            or any(part in {"", ".", ".."} or ":" in part for part in parts)
        ):
            raise ValueError("Invalid path")
        candidate = self.server.config.root.joinpath(*parts).resolve(strict=True)
        if not is_path_within_root(candidate, self.server.config.root):
            raise ValueError("Path escapes the served root")
        return candidate

    def _serve_view(self, path: Path, query: dict[str, list[str]], send_body: bool) -> None:
        first = lambda key: query.get(key, [""])[0]
        try:
            path = path.resolve(strict=True)
        except OSError:
            self._not_found(send_body)
            return
        if not is_path_within_root(path, self.server.config.root):
            self._not_found(send_body)
            return
        if not path.exists():
            self._not_found(send_body)
            return
        if not path.is_dir() and not path.is_file():
            self._not_found(send_body)
            return
        if path.is_file() and not self.server.config.forced_handler and not first("as") and self._is_native(path):
            relative = path.relative_to(self.server.config.root).as_posix()
            from urllib.parse import quote

            self.send_response(302)
            self.send_header("Location", "/__raw__/" + quote(relative, safe="/"))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        forced: str | None = None
        if first("as") == "text":
            forced = "text"
        elif first("as") == "hex":
            forced = "binary"
        elif path == self.server.config.target:
            forced = self.server.config.forced_handler
        file_info = classify(path, forced_handler=forced)
        context = RenderContext(
            root=self.server.config.root,
            path=path,
            mime_type=file_info.mime_type,
            detected_by=file_info.detected_by,
            light=self.server.config.light or first("theme") == "light",
            query={key: value[0] for key, value in query.items()},
            forced_text=first("as") == "text",
            forced_hex=first("as") == "hex",
        )
        document = file_info.handler.render(context)
        self._send_html(document, send_body=send_body)

    @staticmethod
    def _is_native(path: Path) -> bool:
        info = classify(path)
        return bool(getattr(info.handler, "native", False))

    def _send_file(self, path: Path, *, send_body: bool) -> None:
        if not path.is_file():
            self._not_found(send_body)
            return
        try:
            size = path.stat().st_size
            mime_type, _ = mimetypes.guess_type(path.name)
            mime_type = mime_type or "application/octet-stream"
            if path.suffix.lower() == ".mkv":
                mime_type = "video/x-matroska"
            elif path.suffix.lower() == ".flac":
                mime_type = "audio/flac"
            elif path.suffix.lower() == ".opus":
                mime_type = "audio/ogg"
            start, end, status = 0, max(size - 1, 0), 200
            range_header = self.headers.get("Range")
            if range_header and size:
                try:
                    unit, spec = range_header.split("=", 1)
                    if unit.strip() != "bytes" or "," in spec:
                        raise ValueError
                    left, right = spec.strip().split("-", 1)
                    if left:
                        start = int(left)
                        end = int(right) if right else size - 1
                    else:
                        length = int(right)
                        start = max(size - length, 0)
                    if start < 0 or end < start or start >= size:
                        raise ValueError
                    end = min(end, size - 1)
                    status = 206
                except ValueError:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            length = max(0, end - start + 1) if size else 0
            self.send_response(status)
            self.send_header("Content-Type", mime_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if send_body and length:
                with path.open("rb") as file:
                    file.seek(start)
                    remaining = length
                    while remaining:
                        chunk = file.read(min(64 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
        except (OSError, BrokenPipeError, ConnectionResetError):
            return

    def _send_html(self, document: str, *, status: int = 200, send_body: bool = True) -> None:
        payload = document.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _not_found(self, send_body: bool) -> None:
        self._send_html(
            "<!doctype html><meta charset=utf-8><title>Not found · NovaHost</title>"
            "<main style='font:16px system-ui;max-width:600px;margin:15vh auto;padding:24px'>"
            "<h1>That path is not available</h1><p>NovaHost only serves files inside the selected root.</p>"
            "<a href='/'>Return to the preview</a></main>",
            status=404,
            send_body=send_body,
        )


def create_server(
    root: Path,
    target: Path,
    host: str = "127.0.0.1",
    port: int = 5000,
    *,
    light: bool = False,
    forced_handler: str | None = None,
    verbose: bool = False,
) -> NovaHTTPServer:
    """Create, but do not start, the local HTTP server."""
    resolved_root = root.expanduser().resolve()
    resolved_target = target.expanduser().resolve()
    if not is_path_within_root(resolved_target, resolved_root):
        raise ValueError("Target must be inside the selected serving root.")
    return NovaHTTPServer(
        (host, port),
        ServerConfig(
            root=resolved_root,
            target=resolved_target,
            light=light,
            forced_handler=forced_handler,
            verbose=verbose,
        ),
    )
