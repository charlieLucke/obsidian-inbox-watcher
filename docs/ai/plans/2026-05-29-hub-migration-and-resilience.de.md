# Plan: Always-On-Hub-Migration & Watcher-Resilienz

- **Autor:** Claude Opus 4.8 (Planung)
- **Datum:** 2026-05-29
- **Status:** vorgeschlagen — wartet auf die drei Entscheidungen in „Nötige Entscheidungen" unten
- **Implementierer:** vor dem Start `CLAUDE.md`, `docs/ai/CONTEXT.md`,
  `docs/ai/ARCHITECTURE.md` und `src/obsidian_inbox_watcher/main.py` lesen. Im
  Scope bleiben, eine logische Änderung pro Commit, `make check` grün vor jedem Commit.

---

## 1. Warum dieser Plan existiert

Heute läuft der Watcher auf der Workstation `<workstation>` unter WSL2, mit der Roh-
Inbox auf dem Windows-Laufwerk (`/mnt/f/0_Pipeline/In`, drvfs) und Notizen direkt
in Titans Vault geschrieben (`/mnt/f/vault/notes/inbox`). Zwei Fakten dieser
Umgebung verbargen latente Bugs:

1. Die Roh-Inbox liegt unter `/mnt`, sodass `select_observer()` einen **PollingObserver** nutzt.
   Polling rescannt das Verzeichnis und nimmt neue Dateien auf, egal welches
   inotify-Event feuerte — und maskiert so jede Event-Typ-Lücke im Handler.
2. Dateien werden von Hand aus dem Explorer abgelegt (normales Create), sodass `on_created`
   immer ausreichte.

Wir verlagern den Watcher auf einen **Always-on-Mini-PC-Hub**, sodass die Workstation
nicht mehr wach sein muss, um Input anzunehmen und zu verarbeiten. Auf dem Hub ist die Umgebung
auf eine Weise anders, die die Korrektheit verändert:

- Natives Linux-**ext4** → `select_observer()` nutzt natives **inotify** (kein Polling-
  Safety-Net).
- Die Roh-Inbox wird von **Syncthing** gespeist (und optional dem Telegram-Capture-
  Service, Anhang A), das
  Dateien liefert, indem es eine Temp-Datei schreibt und an Ort und Stelle **umbenennt**. Ein Rename
  *innerhalb* des überwachten Verzeichnisses feuert `on_moved` (`FileMovedEvent`), **nicht**
  `on_created`. Der aktuelle Handler implementiert nur `on_created`, sodass auf dem Hub
  Syncthing-gelieferte Dateien still verpasst würden (nur der Startup-Scan würde sie
  erfassen).

Der Hub hält Titan auch vollständig entkoppelt: der Watcher schreibt die `.md`-Notiz in
die lokale Kopie des Syncthing-gespiegelten Vaults des Hubs; Syncthing repliziert sie zur
`/mnt/f/vault/notes/inbox` der Workstation, wo `brain-watcher` sie in Titan ingestet,
**wenn die Workstation an ist**. Die Integration gewinnt einen Syncthing-
Hop und ist sonst unverändert.

### Ziel-Hub (Kontext für den Implementierer)
`charlie-Mini-PC`, Ubuntu 24.04, Intel Pentium J3710 (4 schwache Kerne), 7,7 GB RAM,
116 GB eMMC + eine geplante USB-3-SSD. Läuft bereits Docker (syncthing, n8n, mysql,
planka), Tailscale, `unattended-upgrades`. Harte Einschränkung durch die schwache CPU:
**alle Schwerverarbeitung bleibt in der Gemini-API** — kein lokales OCR, keine Transkription,
keine Embeddings auf dieser Box.

---

## 2. Vom Nutzer nötige Entscheidungen vor der Implementierung

1. **`tenacity` als Abhängigkeit hinzufügen?** Es ist die idiomatische Retry-Bibliothek und wird
   bereits anderswo in diesem Ökosystem genutzt (brain-mcp). Laut `CLAUDE.md` brauchen neue
   Deps explizite Freigabe. Alternative: eine kleine handgeschriebene Retry-Schleife ohne
   neue Abhängigkeit. *Empfehlung: tenacity (konsistent, gut typisiert).*
