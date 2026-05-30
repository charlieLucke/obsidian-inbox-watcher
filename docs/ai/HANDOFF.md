# Handoff

> Written at session end or before hitting a usage limit.
> The next session (or different model) starts here.
> Overwrite this file with each new handoff.

# Handoff – 2026-05-29
Model: Claude Opus 4.7 (implementing the hub-migration & resilience plan)

## Done in this session
Implemented `docs/ai/plans/2026-05-29-hub-migration-and-resilience.md`, one
commit per work item, `make check` green before each:
- **WI-1** `feat: process files arriving via rename (on_moved) for Syncthing` —
  `_maybe_process` funnels `on_created`/`on_moved`, in-flight set guards against
  double-processing, daemon `_rescan_loop` rescans the raw dir every 60 s.
- **WI-1b** `refactor: pick the observer by filesystem type instead of a /mnt prefix`
  — `_filesystem_type()` reads `/proc/mounts`; `_POLLING_FS_TYPES` (drvfs/9p/
  cifs/nfs/…) → polling, else inotify; legacy `/mnt` fallback when type unknown.
- **WI-2** `feat: retry Gemini calls and dead-letter unprocessable files` —
  shared tenacity policy (`stop_after_attempt(5)`, `wait_exponential(max=30)`,
  `_is_transient` predicate) on `_http_get`/`_generate_note_json`; new
  `VAULT_WATCHER_FAILED_DIR` + `_dead_letter()` with `.error.txt` sidecar;
  `process_file` restructured with explicit failure branches (no catch-all swallow).
- **WI-3** `fix: never overwrite an existing processed note` — `unique_output_path`.
- **WI-5** `feat: make extraction length limit configurable and log truncation` —
  `get_max_chars()` / `VAULT_WATCHER_MAX_CHARS` (default 200k), warns on truncation.
- **WI-7** `chore: add hub systemd unit and document hub deployment` —
  `deploy/obsidian-inbox-watcher.hub.service` (user charlie), `.env.example`
  rewrite, two-tier Syncthing topology documented across all living docs.
- Also committed the plan doc and updated CURRENT_TASK / IDEAS / DECISIONS.

## In progress
- Nothing in flight. 21 tests pass; ruff + mypy-strict clean.

## Deferred (in IDEAS.md, not implemented)
- **WI-4** crash-safe `_processing/<uuid>/` claim — reshapes ordering/idempotency;
  was gated on a user decision and deferred. `VAULT_WATCHER_PROCESSING_DIR` is
  referenced in docs as a *future* local-only dir but is NOT wired in code yet.
- **WI-6** multimodal PDF to Gemini (scanned-doc support) — own plan.

## Next concrete step (operator, on the hub)
- Provision the hub: mount SSD at `/srv/cloud`, create Syncthing folders
  (`inbox/raw` receive-only, `vault` bidirectional; `archive`/`failed` local-only),
  write `/home/charlie/.config/vault_watcher/env`, `loginctl enable-linger charlie`,
  link + enable `obsidian-inbox-watcher.hub.service`. Then a real PDF→note→Titan test.

## Open questions / decisions needed
- Whether/when to implement WI-4 (crash-safety) before the hub goes fully live.
- Optional: have brain-dashboard monitor/control this service.

## Files the next session must read first
- docs/ai/plans/2026-05-29-hub-migration-and-resilience.md
- docs/ai/ARCHITECTURE.md, docs/ai/CONTEXT.md, src/obsidian_inbox_watcher/main.py

## Notes / gotchas discovered
- `InboxHandler.__init__` signature is now `(processed_dir, archive_dir, failed_dir)`.
- tenacity attaches the `Retrying` instance as `_generate_note_json.retry`; tests
  patch `.retry.sleep` for instant retries (needs `# type: ignore[attr-defined]`).
- A missing API key returns before extraction and leaves the file in place — it is
  config, not a poison file, so it is NOT dead-lettered.
- systemd does not expand `~` in EnvironmentFile — absolute paths only.
- `# type: ignore[misc]` stays on `InboxHandler(FileSystemEventHandler)` (watchdog typing).
- mypy here also checks `tests/` (`mypy src tests`).
