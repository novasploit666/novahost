"""Command line interface for NovaHost."""

from __future__ import annotations

import argparse
import ipaddress
import platform
import sys
from pathlib import Path

from novahost import __version__
from novahost.browser import open_browser
from novahost.core.models import is_path_within_root
from novahost.core.registry import HANDLERS_BY_KEY, registered_handlers
from novahost.server import create_server
from novahost.ui.shell import human_size


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novahost",
        description="Turn a local file or folder into a polished, read-only browser preview.",
        epilog="Examples:\n  novahost README.md\n  novahost ./site --port 9000\n  novahost image.png --light --no-browser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("target", nargs="?", help="File or directory to preview")
    parser.add_argument("-p", "--port", type=int, default=5000, help="Local HTTP port (default: 5000; use 0 for an available port)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1; non-loopback hosts expose files to your network)")
    parser.add_argument("--root", type=Path, help="Serving root; target and links must remain inside it")
    parser.add_argument("--light", action="store_true", help="Open with the light theme")
    parser.add_argument("--no-browser", action="store_true", help="Print the local URL without opening a browser")
    parser.add_argument("--info", action="store_true", help="Show version, runtime, and supported handler information")
    parser.add_argument("--list-handlers", action="store_true", help="List available file viewers")
    parser.add_argument("--handler", choices=sorted(HANDLERS_BY_KEY), help="Force a viewer for the target")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show local request and preview diagnostics")
    return parser


def _print_info() -> None:
    print(f"NovaHost {__version__}")
    print(f"Python {platform.python_version()} · {platform.system()} {platform.release()}")
    print("Default bind: 127.0.0.1 · No remote APIs, assets, or rendering services")
    print("Viewer handlers:")
    for handler in registered_handlers():
        print(f"  {handler.key:<16} {handler.label}")
    print(f"  {'unknown':<16} Safe fallback inspection")


def _format_url(host: str, port: int) -> str:
    display_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"http://{display_host}:{port}/"


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.info:
        _print_info()
        if not args.target:
            return 0
    if args.list_handlers:
        for handler in registered_handlers():
            print(f"{handler.key:<16} {handler.label}")
        print("unknown          Safe fallback inspection")
        return 0
    if not args.target:
        parser.print_help()
        return 2
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")

    target = Path(args.target).expanduser().resolve()
    if not target.exists():
        print(f"novahost: target does not exist: {target}", file=sys.stderr)
        return 2
    if not (target.is_file() or target.is_dir()):
        print(f"novahost: target must be a regular file or directory: {target}", file=sys.stderr)
        return 2
    root = args.root.expanduser().resolve() if args.root else (target if target.is_dir() else target.parent)
    if not root.is_dir():
        print(f"novahost: serving root is not a directory: {root}", file=sys.stderr)
        return 2
    if not is_path_within_root(target, root):
        print("novahost: target is outside --root; choose a root containing the target.", file=sys.stderr)
        return 2
    if args.handler and target.is_dir():
        print("novahost: --handler can only be forced for a file target.", file=sys.stderr)
        return 2

    try:
        loopback = ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        loopback = args.host.lower() == "localhost"
    if not loopback:
        print("novahost: warning: a non-loopback host may make files accessible to other devices on your network.", file=sys.stderr)
    try:
        server = create_server(
            root,
            target,
            args.host,
            args.port,
            light=args.light,
            forced_handler=args.handler,
            verbose=args.verbose,
        )
    except OSError as error:
        print(f"novahost: could not start local server: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"novahost: {error}", file=sys.stderr)
        return 2

    host, port = server.server_address[:2]
    url = _format_url(str(host), int(port))
    print(f"NovaHost {__version__} · serving {target} ({human_size(target.stat().st_size) if target.is_file() else 'folder'})")
    print(f"Open {url}  ·  Press Ctrl+C to stop")
    if not args.no_browser and not open_browser(url):
        print("Could not open a browser automatically; copy the URL above.")
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nNovaHost stopped.")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
