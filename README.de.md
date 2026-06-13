# obsidian_inbox_watcher

Ein lokaler Ordner-Watcher, der abgelegte Dokumente mit Google Gemini in strukturierte
Obsidian-Notizen verwandelt — das Dokumentverarbeitungs-Frontend zum **Titan**-
RAG-System.

Er überwacht eine Roh-Inbox auf **TXT- / PDF- / DOCX- / `.url`**-Dateien, extrahiert den Text
(crawlt bei URLs die Seite), klassifiziert und fasst ihn mit `gemini-2.5-flash` zusammen,
schreibt eine Obsidian-Markdown-Notiz (YAML-Frontmatter, Action Items, offene Fragen)
und archiviert das Original. Alles, was er nicht verarbeiten kann, wird mit einer Fehler-
Notiz beiseitegelegt, statt für immer wiederholt zu werden.

Er läuft perfekt **standalone** — er schreibt die Notizen einfach in einen von dir
gewählten Ordner. Die **Titan**-RAG-Integration ist optional: zeigt der Ausgabeordner in
Titans Vault, ingestet `brain-watcher` jede Notiz automatisch in den Suchindex.

## Voraussetzungen

- **Linux oder WSL2.** Der Watcher ist darauf ausgelegt, als systemd-User-Service zu laufen,
  und liest `/proc/mounts`, um seine Datei-Überwachungsstrategie zu wählen, zielt also auf Linux
  (ein natives System oder Ubuntu unter WSL2). Andere Betriebssysteme sind ungetestet.
- **Python 3.12+** und **[uv](https://docs.astral.sh/uv/)** (der Paketmanager —
  `uv` installiert dir bei Bedarf das passende Python).
