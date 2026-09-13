# Projektkontext

> Zuerst lesen. Unter 200 Zeilen halten. Mit der Weiterentwicklung des Projekts aktualisieren.

## Was dieses Projekt macht

Dieses Projekt ist ein autonomer lokaler Ordner-Monitor und KI-gestützter Prozessor für einen Obsidian-Vault — ein Ingestion-Trichter für ein „Personal Corporate Memory"-System. Es überwacht einen Roh-Eingabeordner (Default `~/0_Pipeline/In`, konfigurierbar) auf neue TXT-, PDF-, Word-DOCX- und Internet-Shortcut-`.url`-Dateien.

Wird eine Datei erkannt, extrahiert der Service den Text (und crawlt bei `.url`-Dateien die Webseite), analysiert ihn mit der Google-Gemini-API (`gemini-2.5-flash`), klassifiziert ihn in eine einzelne `domain` (geseedet aus `VAULT_WATCHER_DOMAINS`, aber Gemini darf eine neue erfinden), extrahiert Action Items und offene Fragen, schreibt eine strukturierte Obsidian-Markdown-Notiz (YAML-Frontmatter, `ai_processed: true`) in den Processed-Ordner und archiviert das Original-Input sicher. Inputs, die nie eine Notiz werden können (korrupte Datei, leerer Text, erschöpfte Retries), werden in ein Failed-Verzeichnis dead-lettert mit einem `.error.txt`-Sidecar, statt für immer zu loopen.

Es ist das Dokumentverarbeitungs-**Frontend zu Titan** (dem RAG-Service). Indem man seinen Processed-Notes-Ordner in Titans Vault zeigen lässt (`/mnt/f/vault`, z. B. `notes/inbox/`), ingestet der `brain-watcher`-Service jede generierte Notiz automatisch in Titan — und gibt dem RAG-System die PDF-/DOCX-/URL-Ingestion, die ihm sonst fehlt (brain-watcher ingestet nur `.md` automatisch).

