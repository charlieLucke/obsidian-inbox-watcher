# Entscheidungs-Log

> Architecture Decision Records. Nur anhängen. Ein Eintrag pro signifikanter Entscheidung.
> Das verhindert, dieselben Fragen in jeder neuen KI-Sitzung neu auszufechten.

---

## 2026-05-20: uv als Paketmanager verwenden
**Entscheidung:** uv (statt pip+venv, poetry, pdm).
**Begründung:** 10–100× schneller als pip; vereintes Werkzeug, das pip, pip-tools, virtualenv, pyenv ersetzt; Lockfile standardmäßig; getragen von Astral (dasselbe Team wie ruff).
**Erwogene Alternativen:** Poetry (langsamer, mehr Konfigurationsaufwand, getrennt vom venv-Tooling). pip+venv (kein Lockfile by default, manueller Workflow).
**Konsequenzen:** Alle Dependency-Operationen laufen über `uv add` / `uv remove` / `uv sync`. Niemals pyproject.toml-Abhängigkeiten manuell bearbeiten.

## 2026-05-20: ruff für Lint und Format verwenden
**Entscheidung:** ruff ersetzt black + flake8 + isort + pyupgrade.
**Begründung:** Einzelwerkzeug, deutlich schneller, konsistente Konfiguration, aktiv gepflegt.
**Konsequenzen:** black, flake8 oder isort nicht als separate Werkzeuge ergänzen.

## 2026-05-20: Mypy Strict Mode
**Entscheidung:** Mypy im Strict Mode ab Tag eins.
**Begründung:** Striktheit ist von Anfang an viel leichter durchzusetzen als nachzurüsten. Fängt ganze Bug-Kategorien zur Schreibzeit ab.
**Konsequenzen:** Jede Funktion braucht vollständige Type-Hints. `# type: ignore` erfordert einen Inline-Kommentar mit Begründung.

## 2026-05-20: Vom flachen Verzeichnis zum paketbasierten Layout migrieren
**Entscheidung:** Erste Prototyp-Skripte (`watcher.py` & `test_watcher.py`) in den hochstrukturierten Python-Workspace `obsidian-inbox-watcher` portiert, geklont aus dem `python-template`-Repository.
**Begründung:** Ermöglicht saubere Distribution, Test-Trennung, Dependency-Kapselung via Astrals `uv`, vereinte Konfigurationen (`pyproject.toml`) und lokale Packaging-Unterstützung (editierbare Installation via `make install`).
**Erwogene Alternativen:** Das Projekt als flache Skripte belassen (führt zu Dependency-Verschmutzung, Linting-Problemen, fragilen Test-Pfaden und es fehlen strikte Developer-Gates).
**Konsequenzen:** Der Code ist vollständig innerhalb des Pakets `src/obsidian_inbox_watcher` strukturiert und vollständig konform mit PEP-8-Formatting und statischen Check-Standards.

## 2026-05-20: Konfigurationsdatei für Environment-Secrets
**Entscheidung:** API-Keys und Credentials in `~/.config/vault_watcher/env` ablegen, statt sie hartzucodieren oder globale System-Environment-Exporte zu verlangen.
**Begründung:** systemd-User-Level-Services können saubere `EnvironmentFile=`-Dateien leicht lesen. Das isoliert private API-Keys vollständig davor, in Git-Historien getrackt zu werden.
**Erwogene Alternativen:** Keys via Kommandozeilen-Argumente injizieren (unsicher, da sie in System-Prozesslisten erscheinen) oder Standard-Umgebungsvariablen (erfordert Exportieren in mehreren Shells und wird von systemd nicht automatisch erfasst).
**Konsequenzen:** Die Environment-Datei muss auf jedem Ziel-PC erstellt werden, bevor der systemd-Service aktiviert wird.

## 2026-05-21: Die Roh-/Processed-/Archiv-Verzeichnisse env-konfigurierbar machen
**Entscheidung:** Die drei Arbeitsverzeichnisse aus `VAULT_WATCHER_RAW_DIR` / `VAULT_WATCHER_PROCESSED_DIR` / `VAULT_WATCHER_ARCHIVE_DIR` lesen (mit den bisherigen `~/0_Pipeline/*`-Werten als Defaults) und `~/.config/vault_watcher/env` beim Start in `os.environ` laden. `InboxHandler` trägt jetzt die Processed-/Archiv-Verzeichnisse und reicht sie an `process_file` weiter.
**Begründung:** Die Pfade waren in `main()` hartcodiert und der Event-Handler rief `process_file` ohne Overrides auf, sodass der Output nicht ohne Code-Änderung umgeleitet werden konnte. Konfigurierbarkeit ist erforderlich, um den Output in Titans Vault zu leiten.
**Erwogene Alternativen:** `~/0_Pipeline/Out` in den Vault symlinken (versteckt, fragil über Maschinen hinweg); Pfade im Code pro Maschine editieren (nicht portabel).
**Konsequenzen:** Das Deployment wird über die systemd-`EnvironmentFile` konfiguriert; Defaults lassen die Standalone-Nutzung unverändert.

