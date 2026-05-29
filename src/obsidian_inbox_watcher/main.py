"""Main module for obsidian_inbox_watcher."""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
from typing import Any

import docx
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.observers.polling import PollingObserver

# Configure Logging
logger = logging.getLogger(__name__)

# Input file extensions the watcher knows how to process.
_SUPPORTED_EXTENSIONS = (".txt", ".pdf", ".docx", ".url")

# How often the safety-net rescan re-checks the raw dir for files whose
# filesystem event was missed (see _rescan_loop / InboxHandler.rescan).
_RESCAN_INTERVAL_SECONDS = 60.0


def load_env_file(path: str = "~/.config/vault_watcher/env") -> None:
    """Populate os.environ from a simple KEY=VALUE config file.

    Existing environment variables are not overridden, so systemd's
    EnvironmentFile (or a real shell export) always wins over the file.
    """
    env_path = os.path.expanduser(path)
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
    except OSError as e:
        logger.error("Failed to read env file %s: %s", env_path, e)


def resolve_dir(env_var: str, default: str) -> str:
    """Resolve a directory from an env var, falling back to a default (expands ~)."""
    return os.path.expanduser(os.environ.get(env_var) or default)


# Filesystems where inotify is unreliable or unsupported, so watchdog must poll:
# the WSL Windows-drive mount (drvfs/9p) and network shares.
_POLLING_FS_TYPES = frozenset({"drvfs", "9p", "cifs", "smbfs", "nfs", "nfs4", "fuse.sshfs"})


def _filesystem_type(path: str) -> str | None:
    """Return the filesystem type backing ``path`` via /proc/mounts (Linux only).

    Matches the longest mount point that is a prefix of ``path``. Returns None
    when the type cannot be determined (e.g. /proc/mounts unreadable).
    """
    abs_path = os.path.abspath(path)
    best_mount = ""
    best_fstype: str | None = None
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mount_point, fstype = parts[1], parts[2]
                is_prefix = abs_path == mount_point or abs_path.startswith(
                    mount_point.rstrip("/") + "/"
                )
                if is_prefix and len(mount_point) >= len(best_mount):
                    best_mount = mount_point
                    best_fstype = fstype
    except OSError:
        return None
    return best_fstype


def select_observer(watch_dir: str) -> BaseObserver:
    """Pick a watchdog observer based on the watched directory's filesystem.

    inotify is not delivered on the WSL Windows-drive mount (drvfs/9p) and is
    unreliable on network shares, so those use the polling observer; native
    local filesystems (ext4, etc.) use inotify. Falls back to the legacy
    ``/mnt/`` path heuristic when the filesystem type cannot be read.
    """
    fstype = _filesystem_type(watch_dir)
    if fstype is None:
        return PollingObserver() if watch_dir.startswith("/mnt/") else Observer()
    if fstype in _POLLING_FS_TYPES:
        return PollingObserver()
    return Observer()


# Existing Titan domains to steer classification toward a consistent graph.
# Gemini may still invent a new domain when none of these fit.
_DEFAULT_DOMAINS = ("business", "lernen", "projekte", "system")


def get_known_domains() -> list[str]:
    """Return the seed list of Titan domains (comma-separated env override)."""
    raw = os.environ.get("VAULT_WATCHER_DOMAINS", "")
    domains = [d.strip() for d in raw.split(",") if d.strip()]
    return domains or list(_DEFAULT_DOMAINS)


def normalize_domain(value: str) -> str:
    """Normalize a domain to a lowercase, space-free token for stable filtering.

    Titan matches the ``domain`` payload exactly in Qdrant, so casing and
    whitespace must be canonical. German umlauts are preserved.
    """
    slug = re.sub(r"\s+", "-", value.strip().lower())
    slug = re.sub(r"[^0-9a-zäöüß_-]", "", slug)
    return slug.strip("-") or "inbox"


# Maximum characters of extracted text sent to Gemini. Longer inputs are
# truncated: the prompt budget is finite and the most relevant signal in a
# captured document is almost always near the top.
_DEFAULT_MAX_CHARS = 200_000


def get_max_chars() -> int:
    """Return the prompt char limit (``VAULT_WATCHER_MAX_CHARS``, positive int)."""
    raw = os.environ.get("VAULT_WATCHER_MAX_CHARS", "")
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_CHARS
    return value if value > 0 else _DEFAULT_MAX_CHARS


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


