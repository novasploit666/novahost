# NovaHost Developer Manual

This is the engineering manual for NovaHost. It explains the architecture, source tree, request flow, handlers, security model, testing workflow, CLI, and the correct way to add new features.

---

# 1. What NovaHost Is

NovaHost is a Python CLI application that exposes a selected local file or directory through a local HTTP server and presents the target in a browser.

The core flow is:

```text
CLI
 │
 ▼
Target validation
 │
 ▼
Detection / Classification
 │
 ▼
Central Handler Registry
 │
 ▼
Handler
 ├── Custom viewer
 └── Native browser serving
 │
 ▼
Local HTTP Server
 │
 ▼
Browser
```

NovaHost is intentionally local-first.

It does not require:

- a cloud backend
- a database
- an external API
- telemetry
- a remote rendering service
- Node.js
- React
- a JavaScript build system

The UI assets are bundled with the Python project.

---

# 2. Repository Structure

The important source tree is:

```text
NovaHost-CLI/
│
├── novahost/
│   ├── __init__.py
│   ├── __main__.py
│   ├── browser.py
│   ├── cli.py
│   ├── server.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── registry.py
│   │
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── archive.py
│   │   ├── binary.py
│   │   ├── data.py
│   │   ├── directory.py
│   │   ├── image.py
│   │   ├── markdown.py
│   │   ├── media.py
│   │   ├── native.py
│   │   ├── special.py
│   │   └── text.py
│   │
│   └── ui/
│       ├── __init__.py
│       ├── assets.py
│       └── shell.py
│
├── tests/
├── README.md
├── MANUAL.md
├── LICENSE
├── .gitignore
├── novahost.jpg
└── pyproject.toml
```

The project deliberately keeps the CLI, server, detection logic, handlers and UI separated.

---

# 3. Installation for Development

## Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
```

## Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
```

## Normal installation

Without development/test dependencies:

```bash
python -m pip install .
```

The runtime dependencies are declared by `pyproject.toml`.

---

# 4. Running From Source

The package exposes the CLI entry point:

```text
novahost = novahost.cli:main
```

Therefore:

```bash
novahost README.md
```

is the normal installed command.

Module execution is also supported:

```bash
python -m novahost README.md
```

On Linux:

```bash
python3 -m novahost README.md
```

---

# 5. CLI Architecture

The main CLI implementation is:

```text
novahost/cli.py
```

Its responsibilities are:

1. Parse arguments.
2. Resolve and validate the target.
3. Determine the serving root.
4. Configure the host and port.
5. Start the HTTP server.
6. Open the system browser unless disabled.
7. Handle shutdown and useful errors.

The CLI should not contain file-type-specific rendering logic.

That belongs in handlers.

---

# 6. CLI Options

Current interface:

```text
novahost TARGET [-p PORT] [--host HOST] [--root ROOT]
                [--light] [--no-browser]
                [--handler HANDLER] [--verbose]

novahost --info
novahost --list-handlers
novahost --version
```

Examples:

```bash
novahost README.md
novahost .
novahost project/
novahost image.png
novahost data.csv --light
novahost README.md --no-browser
novahost README.md --port 9000
novahost README.md --port 0
novahost README.md --handler markdown
novahost --list-handlers
novahost --info
```

Default:

```text
Host: 127.0.0.1
Port: 5000
```

Port `0` lets the operating system select an available port.

---

# 7. Browser Launching

Browser behavior is isolated in:

```text
novahost/browser.py
```

The goal is to use the system's default browser rather than assuming Chrome.

The implementation must remain cross-platform.

Linux may use normal desktop browser-opening facilities.

Windows uses Windows-compatible standard-library behavior.

The `--no-browser` option bypasses automatic browser launching.

Browser-launch failure should not terminate the HTTP server. The user can still open the printed URL manually.

---

# 8. Core Models

Core data structures live in:

```text
novahost/core/models.py
```

The important object is `RenderContext`.

A handler receives a context containing information such as:

