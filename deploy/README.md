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
