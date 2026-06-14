# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

LibbyRip is a Tampermonkey userscript that runs inside the Libby/OverDrive reader (`listen.libbyapp.com` for audiobooks, `read.libbyapp.com` for ebooks). It intercepts the page's internal state to extract and download audiobooks as MP3/ZIP or ebooks as EPUB. There is no build step for the userscript — `userscript.js` is the deliverable, installed directly via GreasyFork/Tampermonkey.

A companion set of Python scripts handles post-download metadata processing.

## File Map

- **`userscript.js`** — The entire client-side application. A single-file Tampermonkey userscript with three logical sections (marked by `BEGIN/END` block comments):
  - **Audiobook section** — Hooks `JSON.parse` to capture `odreadCmptParams` (the signed URL query strings Libby strips before exposing to the page). Builds a UI nav bar and download panel. Exports as individual MP3s, a ZIP with metadata, or a single concatenated MP3 (via FFmpeg.wasm).
  - **Book (EPUB) section** — Hooks `Function.prototype.bind` to capture Libby's content-decryption function. Intercepts `__bif_cfc1` to collect decrypted XHTML page content as it loads. Assembles a valid EPUB (content.opf, toc.ncx, XHTML chapters, assets) in memory and downloads it as a zip.
  - **Initializer section** — Polls for the global `BIF` object (Libby's internal Book Info Frame). Once present, routes to `bifFoundAudiobook()` or `bifFoundBook()` based on whether the subdomain is `listen` or `read`.

- **`bakeMetadata.py`** — Post-download CLI tool to embed ID3 tags (title, artist, album, track number, cover art, per-file chapter markers) into the `Part NNN.mp3` files exported by the userscript. Reads `metadata/metadata.json` and `metadata/cover.*`.

- **`buildChapters.py`** — Reads `metadata.json` from stdin and outputs chapter metadata in either `chapters.txt` format (for m4b-tool/tone) or ffmetadata format (for ffmpeg). Contains `Metadata` and `Chapter` dataclasses that model the Libby metadata structure, including spine-offset calculation and the "author and narrator" combined role.

- **`convertToM4b.py`** — Simple interactive script that converts a single MP3 (with embedded chapters) to M4B via ffmpeg. Superseded by `mise run m4b` for normal use.

- **`pyproject.toml` / `uv.lock`** — Python dependency declaration and lockfile for the helper scripts. `uv` is the source of truth for Python packages.

- **`mise.toml`** — Task runner and toolchain definition for common operations. Provides Python 3.13, `uv`, and `ffmpeg` through `mise`.

## Key Architectural Details

**The `BIF` global** — Libby's reader exposes a `BIF` (Book Info Frame) global on the window object. This is the primary data source. `BIF.objects.spool.components` contains the audiobook spine; `BIF.map` contains title, creator, spine durations, chapters/TOC, and language. `BIF.objects.reader` contains ebook spine components.

**Audiobook URL reconstruction** — Libby strips the signed query parameters from audio URLs before putting them in the BIF. The userscript recovers these by hooking `JSON.parse` to intercept the raw parsed object before Libby processes it, extracting `-odread-cmpt-params` (an array indexed by spine position).

**EPUB decryption interception** — Libby passes encrypted XHTML to a callback (`__bif_cfc1`) along with a decryption function, bound via `.bind()`. The userscript hooks `Function.prototype.bind` to capture the bound decryption function, then wraps `__bif_cfc1` to decrypt and store each page's content as it loads.

**FFmpeg.wasm** — The "Export as MP3" path concatenates all spine MP3s into a single file with chapter metadata and cover art, using FFmpeg.wasm (a ~50MB bundle loaded asynchronously). The ffmpeg instance is initialized lazily and cached via a promise (`ffmpegInitPromise`).

**ZIP streaming** — Both audiobook ZIP export and EPUB export use `client-zip` (`downloadZip`). When the browser supports the File System Access API (`showSaveFilePicker`), the zip is streamed directly to disk; otherwise it falls back to a blob download.

**EPUB assembly** — XHTML pages are repaired to be valid XHTML (lowercase tags, proper namespaces, relative asset paths). `content.opf` (manifest/spine) and `toc.ncx` (navigation) are generated programmatically using `document.implementation.createDocument`.

**`metadata.json` structure** — The JSON exported alongside the audiobook ZIP contains: `title`, `description`, `coverUrl`, `creator` (array of `{name, role}`), `spine` (array of `{duration, type, bitrate}`), and `chapters` (array of `{title, spine, offset}`). The `spine` index + `offset` together locate each chapter within the audiobook.

## Commands

**mise** provides `ffmpeg`, `uv`, and Python 3.13. Install the toolchain before running anything:
```bash
mise install
mise run uv-sync
```

**mise** tasks:
```bash
mise run m4b path/to/audiobook.mp3       # Convert MP3 (with embedded chapters) to M4B
mise run all-mp3                         # Convert every root-level MP3 that is not already an M4B
mise run bake-metadata path/to/audiobook # Bake ID3 tags into Part NNN.mp3 files
mise tasks ls                            # List all available tasks
```

**Python / uv scripts:**
```bash
uv lock          # Update the dependency lockfile after changing dependencies
uv sync --locked # Install exactly what is pinned in uv.lock

python bakeMetadata.py /path/to/audiobook        # Bake ID3 tags into Part NNN.mp3 files (CLI)

python buildChapters.py --ffmpeg  < metadata/metadata.json > metadata.txt   # ffmetadata format
python buildChapters.py --chapters < metadata/metadata.json > chapters.txt  # chapters.txt format
```

## Development Environment

`mise.toml` provisions: Python 3.13, `uv`, and a pinned `ffmpeg` release. `pyproject.toml` plus `uv.lock` pin the Python helper dependencies. There is no build, lint, or test infrastructure. The userscript is a single vanilla JS file with no transpilation or bundling — changes to `userscript.js` are effective immediately when re-read by Tampermonkey (or uploaded to GreasyFork).

If your shell is not already activated with `mise`, use `mise exec -- <command>` for one-off commands so you get the pinned tools on every platform.

## Upstream Sync Notes

This fork is CLI-only for the Python helper tooling. Treat any upstream PyQt5 or GUI-oriented changes in `bakeMetadata.py`, `pyproject.toml`, `mise.toml`, `README.md`, or related docs/tasks as out of scope unless the user explicitly asks to restore a GUI path.
