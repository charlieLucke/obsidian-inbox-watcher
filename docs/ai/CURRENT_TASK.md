# Aktuelle Aufgabe

> Kurz halten. Maximal ein Bildschirm. Mit dem Fortschritt aktualisieren.

## Ziel

Den Watcher härten und seine Migration auf den Always-on-Mini-PC-Hub vorbereiten, gemäß
`docs/ai/plans/2026-05-29-hub-migration-and-resilience.md`. Code-Arbeit erledigt.

## Abgeschlossene Schritte
- [x] **WI-1** — `on_moved` zusätzlich zu `on_created` dispatchen (Syncthing liefert
      via Temp-Write-dann-Rename); refactort in `_maybe_process` mit einem
      In-Flight-Guard; einen 60-s-Safety-Net-Rescan-Thread ergänzt.
- [x] **WI-1b** — `select_observer()` wählt jetzt Polling vs. inotify nach *Dateisystem-
      Typ* (`/proc/mounts`), nicht nach einem `/mnt`-Pfad-Präfix (DECISIONS-Eintrag).
- [x] **WI-2** — begrenzter tenacity-Retry für transiente Gemini-/URL-Fehler; Poison-
      Inputs nach `VAULT_WATCHER_FAILED_DIR` dead-lettert mit `.error.txt`-Sidecar.
- [x] **WI-3** — `unique_output_path()` (`_v2`/`_v3`) überschreibt nie eine Notiz.
- [x] **WI-5** — `VAULT_WATCHER_MAX_CHARS` (Default 200k) + geloggte Kürzung.
- [x] **WI-7** — Hub-systemd-Unit + `.env.example`-Neufassung + Docs (README,
      deploy/README, CONTEXT, ARCHITECTURE, DECISIONS).
- [x] `make check` grün; 21 Tests bestehen. Jedes WI separat committet.

## Zurückgestellt (in IDEAS.md festgehalten)
- **WI-4** crash-sicherer `_processing/<uuid>/`-Claim (formt Ordering/Idempotenz um).
- **WI-6** PDFs multimodal an Gemini senden (verarbeitet Scans; eigener Plan).

## Nächste Schritte (Operator, auf dem Hub)
- [x] **Hub deployt (2026-06-06):** HDD unter `/srv/cloud`, uv + Repo + `uv sync`,
      `~/.config/vault_watcher/env` (wiederverwendeter Key), Linger an, `.hub.service` verlinkt +
      enabled + laufend. Lokaler e2e-Test bestanden: ein `.txt` in `/srv/cloud/inbox/raw`
      wurde zu einer `domain`-Frontmatter-Notiz in `/srv/cloud/vault/notes/inbox` in ~16 s
      (inotify auf ext4), Original archiviert.
- [x] **Vault-Syncthing-Ordner live (2026-06-06):** `titan-vault` teilt Hub
      `/srv/cloud/vault` ↔ Workstation `F:\vault` (bidirektional; `.git`/`.obsidian`-
      Caches via `.stignore` ausgeschlossen). Beide Richtungen verifiziert (eine auf dem Hub erstellte Notiz
      erreichte `F:\vault` in ~12 s; Löschung propagierte). Der Hub-Container brauchte einen neuen
      Bind-Mount `/srv/cloud/vault:/var/syncthing/titan-vault`. Der bestehende persönliche
      `Obsidian-KI-Vault`-Share blieb unberührt.
- [ ] Einen Roh-Input-Pfad zu `/srv/cloud/inbox/raw` verdrahten (Telegram-Service läuft auf dem
      Hub direkt; Phone/Laptop als receive-only Syncthing-Quellen) — eigene Phase wegen
      der receive-only „consumes files"-Feinheit. Dann einen vollständigen
      Capture → Notiz → Titan-Fluss bestätigen, sobald brain-watcher/Titan laufen.

## Notizen
- Tests mocken die Gemini-API, daher läuft `make check` offline.
- Ein fehlender API-Key lässt die Roh-Datei an Ort und Stelle (Config-Problem, kein Poison).