2. **USB-SSD-Mountpoint.** Die SSD **außerhalb von `/mnt`** mounten (empfohlen:
   `/srv/cloud`). Wird sie unter `/mnt/...` gemountet, würde die aktuelle
   `select_observer()`-Heuristik (`watch_dir.startswith("/mnt/")`) den
   PollingObserver erzwingen, obwohl die SSD natives ext4 ist, wo inotify funktioniert.
   Siehe WI-1 für einen optionalen saubereren Fix dieser Heuristik.
3. **WI-4 jetzt einbeziehen oder zurückstellen?** WI-4 (crash-sicherer `_processing/`-Claim) formt
   den Kern-Verarbeitungsfluss um. Es ist der eine Punkt, der Ordering/Idempotenz berührt.
   Die Must-Fixes (WI-1/2/3) liefern den Großteil der Sicherheit auch ohne ihn.

---

## 3. Ziel-Topologie

```
 Laptop / Workstation / Phone ── Syncthing ─┐
 Telegram-Capture (eigener Python-Service) ─┤
                                            ▼
                              Hub: …/cloud/inbox/raw/   (Syncthing, receive-only auf dem Hub)
                                            │  on_created / on_moved
                                            ▼
                          obsidian-inbox-watcher (Gemini 2.5-flash)
                            ├─ ok  → …/cloud/vault/notes/inbox/<note>.md   (Syncthing → Workstation)
                            ├─ ok  → …/cloud/archive/  (nur lokal)
                            └─ fail→ …/cloud/failed/   (nur lokal, + .error-Sidecar)
                                            │
                Syncthing spiegelt vault/ ──┘
                                            ▼
        Workstation /mnt/f/vault ── brain-watcher (wenn PC an) ── Titan → Qdrant
```

### Syncthing-Ordner-Grenzen (kritisch — Titan sauber halten)
- `…/cloud/inbox/raw/` — Syncthing-Ordner, **receive-only auf dem Hub** von den
  Clients (plus Drops vom Telegram-Capture-Service, Anhang A). Das ist
  *roher* Input.
- `…/cloud/vault/` — Syncthing-Ordner, **bidirektional** Hub ↔ Workstation ↔
  Laptop. Notizen werden nach `…/cloud/vault/notes/inbox/` geschrieben.
- `…/cloud/{archive,failed,processing}/` — **nur lokal, nie synchronisiert.** Roh-
  Inputs dürfen nie in den Vault gelangen, sonst würde Titan sie indexieren.

---

## 4. Arbeitspakete

> Die Reihenfolge ist die empfohlene Commit-Sequenz. WI-1 ist hub-blockierend; WI-2/3 sind
> hochwertig; WI-4 ist an Entscheidung 3 gebunden; WI-5 ist klein; WI-6 ist optional.

### WI-1 — Auf `on_moved` zusätzlich zu `on_created` dispatchen  *(HUB-BLOCKIEREND)*
**Problem:** `InboxHandler` implementiert nur `on_created`. Auf dem Hub (natives
inotify) feuert Syncthings Temp-Write-dann-Rename `on_moved`, sodass diese Dateien
verpasst werden.

**Änderung (`src/obsidian_inbox_watcher/main.py`):**
- Den bestehenden Per-Datei-Guard + Dispatch in `on_created` in eine private
  Methode extrahieren, z. B. `_maybe_process(self, raw_path: str) -> None`, enthaltend: bytes→str-
  Coercion, den Archiv-Verzeichnis-Selbstausschluss-Check, die Erweiterungs-Allowlist,
  den Settle-Sleep und den `process_file(...)`-Call.
- `on_created` ruft `self._maybe_process(event.src_path)`.
- `on_moved(self, event: FileSystemEvent) -> None` ergänzen, das
  `self._maybe_process(event.dest_path)` aufruft (den hineingeschobenen Pfad). `dest_path`
  von `bytes` coercen wie `src_path`. Directory-Events ignorieren.
