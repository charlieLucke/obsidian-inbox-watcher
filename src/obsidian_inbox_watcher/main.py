"""Main module for obsidian_inbox_watcher."""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import shutil
import sys
import time
from typing import Any

import docx
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

# Configure Logging
logger = logging.getLogger(__name__)


def load_api_key() -> str | None:
    """Load the Gemini API key from environment or config file."""
    # 1. Try environment
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key and api_key != "YOUR_GEMINI_API_KEY_HERE":
        return api_key
    # 2. Try configuration env file
    env_path = os.path.expanduser("~/.config/vault_watcher/env")
    if os.path.exists(env_path):
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("GEMINI_API_KEY=", 1)[1].strip()
                        if val and val != "YOUR_GEMINI_API_KEY_HERE":
                            return val
        except Exception as e:
            logger.error("Failed to read env file: %s", e)
    return None


def wait_for_file_to_be_written(
    filepath: str, check_interval: float = 0.5, timeout: float = 10.0
) -> bool:
    """Wait until the file size is stable (fully written)."""
    last_size = -1
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            if not os.path.exists(filepath):
                return False
            current_size = os.path.getsize(filepath)
            if current_size == last_size and current_size > 0:
                return True
            last_size = current_size
        except OSError:
            pass
        time.sleep(check_interval)
    return False


