# Plan: Always-On Hub Migration & Watcher Resilience

- **Author:** Claude Opus 4.8 (planning)
- **Date:** 2026-05-29
- **Status:** proposed — awaiting the three decisions in "Decisions needed" below
- **Implementer:** before starting, read `CLAUDE.md`, `docs/ai/CONTEXT.md`,
  `docs/ai/ARCHITECTURE.md`, and `src/obsidian_inbox_watcher/main.py`. Stay in
  scope, one logical change per commit, `make check` green before each commit.

---

## 1. Why this plan exists

Today the watcher runs on the workstation `<workstation>` under WSL2, with the raw
inbox on the Windows drive (`/mnt/f/0_Pipeline/In`, drvfs) and notes written
straight into Titan's vault (`/mnt/f/vault/notes/inbox`). Two facts about that
environment hid latent bugs:

1. The raw inbox is under `/mnt`, so `select_observer()` uses a **PollingObserver**.
   Polling re-scans the directory and picks up new files regardless of which
   inotify event fired — masking any event-type gap in the handler.
2. Files are dropped by hand from Explorer (normal create), so `on_created` was
   always enough.

We are moving the watcher to an **always-on Mini-PC hub** so the workstation no
longer needs to be awake to accept and process input. On the hub the environment
is different in ways that change correctness:

- Native Linux **ext4** → `select_observer()` uses native **inotify** (no polling
  safety net).
- The raw inbox is fed by **Syncthing** (and optionally the Telegram capture
  service, Appendix A), which
  delivers files by writing a temp file and **renaming** it into place. A rename
  *within* the watched directory fires `on_moved` (`FileMovedEvent`), **not**
  `on_created`. The current handler only implements `on_created`, so on the hub
  Syncthing-delivered files would be silently missed (only the startup scan would
  catch them).

The hub also keeps Titan fully decoupled: the watcher writes the `.md` note into
the hub's local copy of the Syncthing-mirrored vault; Syncthing replicates it to
the workstation's `/mnt/f/vault/notes/inbox`, where `brain-watcher` ingests it
into Titan **when the workstation is on**. The integration gains one Syncthing
hop and is otherwise unchanged.

### Target hub (context for the implementer)
`<hub-host>`, Ubuntu 24.04, Intel Pentium J3710 (4 weak cores), 7.7 GB RAM,
116 GB eMMC + a planned USB-3 SSD. Already runs Docker (syncthing, n8n, mysql,
planka), Tailscale, `unattended-upgrades`. Hard constraint from the weak CPU:
**all heavy processing stays in the Gemini API** — no local OCR, transcription,
or embeddings on this box.

---

## 2. Decisions needed from the user before implementing

1. **Add `tenacity` as a dependency?** It is the idiomatic retry library and is
   already used elsewhere in this ecosystem (brain-mcp). Per `CLAUDE.md`, new
   deps need explicit approval. Alternative: a small hand-rolled retry loop with
   no new dependency. *Recommendation: tenacity (consistent, well-typed).*
2. **USB-SSD mount point.** Mount the SSD **outside `/mnt`** (recommended:
   `/srv/cloud`). If it is mounted under `/mnt/...`, the current
   `select_observer()` heuristic (`watch_dir.startswith("/mnt/")`) would force
   the PollingObserver even though the SSD is native ext4 where inotify works.
   See WI-1 for an optional cleaner fix to that heuristic.
3. **Include WI-4 now or defer?** WI-4 (crash-safe `_processing/` claim) reshapes
   the core processing flow. It is the one item touching ordering/idempotency.
   The must-fixes (WI-1/2/3) deliver most of the safety without it.

---

## 3. Target topology

```
 Laptop / Workstation / Phone ── Syncthing ─┐
 Telegram capture (own Python service) ─────┤
                                            ▼
                              hub: …/cloud/inbox/raw/   (Syncthing, receive-only on hub)
                                            │  on_created / on_moved
                                            ▼
                          obsidian-inbox-watcher (Gemini 2.5-flash)
                            ├─ ok  → …/cloud/vault/notes/inbox/<note>.md   (Syncthing → workstation)
                            ├─ ok  → …/cloud/archive/  (local only)
                            └─ fail→ …/cloud/failed/   (local only, + .error sidecar)
                                            │
                Syncthing mirrors vault/ ───┘
                                            ▼
        workstation /mnt/f/vault ── brain-watcher (when PC on) ── Titan → Qdrant
```