- **Optionales Safety-Net (geringe Kosten, empfohlen):** einen periodischen Voll-Rescan
  des Roh-Verzeichnisses auf einem Timer ergänzen (z. B. alle 60 s) unter Wiederverwendung von
  `process_existing_files`, sodass ein verpasstes Event nie eine Datei stranden lässt. Als Daemon-
  `threading.Timer`-Loop oder einfache Sleep-Schleife in `main()` implementieren; idempotent
  gegen WI-3/WI-4 halten.

**`select_observer()`-Hinweis:** mit Entscheidung 2 (SSD außerhalb von `/mnt`) ist keine Code-Änderung
nötig. *Optionaler saubererer Fix (vorschlagen, nicht ohne Freigabe tun):*
die `/mnt/`-String-Heuristik durch einen Dateisystem-Typ-Check ersetzen (`drvfs`,
`9p`, `cifs`, `nfs` als Polling behandeln; alles andere inotify). Falls verfolgt,
ist das ein eigener Commit + DECISIONS-Eintrag.

**Tests (`tests/test_watcher.py`):** ein echtes
`watchdog.events.FileMovedEvent(src_path=<außerhalb>, dest_path=<raw/file.txt>)`
konstruieren und prüfen, dass `process_file` aufgerufen wird (es patchen oder prüfen, dass eine Notiz
via den gemockten Gemini-Client geschrieben wird). Den bestehenden `on_created`-Test-Stil spiegeln;
`time.sleep` via Dotted-Path-String patchen.

**Commit:** `feat: process files arriving via rename (on_moved) for Syncthing`

---

### WI-2 — Den Gemini-Call wiederholen + Dead-Letter-`_failed/`-Queue
**Problem:** der Gemini-Call läuft einmal. Ein transienter Fehler (429/5xx/Netzwerk)
wirft, das breite `except Exception` loggt und kehrt zurück, und die Roh-Datei bleibt in
der Inbox — wiederholt nur beim nächsten Service-Neustart. Eine dauerhaft schlechte Datei
(z. B. korruptes PDF) loopt bei jedem Neustart für immer und verlässt die Inbox nie.
Das pauschale `except` verletzt außerdem die Projektregel gegen das Verschlucken von Fehlern.

**Änderungen:**
- Eine `VAULT_WATCHER_FAILED_DIR`-Config-Var ergänzen (Default `~/0_Pipeline/Failed`,
  **außerhalb** des Vaults gehalten). Wie die anderen Verzeichnisse in `main()` auflösen, beim
  Start anlegen und durch `InboxHandler` → `process_file` durchreichen wie
  `processed_dir`/`archive_dir`.
- **Nur die transienten Operationen** in einen begrenzten Retry mit exponentiellem
  Backoff wickeln: den `client.models.generate_content(...)`-Call und den `.url`-
  `requests.get(...)`. Nur bei Netzwerk/Timeout/HTTP-5xx/429 wiederholen. `json.JSONDecodeError`,
  Empty-Text oder Programmierfehler **nicht** wiederholen.
  - Mit tenacity (Entscheidung 1 = ja): `@retry(stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, max=30), retry=retry_if_exception_type(...))`
    auf einem kleinen Helper, der den Call ausführt und das geparste Ergebnis zurückgibt.
  - Ohne tenacity: eine handgeschriebene Schleife mit `for attempt in range(5)` +
    `time.sleep(backoff)`; identische Retry-Prädikat-Logik.
- Das einzelne Catch-all in `process_file` durch explizites Handling ersetzen:
  - **Transient, Retries erschöpft** oder **dauerhafter Verarbeitungsfehler** → die
    Roh-Datei nach `VAULT_WATCHER_FAILED_DIR` verschieben und ein Sidecar
    `<original_name>.error.txt` schreiben mit Zeitstempel + Exception-Typ + Message
    (kein voller Traceback im Sidecar; volles `logger.exception` geht weiterhin ins
    Journal). Keine Notiz schreiben, nicht archivieren.
  - **Leerer extrahierter Text / nicht unterstütztes Format** → aktuelles Verhalten behalten (Log
    + Skip), aber auch nach `_failed/` verschieben mit Grund `empty_text` /
    `unsupported_format`, sodass es die Inbox verlässt und nicht für immer neu gescannt wird.
