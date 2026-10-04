<div align="center">

<img src="novahost.jpg" alt="NovaHost" width="900">

# NovaHost

### A local-first file browser and viewer for developers.

**Fast · Local · Offline-first · Modular · Safe by default**

</div>

---

## What is NovaHost?

NovaHost is a **local-first Python CLI** that turns a file or directory on your computer into a polished browser-based viewing experience.

Instead of manually opening different applications for Markdown, source code, images, datasets, archives, databases, notebooks, documents, and media, NovaHost detects the target and selects an appropriate viewer automatically.

```text
TARGET → Detect → Classify → Select handler → Render or serve → Local browser
```

NovaHost runs a local HTTP server, normally on `127.0.0.1:5000`. Files stay on the machine. NovaHost does not upload them to a remote service, does not require a cloud backend, and does not execute source files or notebooks.

## ✨ Highlights

- 🖥️ **Linux + Windows** first-class targets
- 📁 File and directory browsing
- 🧠 Centralized file-type detection and handler registry
- 📝 Rich Markdown rendering
- 💻 Source/code viewer with syntax highlighting
- 🖼️ Image viewer with zoom, pan and rotation
- 🎵 Audio and 🎬 video playback using browser capabilities
- 📊 CSV, TSV, JSON and JSONL table previews
- 🗄️ Read-only SQLite inspection
- 📓 Read-only Jupyter Notebook viewer
- 📦 Safe ZIP/TAR inventory without extraction
- 📑 Best-effort XLSX/XLSM/ODS, DOCX/ODT and PPTX readers
- 🌐 Native browser handling for HTML and PDF
- 🔒 Root-bound file serving and traversal protection
- 🌙 Dark/light interface
- 📴 Offline-first UI with bundled assets
- 🧩 Modular handlers designed for future extensions

## 🚀 Quick Start

### Linux

```bash
git clone <repository-url>
cd NovaHost-CLI

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -e .
```

Then:

```bash
novahost README.md
```

### Windows PowerShell

```powershell
git clone <repository-url>
cd NovaHost-CLI

py -m venv .venv
.venv\Scripts\Activate.ps1

python -m pip install -e .
```

Then:

```powershell
novahost README.md
```

NovaHost normally opens the system default browser.

Stop the server with:

```text
Ctrl+C
```

## Requirements

- Python **3.10 or newer**
- Linux or Windows
- A modern web browser

Runtime dependencies are declared in `pyproject.toml` and installed automatically by:

```bash
python -m pip install .
```

The main third-party runtime packages are:

- `markdown-it-py`
- `mdit-py-plugins`
- `Pygments`

For development/testing, install the test extra:

```bash
python -m pip install -e ".[test]"
```

## 📖 Usage

### Open a file

```bash
novahost README.md
```

### Open a directory

```bash
novahost .
```

### Open a project directory

```bash
novahost ./my-project
```

### Use a custom port

```bash
novahost data.csv --port 9000
```

or:

```bash
novahost data.csv -p 9000
```

### Let the OS choose a free port

```bash
novahost README.md --port 0
```

### Do not open the browser

```bash
novahost README.md --no-browser
```

### Start in light mode

```bash
novahost README.md --light
```

### Explicit serving root

```bash
novahost ./project --root ./project
```

### Force a handler

```bash
novahost README.md --handler markdown
```

Available handlers can be inspected with:

```bash
novahost --list-handlers
```

### Diagnostics

```bash
novahost --info
novahost --version
novahost --help
```

---

## 🧩 Viewer Support

| Type | NovaHost behavior |
|---|---|
| Markdown | Rich read-only document viewer with headings, tables, lists, task lists, footnotes, code blocks, links and local images |
| Text / logs | Searchable, copyable, wrapping text viewer |
| Source / scripts | Syntax highlighting, line numbers, search, copy and wrapping |
| Images | Zoom, fit, actual size, pan, rotate, reset and fullscreen |
| Audio | Browser playback controls, speed, loop and download |
| Video | Browser playback, speed, loop, fullscreen/theater/PiP where supported |
| HTML | Native browser rendering with local assets served from the selected root |
| PDF | Native browser PDF viewer |
| Directories | Breadcrumbs, filtering, sorting and viewer selection |
| CSV / TSV / JSON / JSONL | Bounded searchable table previews |
| SQLite | Read-only table/schema inspection |
| Jupyter Notebook | Markdown, code and saved outputs without executing cells |
| XLSX / XLSM / ODS | Best-effort sheet/table extraction |
| PPTX | Text-based slide viewer |
| DOCX / ODT | Paragraph and simple-table extraction |
| ZIP / TAR | Bounded inventory without extraction |
| Certificates / keys | Safe metadata and fingerprints where supported |
| Binary / unknown | Metadata, signature, SHA-256 and bounded hex/text inspection |