def _is_transient(exc: BaseException) -> bool:
    """Return True for errors worth retrying (network blips, 429, HTTP 5xx)."""
    if isinstance(exc, requests.exceptions.Timeout | requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        resp = exc.response
        return resp is not None and (resp.status_code == 429 or 500 <= resp.status_code < 600)
    from google.genai import errors as genai_errors

    if isinstance(exc, genai_errors.APIError):
        code = exc.code
        return code == 429 or 500 <= code < 600
    return False


# Bounded exponential backoff for transient remote failures; permanent errors
# (bad JSON, empty text, programming errors) fall through immediately.
_retryable = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, max=30),
    retry=retry_if_exception(_is_transient),
    reraise=True,
)


@_retryable
def _http_get(url: str, headers: dict[str, str]) -> requests.Response:
    """GET a URL, retrying transient failures and raising on HTTP error status."""
    res = requests.get(url, headers=headers, timeout=15)
    res.raise_for_status()
    return res


@_retryable
def _generate_note_json(api_key: str, prompt: str) -> str:
    """Call Gemini and return the raw JSON text, retrying transient failures."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    if not response.text:
        raise ValueError("Empty response from Gemini API")
    return str(response.text)


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


def _extract_text(filepath: str, ext: str) -> tuple[str, str]:
    """Extract text from a supported input file.

    Returns a ``(text_content, source_origin)`` tuple. ``source_origin`` is the
    file path for local files and the crawled URL for ``.url`` shortcuts. Raises
    on extraction failure (the caller dead-letters the file).
    """
    if ext == ".txt":
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            return f.read(), filepath
    if ext == ".pdf":
        reader = PdfReader(filepath)
        text_list = [t for page in reader.pages if (t := page.extract_text())]
        return "\n".join(text_list), filepath
    if ext == ".docx":
        document = docx.Document(filepath)
        return "\n".join(p.text for p in document.paragraphs), filepath
    if ext == ".url":
        url = None
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip().startswith("URL="):
                    url = line.split("URL=", 1)[1].strip()
                    break
        if not url:
            raise ValueError(f"No URL found in .url file: {filepath}")
        logger.info("Extracted URL from shortcut: %s. Fetching page text...", url)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        res = _http_get(url, headers)
        soup = BeautifulSoup(res.text, "html.parser")
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()
        raw_text = soup.get_text(separator="\n")
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        return "\n".join(lines), url
    raise ValueError(f"Unsupported file format: {ext}")


def unique_output_path(directory: str, filename: str) -> str:
    """Return a path in ``directory`` for ``filename`` that does not yet exist.

    Two different inputs can yield the same title — and therefore the same note
    name — on the same day. Rather than silently overwrite an existing note,
    append ``_v2``, ``_v3``, ... before the extension until the path is free.
    """
    candidate = os.path.join(directory, filename)
    if not os.path.exists(candidate):
        return candidate
    stem, ext = os.path.splitext(filename)
    version = 2
    while True:
        candidate = os.path.join(directory, f"{stem}_v{version}{ext}")
        if not os.path.exists(candidate):
            return candidate
        version += 1


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
    if ext not in _SUPPORTED_EXTENSIONS:
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
            text_content, source_origin = _extract_text(filepath, ext)
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

        # LLM process prompt
        known_domains = get_known_domains()
        domains_block = "\n".join(f"- {d}" for d in known_domains)
        prompt = f"""
Du bist ein hochpräziser Informations-Analysator für ein "Personal Corporate Memory"
System. Die erzeugten Notizen werden anschließend von der RAG-Engine "Titan"
indexiert; das Feld "domain" steuert die Einordnung im Wissensgraph.

Ordne den Inhalt EINER Domain zu. Bevorzuge eine bereits existierende Domain,
damit der Graph konsistent bleibt:
{domains_block}

Wenn keine davon inhaltlich passt, darfst du eine NEUE, treffende Domain vergeben.
Regeln für "domain": ein einzelnes, kleingeschriebenes deutsches Wort ohne
Leerzeichen (Bindestrich erlaubt), z.B. "trading" oder "infrastruktur".

Du MUSST das Ergebnis als ein valides JSON-Objekt im folgenden Format zurückgeben.

JSON-Struktur:
{{
  "titel": "Ein kurzer, prägnanter und aussagekräftiger deutscher Titel",
  "domain": "eine der obigen Domains oder eine neue, passende Domain",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "summary": "Eine prägnante Zusammenfassung des Inhalts in deutscher Sprache.",
  "questions": "Relevante Wissenslücken oder Fragen an den Benutzer (Fragen an mich).",
  "action_items": ["Action Item 1", "Action Item 2"]
}}