> **Hinweis zu den Pfaden:** Die konkreten Verzeichnisse in diesem Dokument
> (`/mnt/f/vault`, `~/0_Pipeline/…`, `/srv/cloud/…`) stammen aus dem Deployment des
> Autors (WSL2-Workstation + Always-on-Mini-PC als „Hub") und sind **Beispiele**. Alle
> Pfade sind über die `VAULT_WATCHER_*`-Umgebungsvariablen frei konfigurierbar.

## Stack
- **Sprache:** Python 3.12+
- **Paketmanager:** uv
- **Test-Runner:** pytest
- **Lint/Format:** ruff
- **Typprüfer:** mypy (strict)
- **CI:** GitHub Actions
- **Pre-commit:** aktiviert
- **Kern-APIs:** Google GenAI SDK (gemini-2.5-flash)

## Projektaufbau
```text
src/obsidian_inbox_watcher/    # Hier liegt der gesamte Quellcode
├── __init__.py
├── __main__.py
└── main.py                    # Haupt-Watcher-, Extraktor- und Prozessor-Loop
tests/                         # Test-Suite
├── __init__.py
├── test_smoke.py              # Import-Verifikation
└── test_watcher.py            # End-to-end-Integration und API-Mocking-Tests
deploy/                        # Deployment-Konfiguration
├── obsidian-inbox-watcher.service      # Systemd-User-Unit (WSL-Workstation)
├── obsidian-inbox-watcher.hub.service  # Systemd-User-Unit (Always-on-Hub)
└── README.md                  # Deployment-Administrationsanleitung
docs/ai/                       # KI-Kontext und Dokumentation
```

## Konventionen

### Code-Stil
- Zeilenlänge: 100
- Anführungszeichen: doppelt
- Type-Hints auf allen Funktionssignaturen erforderlich (mypy strict)
- Docstrings: Google-Stil für öffentliche APIs
- `from __future__ import annotations` am Anfang jedes Moduls

### Fehlerbehandlung
- Datei-Event-Pfade sicher von `bytes` zu Strings coercen, um strikte Typisierung zu erfüllen.
- Immer eine Stable-Size-Check-Schleife durchführen, um sicherzustellen, dass eingehende Dateien vor der Extraktion vollständig fertig geschrieben sind.
- Niemals Exceptions den Haupt-Service-Loop crashen lassen; Fehler nach Konsole/Journal loggen und sauber weitermachen.

## Befehle
- `make install` — Abhängigkeiten und git-pre-commit-Hooks installieren
- `make test` — Tests mit Coverage ausführen
- `make check` — vollständiges Quality-Gate ausführen (Lint + Typecheck + Test)
- `make format` — Ruff-Auto-Formatter ausführen und Lints automatisch beheben
- `make run` — den Watcher-Service lokal via `uv` ausführen

## Konfiguration
- **`GEMINI_API_KEY`** — erforderlich; aus dem Prozess-Env oder `~/.config/vault_watcher/env` gelesen. Das Literal `YOUR_GEMINI_API_KEY_HERE` zählt als nicht gesetzt.
- **`VAULT_WATCHER_RAW_DIR`** — auf neue Dateien überwachter Ordner (Default `~/0_Pipeline/In`).
- **`VAULT_WATCHER_PROCESSED_DIR`** — wohin Notizen geschrieben werden (Default `~/0_Pipeline/Out`; für die Titan-Integration auf `/mnt/f/vault/notes/inbox` setzen).
- **`VAULT_WATCHER_ARCHIVE_DIR`** — wohin Originale verschoben werden (Default `~/0_Pipeline/Archive`).
- **`VAULT_WATCHER_FAILED_DIR`** — Dead-Letter-Verzeichnis für unverarbeitbare Inputs (Default `~/0_Pipeline/Failed`). Jede fehlgeschlagene Datei wird hierher verschoben mit einem `<name>.error.txt`-Sidecar (Zeitstempel + Grund + Kurzdetail). *Außerhalb* des Vaults halten.
- **`VAULT_WATCHER_DOMAINS`** — kommagetrennte Seed-Liste bestehender Titan-Domains, die Gemini für konsistente Klassifikation übergeben wird (Default `business,lernen,projekte,system`). Gemini darf dennoch eine neue Domain erfinden, wenn keine passt.
- **`VAULT_WATCHER_MAX_CHARS`** — max. Zeichen des an Gemini gesendeten extrahierten Texts (Default `200000`). Längerer Text wird gekürzt und eine Warnung geloggt; nicht-numerische/nicht-positive Werte fallen auf den Default zurück.

## Titan-Frontmatter-Contract
Generierte Notizen tragen ein **erforderliches `domain:`**-Feld (Titans `read_markdown` wirft, wenn es fehlt/leer ist; `indexed: false` überspringt eine Notiz). Die Domain wird zu einem kleingeschriebenen, leerzeichenfreien Token normalisiert, weil Titan in Qdrant exakt darauf filtert. Die H1 der Notiz wird zu Titans Dokumenttitel; andere Frontmatter-Keys (`created`, `source`, `tags`, `ai_processed`) werden von Titan ignoriert, sind aber in Obsidian nützlich.

Die systemd-Unit lädt diese aus `EnvironmentFile=~/.config/vault_watcher/env`; `main()` ruft außerdem `load_env_file()` auf, sodass dieselbe Datei in Dev-Läufen funktioniert. systemd expandiert `~` nicht, daher in der Env-Datei absolute Pfade verwenden.

## Bekannte Fallstricke
- **Das Processed-Verzeichnis muss für die Integration innerhalb von Titans Vault liegen.** Nur Dateien unter `/mnt/f/vault` werden von brain-watcher → Titan ingestet. Die Roh-, Archiv- und Failed-Verzeichnisse *außerhalb* des Vaults halten (z. B. `/mnt/f/0_Pipeline/`), damit Roh-Inputs nie indexiert werden.
- **Der Observer wird nach Dateisystem-Typ gewählt, nicht nach Pfad.** `select_observer()` liest `/proc/mounts` und nutzt einen `PollingObserver` auf `drvfs`/`9p`/`cifs`/`nfs`/usw. (wo inotify unzuverlässig ist) und natives inotify auf lokalen Dateisystemen (ext4). Der WSL-`/mnt/f`-Mount ist `9p` → Polling; die ext4-SSD des Hubs → inotify. Fällt nur auf den Legacy-`/mnt/`-Präfix zurück, wenn der Typ nicht gelesen werden kann.
- **Bei inotify kommen Dateien über `on_moved` an, nicht `on_created`.** Syncthing (und der Telegram-Capture-Service) liefern Dateien, indem sie eine Temp-Datei schreiben und in das überwachte Verzeichnis umbenennen, was `FileMovedEvent` feuert. `InboxHandler` implementiert sowohl `on_created` als auch `on_moved`; beide laufen über `_maybe_process`, abgesichert durch ein In-Flight-Set, sodass der periodische Rescan nicht doppelt verarbeiten kann.
- **Watchdog-Event-Pfade:** `event.src_path` / `event.dest_path` können `str` oder `bytes` sein. Typen immer coercen/prüfen, um strikte Typisierung zu erfüllen.
- **Isoliertes mypy in pre-commit:** der pre-commit mypy-Hook läuft in einem isolierten Env ohne Deps, was einen Subclassing-Fehler auf `FileSystemEventHandler` auslöst. Gelöst mit `# type: ignore[misc]` in der Klassenzeile.
- **mypy prüft hier auch `tests/`** (`mypy src tests`): Test-Helper brauchen echte Typen — z. B. ein `watchdog.events.FileCreatedEvent` konstruieren, kein Ad-hoc-Stub, und `time.sleep` über die Dotted-Path-String-Form patchen.

## Glossar
- **Raw Inbox:** `VAULT_WATCHER_RAW_DIR` (Default `~/0_Pipeline/In`) — wo Dateien abgelegt werden.
- **Processed:** `VAULT_WATCHER_PROCESSED_DIR` — wo fertige Notizen landen; hier `/mnt/f/vault/notes/inbox`.
- **Archive:** `VAULT_WATCHER_ARCHIVE_DIR` (Default `~/0_Pipeline/Archive`) — Originale aufbewahrt, um Reprocessing zu vermeiden.
- **Failed (Dead-Letter):** `VAULT_WATCHER_FAILED_DIR` (Default `~/0_Pipeline/Failed`) — unverarbeitbare Inputs + `.error.txt`-Sidecars, aus der Inbox herausgeschoben, damit sie nicht für immer wiederholt werden.
- **Hub:** der Always-on-Mini-PC, auf den der Watcher migriert; Roh-Inbox von Syncthing gespeist, Output-Vault zurück zur Workstation gespiegelt. Siehe `docs/ai/plans/2026-05-29-hub-migration-and-resilience.md`.
- **Titan / brain-watcher:** der RAG-Service und der Daemon, der `/mnt/f/vault` überwacht und `.md`-Notizen darin ingestet.
- **Personal Corporate Memory:** der Obsidian-Vault des Nutzers. Die Domains sind Konfiguration, keine feste Liste — `VAULT_WATCHER_DOMAINS` gibt sie vor (beim Autor business, lernen, projekte, system), und Gemini darf eine neue anlegen, wenn keine passt.
