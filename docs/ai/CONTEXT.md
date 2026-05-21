# Project Context

> Read this first. Keep under 200 lines. Update as the project evolves.

## What this project does

This project is an autonomous local folder monitor and AI-powered processor for an Obsidian Vault — an ingestion funnel for a "Personal Corporate Memory" system. It watches a raw input folder (default `~/0_Pipeline/In`, configurable) for new TXT, PDF, Word DOCX and internet-shortcut `.url` files.

When a file is detected, the service extracts the text (and crawls the web page for `.url` files), analyzes it with the Google Gemini API (`gemini-2.5-flash`), classifies it into one of four projects (Trading, Informatik-Studium, Lucke Capital Services, IT-Infrastruktur), extracts action items and open questions, writes a structured Obsidian Markdown note (YAML frontmatter, `ai_processed: true`) to the processed folder, and archives the original input safely.

It is the document-processing **front end to Titan** (the RAG service). By pointing its processed-notes folder into Titan's vault (`/mnt/f/vault`, e.g. `notes/inbox/`), the `brain-watcher` service auto-ingests every generated note into Titan — giving the RAG system the PDF/DOCX/URL ingestion it otherwise lacks (brain-watcher only auto-ingests `.md`).

## Stack
- **Language:** Python 3.12+
- **Package manager:** uv
- **Test runner:** pytest
- **Lint/format:** ruff
- **Type checker:** mypy (strict)
- **CI:** GitHub Actions
- **Pre-commit:** enabled
- **Core APIs:** Google GenAI SDK (gemini-2.5-flash)

## Project Layout
```text
src/obsidian_inbox_watcher/    # All source code lives here
├── __init__.py
├── __main__.py
└── main.py                    # Main watcher, extractor and processor loop
tests/                         # Testing suite
├── __init__.py
├── test_smoke.py              # Import verification
└── test_watcher.py            # End-to-end integration and API mocking tests
deploy/                        # Deployment configuration
├── obsidian-inbox-watcher.service  # Systemd user service unit
└── README.md                  # Deployment administration guide
docs/ai/                       # AI context and documentation
```

## Conventions

### Code style
- Line length: 100
- Quotes: double
- Type hints required on all function signatures (mypy strict)
- Docstrings: Google style for public APIs
- `from __future__ import annotations` at top of every module

### Error handling
- Coerce file event paths safely to strings from `bytes` to satisfy strict typing.
- Always perform a stable-size check loop to make sure incoming files have fully finished writing before extraction.
- Never let exceptions crash the main service loop; log errors to console/journal and proceed gracefully.

## Commands
- `make install` — install dependencies and git pre-commit hooks
- `make test` — run tests with coverage
- `make check` — run full quality gate (lint + typecheck + test)
- `make format` — run Ruff auto-formatter and auto-fix lints
- `make run` — run the watcher service locally via `uv`

## Configuration
- **`GEMINI_API_KEY`** — required; read from the process env or `~/.config/vault_watcher/env`. The literal `YOUR_GEMINI_API_KEY_HERE` counts as unset.
- **`VAULT_WATCHER_RAW_DIR`** — folder watched for new files (default `~/0_Pipeline/In`).
- **`VAULT_WATCHER_PROCESSED_DIR`** — where notes are written (default `~/0_Pipeline/Out`; set to `/mnt/f/vault/notes/inbox` for the Titan integration).
- **`VAULT_WATCHER_ARCHIVE_DIR`** — where originals are moved (default `~/0_Pipeline/Archive`).

The systemd unit loads these from `EnvironmentFile=~/.config/vault_watcher/env`; `main()` also calls `load_env_file()` so the same file works in dev runs. systemd does not expand `~`, so use absolute paths in the env file.

## Known pitfalls
- **Processed dir must be inside Titan's vault for the integration.** Only files under `/mnt/f/vault` are ingested by brain-watcher → Titan. Keep the raw and archive dirs *outside* the vault so raw inputs are never indexed.
- **Watchdog event paths:** `event.src_path` can be `str` or `bytes`. Always coerce/check types to satisfy strict typing.
- **Isolated mypy in pre-commit:** the pre-commit mypy hook runs in an isolated env lacking deps, triggering a subclassing error on `FileSystemEventHandler`. Resolved with `# type: ignore[misc]` on the class line.
- **mypy here checks `tests/` too** (`mypy src tests`): test helpers need real types — e.g. construct a `watchdog.events.FileCreatedEvent`, not an ad-hoc stub, and patch `time.sleep` via the dotted-path string form.

## Glossary
- **Raw Inbox:** `VAULT_WATCHER_RAW_DIR` (default `~/0_Pipeline/In`) — where files are dropped.
- **Processed:** `VAULT_WATCHER_PROCESSED_DIR` — where finished notes land; here `/mnt/f/vault/notes/inbox`.
- **Archive:** `VAULT_WATCHER_ARCHIVE_DIR` (default `~/0_Pipeline/Archive`) — originals kept to avoid reprocessing.
- **Titan / brain-watcher:** the RAG service and the daemon that watches `/mnt/f/vault` and ingests `.md` notes into it.
- **Personal Corporate Memory:** the user's Obsidian vault capturing study, trading, capital-services and infrastructure context.
