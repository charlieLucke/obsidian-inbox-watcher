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

3. **Configure your Gemini API key**:
   Ensure `~/.config/vault_watcher/env` contains:
   ```ini
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   ```

4. **Symlink the service configuration to systemd user space**:
   ```bash
   mkdir -p ~/.config/systemd/user/
   ln -sf /home/charlie/Arbeitsplatz/Code/Projekte/obsidian-inbox-watcher/deploy/obsidian-inbox-watcher.service ~/.config/systemd/user/
   ```

5. **Reload and start the service**:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable obsidian-inbox-watcher.service
   systemctl --user restart obsidian-inbox-watcher.service
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