## 2026-05-21: Processed-Notizen für Auto-Ingestion in Titans Vault schreiben
**Entscheidung:** `VAULT_WATCHER_PROCESSED_DIR=/mnt/f/vault/notes/inbox` setzen, sodass generierte Notizen innerhalb von Titans `VAULT_ROOT` landen, wo `brain-watcher` sie aufnimmt und in Titan/Qdrant ingestet.
**Begründung:** Macht diesen Watcher zum PDF/DOCX/URL → Markdown-Frontend zum RAG-System und schließt die Lücke, dass brain-watcher nur `.md` automatisch ingestet (PDFs brauchen sonst einen manuellen CLI-Schritt). Die Integration läuft nur über das gemeinsame Dateisystem — die beiden Services bleiben unabhängig.
**Erwogene Alternativen:** Titans `/ingest/file`-HTTP-API direkt aus diesem Watcher aufrufen (engere Kopplung, duplizierte Retry-/Auth-Logik); die Pipelines unverbunden lassen (manueller Kopierschritt).
**Konsequenzen:** Roh- und Archiv-Verzeichnisse müssen *außerhalb* von `/mnt/f/vault` bleiben, damit Roh-Inputs nicht indexiert werden. brain-watchers rekursiver Polling-Observer behandelt den `/mnt`-Mount.

## 2026-05-21: Roh-Inbox auf dem Windows-Laufwerk + Polling-Observer
**Entscheidung:** Den Roh-Drop-Ordner auf das Windows-Laufwerk legen (`/mnt/f/0_Pipeline/In`, mit Archiv unter `/mnt/f/0_Pipeline/Archive`) und `select_observer()` ergänzen, das für `/mnt/*`-Pfade einen `PollingObserver` und sonst einen nativen `Observer` zurückgibt.
**Begründung:** Der Nutzer legt Dateien aus dem Windows-Explorer ab, daher muss die Inbox ein Windows-sichtbarer Ordner sein. Aber inotify-Events werden auf dem drvfs-(`/mnt`)-Mount nicht zugestellt, sodass der Default-Observer nie `on_created` feuern würde — nur der Startup-Scan würde funktionieren. Polling behebt die Erkennung (derselbe Ansatz, den brain-watcher bereits für den Vault nutzt).
**Erwogene Alternativen:** Die Inbox im WSL-Home (`~/0_Pipeline/In`) mit inotify belassen (schnell, aber von Windows aus umständlich erreichbar); ein Windows-seitiger Watcher (separate Laufzeit).
**Konsequenzen:** Etwas höhere CPU durch Polling; Erkennungslatenz ~1–2 s. Linux-Home-Inboxen nutzen weiterhin automatisch inotify.

## 2026-05-21: Titan-kompatibles Frontmatter mit dynamischer `domain` emittieren
**Entscheidung:** Die feste `category` (4 hartcodierte Projekte) durch ein `domain`-Frontmatter-Feld ersetzen. Gemini erhält eine Seed-Liste bestehender Titan-Domains (`VAULT_WATCHER_DOMAINS`, Default `business,lernen,projekte,system`) und wählt die beste Passung oder erfindet eine neue prägnante Domain; der Wert läuft durch `normalize_domain()` (kleingeschrieben, leerzeichenfrei).
**Begründung:** Titans `read_markdown` **verlangt** ein nicht-leeres `domain`-Feld und filtert in Qdrant exakt darauf — die alten Notizen (nur mit `category`) wären beim Ingest abgelehnt worden. Das Seeden der bekannten Domains hält den Graphen konsistent und erlaubt dennoch Wachstum.
**Erwogene Alternativen:** Die Live-Domain-Liste pro Datei aus Titans `/domains` holen (engere Kopplung + ein Failure-Mode, wenn Titan unten ist; der Endpunkt war beim Setup auch unerreichbar); die festen 4 Kategorien behalten (von Titan abgelehnt).
**Konsequenzen:** Domains müssen konsistent normalisiert werden (Groß-/Kleinschreibung/Leerzeichen sind für den Qdrant-Filter relevant). Die Seed-Liste kann von Titans realen Domains abdriften, aber Neu-Domain-Erstellung + das Env-Override halten es handhabbar.

