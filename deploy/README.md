# Service-Deployment: Obsidian Inbox Watcher

Dieses Paket läuft als standardmäßiger **systemd-User-Service** unter Linux (und Ubuntu unter
WSL2). Es braucht kein Root.

> **Platzhalter:** Werte wie `<your-user>` und Pfade wie `/mnt/f/vault` sind
> **Beispiele aus dem Setup des Autors** — ersetze sie durch deine eigenen. `<your-user>`
> ist dein Linux-Benutzername (`echo $USER`). Der Watcher selbst funktioniert standalone; die
> Titan-Integration ist optional (siehe die Projekt-README).

## Schnellinstallation

Um diesen Service auf deinem lokalen System zu installieren und zu aktivieren:

1. **uv-Paketmanager installieren** (falls noch nicht installiert):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Abhängigkeiten synchronisieren und Environment erstellen**:
   ```bash
   make install
   ```

3. **Key und Ordner konfigurieren** in `~/.config/vault_watcher/env`.
   Mindestens `GEMINI_API_KEY` setzen; die Verzeichnisse fallen auf `~/0_Pipeline/*` zurück, wenn
   weggelassen. Hier absolute Pfade verwenden (systemd expandiert `~` nicht):
   ```ini
   GEMINI_API_KEY=dein_echter_gemini_api_key_hier
   VAULT_WATCHER_RAW_DIR=/home/<your-user>/0_Pipeline/In
   VAULT_WATCHER_PROCESSED_DIR=/home/<your-user>/0_Pipeline/Out
   VAULT_WATCHER_ARCHIVE_DIR=/home/<your-user>/0_Pipeline/Archive
   VAULT_WATCHER_FAILED_DIR=/home/<your-user>/0_Pipeline/Failed
   ```
   `chmod 600 ~/.config/vault_watcher/env`, da sie den Key enthält. **Optionale Titan-
   Integration:** `VAULT_WATCHER_PROCESSED_DIR` auf einen Ordner innerhalb deines RAG-
   Vaults zeigen lassen (der Autor nutzt `/mnt/f/vault/notes/inbox`), sodass `brain-watcher`
   jede generierte Notiz automatisch ingestet (siehe `docs/ai/ARCHITECTURE.md`).

4. **Die Unit in den systemd-User-Space verlinken**:
   ```bash
   systemctl --user link ~/projects/obsidian-inbox-watcher/deploy/obsidian-inbox-watcher.service
   ```

5. **Den Service neu laden, aktivieren und starten**:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now obsidian-inbox-watcher.service
   ```

## Hub-Deployment (optional — Always-on-Server-Beispiel)

Das ist die spezifische „Always-on"-Topologie des Autors: ein kleiner Mini-PC, von Syncthing gespeist.
Du brauchst es nur, wenn du ein ähnliches Setup willst; andernfalls reicht die Schnellinstallation
oben. Der Hub nutzt eine zweite Unit, `obsidian-inbox-watcher.hub.service`, die
als dedizierter Nutzer (`<hub-user>`) läuft, auf das Netzwerk wartet und immer neu startet.
Ersetze `<hub-user>` und den Beispiel-Mountpoint `/srv/cloud` durch deine eigenen.

1. Gleiches `make install` wie oben (in `~/projects/obsidian-inbox-watcher`).

2. **Eine native ext4-Platte mounten** (Beispiel-Mountpoint `/srv/cloud`; ext4 hält inotify
   funktionsfähig) und die Syncthing-Ordner-Grenzen darunter anlegen:
   - `.../inbox/raw` — Syncthing-Ordner, **receive-only** auf dem Hub (Roh-Input).
   - `.../vault` — Syncthing-Ordner, **bidirektional** Hub ↔ Workstation.
   - `.../archive`, `.../failed` — **nur lokal, nie synchronisiert**, sodass Roh-Inputs und
     dead-letterte Dateien nie den RAG-Vault erreichen.

3. **Konfiguriere** `~/.config/vault_watcher/env` für den Hub-Nutzer (absolute Pfade):
   ```ini
   GEMINI_API_KEY=dein_echter_gemini_api_key_hier
   VAULT_WATCHER_RAW_DIR=/srv/cloud/inbox/raw
   VAULT_WATCHER_PROCESSED_DIR=/srv/cloud/vault/notes/inbox
   VAULT_WATCHER_ARCHIVE_DIR=/srv/cloud/archive
   VAULT_WATCHER_FAILED_DIR=/srv/cloud/failed
   VAULT_WATCHER_DOMAINS=business,lernen,projekte,system
   VAULT_WATCHER_MAX_CHARS=200000
   ```
   `chmod 600 ~/.config/vault_watcher/env`. Das Notiz-Verzeichnis liegt innerhalb des Syncthing-
   `vault/`-Ordners, sodass Notizen zur Workstation repliziert werden, wo `brain-watcher`
   sie in Titan ingestet, wenn diese Maschine an ist.

   > Die Unit-Datei wird mit Beispiel-Pfaden ausgeliefert (`/home/<hub-user>/...`). Editiere
   > `WorkingDirectory`, `EnvironmentFile` und `ExecStart` in
   > `deploy/obsidian-inbox-watcher.hub.service` auf deinen Nutzer, bevor du sie verlinkst.

4. **Verlinken, neu laden, aktivieren und starten** (mit der Hub-Unit):
   ```bash
   systemctl --user link ~/projects/obsidian-inbox-watcher/deploy/obsidian-inbox-watcher.hub.service
   systemctl --user daemon-reload
   systemctl --user enable --now obsidian-inbox-watcher.hub.service
   ```
   `loginctl enable-linger <hub-user>` ausführen, damit der User-Service weiterläuft, während
   niemand eingeloggt ist.

> Hier out of scope (Hub-Provisioning, separat getrackt): Installation von `uv`/SSD-
> Tooling, Formatieren/Mounten der Platte, der Backup-Job und der Telegram-Capture-
> Service (ein Schwester-Repo). Siehe `docs/ai/plans/2026-05-29-hub-migration-and-resilience.md`.

## Steuerbefehle

- **Service-Status prüfen**:
  ```bash
  systemctl --user status obsidian-inbox-watcher.service
  ```

- **Service stoppen**:
  ```bash
  systemctl --user stop obsidian-inbox-watcher.service
  ```

- **Service neu starten**:
  ```bash
  systemctl --user restart obsidian-inbox-watcher.service
  ```

- **Logs in Echtzeit inspizieren**:
  ```bash
  journalctl --user -u obsidian-inbox-watcher.service -f -n 100
  ```