- selected root
- selected file/path
- MIME type
- detection source
- theme
- query parameters
- forced rendering options

It also provides safe helpers for generating local URLs.

Important helpers include:

```text
file_url()
view_url()
raw_url()
```

Handlers should use these helpers instead of constructing local paths manually.

This keeps URL generation and root-bound path checking centralized.

---

# 9. Handler Registry

The most important extension point is:

```text
novahost/core/registry.py
```

The registry maps extensions and detection information to handler objects.

A simplified registration looks like:

```python
(
    MarkdownHandler(),
    (".md", ".markdown", ".mkd")
)
```

The registry also participates in:

- extension detection
- MIME detection
- magic/signature detection
- handler lookup
- forced handler selection

Do not spread extension checks across the server or CLI.

If a new extension belongs to an existing handler, normally only the registry needs to change.

---

# 10. Handler Base Class

The handler interface is defined in:

```text
novahost/handlers/base.py
```

A handler is responsible for deciding how a particular class of files should be displayed.

The important operation is conceptually:

```python
render(context)
```

The handler should:

1. Read the target safely.
2. Respect size/resource limits.
3. Produce a viewer response.
4. Avoid modifying the source file.
5. Avoid executing the source.
6. Use safe URL helpers for related local files.

---

# 11. Existing Handlers

## Markdown

```text
handlers/markdown.py
```

Uses the Markdown parser dependencies declared in `pyproject.toml`.

It provides rich read-only rendering for:

- headings
- paragraphs
- lists
- tables
- task lists
- footnotes
- fenced code
- links
- local images

Raw HTML is deliberately not activated.

## Text and Code

```text
handlers/text.py
```

Contains text-oriented viewers.

Code viewing uses Pygments for syntax highlighting.

Features include:

- line numbers
- syntax highlighting
- search
- copy
- wrapping
- language identification
- file metadata

Source files are displayed only. They are never executed.

## Image

```text
handlers/image.py
```

Provides the image viewer.

Typical controls include:

- fit
- zoom
- actual size
- pan
- rotate
- reset
- fullscreen

## Media

```text
handlers/media.py
```

Handles audio and video.

Playback is performed by the browser.

NovaHost does not transcode media.

Therefore codec support depends on the browser and operating system.

## Native

```text
handlers/native.py
```

Used where the browser itself is the correct renderer.

Typical examples:

- HTML
- PDF
- selected web-native assets

NovaHost still controls how the file is reached through the local root boundary.

## Directory

```text
handlers/directory.py
```

Provides folder browsing.

Responsibilities include:

- directory listing
- breadcrumbs
- sorting
- filtering
- metadata
- links to appropriate viewers

Out-of-root symlinks must not be served.

## Data

```text
handlers/data.py
```

Handles structured data previews such as:

- CSV
- TSV
- JSON
- JSONL
- NDJSON

The viewer is intentionally bounded.

Large datasets should not cause NovaHost to load unlimited data into memory.

## Database

SQLite support is implemented in the special-format handlers.

The viewer is read-only and can inspect:

- tables
- schemas
- row counts
- paginated samples

Arbitrary SQL supplied by a user is not executed by the viewer.

## Notebook

The notebook viewer displays:

- Markdown cells
- source code
- saved text output
- saved image output

Notebook cells are never executed.

Saved HTML output is treated as data rather than activated browser content.

## Spreadsheet

The spreadsheet handler provides best-effort extraction for:

- XLSX
- XLSM
- ODS

It is not intended to reproduce the complete Excel/LibreOffice rendering engine.

Formulas are not recalculated.

## Presentation

PPTX support is a text-oriented slide viewer.

It can extract slide text and provide keyboard navigation.

It does not promise pixel-perfect reproduction of:

- animations
- charts
- complex layouts
- embedded media

## Document

DOCX/ODT support extracts readable content such as:

- paragraphs
- simple tables

Original page layout and advanced formatting are not guaranteed to match a desktop office application.

## Archive

```text
handlers/archive.py
```

Archives are inspected without extracting them into the served directory.

