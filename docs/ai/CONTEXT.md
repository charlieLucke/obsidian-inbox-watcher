# Project Context

> Read this first. Keep under 200 lines. Update as the project evolves.

## What this project does

This project is an autonomous local folder monitor and AI-powered processor for an Obsidian Vault. It acts as an intelligent ingestion funnel for a "Personal Corporate Memory" system. The application monitors a dedicated raw input folder (`~/Vault/00_Inbox/Raw`) for new documents (TXT, PDF, Word DOCX, and internet shortcut URL files).

When a file is detected, the service extracts the text content (and crawls web pages if it's a URL), analyzes the content using the modern Google Gemini API (`gemini-2.5-flash`), determines project relevancy (classifying it into Trading, Informatik-Studium, Lucke Capital Services, or IT-Infrastruktur), extracts action items and open questions, formats a structured Obsidian Markdown note with appropriate frontmatter metadata into a processed folder, and archives the original input safely.

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

## Known pitfalls
- **Watchdog event paths:** `event.src_path` can be `str` or `bytes`. Must always coerce or check types to prevent static type errors.
- **Isolated mypy in pre-commit:** Pre-commit mypy hook runs in an isolated environment that lacks standard package dependencies, which triggers a subclassing error on `FileSystemEventHandler`. Resolved by appending `# type: ignore[misc]` on the class inheritance line.

## Glossary
- **Raw Inbox:** Directory `~/Vault/00_Inbox/Raw` where files are dropped.
- **Processed Inbox:** Directory `~/Vault/00_Inbox/Processed` where finished Obsidian notes are written.
- **Archive:** Directory `~/Vault/00_Inbox/Raw/Archive` where original raw inputs are kept to avoid reprocessing.
- **Personal Corporate Memory:** The user's Obsidian Vault structure designed to capture study material, trading insights, capital services, and infrastructure context.
