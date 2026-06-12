"""Verarbeitungs-Pipeline: Rohdatei → Extraktion → Gemini → Obsidian-Note → Archiv."""

from __future__ import annotations

import datetime
import logging
import os
import shutil
import time

from pydantic import ValidationError

from obsidian_inbox_watcher.config import get_max_chars, load_api_key
from obsidian_inbox_watcher.extractors import SUPPORTED_EXTENSIONS, extract_text
from obsidian_inbox_watcher.note_builder import (
    GEMINI_MODEL,
    GeminiNote,
    _generate_note_json,
    build_prompt,
    normalize_domain,
    render_note,
    unique_output_path,
)

logger = logging.getLogger(__name__)


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


def _dead_letter(filepath: str, failed_dir: str, reason: str, detail: str) -> None:
    """Move an unprocessable raw file out of the inbox and write an error sidecar.

    The raw file goes to ``failed_dir`` (a timestamp suffix avoids clobbering an
    existing same-named file) with a ``<name>.error.txt`` sidecar holding the
    timestamp, reason and a short detail — never a full traceback (that goes to
    the journal via ``logger.exception``).
    """
    os.makedirs(failed_dir, exist_ok=True)
    base_name = os.path.basename(filepath)
    dest = os.path.join(failed_dir, base_name)
    if os.path.exists(dest):
        name_part, ext_part = os.path.splitext(base_name)
        timestamp = datetime.datetime.now().strftime("%H%M%S")
        dest = os.path.join(failed_dir, f"{name_part}_{timestamp}{ext_part}")
    shutil.move(filepath, dest)
    sidecar = f"{dest}.error.txt"
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with open(sidecar, "w", encoding="utf-8") as f:
        f.write(f"timestamp: {now}\nreason: {reason}\ndetail: {detail}\n")
    logger.warning("Dead-lettered %s -> %s (%s)", filepath, dest, reason)


def process_file(
    filepath: str,
    *,
    processed_dir: str | None = None,
    archive_dir: str | None = None,
    failed_dir: str | None = None,
) -> None:
    """Extract a file's content, process it via Gemini, and write an Obsidian note.

    On success the original is archived. Unprocessable inputs (extraction
    failure, exhausted transient retries, invalid JSON, empty text, unsupported
    format) are moved to ``failed_dir`` with an ``.error.txt`` sidecar so they
    leave the inbox instead of being retried on every restart. A missing API
    key is a config issue and leaves the file in place for a later run.

    Args:
        filepath: Path to the input file.
        processed_dir: Override for the output notes directory.
        archive_dir: Override for the archive directory.
        failed_dir: Override for the dead-letter directory.
    """
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

    if processed_dir is None:
        processed_dir = os.path.expanduser("~/0_Pipeline/Out")
    if archive_dir is None:
        archive_dir = os.path.expanduser("~/0_Pipeline/Archive")
    if failed_dir is None:
        failed_dir = os.path.expanduser("~/0_Pipeline/Failed")

    ext = os.path.splitext(filepath)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        logger.warning("Unsupported file format: %s", ext)
        _dead_letter(filepath, failed_dir, "unsupported_format", f"extension {ext or '(none)'}")
        return

    # A missing key is a configuration problem, not a poison file: leave the raw
    # file in the inbox so it is processed once the key is set.
    api_key = load_api_key()
    if not api_key:
        logger.error(
            "GEMINI_API_KEY is missing or set to placeholder. "
            "Please configure your API key in ~/.config/vault_watcher/env"
        )
        return

    try:
        try:
            text_content, source_origin = extract_text(filepath, ext)
        except Exception as e:
            logger.exception("Text extraction failed for %s", filepath)
            _dead_letter(filepath, failed_dir, "extraction_failed", f"{type(e).__name__}: {e}")
            return

        if not text_content.strip():
            logger.warning("Extracted text content is empty for: %s", filepath)
            _dead_letter(filepath, failed_dir, "empty_text", "no extractable text")
            return

        max_chars = get_max_chars()
        if len(text_content) > max_chars:
            logger.warning(
                "Truncating extracted text for %s from %d to %d chars",
                filepath,
                len(text_content),
                max_chars,
            )
            text_content = text_content[:max_chars]

        prompt = build_prompt(text_content)

        logger.info("Querying Gemini API (%s)...", GEMINI_MODEL)
        try:
            response_text = _generate_note_json(api_key, prompt)
        except Exception as e:
            logger.exception("Gemini API call failed for %s", filepath)
            _dead_letter(filepath, failed_dir, "gemini_failed", f"{type(e).__name__}: {e}")
            return

        # Parse + Validate Results (Pydantic: Parsing und Schema in einem)
        try:
            result = GeminiNote.model_validate_json(response_text)
        except ValidationError as e:
            logger.exception("Gemini returned invalid JSON/schema for %s", filepath)
            _dead_letter(filepath, failed_dir, "invalid_json", f"{type(e).__name__}: {e}")
            return
        domain = normalize_domain(result.domain)
        logger.info(
            "Gemini API returned valid response. Title: '%s', Domain: '%s'",
            result.titel,
            domain,
        )

        # Render + write markdown file
        created_date = datetime.datetime.now().strftime("%Y-%m-%d")
        filename, markdown_content = render_note(result, domain, source_origin, created_date)

        out_filepath = unique_output_path(processed_dir, filename)
        with open(out_filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        logger.info("Successfully processed and saved note to: %s", out_filepath)

        # Move original file to archive directory
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
        logger.exception("Unexpected error processing %s", filepath)
        if os.path.exists(filepath):
            _dead_letter(filepath, failed_dir, "unexpected_error", f"{type(e).__name__}: {e}")


def process_existing_files(
    raw_dir: str, processed_dir: str, archive_dir: str, failed_dir: str
) -> None:
    """Scan and process files that already exist in the raw directory."""
    logger.info("Scanning for existing un-processed raw files in %s...", raw_dir)
    try:
        entries = os.listdir(raw_dir)
    except OSError as e:
        logger.error("Error scanning existing files: %s", e)
        return
    for entry in entries:
        filepath = os.path.join(raw_dir, entry)
        if os.path.isdir(filepath):
            continue
        ext = os.path.splitext(entry)[1].lower()
        if ext in SUPPORTED_EXTENSIONS:
            logger.info("Found existing file at startup: %s", filepath)
            process_file(
                filepath,
                processed_dir=processed_dir,
                archive_dir=archive_dir,
                failed_dir=failed_dir,
            )