### Syncthing folder boundaries (critical — keep Titan clean)
- `…/cloud/inbox/raw/` — Syncthing folder, **receive-only on the hub** from the
  clients (plus drops from the Telegram capture service, Appendix A). This is
  *raw* input.
- `…/cloud/vault/` — Syncthing folder, **bidirectional** hub ↔ workstation ↔
  laptop. Notes are written to `…/cloud/vault/notes/inbox/`.
- `…/cloud/{archive,failed,processing}/` — **local only, never synced.** Raw
  inputs must never enter the vault, or Titan would index them.

---

## 4. Work items

> Order is the recommended commit sequence. WI-1 is hub-blocking; WI-2/3 are
> high-value; WI-4 is gated on decision 3; WI-5 is small; WI-6 is optional.

### WI-1 — Dispatch on `on_moved` as well as `on_created`  *(HUB-BLOCKING)*
**Problem:** `InboxHandler` only implements `on_created`. On the hub (native
inotify) Syncthing's temp-write-then-rename fires `on_moved`, so those files are
missed.

**Change (`src/obsidian_inbox_watcher/main.py`):**
- Extract the existing per-file guard + dispatch in `on_created` into one private
  method, e.g. `_maybe_process(self, raw_path: str) -> None`, containing: bytes→str
  coercion, the archive-dir self-exclusion check, the extension allowlist, the
  settle sleep, and the `process_file(...)` call.
- `on_created` calls `self._maybe_process(event.src_path)`.
- Add `on_moved(self, event: FileSystemEvent) -> None` that calls
  `self._maybe_process(event.dest_path)` (the moved-in path). Coerce `dest_path`
  from `bytes` like `src_path`. Ignore directory events.
- **Optional safety net (low cost, recommended):** add a periodic full rescan of
  the raw dir on a timer (e.g. every 60 s) reusing `process_existing_files`, so a
  missed event never strands a file. Implement as a daemon `threading.Timer`
  loop or a simple sleep loop in `main()`; keep it idempotent against WI-3/WI-4.

