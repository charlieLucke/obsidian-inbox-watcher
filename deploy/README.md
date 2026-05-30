# Service Deployment: Obsidian Inbox Watcher

This package is managed as a standard systemd user-level service on Linux Mint / Ubuntu systems.

## Quick Installation

To install and enable this service on your local system:

1. **Install uv package manager** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Sync dependencies and create environment**:
   ```bash
   make install
   ```

3. **Configure the key and folders** in `~/.config/vault_watcher/env`
   (absolute paths — systemd does not expand `~`):
   ```ini
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   VAULT_WATCHER_RAW_DIR=/home/charl/0_Pipeline/In
   VAULT_WATCHER_PROCESSED_DIR=/mnt/f/vault/notes/inbox
   VAULT_WATCHER_ARCHIVE_DIR=/home/charl/0_Pipeline/Archive
   ```
   `chmod 600 ~/.config/vault_watcher/env` since it holds the key. Pointing
   `VAULT_WATCHER_PROCESSED_DIR` inside Titan's vault (`/mnt/f/vault`) lets
   `brain-watcher` auto-ingest every generated note (see `docs/ai/ARCHITECTURE.md`).

4. **Link the unit into systemd user space**:
   ```bash
   systemctl --user link ~/projects/obsidian-inbox-watcher/deploy/obsidian-inbox-watcher.service
   ```

5. **Reload, enable and start the service**:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now obsidian-inbox-watcher.service
   ```

## Hub deployment (always-on Mini-PC, user `charlie`)

For the always-on hub use `obsidian-inbox-watcher.hub.service` instead of the WSL
unit. It runs as user `charlie`, waits for the network (the dirs are fed/mirrored
by Syncthing) and always restarts.

1. Same `make install` as above (in `/home/charlie/projects/obsidian-inbox-watcher`).

2. **Mount the SSD at `/srv/cloud`** (native ext4 — keeps inotify working) and
   create the Syncthing folder boundaries:
   - `/srv/cloud/inbox/raw` — Syncthing folder, **receive-only** on the hub (raw input).
   - `/srv/cloud/vault` — Syncthing folder, **bidirectional** hub ↔ workstation.
   - `/srv/cloud/archive`, `/srv/cloud/failed` — **local only, never synced**, so
     raw inputs and dead-lettered files never reach Titan's vault.

3. **Configure** `/home/charlie/.config/vault_watcher/env` (absolute paths):
   ```ini
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   VAULT_WATCHER_RAW_DIR=/srv/cloud/inbox/raw
   VAULT_WATCHER_PROCESSED_DIR=/srv/cloud/vault/notes/inbox
   VAULT_WATCHER_ARCHIVE_DIR=/srv/cloud/archive
   VAULT_WATCHER_FAILED_DIR=/srv/cloud/failed
   VAULT_WATCHER_DOMAINS=business,lernen,projekte,system
   VAULT_WATCHER_MAX_CHARS=200000
   ```
   `chmod 600 ~/.config/vault_watcher/env`. The note dir lives inside the
   Syncthing `vault/` folder so notes replicate to the workstation, where
   `brain-watcher` ingests them into Titan when the PC is on.

4. **Link, reload, enable and start** (same commands as below, with the hub unit):
   ```bash
   systemctl --user link ~/projects/obsidian-inbox-watcher/deploy/obsidian-inbox-watcher.hub.service
   systemctl --user daemon-reload
   systemctl --user enable --now obsidian-inbox-watcher.hub.service
   ```
   Run `loginctl enable-linger charlie` so the user service keeps running while
   no one is logged in.

> Out of scope here (hub provisioning, tracked separately): installing `uv`/SSD
> tooling, formatting/mounting the SSD, the backup job, and the Telegram capture
> service (a sibling repo). See `docs/ai/plans/2026-05-29-hub-migration-and-resilience.md`.

## Control Commands

- **Check Service Status**:
  ```bash
  systemctl --user status obsidian-inbox-watcher.service
  ```

- **Stop Service**:
  ```bash
  systemctl --user stop obsidian-inbox-watcher.service
  ```

- **Restart Service**:
  ```bash
  systemctl --user restart obsidian-inbox-watcher.service
  ```

- **Inspect Logs in Real-time**:
  ```bash
  journalctl --user -u obsidian-inbox-watcher.service -f -n 100
  ```
