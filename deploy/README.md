# Service Deployment: Obsidian Inbox Watcher

This package runs as a standard **systemd user service** on Linux (and Ubuntu under
WSL2). It needs no root.

> **Placeholders:** values like `<your-user>` and paths such as `/mnt/f/vault` are
> **examples from the author's setup** — replace them with your own. `<your-user>`
> is your Linux username (`echo $USER`). The watcher itself works standalone; the
> Titan integration is optional (see the project README).

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

3. **Configure the key and folders** in `~/.config/vault_watcher/env`.
   At minimum set `GEMINI_API_KEY`; the directories default to `~/0_Pipeline/*` if
   omitted. Use absolute paths here (systemd does not expand `~`):
   ```ini
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   VAULT_WATCHER_RAW_DIR=/home/<your-user>/0_Pipeline/In
   VAULT_WATCHER_PROCESSED_DIR=/home/<your-user>/0_Pipeline/Out
   VAULT_WATCHER_ARCHIVE_DIR=/home/<your-user>/0_Pipeline/Archive
   VAULT_WATCHER_FAILED_DIR=/home/<your-user>/0_Pipeline/Failed
   ```
   `chmod 600 ~/.config/vault_watcher/env` since it holds the key. **Optional Titan
   integration:** point `VAULT_WATCHER_PROCESSED_DIR` at a folder inside your RAG
   vault (the author uses `/mnt/f/vault/notes/inbox`) so `brain-watcher` auto-ingests
   every generated note (see `docs/ai/ARCHITECTURE.md`).

4. **Link the unit into systemd user space**:
   ```bash
   systemctl --user link ~/projects/obsidian-inbox-watcher/deploy/obsidian-inbox-watcher.service
   ```

5. **Reload, enable and start the service**:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now obsidian-inbox-watcher.service
   ```

## Hub deployment (optional — always-on server example)

This is the author's specific "always-on" topology: a small Mini-PC fed by Syncthing.
You only need it if you want a similar setup; otherwise the Quick Installation above
is enough. The hub uses a second unit, `obsidian-inbox-watcher.hub.service`, which
runs as a dedicated user (`<hub-user>`), waits for the network, and always restarts.
Substitute `<hub-user>` and the example mount point `/srv/cloud` with your own.

1. Same `make install` as above (in `~/projects/obsidian-inbox-watcher`).

2. **Mount a native ext4 disk** (example mount point `/srv/cloud`; ext4 keeps inotify
   working) and create the Syncthing folder boundaries underneath it:
   - `.../inbox/raw` — Syncthing folder, **receive-only** on the hub (raw input).
   - `.../vault` — Syncthing folder, **bidirectional** hub ↔ workstation.
   - `.../archive`, `.../failed` — **local only, never synced**, so raw inputs and
     dead-lettered files never reach the RAG vault.

3. **Configure** `~/.config/vault_watcher/env` for the hub user (absolute paths):
   ```ini
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   VAULT_WATCHER_RAW_DIR=/srv/cloud/inbox/raw
   VAULT_WATCHER_PROCESSED_DIR=/srv/cloud/vault/notes/inbox
   VAULT_WATCHER_ARCHIVE_DIR=/srv/cloud/archive
   VAULT_WATCHER_FAILED_DIR=/srv/cloud/failed
   VAULT_WATCHER_DOMAINS=business,lernen,projekte,system
   VAULT_WATCHER_MAX_CHARS=200000
   ```
   `chmod 600 ~/.config/vault_watcher/env`. The note dir lives inside the Syncthing
   `vault/` folder so notes replicate to the workstation, where `brain-watcher`
   ingests them into Titan when that machine is on.

   > The unit file ships with example paths (`/home/<hub-user>/...`). Edit
   > `WorkingDirectory`, `EnvironmentFile` and `ExecStart` in
   > `deploy/obsidian-inbox-watcher.hub.service` to match your user before linking it.

4. **Link, reload, enable and start** (with the hub unit):
   ```bash
   systemctl --user link ~/projects/obsidian-inbox-watcher/deploy/obsidian-inbox-watcher.hub.service
   systemctl --user daemon-reload
   systemctl --user enable --now obsidian-inbox-watcher.hub.service
   ```
   Run `loginctl enable-linger <hub-user>` so the user service keeps running while
   no one is logged in.

> Out of scope here (hub provisioning, tracked separately): installing `uv`/SSD
> tooling, formatting/mounting the disk, the backup job, and the Telegram capture
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