- Beim Start drainiert `process_existing_files` bereits die Inbox; sicherstellen, dass Dateien in
  `_failed/` nie aufgenommen werden (sie liegen außerhalb des Roh-Verzeichnisses, das hält also).

**Tests:** (a) Gemini mocken, dass es N−1 mal einen transienten Fehler wirft und dann erfolgreich ist →
prüfen, dass genau eine Notiz geschrieben und der Call wiederholt wird; (b) einen dauerhaften
Fehler mocken → prüfen, dass die Roh-Datei in `failed_dir` ist, ein `.error.txt`-Sidecar existiert
und nichts in `processed_dir`/`archive_dir` ist.

**DECISIONS.md anhängen:** „Gemini mit begrenztem Backoff wiederholen; dead-lettern nach
`VAULT_WATCHER_FAILED_DIR`" — Begründung: Poison-Dateien müssen die Inbox verlassen;
transiente Fehler dürfen keinen Service-Neustart brauchen; spiegelt brain-mcps
Failed-Queue-Pattern.

**Commit:** `feat: retry Gemini calls and dead-letter unprocessable files`

---

### WI-3 — Nie eine bestehende Ausgabe-Notiz überschreiben
**Problem:** der Ausgabe-Dateiname ist `{date}_{safe_title}.md` ohne Kollisions-
Guard (nur die Archiv-Seite sichert ab). Zwei Inputs, die am selben Tag denselben Titel
ergeben, oder jede Wiederverarbeitung einer Roh-Datei, **überschreiben** eine bestehende Notiz —
inklusive einer, die der Nutzer seither in Obsidian editiert hat.

**Änderung:** einen Helper `unique_output_path(directory: str, filename: str) -> str`
ergänzen, der `filename` zurückgibt, wenn frei, sonst `_v2`, `_v3`, … vor der `.md`-
Erweiterung einfügt, bis frei. Ihn für den Processed-Note-Pfad in `process_file`
verwenden (die Absicht des bestehenden Archiv-Zeitstempel-Suffix-Guards spiegeln, aber versioniert,
weil das nutzersichtbare Notizen sind, keine entbehrlichen Originale).

**Tests:** `<date>_<title>.md` in `processed_dir` vorab anlegen, Verarbeitung laufen lassen,
prüfen, dass eine `<date>_<title>_v2.md` erstellt wird und der Inhalt der vorbestehenden Datei
unberührt bleibt.

**Commit:** `fix: never overwrite an existing processed note`

---

### WI-4 — Crash-sichere Verarbeitung via einen `_processing/`-Claim  *(an Entscheidung 3 gebunden)*
**Problem:** der Fluss ist Notiz-schreiben → Original-verschieben. Ein Crash zwischen den beiden
verarbeitet die Roh-Datei beim Neustart erneut (Duplikat-Notiz / Überschreib-Risiko, das WI-3
mildert, aber an der Quelle nicht eliminiert).

**Änderung:**
- `VAULT_WATCHER_PROCESSING_DIR` ergänzen (Default `~/0_Pipeline/Processing`, lokal).
- Am *Anfang* der Verarbeitung einer Datei die Roh-Datei **atomar** nach
  `…/Processing/<uuid>/` verschieben und dort daran arbeiten. Das „beansprucht" die Datei, sodass ein
  nebenläufiges Event oder ein Restart-Scan sie nicht erneut aufnehmen kann.
- Bei Erfolg: die Notiz schreiben (WI-3-Guard), dann das Original aus
  `…/Processing/<uuid>/` ins Archiv verschieben; das nun leere uuid-Verzeichnis entfernen.
- Bei Fehler: von `…/Processing/<uuid>/` nach `…/Failed/` verschieben (WI-2).
- Beim Start, vor dem normalen Scan, **`…/Processing/` drainieren**: etwaige übrig gebliebene
  uuid-Verzeichnisse sind Crash-Reste → ihre Inhalte nach `…/Failed/` verschieben mit Grund
  `interrupted` zur Inspektion (sicherer als blinde Wiederverarbeitung).

**Hinweis für den Implementierer:** das ist der Punkt mit Nebenläufigkeits-/Ordering-
Implikationen. Ist hier etwas gegenüber dem bestehenden Code mehrdeutig, ANHALTEN und
gemäß `CLAUDE.md` für Opus flaggen, statt zu raten.

