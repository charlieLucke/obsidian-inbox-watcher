"""Automated test suite for obsidian_inbox_watcher."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import requests

from obsidian_inbox_watcher import main as watcher
from obsidian_inbox_watcher import pipeline
from obsidian_inbox_watcher import watcher as watchermod

# Configure logging
logger = logging.getLogger(__name__)


class MockResponse:
    def __init__(self, text: str):
        self.text = text


def get_mock_gemini_client(api_key: str | None = None) -> MagicMock:
    """Return a mocked google-genai client that simulates Gemini responses."""
    mock_client = MagicMock()

    def generate_content(model: str, contents: Any, config: Any = None) -> MockResponse:
        logger.info("Mock Gemini API generate_content was called.")

        # Analyze content to decide category and details
        contents_str = str(contents).lower()
        actual_text = contents_str.split("textinhalt, der analysiert werden soll:")[-1]

        if "vorlesung" in actual_text or "studium" in actual_text or "avl" in actual_text:
            mock_json = {
                "titel": "Datenstrukturen und Algorithmen Vorlesung",
                "domain": "lernen",
                "tags": ["Informatik", "Studium", "Algorithmen", "Datenstrukturen", "AVL-Bäume"],
                "summary": (
                    "In dieser Vorlesung geht es um binäre Suchbäume, "
                    "AVL-Bäume und Komplexitätsklassen."
                ),
                "questions": "Wie genau funktioniert die AVL-Rebalancierung im Detail?",
                "action_items": [
                    "Übungsblatt 4 lösen bis nächsten Montag",
                    "Skript Kapitel 5 lesen",
                ],
            }
        elif (
            "börse" in actual_text
            or "trading" in actual_text
            or "aktien" in actual_text
            or "wikipedia" in actual_text
        ):
            mock_json = {
                "titel": "Börse und Finanzmärkte Grundlagen",
                "domain": "trading",
                "tags": ["Trading", "Börse", "Finanzen", "Aktien", "Marktplatz"],
                "summary": (
                    "Eine Einführung in das Funktionieren von Börsen und "
                    "organisierten Finanzmärkten."
                ),
                "questions": (
                    "Welche regulatorischen Unterschiede gibt es zwischen "
                    "Parketthandel und elektronischem Handel?"
                ),
                "action_items": ["Markttrends für das nächste Quartal analysieren"],
            }
        else:
            mock_json = {
                "titel": "Musterdokument Analyse",
                "domain": "system",
                "tags": ["Infrastruktur", "Systeme", "Netzwerk", "Automatisierung", "Linux"],
                "summary": "Ein allgemeines Dokument zur IT-Infrastruktur und Automatisierung.",
                "questions": "Welche Skalierungsanforderungen gibt es für dieses System?",
                "action_items": ["Konfiguration überprüfen"],
            }

        return MockResponse(json.dumps(mock_json))

    mock_client.models.generate_content = generate_content
    return mock_client


def test_watcher_pipeline(tmp_path):
    """Verify end-to-end file parsing, API prompting, markdown output formatting, and archiving."""
    # Paths - use pytest tmp_path so CI doesn't need ~/Vault
    raw_dir = tmp_path / "Raw"
    processed_dir = tmp_path / "Processed"
    archive_dir = raw_dir / "Archive"

    raw_dir.mkdir()
    processed_dir.mkdir()
    archive_dir.mkdir()

    # 1. Create test files
    # Test file 1: Text file (Informatik-Studium)
    txt_path = raw_dir / "studium_notiz.txt"
    txt_path.write_text(
        "Vorlesung Datenstrukturen und Algorithmen:\n"
        "Heute besprechen wir binäre Suchbäume, AVL-Bäume "
        "und Komplexitätsklassen.\n"
        "Wir müssen ein Übungsblatt 4 lösen bis nächsten "
        "Montag und Skript Kapitel 5 lesen.\n",
        encoding="utf-8",
    )

    # Test file 2: URL file (Trading/Börse)
    url_path = raw_dir / "trading_boerse.url"
    url_path.write_text(
        "[InternetShortcut]\nURL=https://de.wikipedia.org/wiki/B%C3%B6rse\n",
        encoding="utf-8",
    )

    # 2. Process files (using Mock)
    with (
        patch(
            "obsidian_inbox_watcher.pipeline.load_api_key",
            return_value="dummy-key-for-testing",
        ),
        patch("google.genai.Client", side_effect=get_mock_gemini_client),
    ):
        watcher.process_file(
            str(txt_path),
            processed_dir=str(processed_dir),
            archive_dir=str(archive_dir),
        )
        watcher.process_file(
            str(url_path),
            processed_dir=str(processed_dir),
            archive_dir=str(archive_dir),
        )

    # 3. Verification
    processed_files = list(processed_dir.iterdir())
    assert len(processed_files) == 2, f"Expected 2 processed notes, found {len(processed_files)}"

    for pfp in processed_files:
        content = pfp.read_text(encoding="utf-8")

        # Verify markdown template structure and frontmatter
        assert "created:" in content, "Frontmatter 'created' is missing"
        assert "source:" in content, "Frontmatter 'source' is missing"
        assert "domain:" in content, "Frontmatter 'domain' is missing"
        assert "tags:" in content, "Frontmatter 'tags' is missing"
        assert "ai_processed: true" in content, "Frontmatter 'ai_processed' is missing"
        assert "## Zusammenfassung" in content, "Heading '## Zusammenfassung' is missing"
        assert "## Wissenslücken / Fragen an mich" in content, (
            "Heading '## Wissenslücken / Fragen an mich' is missing"
        )
        assert "## Action Items" in content, "Heading '## Action Items' is missing"
        assert "- [ ]" in content, "Action items format incorrect"

    # 4. Verify Archive folder
    archived_files = [f.name for f in archive_dir.iterdir()]
    assert any(f.startswith("studium_notiz") for f in archived_files), (
        "studium_notiz.txt was not archived"
    )
    assert any(f.startswith("trading_boerse") for f in archived_files), (
        "trading_boerse.url was not archived"
    )


def test_resolve_dir_env_override(monkeypatch):
    """An env var overrides the default directory."""
    monkeypatch.setenv("VAULT_WATCHER_PROCESSED_DIR", "/mnt/f/vault/notes/inbox")
    assert (
        watcher.resolve_dir("VAULT_WATCHER_PROCESSED_DIR", "~/0_Pipeline/Out")
        == "/mnt/f/vault/notes/inbox"
    )


def test_resolve_dir_default_expands_tilde(monkeypatch):
    """Falling back to the default expands ~ to an absolute path."""
    monkeypatch.delenv("VAULT_WATCHER_RAW_DIR", raising=False)
    result = watcher.resolve_dir("VAULT_WATCHER_RAW_DIR", "~/0_Pipeline/In")
    assert result == os.path.expanduser("~/0_Pipeline/In")
    assert "~" not in result


def test_load_env_file_no_override(tmp_path, monkeypatch):
    """load_env_file fills missing vars but never overrides existing ones."""
    env_file = tmp_path / "env"
    env_file.write_text(
        "# a comment\n"
        "GEMINI_API_KEY=abc123\n"
        "VAULT_WATCHER_PROCESSED_DIR=/mnt/f/vault/notes/inbox\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("VAULT_WATCHER_PROCESSED_DIR", "/already/set")

    watcher.load_env_file(str(env_file))

    assert os.environ["GEMINI_API_KEY"] == "abc123"
    assert os.environ["VAULT_WATCHER_PROCESSED_DIR"] == "/already/set"


def test_inbox_handler_routes_configured_dirs(monkeypatch):
    """The handler forwards its configured processed/archive dirs to process_file."""
    from watchdog.events import FileCreatedEvent

    calls: dict[str, Any] = {}

    def fake_process(filepath, *, processed_dir=None, archive_dir=None, failed_dir=None):
        calls["filepath"] = filepath
        calls["processed_dir"] = processed_dir
        calls["archive_dir"] = archive_dir
        calls["failed_dir"] = failed_dir

    monkeypatch.setattr(watchermod, "process_file", fake_process)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    handler = watcher.InboxHandler("/out", "/arch", "/failed")
    handler.on_created(FileCreatedEvent("/raw/note.txt"))

    assert calls["filepath"] == "/raw/note.txt"
    assert calls["processed_dir"] == "/out"
    assert calls["archive_dir"] == os.path.abspath("/arch")
    assert calls["failed_dir"] == "/failed"


def test_inbox_handler_processes_moved_file(monkeypatch):
    """on_moved dispatches the moved-in (dest) path — Syncthing delivers via rename."""
    from watchdog.events import FileMovedEvent

    calls: dict[str, Any] = {}

    def fake_process(filepath, *, processed_dir=None, archive_dir=None, failed_dir=None):
        calls["filepath"] = filepath
        calls["processed_dir"] = processed_dir
        calls["archive_dir"] = archive_dir
        calls["failed_dir"] = failed_dir

    monkeypatch.setattr(watchermod, "process_file", fake_process)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    handler = watcher.InboxHandler("/out", "/arch", "/failed")
    handler.on_moved(FileMovedEvent("/tmp/.syncthing.note.txt.tmp", "/raw/note.txt"))

    assert calls["filepath"] == os.path.abspath("/raw/note.txt")
    assert calls["processed_dir"] == "/out"
    assert calls["archive_dir"] == os.path.abspath("/arch")
    assert calls["failed_dir"] == "/failed"


def test_rescan_dispatches_only_supported_files(tmp_path, monkeypatch):
    """rescan() re-dispatches supported files but skips unsupported files and subdirs."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "keep.txt").write_text("x", encoding="utf-8")
    (raw_dir / "ignore.bin").write_text("x", encoding="utf-8")
    (raw_dir / "sub").mkdir()

    processed: list[str] = []
    monkeypatch.setattr(watchermod, "process_file", lambda fp, **_kw: processed.append(fp))
    monkeypatch.setattr("time.sleep", lambda _s: None)

    handler = watcher.InboxHandler(
        str(tmp_path / "out"), str(tmp_path / "arch"), str(tmp_path / "failed")
    )
    handler.rescan(str(raw_dir))

    assert processed == [os.path.abspath(str(raw_dir / "keep.txt"))]


