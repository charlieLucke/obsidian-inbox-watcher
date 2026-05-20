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
                "category": "Informatik-Studium",
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
                "category": "Trading",
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
                "category": "IT-Infrastruktur",
                "tags": ["Infrastruktur", "Systeme", "Netzwerk", "Automatisierung", "Linux"],
                "summary": "Ein allgemeines Dokument zur IT-Infrastruktur und Automatisierung.",
                "questions": "Welche Skalierungsanforderungen gibt es für dieses System?",
                "action_items": ["Konfiguration überprüfen"],
            }

        return MockResponse(json.dumps(mock_json))

    mock_client.models.generate_content = generate_content
    return mock_client


def test_watcher_pipeline() -> None:
    """Verify end-to-end file parsing, API prompting, markdown output formatting, and archiving."""
    # Paths
    raw_dir = os.path.expanduser("~/Vault/00_Inbox/Raw")
    processed_dir = os.path.expanduser("~/Vault/00_Inbox/Processed")
    archive_dir = os.path.expanduser("~/Vault/00_Inbox/Raw/Archive")

    # Ensure folders exist
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)

    # 1. Clean up test files if they exist
    for d in [raw_dir, processed_dir, archive_dir]:
        if os.path.exists(d):
            for filename in os.listdir(d):
                fp = os.path.join(d, filename)
                if os.path.isfile(fp):
                    os.remove(fp)

    # 2. Create test files
    # Test file 1: Text file (Informatik-Studium)
    txt_path = os.path.join(raw_dir, "studium_notiz.txt")
    with open(txt_path, "w", encoding="utf-8") as file_h:
        file_h.write("Vorlesung Datenstrukturen und Algorithmen:\n")
        file_h.write("Heute besprechen wir binäre Suchbäume, AVL-Bäume und Komplexitätsklassen.\n")
        file_h.write(
            "Wir müssen ein Übungsblatt 4 lösen bis nächsten Montag und Skript Kapitel 5 lesen.\n"
        )

    # Test file 2: URL file (Trading/Börse)
    url_path = os.path.join(raw_dir, "trading_boerse.url")
    with open(url_path, "w", encoding="utf-8") as file_h:
        file_h.write("[InternetShortcut]\n")
        file_h.write("URL=https://de.wikipedia.org/wiki/B%C3%B6rse\n")

    # 3. Process files (using Mock)
    with (
        patch("obsidian_inbox_watcher.main.load_api_key", return_value="dummy-key-for-testing"),
        patch("google.genai.Client", side_effect=get_mock_gemini_client),
    ):
        watcher.process_file(txt_path)
        watcher.process_file(url_path)

    # 4. Verification
    processed_files = os.listdir(processed_dir)
    assert len(processed_files) == 2, f"Expected 2 processed notes, found {len(processed_files)}"

    for pf in processed_files:
        pfp = os.path.join(processed_dir, pf)
        with open(pfp, encoding="utf-8") as file_h:
            content = file_h.read()

        # Verify markdown template structure and frontmatter
        assert "created:" in content, "Frontmatter 'created' is missing"
        assert "source:" in content, "Frontmatter 'source' is missing"
        assert "category:" in content, "Frontmatter 'category' is missing"
        assert "tags:" in content, "Frontmatter 'tags' is missing"
        assert "ai_processed: true" in content, "Frontmatter 'ai_processed' is missing"
        assert "## Zusammenfassung" in content, "Heading '## Zusammenfassung' is missing"
        assert "## Wissenslücken / Fragen an mich" in content, (
            "Heading '## Wissenslücken / Fragen an mich' is missing"
        )
        assert "## Action Items" in content, "Heading '## Action Items' is missing"
        assert "- [ ]" in content, "Action items format incorrect"

    # Verify Archive folder
    archived_files = os.listdir(archive_dir)
    assert any(f.startswith("studium_notiz") for f in archived_files), (
        "studium_notiz.txt was not archived"
    )
    assert any(f.startswith("trading_boerse") for f in archived_files), (
        "trading_boerse.url was not archived"
    )
