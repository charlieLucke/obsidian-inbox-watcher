# obsidian_inbox_watcher

A local folder watcher that turns dropped documents into structured Obsidian
notes with Google Gemini — the document-processing front end to the **Titan**
RAG system.

It watches a raw inbox for **TXT / PDF / DOCX / `.url`** files, extracts the text
(crawling the page for URLs), classifies and summarizes it with `gemini-2.5-flash`,
writes an Obsidian Markdown note (YAML frontmatter, action items, open questions)
and archives the original. When the output folder points into Titan's vault,
`brain-watcher` auto-ingests every note into the RAG index.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
make install
```

This installs all dependencies and registers pre-commit hooks.

## Configuration

Set these in `~/.config/vault_watcher/env` (loaded by the app and by systemd;
use absolute paths):

| Variable | Purpose | Default |
|---|---|---|
| `GEMINI_API_KEY` | Gemini API key (required) | — |
| `VAULT_WATCHER_RAW_DIR` | folder watched for new files | `~/0_Pipeline/In` |
| `VAULT_WATCHER_PROCESSED_DIR` | where notes are written | `~/0_Pipeline/Out` |
| `VAULT_WATCHER_ARCHIVE_DIR` | where originals are moved | `~/0_Pipeline/Archive` |
| `VAULT_WATCHER_DOMAINS` | seed Titan domains for classification (Gemini may add new ones) | `business,lernen,projekte,system` |

Notes are written with a Titan-required `domain:` frontmatter field (Gemini picks
from the seed list or creates a new one); see `docs/ai/ARCHITECTURE.md`.

For the Titan integration set `VAULT_WATCHER_PROCESSED_DIR` to a folder inside
Titan's vault, e.g. `/mnt/f/vault/notes/inbox`. Keep the raw and archive dirs
*outside* the vault. See `docs/ai/ARCHITECTURE.md`.

The raw dir may live on a Windows drive (e.g. `/mnt/f/0_Pipeline/In` →
`F:\0_Pipeline\In`) so you can drop files from Explorer — the watcher
auto-uses a polling observer there, since inotify is not delivered on the
`/mnt` mount.

## Run & Develop

```bash
make run        # run the watcher locally
make test       # run tests with coverage
make check      # full quality gate: lint + types + tests
make format     # auto-fix style issues
make help       # list all available commands
```

Deploy as a systemd user service — see `deploy/README.md`.

## Project Structure

```
src/obsidian_inbox_watcher/    Source code
tests/               Pytest tests (mirrors src/ layout)
docs/ai/             AI agent context and plans
.github/workflows/   CI configuration
```

## Tooling

| Tool         | Purpose                              |
|--------------|--------------------------------------|
| **uv**       | Package manager + Python installer   |
| **ruff**     | Linter + formatter                   |
| **mypy**     | Static type checker (strict mode)    |
| **pytest**   | Test runner with coverage            |
| **pre-commit** | Git hook runner                    |

All tools run in CI on every push.

## Working with AI Tools

This project uses a structured workflow for AI-assisted coding. Any AI agent (Claude, Gemini, Cursor, Aider, etc.) should read `CLAUDE.md` first — it's mirrored as `AGENTS.md` and `GEMINI.md` for tool compatibility.

Key files for AI context:

- `docs/ai/CONTEXT.md` — stack, conventions, glossary
- `docs/ai/CURRENT_TASK.md` — what's actively being worked on
- `docs/ai/HANDOFF.md` — state for resuming sessions across model switches
- `docs/ai/DECISIONS.md` — log of architectural decisions
- `docs/ai/plans/` — saved plans authored by a planning model (e.g. Opus)

The intended workflow:

1. Architecture and feature plans are authored by a strong reasoning model and saved to `docs/ai/plans/`
2. A faster/cheaper model implements the plans
3. Both reference the shared context in `docs/ai/`
4. State is preserved across sessions via `HANDOFF.md`

## License

TBD