def test_select_observer_polling_for_translated_fs(monkeypatch):
    """Translated/network filesystems (drvfs/9p/cifs/nfs) use the polling observer."""
    from watchdog.observers.polling import PollingObserver

    monkeypatch.setattr(watchermod, "_filesystem_type", lambda _p: "9p")
    assert isinstance(watcher.select_observer("/mnt/f/0_Pipeline/In"), PollingObserver)


def test_select_observer_inotify_for_native_fs(monkeypatch):
    """Native local filesystems (ext4) use the inotify observer."""
    from watchdog.observers.polling import PollingObserver

    monkeypatch.setattr(watchermod, "_filesystem_type", lambda _p: "ext4")
    assert not isinstance(watcher.select_observer("/srv/cloud/inbox/raw"), PollingObserver)


def test_select_observer_falls_back_to_path_heuristic(monkeypatch):
    """When the filesystem type is unknown, fall back to the /mnt path heuristic."""
    from watchdog.observers.polling import PollingObserver

    monkeypatch.setattr(watchermod, "_filesystem_type", lambda _p: None)
    assert isinstance(watcher.select_observer("/mnt/f/0_Pipeline/In"), PollingObserver)
    assert not isinstance(watcher.select_observer("/home/user/0_Pipeline/In"), PollingObserver)


