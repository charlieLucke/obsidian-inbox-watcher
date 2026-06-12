"""Service-Einstieg + Re-Exports der Public Surface.

Die Implementierung lebt seit dem Review-P1.4-Split in config, extractors,
note_builder, pipeline und watcher; main bleibt der systemd-Entry-Point und
re-exportiert die bisherigen Namen für Aufrufer und Tests. Wer Verhalten
patcht, patcht die definierenden Module (z.B. pipeline.load_api_key), nicht
diese Re-Exports.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

from obsidian_inbox_watcher.config import (
    get_known_domains,
    get_max_chars,
    load_api_key,
    load_env_file,
    resolve_dir,
)
from obsidian_inbox_watcher.extractors import SUPPORTED_EXTENSIONS, extract_text
from obsidian_inbox_watcher.note_builder import (
    GeminiNote,
    _generate_note_json,
    build_prompt,
    normalize_domain,
    render_note,
    unique_output_path,
)
from obsidian_inbox_watcher.pipeline import (
    process_existing_files,
    process_file,
    wait_for_file_to_be_written,
)
from obsidian_inbox_watcher.watcher import InboxHandler, _rescan_loop, select_observer

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "GeminiNote",
    "InboxHandler",
    "_generate_note_json",
    "build_prompt",
    "extract_text",
    "get_known_domains",
    "get_max_chars",
    "load_api_key",
    "load_env_file",
    "main",
    "normalize_domain",
    "process_existing_files",
    "process_file",
    "render_note",
    "resolve_dir",
    "select_observer",
    "unique_output_path",
    "wait_for_file_to_be_written",
]

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the main watcher service loop."""
    # Configure root logger to output to stdout for systemd capture
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Load the config file so dir overrides + the API key are available whether
    # we run under systemd (EnvironmentFile) or directly.
    load_env_file()

    raw_dir = resolve_dir("VAULT_WATCHER_RAW_DIR", "~/0_Pipeline/In")
    processed_dir = resolve_dir("VAULT_WATCHER_PROCESSED_DIR", "~/0_Pipeline/Out")
    archive_dir = resolve_dir("VAULT_WATCHER_ARCHIVE_DIR", "~/0_Pipeline/Archive")
    failed_dir = resolve_dir("VAULT_WATCHER_FAILED_DIR", "~/0_Pipeline/Failed")
    config_dir = os.path.expanduser("~/.config/vault_watcher")

    # Ensure all required directories exist (safe on first run / new PC)
    for directory in [raw_dir, processed_dir, archive_dir, failed_dir, config_dir]:
        os.makedirs(directory, exist_ok=True)

    logger.info("Starting Obsidian Inbox Watcher service.")
    logger.info("Monitoring %s  ->  notes: %s", raw_dir, processed_dir)

    # Process existing files first (for robustness on reboot)
    process_existing_files(raw_dir, processed_dir, archive_dir, failed_dir)

    # Set up watchdog observer (polling on /mnt drive mounts; inotify elsewhere)
    event_handler = InboxHandler(processed_dir, archive_dir, failed_dir)
    observer = select_observer(raw_dir)
    observer.schedule(event_handler, path=raw_dir, recursive=False)
    observer.start()

    # Safety-net rescan: a missed filesystem event must never strand a file.
    stop_event = threading.Event()
    rescan_thread = threading.Thread(
        target=_rescan_loop,
        args=(event_handler, raw_dir, stop_event),
        name="inbox-rescan",
        daemon=True,
    )
    rescan_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        stop_event.set()
    observer.join()
    logger.info("Service stopped cleanly.")


if __name__ == "__main__":
    main()
