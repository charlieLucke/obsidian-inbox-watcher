"""Watchdog-Anbindung: Observer-Auswahl, Inbox-Handler, Sicherheits-Rescan."""

from __future__ import annotations

import logging
import os
import threading
import time

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.observers.polling import PollingObserver

from obsidian_inbox_watcher.extractors import SUPPORTED_EXTENSIONS
from obsidian_inbox_watcher.pipeline import process_file

logger = logging.getLogger(__name__)

# How often the safety-net rescan re-checks the raw dir for files whose
# filesystem event was missed (see _rescan_loop / InboxHandler.rescan).
_RESCAN_INTERVAL_SECONDS = 60.0

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
        if ext not in SUPPORTED_EXTENSIONS:
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


def _rescan_loop(handler: InboxHandler, raw_dir: str, stop_event: threading.Event) -> None:
    """Periodically rescan the raw dir until ``stop_event`` is set."""
    while not stop_event.wait(_RESCAN_INTERVAL_SECONDS):
        handler.rescan(raw_dir)
