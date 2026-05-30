# obsidian_inbox_watcher

A local folder watcher that turns dropped documents into structured Obsidian
notes with Google Gemini — the document-processing front end to the **Titan**
RAG system.

It watches a raw inbox for **TXT / PDF / DOCX / `.url`** files, extracts the text
(crawling the page for URLs), classifies and summarizes it with `gemini-2.5-flash`,
writes an Obsidian Markdown note (YAML frontmatter, action items, open questions)
and archives the original. Anything it can't process is moved aside with an error
note instead of being retried forever.

It runs perfectly **standalone** — it just writes the notes into a folder you
choose. The **Titan** RAG integration is optional: point the output folder into
Titan's vault and `brain-watcher` auto-ingests every note into the search index.

## Prerequisites

- **Linux or WSL2.** The watcher is built to run as a systemd user service and
  reads `/proc/mounts` to pick its file-watching strategy, so it targets Linux
  (a native box or Ubuntu under WSL2). Other operating systems are untested.
- **Python 3.12+** and **[uv](https://docs.astral.sh/uv/)** (the package manager —
  `uv` installs the right Python for you if needed).
- **A Google Gemini API key.** Classification and summarization run on
  `gemini-2.5-flash`. Create a key (the free tier is enough to try it) in
  [Google AI Studio](https://aistudio.google.com/app/apikey).
- **(Optional) Titan + `brain-watcher`** for the RAG integration — *not* required.
  Without them the watcher simply writes Markdown notes into a folder.

No extra system packages are needed: PDF / DOCX / HTML parsing comes from Python
dependencies (`pypdf`, `python-docx`, `beautifulsoup4`) that `uv` installs for you.

## Quickstart (standalone)

```bash
# 1. Install dependencies and the git pre-commit hooks
make install

# 2. Provide your Gemini API key (the only required setting)
mkdir -p ~/.config/vault_watcher
echo 'GEMINI_API_KEY=your-real-key-here' > ~/.config/vault_watcher/env
chmod 600 ~/.config/vault_watcher/env   # the file holds a secret

# 3. Run it (the working folders are created on first start)
make run
```

With only the key set, the watcher uses these default folders and creates them
automatically:

- drop files into **`~/0_Pipeline/In`**
- finished notes appear in **`~/0_Pipeline/Out`**
- originals are moved to **`~/0_Pipeline/Archive`**
- unprocessable files go to **`~/0_Pipeline/Failed`** (with a `.error.txt` reason)

Drop a `.txt`, `.pdf`, `.docx` or `.url` file into the inbox and within a second or
two a structured note appears in the output folder. To point those folders
elsewhere (or into Titan's vault), set the variables below.

## Configuration

Set these in `~/.config/vault_watcher/env` (loaded by the app and by systemd;
use absolute paths):

| Variable | Purpose | Default |
|---|---|---|
| `GEMINI_API_KEY` | Gemini API key (required) | — |
| `VAULT_WATCHER_RAW_DIR` | folder watched for new files | `~/0_Pipeline/In` |
| `VAULT_WATCHER_PROCESSED_DIR` | where notes are written | `~/0_Pipeline/Out` |
| `VAULT_WATCHER_ARCHIVE_DIR` | where originals are moved | `~/0_Pipeline/Archive` |
| `VAULT_WATCHER_FAILED_DIR` | dead-letter dir for unprocessable inputs (+ `.error.txt` sidecar) | `~/0_Pipeline/Failed` |
| `VAULT_WATCHER_DOMAINS` | seed Titan domains for classification (Gemini may add new ones) | `business,lernen,projekte,system` |
| `VAULT_WATCHER_MAX_CHARS` | max characters of extracted text sent to Gemini (truncated + logged beyond) | `200000` |

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
