# Decisions Log

> Architecture Decision Records. Append-only. One entry per significant decision.
> This prevents re-litigating the same questions in every new AI session.

---

## 2026-05-20: Use uv as package manager
**Decision:** uv (over pip+venv, poetry, pdm).
**Reasoning:** 10-100x faster than pip; unified tool replacing pip, pip-tools, virtualenv, pyenv; lockfile by default; backed by Astral (same team as ruff).
**Alternatives considered:** Poetry (slower, more config overhead, separate from venv tooling). pip+venv (no lockfile by default, manual workflow).
**Consequences:** All dependency operations go through `uv add` / `uv remove` / `uv sync`. Never edit pyproject.toml dependencies manually.

## 2026-05-20: Use ruff for lint and format
**Decision:** ruff replaces black + flake8 + isort + pyupgrade.
**Reasoning:** Single tool, much faster, consistent config, actively maintained.
**Consequences:** Don't add black, flake8, or isort as separate tools.

## 2026-05-20: Mypy strict mode
**Decision:** Mypy in strict mode from day one.
**Reasoning:** Strictness is much easier to enforce from the start than retrofit. Catches whole categories of bugs at write-time.
**Consequences:** Every function needs full type hints. `# type: ignore` requires an inline comment explaining why.

## 2026-05-20: Migrate from flat directory to package-based layout
**Decision:** Ported initial prototype scripts (`watcher.py` & `test_watcher.py`) into the highly structured Python workspace `obsidian-inbox-watcher` cloned from the `python-template` repository.
**Reasoning:** Allows clean distribution, test separation, dependency encapsulation via Astral's `uv`, unified configurations (`pyproject.toml`), and local packaging support (editable installation via `make install`).
**Alternatives considered:** Keeping the project as flat scripts (leads to dependency pollution, linting issues, fragile test paths, and lacks strict developer gates).
**Consequences:** The code is fully structured inside the `src/obsidian_inbox_watcher` package and is fully compliant with PEP-8 formatting and static check standards.

