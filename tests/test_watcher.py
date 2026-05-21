"""Automated test suite for obsidian_inbox_watcher."""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from unittest.mock import MagicMock, patch

from obsidian_inbox_watcher import main as watcher

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
            "obsidian_inbox_watcher.main.load_api_key",
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

    def fake_process(filepath, *, processed_dir=None, archive_dir=None):
        calls["filepath"] = filepath
        calls["processed_dir"] = processed_dir
        calls["archive_dir"] = archive_dir

    monkeypatch.setattr(watcher, "process_file", fake_process)
    monkeypatch.setattr("obsidian_inbox_watcher.main.time.sleep", lambda _s: None)

    handler = watcher.InboxHandler("/out", "/arch")
    handler.on_created(FileCreatedEvent("/raw/note.txt"))

    assert calls["filepath"] == "/raw/note.txt"
    assert calls["processed_dir"] == "/out"
    assert calls["archive_dir"] == os.path.abspath("/arch")


def test_select_observer_polling_for_mnt():
    """Windows drive mounts (/mnt/...) need the polling observer; native otherwise."""
    from watchdog.observers.polling import PollingObserver

    assert isinstance(watcher.select_observer("/mnt/f/0_Pipeline/In"), PollingObserver)
    assert not isinstance(watcher.select_observer("/home/charl/0_Pipeline/In"), PollingObserver)


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
