# Current Task

> Keep this short. One screen max. Update as you progress.

## Goal

Harden the watcher and prepare its migration to the always-on Mini-PC hub, per
`docs/ai/plans/2026-05-29-hub-migration-and-resilience.md`. Code work done.

## Completed Steps
- [x] **WI-1** — dispatch `on_moved` as well as `on_created` (Syncthing delivers
      via temp-write-then-rename); refactored into `_maybe_process` with an
      in-flight guard; added a 60 s safety-net rescan thread.
- [x] **WI-1b** — `select_observer()` now picks polling vs. inotify by *filesystem
      type* (`/proc/mounts`), not a `/mnt` path prefix (DECISIONS entry).
- [x] **WI-2** — bounded tenacity retry for transient Gemini/URL failures; poison
      inputs dead-lettered to `VAULT_WATCHER_FAILED_DIR` with `.error.txt` sidecar.
- [x] **WI-3** — `unique_output_path()` (`_v2`/`_v3`) never overwrites a note.
- [x] **WI-5** — `VAULT_WATCHER_MAX_CHARS` (default 200k) + logged truncation.
- [x] **WI-7** — hub systemd unit + `.env.example` rewrite + docs (README,
      deploy/README, CONTEXT, ARCHITECTURE, DECISIONS).
- [x] `make check` green; 21 tests pass. Each WI committed separately.

## Deferred (captured in IDEAS.md)
- **WI-4** crash-safe `_processing/<uuid>/` claim (reshapes ordering/idempotency).
- **WI-6** send PDFs to Gemini multimodally (handles scans; own plan).

## Next Steps (operator, on the hub)
- [x] **Hub deployed (2026-06-06):** HDD at `/srv/cloud`, uv + repo + `uv sync`,
      `~/.config/vault_watcher/env` (reused key), linger on, `.hub.service` linked +
      enabled + running. Local e2e test passed: a `.txt` in `/srv/cloud/inbox/raw`
      became a `domain`-frontmatter note in `/srv/cloud/vault/notes/inbox` in ~16 s
      (inotify on ext4), original archived.
- [x] **Vault Syncthing folder live (2026-06-06):** `titan-vault` shares hub
      `/srv/cloud/vault` ↔ workstation `F:\vault` (bidirectional; `.git`/`.obsidian`
      caches excluded via `.stignore`). Verified both ways (a note created on the hub
      reached `F:\vault` in ~12 s; deletion propagated). Hub container needed a new
      bind mount `/srv/cloud/vault:/var/syncthing/titan-vault`. The existing personal
      `Obsidian-KI-Vault` share was left untouched.
- [ ] Wire a raw-input path to `/srv/cloud/inbox/raw` (Telegram service runs on the
      hub directly; phone/laptop as receive-only Syncthing sources) — own phase due
      to the receive-only "consumes files" subtlety. Then confirm a full
      capture → note → Titan flow once brain-watcher/Titan are running.

## Notes
- Tests mock the Gemini API, so `make check` runs offline.
- A missing API key leaves the raw file in place (config issue, not poison).
