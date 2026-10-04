"""Safe inspection and download for binary and unrecognized formats."""

from __future__ import annotations

import hashlib
import struct

from novahost.core.models import RenderContext
from novahost.handlers.base import Handler
from novahost.ui.shell import esc, human_size, page


SIGNATURES = (
    (b"\x7fELF", "ELF executable/object"),
    (b"MZ", "DOS/Windows PE executable"),
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF87a", "GIF image"),
    (b"GIF89a", "GIF image"),
    (b"PK\x03\x04", "ZIP container"),
    (b"%PDF-", "PDF document"),
    (b"SQLite format 3\x00", "SQLite database"),
    (b"RIFF", "RIFF container (WAV/WebP/AVI)"),
)


def fingerprint(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_hex(context: RenderContext) -> str:
    try:
        with context.path.open("rb") as file:
            content = file.read(4096)
    except OSError as error:
        content = b""
        error_html = f'<div class="notice error">{esc(error)}</div>'
    else:
        error_html = ""
    lines = []
    for offset in range(0, len(content), 16):
        chunk = content[offset:offset + 16]
        hexadecimal = " ".join(f"{byte:02x}" for byte in chunk)
        printable = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{offset:08x}  {hexadecimal:<47}  {esc(printable)}")
    body = f'<section class="surface surface-pad">{error_html}<div class="code-frame"><pre>{chr(10).join(lines) or "Empty file"}</pre></div><p class="muted">First 4 KiB only.</p></section>'
    return page(context, context.label, "Hex preview", body)


class BinaryHandler(Handler):
    key = "binary"
    label = "Binary file"

    def __init__(self, key: str = "binary", label: str = "Binary file") -> None:
        self.key = key
        self.label = label

    def render(self, context: RenderContext) -> str:
        if context.forced_hex:
            return render_hex(context)
        try:
            with context.path.open("rb") as file:
                header = file.read(64)
            format_name = next((label for signature, label in SIGNATURES if header.startswith(signature)), "No known signature")
            architecture = self._architecture(header, context.path)
            digest = fingerprint(context.path)
        except OSError as error:
            format_name, architecture, digest = "Could not inspect", "—", str(error)
        actions = f'<a class="button" href="{context.file_url(context.path)}" download>Download</a><a class="button" href="{context.view_url(context.path)}?as=text">Open as text</a><a class="button" href="{context.view_url(context.path)}?as=hex">Hex preview</a>'
        body = f"""
<section class="surface surface-pad"><div class="kv">
<div><small>Format signature</small><strong>{esc(format_name)}</strong></div>
<div><small>MIME type</small><strong>{esc(context.mime_type)}</strong></div>
<div><small>Size</small><strong>{human_size(context.size)}</strong></div>
<div><small>Architecture</small><strong>{esc(architecture)}</strong></div>
<div><small>SHA-256</small><strong style="font:11px ui-monospace,monospace">{esc(digest)}</strong></div>
</div><div class="actions">{actions}</div>
<div class="notice">This file is treated as data. NovaHost will not execute or extract it.</div></section>"""
        category = "Unknown file" if self.key == "unknown" else self.label
        return page(context, context.label, category, body, subtitle="Safe fallback inspection.")

    @staticmethod
    def _architecture(header: bytes, path=None) -> str:
        if header.startswith(b"\x7fELF") and len(header) >= 20:
            bits = {1: "32-bit", 2: "64-bit"}.get(header[4], "unknown bitness")
            endian = "<" if header[5] == 1 else ">"
            machine = struct.unpack(endian + "H", header[18:20])[0]
            names = {3: "x86", 40: "ARM", 62: "x86-64", 183: "AArch64", 243: "RISC-V"}
            return f"{bits} {names.get(machine, f'machine {machine}')}"
        if header.startswith(b"MZ") and len(header) >= 64:
            try:
                offset = struct.unpack_from("<I", header, 0x3C)[0]
                if path is not None:
                    with path.open("rb") as file:
                        file.seek(offset)
                        signature_and_machine = file.read(6)
                    if signature_and_machine[:4] == b"PE\x00\x00":
                        machine = struct.unpack("<H", signature_and_machine[4:6])[0]
                        names = {0x014C: "x86", 0x8664: "x86-64", 0x01C0: "ARM", 0xAA64: "ARM64"}
                        return f"PE {names.get(machine, f'machine 0x{machine:04x}')}"
            except (OSError, struct.error):
                pass
            return "PE executable (architecture not detected)"
        return "Not detected"


class CryptoHandler(Handler):
    key = "crypto"
    label = "Certificate / key"

    def render(self, context: RenderContext) -> str:
        try:
            with context.path.open("rb") as file:
                raw = file.read(4 * 1024 * 1024)
            digest = fingerprint(context.path)
            text = raw.decode("ascii", errors="ignore")
            first_line = next((line.strip() for line in text.splitlines() if line.startswith("-----BEGIN ")), "DER or unrecognized encoding")
            is_private = any(word in first_line for word in ("PRIVATE KEY", "RSA PRIVATE", "EC PRIVATE"))
            fields: dict[str, object] = {}
            if "CERTIFICATE" in first_line:
                try:
                    import ssl

                    fields = ssl._ssl._test_decode_cert(str(context.path))  # type: ignore[attr-defined]
                except (OSError, ValueError):
                    fields = {}
        except OSError as error:
            raw, digest, first_line, is_private, fields = b"", str(error), "Unavailable", False, {}
        facts = [
            ("Format", first_line.removeprefix("-----BEGIN ").removesuffix("-----")),
            ("Size", human_size(context.size)),
            ("SHA-256", digest),
            ("Handling", "Private key contents are never displayed" if is_private else "Read-only inspection"),
        ]
        for name in ("subject", "issuer", "serialNumber", "notBefore", "notAfter", "version"):
            if name in fields:
                facts.append((name, fields[name]))
        values = "".join(f"<div><small>{esc(key)}</small><strong>{esc(value)}</strong></div>" for key, value in facts)
        body = f'<section class="surface surface-pad"><div class="kv">{values}</div><div class="notice">NovaHost does not modify certificates or keys. Treat private-key files as sensitive.</div><a class="button" href="{context.file_url(context.path)}" download>Download original</a></section>'
        return page(context, context.label, "Crypto material", body, subtitle="Metadata only; key bytes are not rendered.")