## 2026-05-29: Den watchdog-Observer nach Dateisystem-Typ wählen, nicht nach Pfad-Präfix
**Entscheidung:** Die `watch_dir.startswith("/mnt/")`-Heuristik in `select_observer()` durch einen `/proc/mounts`-Lookup (`_filesystem_type()`) ersetzen: `drvfs`, `9p`, `cifs`, `smbfs`, `nfs`, `nfs4`, `fuse.sshfs` als Polling-Dateisysteme behandeln und überall sonst natives inotify nutzen. Nur auf den alten `/mnt`-Präfix zurückfallen, wenn der Typ nicht gelesen werden kann.
**Begründung:** Der Always-on-Hub mountet seine Roh-Inbox auf einer nativen ext4-USB-SSD *außerhalb* von `/mnt` (`/srv/cloud`), wo inotify funktioniert — die Pfad-Heuristik hätte dort unnötiges Polling erzwungen, und umgekehrt hätte sie inotify auf einem außerhalb von `/mnt` gemounteten Netzwerk-Share genutzt, wo Events unzuverlässig sind. Auf den tatsächlichen Dateisystem-Typ abzustellen ist unabhängig vom Mountpoint korrekt.
**Erwogene Alternativen:** Die `/mnt`-String-Heuristik behalten und einfach die SSD außerhalb von `/mnt` verlangen (fragil — still falsch für Shares oder einen ext4-Pfad unter `/mnt`); ein Config-Flag zum Erzwingen von Polling (mehr Config-Oberfläche als ein automatischer Check).
**Konsequenzen:** `select_observer()` liest jetzt `/proc/mounts` (nur Linux, das einzige Ziel). Das `/mnt/f` der WSL-Workstation ist `9p` → weiterhin Polling; das `/srv/cloud` des Hubs ist `ext4` → inotify. Tests monkeypatchen `_filesystem_type`, sodass die Observer-Wahl über CI-Umgebungen hinweg deterministisch ist.

## 2026-05-29: Transiente Gemini-/Netzwerk-Fehler wiederholen und Poison-Inputs dead-lettern
**Entscheidung:** Den Gemini-Call (`_generate_note_json`) und URL-Fetch (`_http_get`) in eine gemeinsame tenacity-Policy wickeln (`stop_after_attempt(5)`, `wait_exponential(max=30)`, `reraise=True`), gegated durch `_is_transient()` — nur Timeouts, Connection-Errors, HTTP 429 und 5xx werden wiederholt. Jeder Input, der nicht zu einer Notiz werden kann (nicht unterstütztes Format, leerer Text, Extraktionsfehler, erschöpfte Retries, ungültiges JSON, unerwarteter Fehler), wird in ein neues `failed_dir` (`VAULT_WATCHER_FAILED_DIR`, Default `~/0_Pipeline/Failed`) verschoben mit einem `<name>.error.txt`-Sidecar, statt in der Inbox zu verbleiben. Ein fehlender API-Key wird als Config behandelt, nicht als Poison: die Datei bleibt für einen späteren Lauf an Ort und Stelle.
**Begründung:** Davor ließ ein einzelner transienter API-Aussetzer eine Datei still fallen, und eine dauerhaft schlechte Datei (korruptes PDF, 403-URL) wurde bei jedem Neustart wiederholt, blockierte die Queue und spammte das Journal. Dead-Lettering holt Poison-Dateien aus dem Hot-Path, bewahrt sie aber zur Inspektion; begrenztes Backoff übersteht echte Ausfälle, ohne die API zu hämmern.
**Erwogene Alternativen:** Alles wiederholen (macht aus einem dauerhaften 400 fünf langsame Fehlschläge); unverarbeitbare Dateien löschen (verliert Original + Grund); ein In-Memory-Retry-Zähler (über Neustarts verloren, anders als ein Dateisystem-Move).
**Konsequenzen:** `InboxHandler`, `process_existing_files` und `process_file` nehmen alle ein `failed_dir`; `main()` löst es auf und legt es vorab an. Das Sidecar enthält nur Zeitstempel/Grund/Kurzdetail — vollständige Tracebacks gehen via `logger.exception` ins Journal. Operatoren müssen `failed_dir` gelegentlich leeren. tenacity ist eine neue Abhängigkeit.

## 2026-05-29: Niemals eine bestehende Processed-Notiz überschreiben
**Entscheidung:** Den Ausgabepfad durch `unique_output_path(directory, filename)` leiten, das `_v2`, `_v3`, … vor der Erweiterung anhängt, wenn das Ziel bereits existiert.
**Begründung:** Der Notiz-Name ist `{date}_{title}.md`, und Gemini kann am selben Tag für zwei verschiedene Inputs denselben Titel erzeugen. Der alte Code öffnete diesen Pfad mit `"w"` und zerstörte still die frühere Notiz (und deren Quelle war bereits archiviert, sie war also unwiederbringlich).
**Erwogene Alternativen:** Den Inhalt in den Namen hashen (hässlich, instabil über Re-Runs); immer einen Zeitstempel anhängen (laut für den häufigen Nicht-Kollisions-Fall); den Schreibvorgang bei Kollision überspringen (verliert Daten — der gegenteilige Fehler).
**Konsequenzen:** Kollisionen erzeugen jetzt Geschwister-`_v2`-Notizen, die der Nutzer mergen oder löschen kann. Das Archiv-Kollisions-Handling (Zeitstempel-Suffix auf der Roh-Datei) bleibt unverändert.