The viewer can list archive contents within bounded limits.

Archive processing must remain bounded to avoid archive bombs and excessive resource consumption.

## Binary

```text
handlers/binary.py
```

Unknown/binary files should not be guessed to be text.

The viewer can expose information such as:

- MIME type
- signature
- size
- SHA-256
- architecture hints where available
- bounded hex preview
- bounded text preview
- download

---

# 12. HTTP Server

The server is:

```text
novahost/server.py
```

It uses Python's standard-library HTTP server infrastructure.

The server is responsible for:

- routing
- serving local files
- serving viewer pages
- serving shared assets
- path validation
- byte-range media responses
- graceful shutdown

Important virtual routes include:

```text
/__asset__/
/__raw__/
/__view__/
```

These are application routes, not filesystem directories.

---

# 13. Root Security

The selected root is the most important security boundary.

A request should never be able to escape it through:

```text
..
```

encoded traversal, absolute paths, symlinks that resolve outside the root, Windows drive-path tricks, or equivalent path manipulation.

Never use raw string prefix comparisons for security.

Bad:

```python
str(path).startswith(str(root))
```

Use resolved filesystem paths and proper path relationship checks.

---

# 14. Windows Compatibility

NovaHost must not assume POSIX filesystem behavior.

Use:

```python
from pathlib import Path
```

for filesystem paths.

Do not manually construct paths using `/`.

Do not assume Linux-only paths or commands.

Windows paths such as:

```text
C:\Users\User\Documents
```

must work.

Filesystem paths and HTTP URLs are different:

```text
Filesystem:
C:\Users\User\file.md

HTTP:
 /__raw__/file.md
```

Always normalize URL paths separately.

---

# 15. Shared UI

The shared UI lives under:

```text
novahost/ui/
```

Important files:

```text
assets.py
shell.py
```

The UI provides common:

- HTML shell
- CSS
- JavaScript
- theme behavior
- buttons
- cards
- navigation
- responsive layout
- viewer controls

When adding a viewer, reuse the shared shell instead of creating a completely separate design system.

---

# 16. Adding a New File Extension

Suppose `.foo` should behave exactly like an existing image viewer.

Open:

```text
novahost/core/registry.py
```

Find the image registration and add:

```text
".foo"
```

No new handler is necessary.

---

# 17. Adding a Completely New Viewer

Suppose you want a new format:

```text
.xyz
```

Create:

```text
novahost/handlers/xyz.py
```

Implement a handler following the existing base interface.

Conceptually:

```python
class XYZHandler(Handler):
    key = "xyz"
    label = "XYZ"

    def render(self, context):
        ...
```

Keep the implementation:

- read-only
- bounded
- safe
- root-aware
- independent from the CLI

Then register it in:

```text
novahost/core/registry.py
```

For example:

```python
(
    XYZHandler(),
    (".xyz",)
)
```

The CLI and HTTP server should not need format-specific edits.

---

# 18. Adding Tests for a New Handler

Add tests under:

```text
tests/
```

At minimum test:

1. Detection.
2. Rendering.
3. A representative fixture.
4. Invalid/malformed input where relevant.
5. Root/path behavior if the handler creates local links.

Run:

```bash
python -m pytest -q
```

For parsers, also test bounded behavior and malformed input.

---

# 19. Adding a New CLI Feature

CLI-specific changes belong in:

```text
novahost/cli.py
```

Do not add file-format logic there.

A CLI feature should normally be:

```text
Argument parser
    ↓
validated option
    ↓
core/server behavior
```

If the feature requires server behavior, put the actual behavior in `server.py` or an appropriate core component rather than embedding everything in argument parsing.

---

# 20. Adding a New Server Route

Server routes belong in:

```text
novahost/server.py
```

Before adding a route, decide whether it is:

- a viewer route
- a raw asset route
- a local file route
- an internal metadata route

Never create a route that bypasses root validation.

Never allow an HTTP parameter to become an unchecked filesystem path.

---

# 21. Adding UI Features