Textinhalt, der analysiert werden soll:
{text_content}
"""

        logger.info("Querying Gemini API (gemini-2.5-flash)...")
        try:
            response_text = _generate_note_json(api_key, prompt)
        except Exception as e:
            logger.exception("Gemini API call failed for %s", filepath)
            _dead_letter(filepath, failed_dir, "gemini_failed", f"{type(e).__name__}: {e}")
            return

        # Step 4: Parse Results
        try:
            result: dict[str, Any] = json.loads(response_text)
        except Exception as e:
            logger.exception("Gemini returned invalid JSON for %s", filepath)
            _dead_letter(filepath, failed_dir, "invalid_json", f"{type(e).__name__}: {e}")
            return
        domain = normalize_domain(str(result.get("domain") or ""))
        logger.info(
            "Gemini API returned valid response. Title: '%s', Domain: '%s'",
            result.get("titel"),
            domain,
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
domain: {domain}
created: {created_date}
source: {source_origin}
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

        out_filepath = unique_output_path(processed_dir, filename)

        with open(out_filepath, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        logger.info("Successfully processed and saved note to: %s", out_filepath)

        # Step 6: Move original file to archive directory
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


class InboxHandler(FileSystemEventHandler):  # type: ignore[misc]
    """Event handler for monitoring files in raw inbox."""

    def __init__(self, processed_dir: str, archive_dir: str, failed_dir: str) -> None:
        super().__init__()
        self._processed_dir = processed_dir
        self._archive_dir = os.path.abspath(archive_dir)
        self._failed_dir = failed_dir
        # Paths currently being processed, guarding against the same file being
        # picked up twice when an event and the safety-net rescan race.
        self._inflight: set[str] = set()
        self._inflight_lock = threading.Lock()

    def _maybe_process(self, raw_path: str) -> None:
        """Process ``raw_path`` if it is a supported, not-already-in-flight input."""
        abs_path = os.path.abspath(raw_path)

        # Never reprocess files that live in the archive directory.
        if abs_path.startswith(self._archive_dir + os.sep):
            return

        ext = os.path.splitext(abs_path)[1].lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            return

        with self._inflight_lock:
            if abs_path in self._inflight:
                return
            self._inflight.add(abs_path)
        try:
            logger.info("New incoming file detected: %s", abs_path)
            # Small initial sleep to let file creation settle
            time.sleep(0.5)
            process_file(
                abs_path,
                processed_dir=self._processed_dir,
                archive_dir=self._archive_dir,
                failed_dir=self._failed_dir,
            )
        finally:
            with self._inflight_lock:
                self._inflight.discard(abs_path)

    def on_created(self, event: FileSystemEvent) -> None:
        """Triggered when a file is created in the watched directory."""
        if event.is_directory:
            return
        src_path = event.src_path
        if isinstance(src_path, bytes):
            src_path = src_path.decode("utf-8")
        self._maybe_process(src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Triggered when a file is renamed into the watched directory.

        Syncthing (and the Telegram capture service) deliver files by writing a
        temp file and renaming it into place, which fires ``on_moved`` rather
        than ``on_created`` on native inotify.
        """
        if event.is_directory:
            return
        dest_path = event.dest_path
        if isinstance(dest_path, bytes):
            dest_path = dest_path.decode("utf-8")
        self._maybe_process(dest_path)

    def rescan(self, raw_dir: str) -> None:
        """Re-dispatch any files still sitting in the raw dir.

        A safety net: if a filesystem event is ever missed, the file would
        otherwise be stranded until the next service restart. The in-flight
        guard makes this safe to run concurrently with live events.
        """
        try:
            entries = os.listdir(raw_dir)
        except OSError as e:
            logger.error("Rescan could not list %s: %s", raw_dir, e)
            return
        for entry in entries:
            path = os.path.join(raw_dir, entry)
            if not os.path.isdir(path):
                self._maybe_process(path)


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
        if ext in _SUPPORTED_EXTENSIONS:
            logger.info("Found existing file at startup: %s", filepath)
            process_file(
                filepath,
                processed_dir=processed_dir,
                archive_dir=archive_dir,
                failed_dir=failed_dir,
            )


def _rescan_loop(handler: InboxHandler, raw_dir: str, stop_event: threading.Event) -> None:
    """Periodically rescan the raw dir until ``stop_event`` is set."""
    while not stop_event.wait(_RESCAN_INTERVAL_SECONDS):
        handler.rescan(raw_dir)


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