def test_get_known_domains_default(monkeypatch):
    """Without the env var, the default Titan domains are returned."""
    monkeypatch.delenv("VAULT_WATCHER_DOMAINS", raising=False)
    assert watcher.get_known_domains() == ["business", "lernen", "projekte", "system"]


def test_get_known_domains_env_override(monkeypatch):
    """The env var overrides and is split/trimmed; empty entries are dropped."""
    monkeypatch.setenv("VAULT_WATCHER_DOMAINS", " trading , lernen ,, system ")
    assert watcher.get_known_domains() == ["trading", "lernen", "system"]


def test_normalize_domain():
    """Domains are lowercased, space-free and stripped to a stable token."""
    assert watcher.normalize_domain("Trading") == "trading"
    assert watcher.normalize_domain("IT-Infrastruktur") == "it-infrastruktur"
    assert watcher.normalize_domain("Lucke Capital Services") == "lucke-capital-services"
    assert watcher.normalize_domain("Ernährung") == "ernährung"
    assert watcher.normalize_domain("   ") == "inbox"


def test_get_max_chars_default(monkeypatch):
    """Without the env var, the default prompt char limit is returned."""
    monkeypatch.delenv("VAULT_WATCHER_MAX_CHARS", raising=False)
    assert watcher.get_max_chars() == 200_000


def test_get_max_chars_env_override(monkeypatch):
    """A positive env value overrides; non-numeric or non-positive falls back."""
    monkeypatch.setenv("VAULT_WATCHER_MAX_CHARS", "5000")
    assert watcher.get_max_chars() == 5000
    monkeypatch.setenv("VAULT_WATCHER_MAX_CHARS", "not-a-number")
    assert watcher.get_max_chars() == 200_000
    monkeypatch.setenv("VAULT_WATCHER_MAX_CHARS", "0")
    assert watcher.get_max_chars() == 200_000