def process_file(
    filepath: str,
    *,
    processed_dir: str | None = None,
    archive_dir: str | None = None,
) -> None:
    """Extract content from file, process via Gemini, and generate Obsidian markdown note.

    Args:
        filepath: Path to the input file.
        processed_dir: Override for the output notes directory.
        archive_dir: Override for the archive directory.
    """
    # Ensure filepath is absolute
    filepath = os.path.abspath(filepath)
    if not os.path.exists(filepath):
        logger.warning("File not found: %s", filepath)
        return

    # Wait for file to finish writing
    if not wait_for_file_to_be_written(filepath):
        logger.warning(
            "File %s was not stable after timeout, attempting to process anyway.", filepath
        )

    logger.info("Starting processing for: %s", filepath)

    ext = os.path.splitext(filepath)[1].lower()
    text_content = ""
    source_origin = filepath

    try:
        # Step 1: Content Extraction
        if ext == ".txt":
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                text_content = f.read()
        elif ext == ".pdf":
            reader = PdfReader(filepath)
            text_list = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text_list.append(t)
            text_content = "\n".join(text_list)
        elif ext == ".docx":
            doc = docx.Document(filepath)
            text_content = "\n".join([p.text for p in doc.paragraphs])
        elif ext == ".url":
            url = None
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().startswith("URL="):
                        url = line.split("URL=", 1)[1].strip()
                        break
            if not url:
                logger.error("No URL found in .url file: %s", filepath)
                return

            source_origin = url
            logger.info("Extracted URL from shortcut: %s. Fetching page text...", url)

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            }
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()

            soup = BeautifulSoup(res.text, "html.parser")
            for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
                element.decompose()

            raw_text = soup.get_text(separator="\n")
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            text_content = "\n".join(lines)
        else:
            logger.warning("Unsupported file format: %s", ext)
            return

        if not text_content.strip():
            logger.warning("Extracted text content is empty for: %s", filepath)
            return

        # Step 2: Load API Key & Configure Gemini client
        api_key = load_api_key()
        if not api_key:
            logger.error(
                "GEMINI_API_KEY is missing or set to placeholder. "
                "Please configure your API key in ~/.config/vault_watcher/env"
            )
            return

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        # Step 3: LLM Process Prompt
        prompt = f"""
Du bist ein hochpräziser Informations-Analysator für ein "Personal Corporate Memory" System.
Deine Aufgabe ist es, den folgenden Textinhalt kritisch zu analysieren,
Relevanzprüfungen vorzunehmen und strukturiert aufzubereiten.

Zielkategorien für Projekte (Wähle zwingend eine dieser vier aus):
- Trading
- Informatik-Studium
- Lucke Capital Services
- IT-Infrastruktur

Du MUSST das Ergebnis als ein valides JSON-Objekt im folgenden Format zurückgeben.

JSON-Struktur:
{{
  "titel": "Ein kurzer, prägnanter und aussagekräftiger deutscher Titel",
  "category": "Trading oder Informatik-Studium oder Lucke Capital Services oder IT-Infrastruktur",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "summary": "Eine prägnante Zusammenfassung des Inhalts in deutscher Sprache.",
  "questions": "Relevante Wissenslücken oder Fragen an den Benutzer (Fragen an mich).",
  "action_items": ["Action Item 1", "Action Item 2"]
}}

Textinhalt, der analysiert werden soll:
---
{text_content[:20000]}
---
"""

        logger.info("Querying Gemini API (gemini-2.5-flash)...")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

        # Step 4: Parse Results
        if not response.text:
            logger.error("Empty response from Gemini API")
            return

        result: dict[str, Any] = json.loads(response.text)
        logger.info(
            "Gemini API returned valid response. Title: '%s', Category: '%s'",
            result.get("titel"),
            result.get("category"),
        )

        # Format tags to make sure we have exactly 5 elements
        tags_list: list[str] = result.get("tags", [])
        if not isinstance(tags_list, list):
            tags_list = []
        if len(tags_list) < 5:
            tags_list += ["Knowledge", "System", "Archive", "Inbox", "Automated"]
        tags_list = tags_list[:5]
        tags_str = ", ".join(f'"{t}"' for t in tags_list)

        # Format action items
        action_items: list[str] = result.get("action_items", [])
        if not isinstance(action_items, list) or not action_items:
            action_items = ["Keine direkten Action Items identifiziert"]
        action_items_str = "\n".join(f"- [ ] {item}" for item in action_items)

        # Format YAML metadata and document structure
        created_date = datetime.datetime.now().strftime("%Y-%m-%d")
        markdown_content = f"""---
created: {created_date}
source: {source_origin}
category: {result.get("category", "Sonstiges")}
tags: [{tags_str}]
ai_processed: true
---
# {result.get("titel", "Unbenannt")}

## Zusammenfassung
{result.get("summary", "Keine Zusammenfassung verfügbar.")}

## Wissenslücken / Fragen an mich
> [!IMPORTANT]
> {result.get("questions", "Keine Fragen identifiziert.")}

## Action Items
{action_items_str}
"""

        # Step 5: Write markdown file
        title = result.get("titel", "Unbenannt")
        safe_title = re.sub(r'[\/*?:"<>|]', "", title)
        safe_title = re.sub(r"\s+", "_", safe_title)
        filename = f"{created_date}_{safe_title}.md"

        if processed_dir is None:
            processed_dir = os.path.expanduser("~/Vault/00_Inbox/Processed")
        out_filepath = os.path.join(processed_dir, filename)

        with open(out_filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        logger.info("Successfully processed and saved note to: %s", out_filepath)

        # Step 6: Move original file to archive directory
        if archive_dir is None:
            archive_dir = os.path.expanduser("~/Vault/00_Inbox/Raw/Archive")
        base_name = os.path.basename(filepath)
        archive_filepath = os.path.join(archive_dir, base_name)

        # If the file already exists in archive, add a timestamp suffix to avoid overwriting
        if os.path.exists(archive_filepath):
            name_part, ext_part = os.path.splitext(base_name)
            timestamp = datetime.datetime.now().strftime("%H%M%S")
            archive_filepath = os.path.join(archive_dir, f"{name_part}_{timestamp}{ext_part}")

        shutil.move(filepath, archive_filepath)
        logger.info("Successfully archived raw source to: %s", archive_filepath)

    except Exception as e:
        logger.exception("Error processing file %s: %s", filepath, e)


class InboxHandler(FileSystemEventHandler):  # type: ignore[misc]
    """Event handler for monitoring files in raw inbox."""

    def on_created(self, event: FileSystemEvent) -> None:
        """Triggered when a file is created."""
        if event.is_directory:
            return

        filepath = event.src_path
        if isinstance(filepath, bytes):
            filepath = filepath.decode("utf-8")

        # Avoid processing any file inside Archive subfolder
        if "Raw/Archive" in filepath:
            return

        ext = os.path.splitext(filepath)[1].lower()
        if ext in [".pdf", ".txt", ".docx", ".url"]:
            logger.info("New incoming file detected: %s", filepath)
            # Small initial sleep to let file creation settle
            time.sleep(0.5)
            process_file(filepath)


def process_existing_files(raw_dir: str) -> None:
    """Scan and process files that already exist in the raw directory."""
    logger.info("Scanning for existing un-processed raw files in %s...", raw_dir)
    try:
        for entry in os.listdir(raw_dir):
            filepath = os.path.join(raw_dir, entry)
            if os.path.isdir(filepath):
                continue
            ext = os.path.splitext(entry)[1].lower()
            if ext in [".pdf", ".txt", ".docx", ".url"]:
                logger.info("Found existing file at startup: %s", filepath)
                process_file(filepath)
    except Exception as e:
        logger.error("Error scanning existing files: %s", e)


def main() -> None:
    """Run the main watcher service loop."""
    # Configure root logger to output to stdout for systemd capture
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    raw_dir = os.path.expanduser("~/Vault/00_Inbox/Raw")
    logger.info("Starting Obsidian Inbox Watcher service.")
    logger.info("Monitoring folder: %s", raw_dir)

    # Process existing files first (for robustness on reboot)
    process_existing_files(raw_dir)

    # Set up watchdog observer
    event_handler = InboxHandler()
    observer = Observer()
    observer.schedule(event_handler, path=raw_dir, recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    logger.info("Service stopped cleanly.")


if __name__ == "__main__":
    main()