**`select_observer()` note:** with decision 2 (SSD outside `/mnt`) no code change
is required. *Optional cleaner fix (propose, don't do without approval):*
replace the `/mnt/` string heuristic with a filesystem-type check (treat
`drvfs`, `9p`, `cifs`, `nfs` as polling; everything else inotify). If pursued,
that is its own commit + DECISIONS entry.

**Tests (`tests/test_watcher.py`):** construct a real
`watchdog.events.FileMovedEvent(src_path=<outside>, dest_path=<raw/file.txt>)`
and assert `process_file` is invoked (patch it or assert a note is written via
the mocked Gemini client). Mirror the existing `on_created` test style; patch
`time.sleep` via dotted-path string.

**Commit:** `feat: process files arriving via rename (on_moved) for Syncthing`

---

### WI-2 — Retry the Gemini call + dead-letter `_failed/` queue
**Problem:** the Gemini call runs once. A transient failure (429/5xx/network)
raises, the broad `except Exception` logs and returns, and the raw file stays in
the inbox — retried only on the next service restart. A permanently-bad file
(e.g. corrupt PDF) loops forever on every restart and never leaves the inbox.
The blanket `except` also violates the project rule against swallowing errors.

**Changes:**
- Add a `VAULT_WATCHER_FAILED_DIR` config var (default `~/0_Pipeline/Failed`,
  kept **outside** the vault). Resolve it like the other dirs in `main()`, create
  it on startup, and thread it through `InboxHandler` → `process_file` like
  `processed_dir`/`archive_dir`.
- Wrap **only the transient operations** in a bounded retry with exponential
  backoff: the `client.models.generate_content(...)` call and the `.url`
  `requests.get(...)`. Retry on network/timeout/HTTP-5xx/429 only. Do **not**
  retry `json.JSONDecodeError`, empty-text, or programming errors.
  - With tenacity (decision 1 = yes): `@retry(stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, max=30), retry=retry_if_exception_type(...))`
    on a small helper that performs the call and returns the parsed result.
  - Without tenacity: a hand-rolled loop with `for attempt in range(5)` +
    `time.sleep(backoff)`; identical retry-predicate logic.
- Replace the single catch-all in `process_file` with explicit handling:
  - **Transient, retries exhausted** or **permanent processing error** → move the
    raw file to `VAULT_WATCHER_FAILED_DIR` and write a sidecar
    `<original_name>.error.txt` containing timestamp + exception type + message
    (no full traceback in the sidecar; full `logger.exception` still goes to the
    journal). Do **not** write a note, do **not** archive.
  - **Empty extracted text / unsupported format** → keep current behaviour (log
    + skip), but also move to `_failed/` with reason `empty_text` /
    `unsupported_format` so it leaves the inbox and won't be re-scanned forever.
- On startup, `process_existing_files` already drains the inbox; ensure files in
  `_failed/` are never picked up (they live outside the raw dir, so this holds).

**Tests:** (a) mock Gemini to raise a transient error N−1 times then succeed →
assert exactly one note written and the call retried; (b) mock a permanent
failure → assert the raw file is in `failed_dir`, a `.error.txt` sidecar exists,
and nothing is in `processed_dir`/`archive_dir`.

**DECISIONS.md append:** "Retry Gemini with bounded backoff; dead-letter to
`VAULT_WATCHER_FAILED_DIR`" — reasoning: poison files must leave the inbox;
transient errors must not need a service restart; mirrors brain-mcp's
failed-queue pattern.

**Commit:** `feat: retry Gemini calls and dead-letter unprocessable files`

---

### WI-3 — Never overwrite an existing output note
**Problem:** the output filename is `{date}_{safe_title}.md` with no collision
guard (only the archive side guards). Two inputs that yield the same title on the
same day, or any reprocessing of a raw file, will **overwrite** an existing note —
including one the user has since edited in Obsidian.

**Change:** add a helper `unique_output_path(directory: str, filename: str) -> str`
that returns `filename` if free, else inserts `_v2`, `_v3`, … before the `.md`
extension until free. Use it for the processed-note path in `process_file`
(mirror the intent of the existing archive timestamp-suffix guard, but versioned
because these are user-facing notes, not disposable originals).

**Tests:** pre-create `<date>_<title>.md` in `processed_dir`, run processing,
assert a `<date>_<title>_v2.md` is created and the pre-existing file's contents
are untouched.

**Commit:** `fix: never overwrite an existing processed note`

---

### WI-4 — Crash-safe processing via a `_processing/` claim  *(gated on decision 3)*
**Problem:** the flow is write-note → move-original. A crash between the two
re-processes the raw file on restart (duplicate note / overwrite risk that WI-3
mitigates but does not eliminate at the source).

**Change:**
- Add `VAULT_WATCHER_PROCESSING_DIR` (default `~/0_Pipeline/Processing`, local).
- At the *start* of handling a file, **atomically move** the raw file into
  `…/Processing/<uuid>/` and operate on it there. This "claims" the file so a
  concurrent event or a restart scan cannot pick it up again.
- On success: write the note (WI-3 guard), then move the original from
  `…/Processing/<uuid>/` to the archive; remove the now-empty uuid dir.
- On failure: move from `…/Processing/<uuid>/` to `…/Failed/` (WI-2).
- On startup, before the normal scan, **drain `…/Processing/`**: any leftover
  uuid dirs are crash remnants → move their contents to `…/Failed/` with reason
  `interrupted` for inspection (safer than blind reprocessing).

**Note for the implementer:** this is the item with concurrency/ordering
implications. If anything here is ambiguous against the existing code, STOP and
flag for Opus per `CLAUDE.md` rather than guessing.

**Tests:** monkeypatch the note-write to raise after the claim; assert the raw
file ends up in `failed_dir` (not lost, not in `processed_dir`), and the
`processing_dir` is empty afterwards.

**DECISIONS.md append:** "Claim raw files into `_processing/<uuid>/` before
processing for crash-safety and idempotency" with the alternative considered
(hash-based idempotency marker) and why the claim model was chosen (matches the
brain-ingest directory pipeline, simpler to reason about).

**Commit:** `refactor: claim raw files into a processing dir for crash-safety`

---

### WI-5 — Raise the silent 20k-char truncation + log it
**Problem:** `text_content[:20000]` silently drops the tail of long PDFs.
`gemini-2.5-flash` has a very large context window, so the cap is needlessly
conservative and invisible.

**Change:** introduce a `VAULT_WATCHER_MAX_CHARS` config (default e.g. `200000`).
When the extracted text exceeds it, truncate and `logger.warning(...)` the
original length, the cap, and the filename so truncation is never silent.

**Tests:** feed text longer than a small test cap, assert a warning is logged and
the prompt receives the truncated length.

**Commit:** `feat: make extraction length limit configurable and log truncation`

---

### WI-6 — *(Optional / IDEAS)* Send PDFs to Gemini multimodally
**Rationale:** `pypdf` extracts no text from scanned PDFs → empty text → skipped.
Sending the PDF bytes directly to Gemini (it is multimodal) handles scanned docs
**and** removes local parsing load from the weak J3710. This is a behaviour/design
change, not a bugfix.

**Action:** do **not** implement under this plan. Capture in `docs/ai/IDEAS.md`
with the trade-off (per-call cost / token size vs. handling scans). Revisit as a
separate plan if scanned PDFs become common.

---

### WI-7 — Hub deployment (config + docs only; no live secrets in the repo)
**Scope for this repo** (the actual `systemctl`/key steps are the user's, done on
the hub):

- **New systemd unit** `deploy/obsidian-inbox-watcher.hub.service` (keep the WSL
  one for the workstation). User `charlie`, e.g.:
  - `WorkingDirectory=/home/charlie/projects/obsidian-inbox-watcher`
  - `EnvironmentFile=/home/charlie/.config/vault_watcher/env`
  - `ExecStart=/home/charlie/projects/obsidian-inbox-watcher/.venv/bin/obsidian-inbox-watcher`
  - `Restart=always`, `RestartSec=5`, plus `StartLimitIntervalSec=0` so it keeps
    restarting; `After=network-online.target` and `Wants=network-online.target`.
- **Example env for the hub** (document in `deploy/README.md`, absolute paths —
  systemd does not expand `~`). SSD mounted at `/srv/cloud` per decision 2:
  ```
  GEMINI_API_KEY=...
  VAULT_WATCHER_RAW_DIR=/srv/cloud/inbox/raw
  VAULT_WATCHER_PROCESSED_DIR=/srv/cloud/vault/notes/inbox
  VAULT_WATCHER_ARCHIVE_DIR=/srv/cloud/archive
  VAULT_WATCHER_FAILED_DIR=/srv/cloud/failed
  VAULT_WATCHER_PROCESSING_DIR=/srv/cloud/processing   # if WI-4 landed
  VAULT_WATCHER_DOMAINS=business,lernen,projekte,system
  ```
  (`raw` and `vault` are separate Syncthing folders; `archive`/`failed`/
  `processing` are local-only — see §3.)
- **`.env.example`:** replace the generic OPENAI/ANTHROPIC placeholders with the
  real `GEMINI_API_KEY` + all `VAULT_WATCHER_*` vars this project actually uses,
  matching the README table.
- **Docs:** update `CONTEXT.md` (new config vars, hub deployment note, the
  on_moved/inotify pitfall), `ARCHITECTURE.md` (hub data-flow + the new
  failed/processing dirs), and add DECISIONS entries for the two-tier hub
  topology.

**Out of scope for this repo** (belongs to hub provisioning, tracked in the
separate `projekt-brain-ingest` note): installing `uv`, `restic`, `nfs-common`;
mounting/formatting the USB SSD; the restic→H100 backup job; the Telegram
capture service (a separate sibling Python repo — see Appendix A). Do not add these to this repo's diff.

**Commit:** `chore: add hub systemd unit and document hub deployment`

---

## 5. Definition of done (every work item)
- `make check` is green (ruff + mypy strict + pytest with coverage).
- New behaviour has a regression test mirroring the `tests/` ↔ `src/` layout.
- No bare `except`, no swallowed errors, no `print()`, full type hints, no
  unexplained `# type: ignore`.
- `docs/ai/DECISIONS.md` appended for WI-2 and WI-4 (and WI-1 if the
  `select_observer()` heuristic is changed).
- `docs/ai/CURRENT_TASK.md` updated as steps complete; `docs/ai/HANDOFF.md`
  written before stopping or switching models.
- One logical change per commit; conventional-commit messages as given above.

## 6. Suggested sequence
WI-1 → WI-2 → WI-3 → (WI-4 if approved) → WI-5 → WI-7. WI-6 goes to IDEAS only.
WI-1 must land before the hub goes live, or Syncthing-delivered files are missed.

---

## Appendix A — Telegram capture service (own Python service, sibling repo)

**Decision (Opus):** the capture layer is a **separate, thin Python service** —
**not** n8n, and **not** part of the `obsidian-inbox-watcher` repo. Rationale:
the watcher's single responsibility is *raw file → Gemini → note*; the Telegram
receiver shares nothing with it except the raw-inbox path, and this repo is
deliberately dependency-light (no `python-telegram-bot`). A sibling service keeps
the filesystem-decoupled architecture intact and matches the existing multi-repo
layout (`titan`, `brain-mcp`, `brain-dashboard`, `obsidian-inbox-watcher`).

This appendix is a **specification only** — implement it under its **own plan**
in its own repo, cloned from `python-template` (same uv/ruff/mypy-strict/pytest
gates). It does not belong in this plan's diff.

### Responsibility
Receive Telegram messages from an allow-listed set of users and write them as raw
files into `VAULT_WATCHER_RAW_DIR` (`/srv/cloud/inbox/raw`). Nothing else: no
Gemini, no vault, no Titan. The watcher (this repo) does the rest.

### Suggested repo
`brain-telegram-ingest` under `~/projects/`, entry point
`brain-telegram-ingest`, own systemd service `brain-telegram-ingest` on the hub
(user `charlie`).

### Behaviour
- **Library:** `python-telegram-bot` (async). Long-polling is fine — no inbound
  port, works behind the hub's NAT alongside the existing Tailscale setup.
- **Allowlist:** a `TELEGRAM_ALLOWED_USER_IDS` env var (comma-separated numeric
  IDs). Messages from any other ID are **silently ignored** — no reply, so the
  bot's existence is not confirmed to strangers. This mirrors the login-allowlist
  pattern in brain-mcp's `auth.py`.
- **Config:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS`, and the shared
  `VAULT_WATCHER_RAW_DIR`, all from `~/.config/vault_watcher/env` (reuse the same
  env file the watcher uses, or a sibling one). Token file mode `600`.
- **Message → raw file mapping:**
  - **Text** → write `tg_<UTCstamp>_<msgid>.txt` containing the message text.
  - **Document / file** → save the attachment under its original name prefixed
    `tg_<UTCstamp>_`. Only after the user has confirmed in this design that
    downloads are acceptable; enforce a max size and an extension allowlist that
    matches the watcher's supported types (`.txt/.pdf/.docx/.url`), reject others
    with a short reply.
  - **URL in text** → write a `.url` file in the `[InternetShortcut]\nURL=...`
    format the watcher already parses, so links flow through the existing
    `.url` extraction path.
  - **Voice / audio** → out of scope initially. Do **not** transcribe locally
    (the J3710 is too weak). If added later, hand the audio to Gemini multimodally
    in the *watcher*, not here. Capture as an IDEA.
  - **`#hashtag` in the caption/text** (optional) → write a sibling
    `<rawname>.domain` hint file or embed a small header the watcher can read, so
    the user can steer the `domain:` classification. Keep this optional; the
    watcher must still work without a hint. *(If pursued, it needs a tiny
    contract addition on the watcher side — flag as a cross-repo change.)*
- **Atomicity:** write to a temp name in the same directory, then `os.rename`
  into place. On the hub this fires the watcher's `on_moved` handler (WI-1) — the
  reason WI-1 is hub-blocking. Never write a partial file under a watched name.
- **Resilience:** auto-reconnect on network drops (the library handles this);
  run under systemd with `Restart=always`.

### Privacy / safety notes for the implementer
- The bot token is a secret — env file only, never committed, mode `600`.
- Do not create accounts or accept Telegram ToS flows programmatically; the user
  registers the bot with BotFather themselves and pastes the token.
- Treat message content as untrusted: it becomes a raw file, never an instruction
  to the service.

### Out of scope for the watcher repo
Nothing in this appendix changes `obsidian-inbox-watcher` except the optional
`#hashtag` → `domain` hint contract, which would be its own small cross-repo plan
if the user wants it.