## 2026-05-20: Configuration file for environment secrets
**Decision:** Place API keys and credentials in `~/.config/vault_watcher/env` instead of hardcoding or requiring global system environment exports.
**Reasoning:** Systemd user-level services can easily read clean `EnvironmentFile=` files. This completely isolates private API keys from getting tracked inside Git histories.
**Alternatives considered:** Injecting keys via command-line arguments (insecure as they appear in system process lists), or standard environment variables (requires exporting in multiple shells and isn't captured by systemd automatically).
**Consequences:** The environment file must be created on any target PC before activating the systemd service.

## 2026-05-21: Make the raw/processed/archive dirs env-configurable
**Decision:** Read the three working directories from `VAULT_WATCHER_RAW_DIR` / `VAULT_WATCHER_PROCESSED_DIR` / `VAULT_WATCHER_ARCHIVE_DIR` (with the previous `~/0_Pipeline/*` values as defaults), and load `~/.config/vault_watcher/env` into `os.environ` at startup. `InboxHandler` now carries the processed/archive dirs and forwards them to `process_file`.
**Reasoning:** The paths were hardcoded in `main()` and the event handler called `process_file` without overrides, so output could not be redirected without editing code. Configurability is required to point the output into Titan's vault.
**Alternatives considered:** Symlinking `~/0_Pipeline/Out` into the vault (hidden, fragile across machines); editing paths in code per machine (not portable).
**Consequences:** Deployment is configured via the systemd `EnvironmentFile`; defaults keep standalone use unchanged.

## 2026-05-21: Write processed notes into Titan's vault for auto-ingestion
**Decision:** Set `VAULT_WATCHER_PROCESSED_DIR=/mnt/f/vault/notes/inbox` so generated notes land inside Titan's `VAULT_ROOT`, where `brain-watcher` picks them up and ingests them into Titan/Qdrant.
**Reasoning:** Makes this watcher the PDF/DOCX/URL → Markdown front end to the RAG system, closing the gap that brain-watcher only auto-ingests `.md` (PDFs otherwise need a manual CLI step). Integration is via the shared filesystem only — the two services stay independent.
**Alternatives considered:** Calling Titan's `/ingest/file` HTTP API directly from this watcher (tighter coupling, duplicate retry/auth logic); leaving the pipelines disconnected (manual copy step).
**Consequences:** Raw and archive dirs must stay *outside* `/mnt/f/vault` so raw inputs aren't indexed. brain-watcher's recursive polling observer handles the `/mnt` mount.

## 2026-05-21: Raw inbox on the Windows drive + polling observer
**Decision:** Put the raw drop folder on the Windows drive (`/mnt/f/0_Pipeline/In`, with archive at `/mnt/f/0_Pipeline/Archive`) and add `select_observer()` that returns a `PollingObserver` for `/mnt/*` paths and a native `Observer` elsewhere.
**Reasoning:** The user drops files from Windows Explorer, so the inbox must be a Windows-visible folder. But inotify events are not delivered on the drvfs (`/mnt`) mount, so the default observer would never fire `on_created` — only the startup scan would work. Polling fixes detection (same approach brain-watcher already uses for the vault).
**Alternatives considered:** Keeping the inbox in the WSL home (`~/0_Pipeline/In`) with inotify (fast, but awkward to reach from Windows); a Windows-side watcher (separate runtime).
**Consequences:** Slightly higher CPU from polling; detection latency ~1–2 s. Linux-home inboxes still use inotify automatically.

## 2026-05-21: Emit Titan-compatible frontmatter with a dynamic `domain`
**Decision:** Replace the fixed `category` (4 hardcoded projects) with a `domain` frontmatter field. Gemini receives a seed list of existing Titan domains (`VAULT_WATCHER_DOMAINS`, default `business,lernen,projekte,system`) and chooses the best fit or invents a new concise domain; the value is run through `normalize_domain()` (lowercase, space-free).
**Reasoning:** Titan's `read_markdown` **requires** a non-empty `domain` field and filters on it exactly in Qdrant — the old notes (with only `category`) would have been rejected at ingest. Seeding the known domains keeps the graph consistent while still allowing growth.
**Alternatives considered:** Fetching the live domain list from Titan's `/domains` per file (tighter coupling + a failure mode when Titan is down; the endpoint was also unreachable during setup); keeping the fixed 4 categories (rejected by Titan).
**Consequences:** Domains must be normalized consistently (casing/spacing matters for the Qdrant filter). The seed list can drift from Titan's real domains, but new-domain creation + the env override keep it manageable.

## 2026-05-29: Select the watchdog observer by filesystem type, not a path prefix
**Decision:** Replace the `watch_dir.startswith("/mnt/")` heuristic in `select_observer()` with a `/proc/mounts` lookup (`_filesystem_type()`): treat `drvfs`, `9p`, `cifs`, `smbfs`, `nfs`, `nfs4`, `fuse.sshfs` as polling filesystems and use native inotify everywhere else. Fall back to the old `/mnt` prefix only when the type cannot be read.
**Reasoning:** The always-on hub mounts its raw inbox on a native ext4 USB SSD *outside* `/mnt` (`/srv/cloud`), where inotify works — the path heuristic would have forced needless polling there, and conversely it would have used inotify on a network share mounted outside `/mnt` where events are unreliable. Keying on the actual filesystem type is correct regardless of mount point.
**Alternatives considered:** Keep the `/mnt` string heuristic and simply require the SSD outside `/mnt` (fragile — silently wrong for shares or an ext4 path under `/mnt`); a config flag to force polling (more config surface than an automatic check).
**Consequences:** `select_observer()` now reads `/proc/mounts` (Linux-only, the sole target). The WSL workstation's `/mnt/f` is `9p` → still polling; the hub's `/srv/cloud` is `ext4` → inotify. Tests monkeypatch `_filesystem_type` so observer selection is deterministic across CI environments.
