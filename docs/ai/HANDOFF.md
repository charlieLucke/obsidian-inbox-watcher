# Übergabe

> Geschrieben am Sitzungsende oder bevor ein Nutzungslimit erreicht wird.
> Die nächste Sitzung (oder ein anderes Modell) beginnt hier.
> Diese Datei mit jeder neuen Übergabe überschreiben.

# Übergabe – 2026-06-06
Modell: Claude Opus 4.8 (Operator-Sitzung: Hub-Deployment)

## In dieser Sitzung erledigt
Der Watcher-Code war bereits vollständig (WI-1/1b/2/3/5/7 committet; WI-4 + WI-6
nach IDEAS zurückgestellt). Diese Sitzung war operator-seitig — den Watcher auf den
Always-on-Hub `<hub-host>` deployt und end-to-end verifiziert.
- **Mini-PC-Docker-Migration:** Docker von der eMMC auf die USB-HDD verlegt
  `/srv/cloud` (data-root `/srv/cloud/docker` + alle DB-Bind-Mounts unter
  `/srv/cloud/appdata/*`), `daemon.json` data-root + `RequiresMountsFor=/srv/cloud`,
  Compose-Bind-Pfade umgeschrieben. Reboot-getestet (Auto-Mount + alle 6 Container
  Auto-Start). Originale als Safety-Net auf der eMMC behalten (noch nicht gelöscht).
- **Hub-Watcher-Deploy:** uv installiert (`~/.local/bin`); dieses Repo von der
  Workstation-WSL via Tarball übertragen (das GitHub-Repo ist **privat** → ein Hub-
  `git clone` scheiterte mangels Credentials); `uv sync`;
  `/home/charlie/.config/vault_watcher/env` geschrieben (Mode 600, **GEMINI_API_KEY der
  Workstation wiederverwendet**) mit den `/srv/cloud/*`-Pfaden; `loginctl enable-linger charlie`
  (funktionierte **ohne sudo**); `obsidian-inbox-watcher.hub.service` verlinkt + enabled
  + gestartet (User-Unit).
- **E2E-Test bestanden:** ein `.txt` in `/srv/cloud/inbox/raw` wurde zu einer
  `domain`-Frontmatter-Notiz in `/srv/cloud/vault/notes/inbox` in ~16 s (inotify auf
  ext4); Original archiviert. Test-Artefakte aufgeräumt.

## In Arbeit
- Nichts in Bearbeitung. Service ist `active (running)` + `enabled`.

## Nächster konkreter Schritt (Operator, auf dem Hub)
- **ERLEDIGT 2026-06-06 — Vault-Syncthing-Sync:** `titan-vault` teilt Hub
  `/srv/cloud/vault` ↔ Workstation `F:\vault` (bidirektional, `.stignore` schließt
  `.git`/`.obsidian`-Caches aus). Beide Richtungen verifiziert. Hub & Workstation waren bereits
  gepaarte Geräte; Workstation läuft SyncTrayzor (Autostart bereits gesetzt). Hub-Syncthing
  ist der Docker-Container — er brauchte einen neuen Bind-Mount
  `/srv/cloud/vault:/var/syncthing/titan-vault`. Der persönliche `Obsidian-KI-Vault`-
  Share (`C:\Users\charl\Documents\Obsidian`) ist separat und blieb unberührt.
- **NÄCHSTES: Roh-Input-Pfad** zu `/srv/cloud/inbox/raw`. Der Telegram-Capture-Service
  (Anhang A) läuft auf dem Hub und schreibt Roh-Dateien direkt (kein Syncthing). Für
  Phone-/Laptop-Drops via Syncthing die receive-only „Hub konsumiert Dateien"-
  Feinheit beachten (der Watcher schiebt Dateien aus raw heraus → ein receive-only-Ordner zeigt
  dann „locally changed"). Das vor dem Verdrahten entwerfen.
- Dann **restic-Backups** zum H100-NAS (braucht sudo + NFS/SMB-Details). Hinweis: der
  Syncthing-Vault-Spiegel des Hubs ist eine Off-Machine-*Kopie*, kein echtes Backup (Löschungen
  propagieren) — restic wird weiterhin benötigt.
- **Cleanup:** die eMMC-Docker-Originale löschen (~10 G: `/var/lib/docker`,
  `/data/mysql`, alte `docker/*`-Bind-Verzeichnisse) + verwaiste Volumes `38a0ee…`, `n8n_data`.

## Offene Fragen / nötige Entscheidungen
- Workstation-Syncthing-Topologie (oben).
- restic: H100 über NFS oder SMB, Mount-Pfad, Credentials.
- WI-4 bleibt zurückgestellt (diese Sitzung erneut bestätigt).

## Dateien, die die nächste Sitzung zuerst lesen muss
- docs/ai/plans/2026-05-29-hub-migration-and-resilience.md
- docs/ai/CURRENT_TASK.md, docs/ai/DECISIONS.md, src/obsidian_inbox_watcher/main.py

## Notizen / entdeckte Stolperfallen
- **Hub-Deployment braucht KEIN sudo:** `enable-linger` funktionierte ohne, und
  `systemctl --user` funktioniert über SSH mit `XDG_RUNTIME_DIR=/run/user/$(id -u)`.
- Das GitHub-Repo ist **privat** und der Hub hat keine Credentials → Deploy durch Übertragen
  des Repos von der Workstation, nicht `git clone`. Künftige Hub-Updates brauchen einen PAT /
  Deploy-Key oder einen weiteren Tarball-Push.
- **Workstation-WSL-Networking** fällt oft auf `networkingMode None` zurück (kein Netz
  in WSL → kann nicht aus WSL pushen); Fix mit `wsl --shutdown` und dann Neustart.
- Hub-Zugriff: lokales SSH-Shortcut-Skript → `ssh <hub-user>@<hub-ip>`.
- Hub-Env-Pfade (absolut, systemd expandiert `~` nicht): siehe deploy/README.md Hub-Abschnitt.