def test_process_file_truncates_and_warns(tmp_path, monkeypatch, caplog):
    """Over-long text is truncated to the limit and a warning is logged."""
    dirs = _mk_pipeline_dirs(tmp_path)
    txt_path = dirs["raw"] / "long.txt"
    txt_path.write_text("A" * 50, encoding="utf-8")
    monkeypatch.setenv("VAULT_WATCHER_MAX_CHARS", "10")

    seen: dict[str, str] = {}

    def capture_client(api_key: str | None = None) -> MagicMock:
        client = MagicMock()

        def generate_content(model: str, contents: Any, config: Any = None) -> MockResponse:
            seen["contents"] = str(contents)
            return MockResponse(
                json.dumps(
                    {
                        "titel": "T",
                        "domain": "system",
                        "tags": ["a"],
                        "summary": "s",
                        "questions": "q",
                        "action_items": ["x"],
                    }
                )
            )

        client.models.generate_content = generate_content
        return client

    monkeypatch.setattr("time.sleep", lambda _s: None)
    with (
        caplog.at_level(logging.WARNING),
        patch("obsidian_inbox_watcher.pipeline.load_api_key", return_value="key"),
        patch("google.genai.Client", side_effect=capture_client),
    ):
        watcher.process_file(
            str(txt_path),
            processed_dir=str(dirs["processed"]),
            archive_dir=str(dirs["archive"]),
            failed_dir=str(dirs["failed"]),
        )

    # The prompt body must carry at most the 10-char limit, not all 50 chars.
    body = seen["contents"].split("Textinhalt, der analysiert werden soll:")[-1]
    assert "A" * 10 in body
    assert "A" * 11 not in body
    assert any("Truncating extracted text" in r.message for r in caplog.records)


def test_unique_output_path_appends_version_suffix(tmp_path):
    """A clashing note name gets a _v2/_v3 suffix instead of overwriting."""
    directory = str(tmp_path)

    first = watcher.unique_output_path(directory, "2026-05-29_Note.md")
    assert first == os.path.join(directory, "2026-05-29_Note.md")

    # Once the file exists, the next call must not return the same path.
    Path(first).write_text("x", encoding="utf-8")
    second = watcher.unique_output_path(directory, "2026-05-29_Note.md")
    assert second == os.path.join(directory, "2026-05-29_Note_v2.md")

    Path(second).write_text("x", encoding="utf-8")
    third = watcher.unique_output_path(directory, "2026-05-29_Note.md")
    assert third == os.path.join(directory, "2026-05-29_Note_v3.md")


def _mk_pipeline_dirs(tmp_path: Path) -> dict[str, Path]:
    """Create raw/processed/archive/failed dirs and return them."""
    dirs = {name: tmp_path / name for name in ("raw", "processed", "archive", "failed")}
    for path in dirs.values():
        path.mkdir()
    return dirs


def test_process_file_retries_transient_then_succeeds(tmp_path, monkeypatch):
    """A transient Gemini failure is retried; the note is written once it succeeds."""
    dirs = _mk_pipeline_dirs(tmp_path)
    txt_path = dirs["raw"] / "note.txt"
    txt_path.write_text("Vorlesung AVL-Bäume und Komplexitätsklassen.", encoding="utf-8")

    attempts = {"n": 0}

    def flaky_client(api_key: str | None = None) -> MagicMock:
        client = MagicMock()

        def generate_content(model: str, contents: Any, config: Any = None) -> MockResponse:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise requests.exceptions.ConnectionError("transient blip")
            return MockResponse(
                json.dumps(
                    {
                        "titel": "Titel",
                        "domain": "lernen",
                        "tags": ["a"],
                        "summary": "s",
                        "questions": "q",
                        "action_items": ["x"],
                    }
                )
            )

        client.models.generate_content = generate_content
        return client

    # tenacity attaches the Retrying instance as .retry at decoration time.
    monkeypatch.setattr(watcher._generate_note_json.retry, "sleep", lambda _s: None)  # type: ignore[attr-defined]
    monkeypatch.setattr("time.sleep", lambda _s: None)
    with (
        patch("obsidian_inbox_watcher.pipeline.load_api_key", return_value="key"),
        patch("google.genai.Client", side_effect=flaky_client),
    ):
        watcher.process_file(
            str(txt_path),
            processed_dir=str(dirs["processed"]),
            archive_dir=str(dirs["archive"]),
            failed_dir=str(dirs["failed"]),
        )

    assert attempts["n"] == 3
    assert len(list(dirs["processed"].iterdir())) == 1
    assert list(dirs["failed"].iterdir()) == []
    assert any(f.name.startswith("note") for f in dirs["archive"].iterdir())