If a feature is shared across viewers:

```text
novahost/ui/
```

is the correct place.

If a feature belongs to one viewer only, keep it near that handler.

Avoid duplicating large blocks of CSS/JavaScript between handlers.

---

# 22. Dependencies

Runtime dependencies are defined in:

```text
pyproject.toml
```

Current important runtime libraries include:

```text
markdown-it-py
mdit-py-plugins
Pygments
```

Do not add a dependency merely to solve a problem that Python's standard library can handle well.

When adding a dependency:

1. Add it to `pyproject.toml`.
2. Explain why it is needed.
3. Keep the version constraint reasonable.
4. Add tests.
5. Verify installation on Linux and Windows.

---

# 23. Testing Commands

Full test suite:

```bash
python -m pytest -q
```

Verbose:

```bash
python -m pytest -v
```

Compile check:

```bash
python -m compileall -q novahost
```

CLI:

```bash
python -m novahost --help
python -m novahost --version
python -m novahost --info
python -m novahost --list-handlers
```

Manual smoke test:

```bash
novahost README.md
novahost .
novahost tests/
```

---

# 24. Release Workflow

Before a release:

```text
1. Update code
2. Add/update tests
3. Run pytest
4. Run compileall
5. Test CLI
6. Test representative viewers
7. Test Linux
8. Test Windows
9. Review README
10. Review MANUAL
11. Check git status
12. Build release artifacts
```

Check for accidental files:

```text
.venv/
__pycache__/
.pytest_cache/
build/
dist/
*.egg-info/
Replit workspace files
Node/TypeScript workspace files
```

These should not be committed.

---

# 25. PyInstaller Releases

PyInstaller can be used to create standalone NovaHost executables.

Development installation and standalone distribution are separate concerns.

```text
Linux source
    ↓
PyInstaller
    ↓
Linux executable

Windows source
    ↓
PyInstaller
    ↓
Windows .exe
```

Build each target on the corresponding operating system.

When adding a PyInstaller spec file, verify that all bundled Python dependencies and package assets are included.

---

# 26. GitHub Repository Layout

A clean source repository should look approximately like:

```text
NovaHost-CLI/
├── .github/
├── novahost/
├── tests/
├── .gitignore
├── LICENSE
├── MANUAL.md
├── README.md
├── novahost.jpg
└── pyproject.toml
```

Do not commit Replit workspace internals, virtual environments, caches, generated build directories or unrelated Node/TypeScript scaffolding.

---

# 27. Design Rules

When modifying NovaHost, preserve these principles.

### Local first

Files remain local unless the user deliberately exposes the server.

### Read only

Viewers should inspect data, not silently modify it.

### No execution

Source code, scripts and notebooks are never executed by NovaHost.

### Bounded parsing

Large or hostile inputs must have reasonable limits.

### Honest support

If a format cannot be faithfully rendered, show a useful fallback rather than pretending.

### Central routing

Extension and detection rules belong in the registry.

### Platform neutrality

Linux and Windows are first-class.

### Shared UI

Common viewer behavior belongs in the shared UI layer.

### Security boundary

Every local file access must respect the configured root.

---

# 28. Practical Feature-Addition Checklist

Before submitting a new feature:

```text
[ ] Does it belong in an existing handler?
[ ] Can the existing registry support it?
[ ] Is parsing read-only?
[ ] Is there a size/resource limit?
[ ] Does it respect RenderContext?
[ ] Does it stay inside the root?
[ ] Does it work on Linux?
[ ] Does it work on Windows?
[ ] Is the UI consistent?
[ ] Is there a regression test?
[ ] Is the limitation documented?
[ ] Does README need updating?
[ ] Does MANUAL need updating?
```

The guiding rule is:

```text
New format
   ↓
New/Existing Handler
   ↓
Registry
   ↓
Existing Server
   ↓
Existing UI system
```

Do not redesign the application for every new format. The goal is to grow NovaHost by adding focused handlers and tests, not by making the whole application more complicated.
