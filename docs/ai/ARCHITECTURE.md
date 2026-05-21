# Architecture

> System-level design. Update when modules, contracts, or data models change.

## Overview

The Obsidian Vault Inbox Watcher is a fully autonomous client-side agent service that monitors a directory, processes files locally using Python, extracts text contents based on mime-types, prompts the Google Gemini API to structure the data, and writes structured Markdown files into an Obsidian Vault directory.

```mermaid
graph TD
    A[File Added to Raw Inbox] --> B(Python Watcher Service)
    B --> C{File Type?}
    C -- TXT --> D[Read File Content]
    C -- PDF --> E[Extract Text via pypdf]
    C -- DOCX --> F[Extract Text via python-docx]
    C -- .url --> G[Fetch & Parse URL Content]
    D --> H[Gemini API Processor]
    E --> H
    F --> H
    G --> H
    H --> I[Generate Markdown Notes]
    I --> J[Write to Processed Folder]
    J --> K[Archive Original File]
    style B fill:#3399cc,stroke:#236b8e,stroke-width:2px;
    style H fill:#99ff99,stroke:#33cc33,stroke-width:2px;
    style I fill:#ffcc99,stroke:#ff9933,stroke-width:2px;
```

## Module Map

```text
src/obsidian_inbox_watcher/
├── __init__.py           # Package imports
├── __main__.py           # Executable entrypoint
└── main.py               # Single-module service
    ├── load_env_file()              # Load ~/.config/vault_watcher/env into os.environ
    ├── resolve_dir()                # Read a dir from an env var, else default
    ├── load_api_key()               # Gemini key from env / config file
    ├── wait_for_file_to_be_written()# Size-stability check
    ├── process_file(processed_dir, archive_dir)  # Extraction + Gemini + write + archive
    ├── process_existing_files()     # Drain files already present at startup
    ├── InboxHandler(processed_dir, archive_dir)  # watchdog observer → process_file
    └── main()                       # Resolve config, start observer, monitor loop
```

## Data Model & Formats

### Supported Inputs
1. **TXT (`.txt`)**: Read as standard UTF-8 string.
2. **PDF (`.pdf`)**: Parsed page-by-page via `PdfReader` from `pypdf`.
3. **DOCX (`.docx`)**: Parsed paragraph-by-paragraph via `docx.Document`.
4. **URL (`.url`)**: Parsed using standard `ini` structure looking for `URL=...`. Web page is requested using `requests` with a Chromium user-agent and HTML tags (`script`, `style`, `nav`, `footer`, etc.) decomposed via `BeautifulSoup` to isolate readable body text.

### Output Obsidian Markdown Note
```markdown
---
created: YYYY-MM-DD
source: [Absolute File Path or Crawled URL]
category: [Trading | Informatik-Studium | Lucke Capital Services | IT-Infrastruktur]
tags: ["tag1", "tag2", "tag3", "tag4", "tag5"]
ai_processed: true
---
# [Precise German Title]

## Zusammenfassung
[German Summary]

## Wissenslücken / Fragen an mich
> [!IMPORTANT]
> [Identified Questions or Knowledge Gaps]

## Action Items
- [ ] [Action Item 1]
- [ ] [Action Item 2]
```

## External Services
1. **Google Gemini API**: Utilizes `gemini-2.5-flash` model with structural output enforcement (`response_mime_type="application/json"`). Relevancy constraints are enforced to map to predefined user projects. Requires a valid `GEMINI_API_KEY` loaded from `~/.config/vault_watcher/env` or system environment.
2. **Target Web Servers**: Requested dynamically when processing `.url` shortcuts to fetch information. Timeout is set to 15s.

## Data Flow
1. **Detection**: `watchdog`'s `Observer` captures file creation event.
2. **Settle**: Active loop waits up to 10 seconds for file size to stabilize.
3. **Extraction**: Readable text is isolated based on extension.
4. **API Prompting**: Prepares a strict German system instruction prompt and sends it to the Gemini client.
5. **Obsidian Write**: Parses the returned JSON and saves the YAML-frontmatter note under `VAULT_WATCHER_PROCESSED_DIR` (default `~/0_Pipeline/Out`; set to `/mnt/f/vault/notes/inbox` in this deployment).
6. **Clean**: Original file is moved into `VAULT_WATCHER_ARCHIVE_DIR` (default `~/0_Pipeline/Archive`), with a timestamp suffix if a same-named file already exists.

## Integration with Titan (RAG)

This watcher is the document-processing front end to the Titan RAG service. The
two systems are decoupled through the shared filesystem — no code coupling:

```
PDF/DOCX/URL → (this watcher: Gemini → .md) → /mnt/f/vault/notes/inbox/
            → brain-watcher (polls /mnt/f/vault) → Titan /ingest/file → Qdrant
```

- Titan only accepts paths under `VAULT_ROOT` (`/mnt/f/vault`); brain-watcher
  watches that tree **recursively** with a polling observer (inotify is
  unreliable on the `/mnt` drvfs mount) and auto-ingests `.md` files.
- Therefore `VAULT_WATCHER_PROCESSED_DIR` is set inside the vault, while the raw
  and archive dirs stay outside it so raw inputs are never indexed.

## Deployment

Deployed as a **systemd user service** (user `charl`) in the WSL2 environment.
- **Unit:** `deploy/obsidian-inbox-watcher.service`, linked into
  `~/.config/systemd/user/`.
- **Environment:** `EnvironmentFile=/home/charl/.config/vault_watcher/env`
  (Gemini key + the `VAULT_WATCHER_*` dir overrides).
- **Executable:**
  `/home/charl/projects/obsidian-inbox-watcher/.venv/bin/obsidian-inbox-watcher`.