**Tests:** den Notiz-Write monkeypatchen, sodass er nach dem Claim wirft; prüfen, dass die Roh-
Datei in `failed_dir` landet (nicht verloren, nicht in `processed_dir`) und das
`processing_dir` danach leer ist.

**DECISIONS.md anhängen:** „Roh-Dateien vor der Verarbeitung in `_processing/<uuid>/`
beanspruchen für Crash-Sicherheit und Idempotenz" mit der erwogenen Alternative
(Hash-basierter Idempotenz-Marker) und warum das Claim-Modell gewählt wurde (passt zur
brain-ingest-Verzeichnis-Pipeline, einfacher nachzuvollziehen).

**Commit:** `refactor: claim raw files into a processing dir for crash-safety`

---

### WI-5 — Die stille 20k-Zeichen-Kürzung anheben + loggen
**Problem:** `text_content[:20000]` lässt still das Ende langer PDFs fallen.
`gemini-2.5-flash` hat ein sehr großes Kontextfenster, sodass die Deckelung unnötig
konservativ und unsichtbar ist.

**Änderung:** eine `VAULT_WATCHER_MAX_CHARS`-Config einführen (Default z. B. `200000`).
Überschreitet der extrahierte Text sie, kürzen und die ursprüngliche Länge, die Deckelung
und den Dateinamen via `logger.warning(...)` loggen, sodass die Kürzung nie still ist.

**Tests:** Text länger als eine kleine Test-Deckelung einspeisen, prüfen, dass eine Warnung geloggt wird und
der Prompt die gekürzte Länge erhält.

**Commit:** `feat: make extraction length limit configurable and log truncation`

---

### WI-6 — *(Optional / IDEAS)* PDFs multimodal an Gemini senden
**Begründung:** `pypdf` extrahiert keinen Text aus gescannten PDFs → leerer Text → übersprungen.
Die PDF-Bytes direkt an Gemini zu senden (es ist multimodal) verarbeitet gescannte Docs
**und** nimmt dem schwachen J3710 die lokale Parsing-Last. Das ist eine Verhaltens-/Design-
Änderung, kein Bugfix.

**Aktion:** unter diesem Plan **nicht** implementieren. In `docs/ai/IDEAS.md` erfassen
mit dem Trade-off (Per-Call-Kosten / Token-Größe vs. Verarbeitung von Scans). Als
separaten Plan wieder aufgreifen, falls gescannte PDFs häufig werden.

---

### WI-7 — Hub-Deployment (nur Config + Docs; keine Live-Secrets im Repo)
**Scope für dieses Repo** (die eigentlichen `systemctl`/Key-Schritte gehören dem Nutzer, auf dem
Hub ausgeführt):

- **Neue systemd-Unit** `deploy/obsidian-inbox-watcher.hub.service` (die WSL-Unit
  für die Workstation behalten). Nutzer `charlie`, z. B.:
  - `WorkingDirectory=/home/charlie/projects/obsidian-inbox-watcher`
  - `EnvironmentFile=/home/charlie/.config/vault_watcher/env`
  - `ExecStart=/home/charlie/projects/obsidian-inbox-watcher/.venv/bin/obsidian-inbox-watcher`
  - `Restart=always`, `RestartSec=5`, plus `StartLimitIntervalSec=0`, sodass es immer
    neu startet; `After=network-online.target` und `Wants=network-online.target`.
- **Beispiel-Env für den Hub** (in `deploy/README.md` dokumentieren, absolute Pfade —
  systemd expandiert `~` nicht). SSD unter `/srv/cloud` gemountet gemäß Entscheidung 2:
  ```
  GEMINI_API_KEY=...
  VAULT_WATCHER_RAW_DIR=/srv/cloud/inbox/raw
  VAULT_WATCHER_PROCESSED_DIR=/srv/cloud/vault/notes/inbox
  VAULT_WATCHER_ARCHIVE_DIR=/srv/cloud/archive
  VAULT_WATCHER_FAILED_DIR=/srv/cloud/failed
  VAULT_WATCHER_PROCESSING_DIR=/srv/cloud/processing   # falls WI-4 gelandet ist
  VAULT_WATCHER_DOMAINS=business,lernen,projekte,system
  ```
  (`raw` und `vault` sind separate Syncthing-Ordner; `archive`/`failed`/
  `processing` sind nur lokal — siehe §3.)