## 2026-05-29: Das Prompt-Längenlimit konfigurierbar machen und den Default anheben
**Entscheidung:** Den hartcodierten `text_content[:20000]`-Slice durch `get_max_chars()` (`VAULT_WATCHER_MAX_CHARS`, Default `200_000`) ersetzen, vor dem Bauen des Prompts angewandt, und eine `WARNING` loggen, wann immer der Text tatsächlich gekürzt wird.
**Begründung:** 20k Zeichen ließen still den Großteil jedes echten PDFs/Artikels fallen, sodass Zusammenfassungen nur aus den ersten paar Seiten gebaut wurden — ohne Signal, dass etwas verloren ging. gemini-2.5-flash hat ein sehr großes Kontextfenster, also ist 200k sicher und erfasst ganze Dokumente; das Env-Override lässt den Hub es heruntertunen, wenn Kosten zählen. Das Loggen der Kürzung macht den verlustbehafteten Fall sichtbar statt still.
**Erwogene Alternativen:** Gar kein Limit (unbegrenzte Prompt-Kosten / Token-Limit-Fehler bei pathologischen Inputs); Chunk-and-Map-Reduce-Zusammenfassung (viel komplexer, zurückgestellt — siehe IDEAS); 20k behalten (zu klein, der ursprüngliche Bug).
**Konsequenzen:** Größere Prompts bedeuten höhere Per-Datei-Token-Kosten beim Default; Operatoren, denen das wichtig ist, können `VAULT_WATCHER_MAX_CHARS` senken. Nicht-numerische oder nicht-positive Werte fallen auf den Default zurück, statt zu erroren.

## 2026-05-29: Zweistufiges Hub-Deployment mit Syncthing-entkoppelten Roh-/Vault-Ordnern
**Entscheidung:** Eine zweite systemd-User-Unit `deploy/obsidian-inbox-watcher.hub.service` (Nutzer `charlie`, `After=/Wants=network-online.target`, `StartLimitIntervalSec=0`) für den Always-on-Mini-PC ergänzen, die WSL-`…​.service` (Nutzer `charl`) für die Workstation behalten. Auf dem Hub mountet die SSD unter `/srv/cloud` mit `inbox/raw` + `vault` als Syncthing-Ordnern und `archive` + `failed` (+ einem künftigen `processing`) **nur lokal**. Nur Config + Docs — die eigentlichen `systemctl`/Key/SSD-Schritte gehören dem Operator, ausgeführt auf dem Hub.
**Begründung:** Die Workstation muss wach sein, um Input anzunehmen und zu verarbeiten; ein Always-on-Hub beseitigt das. Die zwei Hosts haben tatsächlich unterschiedliche Units (Nutzer, Pfade, Network-Wait), sodass eine einzelne Unit nicht beiden dienen kann. Syncthing ersetzt den `/mnt/f`-Shared-Mount: es spiegelt `vault/` zurück zur Workstation, wo brain-watcher weiterhin Titan füttert, während raw/archive/failed vom synchronisierten Vault fernbleiben, sodass Titan nie Roh-Inputs indexiert. Das native ext4 des Hubs + Syncthings Rename-Zustellung sind genau das, wofür WI-1 (`on_moved`) und WI-1b (fs-Typ-Observer) gebaut wurden.
**Erwogene Alternativen:** Eine parametrisierte Unit mit `%i`/Templating (mehr bewegliche Teile als zwei winzige Dateien); den Workstation-Vault per NFS auf dem Hub mounten (koppelt die beiden Boxen; bricht, wenn die Workstation aus ist — genau das, was wir beheben); das Capture-/Telegram-Stück in diesem Repo betreiben (verworfen — als Schwester-Service gehalten, siehe Anhang A des Plans).
**Konsequenzen:** Ein Deployment auf einen neuen Host bedeutet, die richtige Unit zu wählen und die Env-Datei mit absoluten Pfaden zu schreiben. `VAULT_WATCHER_PROCESSING_DIR` (WI-4) ist dokumentiert, aber noch nicht implementiert — WI-4 wurde zurückgestellt (siehe IDEAS). Der Telegram-Capture-Service lebt in seinem eigenen Repo.