def test_process_file_dead_letters_permanent_failure(tmp_path, monkeypatch):
    """A non-transient Gemini error moves the raw file to the failed dir with a sidecar."""
    dirs = _mk_pipeline_dirs(tmp_path)
    txt_path = dirs["raw"] / "note.txt"
    txt_path.write_text("Irgendein Inhalt.", encoding="utf-8")

    def broken_client(api_key: str | None = None) -> MagicMock:
        client = MagicMock()

        def generate_content(model: str, contents: Any, config: Any = None) -> MockResponse:
            raise ValueError("permanent 400 bad request")

        client.models.generate_content = generate_content
        return client

    # tenacity attaches the Retrying instance as .retry at decoration time.
    monkeypatch.setattr(watcher._generate_note_json.retry, "sleep", lambda _s: None)  # type: ignore[attr-defined]
    monkeypatch.setattr("time.sleep", lambda _s: None)
    with (
        patch("obsidian_inbox_watcher.pipeline.load_api_key", return_value="key"),
        patch("google.genai.Client", side_effect=broken_client),
    ):
        watcher.process_file(
            str(txt_path),
            processed_dir=str(dirs["processed"]),
            archive_dir=str(dirs["archive"]),
            failed_dir=str(dirs["failed"]),
        )

    assert not txt_path.exists()
    assert (dirs["failed"] / "note.txt").exists()
    sidecar = (dirs["failed"] / "note.txt.error.txt").read_text(encoding="utf-8")
    assert "gemini_failed" in sidecar
    assert list(dirs["processed"].iterdir()) == []


def test_process_file_dead_letters_empty_text(tmp_path, monkeypatch):
    """A file with no extractable text is dead-lettered without calling Gemini."""
    dirs = _mk_pipeline_dirs(tmp_path)
    txt_path = dirs["raw"] / "empty.txt"
    txt_path.write_text("   \n\n", encoding="utf-8")

    monkeypatch.setattr("time.sleep", lambda _s: None)
    with patch("obsidian_inbox_watcher.pipeline.load_api_key", return_value="key"):
        watcher.process_file(
            str(txt_path),
            processed_dir=str(dirs["processed"]),
            archive_dir=str(dirs["archive"]),
            failed_dir=str(dirs["failed"]),
        )

    assert not txt_path.exists()
    assert (dirs["failed"] / "empty.txt").exists()
    sidecar = (dirs["failed"] / "empty.txt.error.txt").read_text(encoding="utf-8")
    assert "empty_text" in sidecar
    assert list(dirs["processed"].iterdir()) == []


def test_frontmatter_survives_hostile_title(tmp_path, monkeypatch):
    """Ein Titel mit ':' und '"' darf das YAML-Frontmatter nicht brechen (P1.5)."""
    import yaml

    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "out"
    archive_dir = tmp_path / "archive"
    failed_dir = tmp_path / "failed"
    for d in (raw_dir, processed_dir, archive_dir, failed_dir):
        d.mkdir()

    txt_path = raw_dir / "hostile.txt"
    txt_path.write_text("Beliebiger Inhalt.", encoding="utf-8")

    hostile = {
        "titel": 'Krise: "Alles kaputt" — Teil 2',
        "domain": "System Themen",
        "tags": ["a"],
        "summary": "Zusammenfassung mit: Doppelpunkt",
        "questions": "Frage?",
        "action_items": [],
    }
    monkeypatch.setattr(pipeline, "load_api_key", lambda: "dummy")
    monkeypatch.setattr(pipeline, "_generate_note_json", lambda key, prompt: json.dumps(hostile))

    watcher.process_file(
        str(txt_path),
        processed_dir=str(processed_dir),
        archive_dir=str(archive_dir),
        failed_dir=str(failed_dir),
    )

    notes = list(processed_dir.iterdir())
    assert len(notes) == 1, f"Note nicht erzeugt, failed_dir: {list(failed_dir.iterdir())}"
    content = notes[0].read_text(encoding="utf-8")

    # Frontmatter muss valides YAML sein und die Felder unbeschadet enthalten
    _, fm_block, _body = content.split("---", 2)
    meta = yaml.safe_load(fm_block)
    assert meta["domain"] == "system-themen"
    assert meta["ai_processed"] is True
    assert isinstance(meta["tags"], list) and len(meta["tags"]) == 5