- **`.env.example`:** die generischen OPENAI/ANTHROPIC-Platzhalter durch den
  echten `GEMINI_API_KEY` + alle `VAULT_WATCHER_*`-Vars ersetzen, die dieses Projekt tatsächlich nutzt,
  passend zur README-Tabelle.
- **Docs:** `CONTEXT.md` aktualisieren (neue Config-Vars, Hub-Deployment-Hinweis, der
  on_moved/inotify-Fallstrick), `ARCHITECTURE.md` (Hub-Datenfluss + die neuen
  failed/processing-Verzeichnisse) und DECISIONS-Einträge für die zweistufige Hub-
  Topologie ergänzen.

**Out of Scope für dieses Repo** (gehört zum Hub-Provisioning, getrackt in der
separaten `projekt-brain-ingest`-Notiz): Installation von `uv`, `restic`, `nfs-common`;
Mounten/Formatieren der USB-SSD; der restic→H100-Backup-Job; der Telegram-
Capture-Service (ein separates Schwester-Python-Repo — siehe Anhang A). Diese nicht zum Diff dieses Repos hinzufügen.

**Commit:** `chore: add hub systemd unit and document hub deployment`

---

## 5. Definition of Done (jedes Arbeitspaket)
- `make check` ist grün (ruff + mypy strict + pytest mit Coverage).
- Neues Verhalten hat einen Regressionstest, der das `tests/` ↔ `src/`-Layout spiegelt.
- Kein nacktes `except`, keine verschluckten Fehler, kein `print()`, vollständige Type-Hints, kein
  unerklärtes `# type: ignore`.
- `docs/ai/DECISIONS.md` für WI-2 und WI-4 angehängt (und WI-1, falls die
  `select_observer()`-Heuristik geändert wird).
- `docs/ai/CURRENT_TASK.md` aktualisiert, wenn Schritte fertig sind; `docs/ai/HANDOFF.md`
  geschrieben vor dem Stoppen oder Modellwechsel.
- Eine logische Änderung pro Commit; Conventional-Commit-Messages wie oben angegeben.

## 6. Vorgeschlagene Reihenfolge
WI-1 → WI-2 → WI-3 → (WI-4 falls freigegeben) → WI-5 → WI-7. WI-6 geht nur in IDEAS.
WI-1 muss landen, bevor der Hub live geht, sonst werden Syncthing-gelieferte Dateien verpasst.

---

## Anhang A — Telegram-Capture-Service (eigener Python-Service, Schwester-Repo)

**Entscheidung (Opus):** die Capture-Schicht ist ein **separater, dünner Python-Service** —
**nicht** n8n und **nicht** Teil des `obsidian-inbox-watcher`-Repos. Begründung:
die einzige Verantwortung des Watchers ist *Roh-Datei → Gemini → Notiz*; der Telegram-
Receiver teilt nichts mit ihm außer dem Roh-Inbox-Pfad, und dieses Repo ist
bewusst dependency-arm (kein `python-telegram-bot`). Ein Schwester-Service hält
die dateisystem-entkoppelte Architektur intakt und passt zum bestehenden Multi-Repo-
Layout (`titan`, `brain-mcp`, `brain-dashboard`, `obsidian-inbox-watcher`).

Dieser Anhang ist **nur eine Spezifikation** — implementiere ihn unter seinem **eigenen Plan**
in seinem eigenen Repo, geklont aus `python-template` (gleiche uv/ruff/mypy-strict/pytest-
Gates). Er gehört nicht in den Diff dieses Plans.

### Verantwortung
Telegram-Nachrichten von einem allow-gelisteten Satz von Nutzern empfangen und sie als Roh-
Dateien in `VAULT_WATCHER_RAW_DIR` (`/srv/cloud/inbox/raw`) schreiben. Sonst nichts: kein
Gemini, kein Vault, kein Titan. Der Watcher (dieses Repo) macht den Rest.