- **Ein Google-Gemini-API-Key.** Klassifikation und Zusammenfassung laufen auf
  `gemini-2.5-flash`. Einen Key erstellen (der Free Tier reicht zum Ausprobieren) im
  [Google AI Studio](https://aistudio.google.com/app/apikey).
- **(Optional) Titan + `brain-watcher`** für die RAG-Integration — *nicht* erforderlich.
  Ohne sie schreibt der Watcher einfach Markdown-Notizen in einen Ordner.

Es werden keine zusätzlichen Systempakete benötigt: PDF- / DOCX- / HTML-Parsing kommt aus Python-
Abhängigkeiten (`pypdf`, `python-docx`, `beautifulsoup4`), die `uv` für dich installiert.

## Schnellstart (standalone)

```bash
# 1. Abhängigkeiten und die git-pre-commit-Hooks installieren
make install

# 2. Deinen Gemini-API-Key bereitstellen (das einzige Pflicht-Setting)
mkdir -p ~/.config/vault_watcher
echo 'GEMINI_API_KEY=dein-echter-key-hier' > ~/.config/vault_watcher/env
chmod 600 ~/.config/vault_watcher/env   # die Datei enthält ein Geheimnis

# 3. Ausführen (die Arbeitsordner werden beim ersten Start angelegt)
make run
```

Mit nur gesetztem Key nutzt der Watcher diese Default-Ordner und legt sie
automatisch an:

- Dateien in **`~/0_Pipeline/In`** ablegen
- fertige Notizen erscheinen in **`~/0_Pipeline/Out`**
- Originale werden nach **`~/0_Pipeline/Archive`** verschoben
- unverarbeitbare Dateien gehen nach **`~/0_Pipeline/Failed`** (mit einem `.error.txt`-Grund)

Eine `.txt`-, `.pdf`-, `.docx`- oder `.url`-Datei in die Inbox legen, und innerhalb von ein,
zwei Sekunden erscheint eine strukturierte Notiz im Ausgabeordner. Um diese Ordner
woandershin zu legen (oder in Titans Vault), die Variablen unten setzen.

## Konfiguration

Diese in `~/.config/vault_watcher/env` setzen (von der App und von systemd geladen;
absolute Pfade verwenden):

| Variable | Zweck | Default |
|---|---|---|
| `GEMINI_API_KEY` | Gemini-API-Key (erforderlich) | — |
| `VAULT_WATCHER_RAW_DIR` | auf neue Dateien überwachter Ordner | `~/0_Pipeline/In` |
| `VAULT_WATCHER_PROCESSED_DIR` | wohin Notizen geschrieben werden | `~/0_Pipeline/Out` |
| `VAULT_WATCHER_ARCHIVE_DIR` | wohin Originale verschoben werden | `~/0_Pipeline/Archive` |
| `VAULT_WATCHER_FAILED_DIR` | Dead-Letter-Verzeichnis für unverarbeitbare Inputs (+ `.error.txt`-Sidecar) | `~/0_Pipeline/Failed` |
| `VAULT_WATCHER_DOMAINS` | Seed-Titan-Domains für die Klassifikation (Gemini darf neue ergänzen) | `business,lernen,projekte,system` |
| `VAULT_WATCHER_MAX_CHARS` | max. Zeichen des an Gemini gesendeten extrahierten Texts (darüber gekürzt + geloggt) | `200000` |

Notizen werden mit einem von Titan benötigten `domain:`-Frontmatter-Feld geschrieben (Gemini wählt
aus der Seed-Liste oder erstellt eine neue); siehe `docs/ai/ARCHITECTURE.md`.

Jeder absolute Pfad funktioniert für die Verzeichnisse — die `/mnt/f/...`-Werte unten sind
**Beispiele aus dem WSL2-Setup des Autors** (wo `/mnt/f` das Windows-Laufwerk `F:` ist).
Auf einem nativen Linux-System einfach Pfade unter deinem Home verwenden, z. B. `~/vault`.

Für die optionale Titan-Integration `VAULT_WATCHER_PROCESSED_DIR` auf einen Ordner
innerhalb deines RAG-Vaults setzen (der Autor nutzt `/mnt/f/vault/notes/inbox`). Die Roh- und
Archiv-Verzeichnisse *außerhalb* des Vaults halten. Siehe `docs/ai/ARCHITECTURE.md`.

Wenn du unter WSL2 läufst und Dateien direkt aus dem Windows-Explorer ablegen willst, kann das Roh-
Verzeichnis auf einem Windows-Laufwerk liegen (z. B. `/mnt/f/0_Pipeline/In` → `F:\0_Pipeline\In`);
der Watcher nutzt dort automatisch einen Polling-Observer, da inotify auf dem
`/mnt`-Mount nicht zugestellt wird.

## Ausführen & Entwickeln

```bash
make run        # den Watcher lokal ausführen
make test       # Tests mit Coverage ausführen
make check      # vollständiges Quality-Gate: Lint + Typen + Tests
make format     # Style-Probleme automatisch beheben
make help       # alle verfügbaren Befehle auflisten
```

Als systemd-User-Service deployen — siehe `deploy/README.md`.

## Projektstruktur

```
src/obsidian_inbox_watcher/    Quellcode
tests/               Pytest-Tests (spiegelt das src/-Layout)
docs/ai/             Kontext und Pläne für KI-Agenten
.github/workflows/   CI-Konfiguration
```

## Tooling

| Tool         | Zweck                                |
|--------------|--------------------------------------|
| **uv**       | Paketmanager + Python-Installer      |
| **ruff**     | Linter + Formatter                   |
| **mypy**     | Statischer Typprüfer (Strict Mode)   |
| **pytest**   | Test-Runner mit Coverage             |
| **pre-commit** | Git-Hook-Runner                    |

Alle Tools laufen bei jedem Push in der CI.

## Arbeiten mit KI-Tools

Dieses Projekt nutzt einen strukturierten Workflow für KI-gestütztes Coding. Jeder
KI-Agent (Claude, Gemini, Cursor, Aider usw.) sollte zuerst `CLAUDE.md` lesen — sie
ist als `AGENTS.md` und `GEMINI.md` für Tool-Kompatibilität gespiegelt.

Wichtige Dateien für den KI-Kontext:

- `docs/ai/CONTEXT.md` — Stack, Konventionen, Glossar
- `docs/ai/CURRENT_TASK.md` — woran aktiv gearbeitet wird
- `docs/ai/HANDOFF.md` — Zustand für die Fortsetzung von Sitzungen über Modellwechsel hinweg
- `docs/ai/DECISIONS.md` — Protokoll der Architekturentscheidungen
- `docs/ai/plans/` — gespeicherte Pläne, erstellt von einem Planungsmodell (z. B. Opus)

Der vorgesehene Workflow:

1. Architektur- und Feature-Pläne werden von einem starken Reasoning-Modell erstellt und unter `docs/ai/plans/` gespeichert
2. Ein schnelleres/günstigeres Modell implementiert die Pläne
3. Beide referenzieren den gemeinsamen Kontext in `docs/ai/`
4. Der Zustand wird über `HANDOFF.md` über Sitzungen hinweg bewahrt

## Lizenz

Noch offen (TBD)