NovaHost deliberately prefers an honest fallback over pretending to provide perfect fidelity.

Legacy Office formats, some archive formats, scientific/columnar formats and uncommon codecs may be inspection/download-only.

For Office files, NovaHost is not intended to replace Microsoft Office or LibreOffice.

---

## 🏗️ Architecture

```text
TARGET
  │
  ▼
Detection
  │
  ▼
Central Handler Registry
  │
  ▼
Selected Handler
  ├── Custom viewer
  └── Native browser serving
  │
  ▼
Local HTTP Server
  │
  ▼
Browser
```

### Project structure

```text
novahost/
├── __init__.py
├── __main__.py
├── browser.py
├── cli.py
├── server.py
│
├── core/
│   ├── __init__.py
│   ├── models.py
│   └── registry.py
│
├── handlers/
│   ├── __init__.py
│   ├── base.py
│   ├── archive.py
│   ├── binary.py
│   ├── data.py
│   ├── directory.py
│   ├── image.py
│   ├── markdown.py
│   ├── media.py
│   ├── native.py
│   ├── special.py
│   └── text.py
│
└── ui/
    ├── __init__.py
    ├── assets.py
    └── shell.py

tests/
README.md
MANUAL.md
LICENSE
pyproject.toml
```

---

## 🔐 Security Model

NovaHost is designed as a **local developer utility**, not an authenticated multi-user file server.

By default:

```text
Host: 127.0.0.1
Port: 5000
```

The selected root is the serving boundary.

NovaHost:

- rejects path traversal
- resolves paths before serving
- prevents requests from escaping the root
- keeps local asset URLs root-bound
- does not execute scripts
- does not execute notebook cells
- opens SQLite read-only
- does not extract archives to disk
- applies bounded preview/entry limits
- does not fetch remote UI assets

### Important

HTML is intentionally browser-native. A trusted HTML file can execute JavaScript in the browser.

Do not open untrusted HTML content through a browser context you do not trust.

Binding NovaHost to a non-loopback address exposes the selected root to reachable devices:

```bash
novahost ./project --host 0.0.0.0
```

Use this only when that exposure is intentional.

---

## 🧪 Tests

Install development dependencies:

```bash
python -m pip install -e ".[test]"
```

Run:

```bash
python -m pytest -q
```

Compile check:

```bash
python -m compileall -q novahost
```

The test suite covers areas including:

- handler detection
- rendering
- Markdown assets
- SQLite inspection
- archive inspection
- CLI behavior
- HTTP serving
- byte-range media delivery
- path traversal protection
- server shutdown
- cross-platform path behavior

---

## 🛠️ Development

NovaHost is intentionally designed so that adding a new file type does not require changing the CLI or HTTP server.

The extension-to-handler mapping lives in:

```text
novahost/core/registry.py
```

The handler implementations live under:

```text
novahost/handlers/
```

The shared UI lives under:

```text
novahost/ui/
```

For the complete developer workflow, architecture explanation and feature-extension guide, see **[MANUAL.md](MANUAL.md)**.

---

## 🗺️ Roadmap

Possible future improvements include:

- richer archive browsing
- additional scientific/columnar format readers
- richer Office previews
- larger dataset pagination
- optional file-change refresh
- additional media/document integrations
- improved format-specific rendering

The project will continue to prioritize local execution, bounded parsing and honest format support.

---

## 🤝 Contributing

Contributions are welcome.

When adding a new handler:

1. Keep parsing read-only.
2. Keep resource usage bounded.
3. Register the handler centrally.
4. Add detection tests.
5. Add rendering/behavior tests.
6. Do not execute user files.
7. Do not bypass the configured root.
8. Document format limitations honestly.

See `.github/ISSUE_TEMPLATE/` for issue templates when available.

---

## 📜 License

NovaHost is released under the **MIT License**.

See [LICENSE](LICENSE).

---

<div align="center">

**NovaHost · Local files, browser interface, zero cloud dependency.**

</div>