### Vorgeschlagenes Repo
`brain-telegram-ingest` unter `~/projects/`, Entry-Point
`brain-telegram-ingest`, eigener systemd-Service `brain-telegram-ingest` auf dem Hub
(Nutzer `charlie`).

### Verhalten
- **Bibliothek:** `python-telegram-bot` (async). Long-Polling ist in Ordnung — kein eingehender
  Port, funktioniert hinter dem NAT des Hubs neben dem bestehenden Tailscale-Setup.
- **Allowlist:** eine `TELEGRAM_ALLOWED_USER_IDS`-Env-Var (kommagetrennte numerische
  IDs). Nachrichten von jeder anderen ID werden **still ignoriert** — keine Antwort, sodass die
  Existenz des Bots Fremden gegenüber nicht bestätigt wird. Das spiegelt das Login-Allowlist-
  Pattern in brain-mcps `auth.py`.
- **Config:** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS` und das geteilte
  `VAULT_WATCHER_RAW_DIR`, alle aus `~/.config/vault_watcher/env` (dieselbe Env-Datei
  wiederverwenden, die der Watcher nutzt, oder eine Geschwister-Datei). Token-Datei-Mode `600`.
- **Nachricht → Roh-Datei-Mapping:**
  - **Text** → `tg_<UTCstamp>_<msgid>.txt` schreiben, das den Nachrichtentext enthält.
  - **Dokument / Datei** → den Anhang unter seinem Originalnamen mit Präfix
    `tg_<UTCstamp>_` speichern. Erst nachdem der Nutzer in diesem Design bestätigt hat, dass
    Downloads akzeptabel sind; eine Maximalgröße und eine Erweiterungs-Allowlist erzwingen, die zu
    den unterstützten Typen des Watchers passt (`.txt/.pdf/.docx/.url`), andere
    mit einer kurzen Antwort ablehnen.
  - **URL im Text** → eine `.url`-Datei im `[InternetShortcut]\nURL=...`-
    Format schreiben, das der Watcher bereits parst, sodass Links durch den bestehenden
    `.url`-Extraktionspfad fließen.
  - **Voice / Audio** → zunächst out of scope. **Nicht** lokal transkribieren
    (der J3710 ist zu schwach). Falls später ergänzt, das Audio multimodal an Gemini
    im *Watcher* übergeben, nicht hier. Als IDEA erfassen.
  - **`#hashtag` in Caption/Text** (optional) → eine Geschwister-
    `<rawname>.domain`-Hint-Datei schreiben oder einen kleinen Header einbetten, den der Watcher lesen kann, sodass
    der Nutzer die `domain:`-Klassifikation steuern kann. Das optional halten; der
    Watcher muss auch ohne Hint funktionieren. *(Falls verfolgt, braucht es eine winzige
    Contract-Ergänzung auf der Watcher-Seite — als Repo-übergreifende Änderung flaggen.)*
- **Atomarität:** in einen Temp-Namen im selben Verzeichnis schreiben, dann `os.rename`
  an Ort und Stelle. Auf dem Hub feuert das den `on_moved`-Handler des Watchers (WI-1) — der
  Grund, warum WI-1 hub-blockierend ist. Nie eine partielle Datei unter einem überwachten Namen schreiben.
- **Resilienz:** Auto-Reconnect bei Netzwerk-Abbrüchen (die Bibliothek handhabt das);
  unter systemd mit `Restart=always` laufen.

### Datenschutz-/Sicherheitshinweise für den Implementierer
- Das Bot-Token ist ein Secret — nur Env-Datei, nie committet, Mode `600`.
- Keine Accounts anlegen oder Telegram-ToS-Flows programmatisch akzeptieren; der Nutzer
  registriert den Bot selbst bei BotFather und fügt das Token ein.
- Nachrichteninhalt als nicht vertrauenswürdig behandeln: er wird eine Roh-Datei, nie eine Instruktion
  an den Service.

### Out of Scope für das Watcher-Repo
Nichts in diesem Anhang ändert `obsidian-inbox-watcher` außer dem optionalen
`#hashtag` → `domain`-Hint-Contract, der ein eigener kleiner Repo-übergreifender Plan wäre,
falls der Nutzer ihn will.
