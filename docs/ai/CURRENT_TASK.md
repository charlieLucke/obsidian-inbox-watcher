# Current Task

> Keep this short. One screen max. Update as you progress.

## Goal

Set up the watcher on the Haupt-PC (WSL2) and wire it into the Titan RAG system.
Done — the service is installed and running; only the API key is pending.

## Completed Steps
- [x] Cloned to `~/projects/obsidian-inbox-watcher`, `uv sync`
- [x] Made the working dirs env-configurable (`VAULT_WATCHER_*`) + `load_env_file()`
- [x] Created `~/.config/vault_watcher/env` (key placeholder + dir overrides, chmod 600)
- [x] Created `~/0_Pipeline/{In,Archive}` and `/mnt/f/vault/notes/inbox`
- [x] Fixed `deploy/obsidian-inbox-watcher.service` paths (user `charl`); linked + enabled + started
- [x] Verified detection end-to-end (drops are detected; stops cleanly at the missing-key check)
- [x] Updated docs (README, CONTEXT, ARCHITECTURE, DECISIONS, deploy/README)
- [x] Moved the raw inbox to the Windows drive `F:\0_Pipeline\In`
      (`/mnt/f/0_Pipeline/In`) + archive `/mnt/f/0_Pipeline/Archive`; added
      `select_observer()` (polling on `/mnt`, inotify elsewhere) — drop
      detection verified

## Next Steps
- [ ] Paste the real `GEMINI_API_KEY` into `~/.config/vault_watcher/env`, then
      `systemctl --user restart obsidian-inbox-watcher`
- [ ] Drop a test PDF in `F:\0_Pipeline\In` and confirm a note appears in
      `/mnt/f/vault/notes/inbox` and gets ingested by brain-watcher → Titan

## Blockers
- API key not yet set (placeholder in place); processing is a no-op until then.

## Notes
- Tests mock the Gemini API, so `make check` runs offline.
