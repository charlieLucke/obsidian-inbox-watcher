# Handoff

> Written at session end or before hitting a usage limit.
> The next session (or different model) starts here.
> Overwrite this file with each new handoff.

# Handoff – 2026-05-21
Model: Claude Opus 4.7

## Done in this session
- Set the watcher up on the Haupt-PC (WSL2): cloned to `~/projects/obsidian-inbox-watcher`, `uv sync`, installed + enabled + started the systemd user service.
- Made the raw/processed/archive dirs env-configurable via `VAULT_WATCHER_*` (+ `load_env_file`, `resolve_dir`); threaded the dirs through `InboxHandler` and `process_existing_files`. Added tests; `make check` is green (note: mypy here also checks `tests/`).
- Wired the Titan integration: `VAULT_WATCHER_PROCESSED_DIR=/mnt/f/vault/notes/inbox`, so brain-watcher auto-ingests generated notes into Titan.
- Created `~/.config/vault_watcher/env` (key placeholder + dir overrides) and the pipeline/vault folders.
- Updated README, CONTEXT, ARCHITECTURE, DECISIONS, deploy/README, CURRENT_TASK.
- Moved the raw inbox to the Windows drive (`/mnt/f/0_Pipeline/In`, archive
  `/mnt/f/0_Pipeline/Archive`) so files can be dropped from Explorer, and added
  `select_observer()` (polling on `/mnt`, inotify elsewhere). Drop detection on
  the mount verified.
- Aligned the note frontmatter with Titan: required `domain:` field (Titan
  rejects notes without it), seed list `VAULT_WATCHER_DOMAINS` passed to Gemini,
  new domains allowed, `normalize_domain()` for exact Qdrant matching. Removed
  the old fixed `category`.

## In progress
- Nothing in flight.

## Next concrete step
- User pastes the real `GEMINI_API_KEY` into `~/.config/vault_watcher/env` and restarts the service; then a real end-to-end test (PDF → note → Titan).

## Open questions / decisions needed
- Optional: have brain-dashboard monitor/control this service (add to `MANAGED_UNITS`).

## Files the next session must read first
- docs/ai/ARCHITECTURE.md, docs/ai/CONTEXT.md, src/obsidian_inbox_watcher/main.py

## Notes / gotchas discovered
- systemd does not expand `~` in EnvironmentFile — use absolute paths.
- Without the key, `process_file` returns before archiving, so the raw file stays in the inbox (no data loss).
- `# type: ignore[misc]` stays on `InboxHandler(FileSystemEventHandler)` (watchdog typing).
