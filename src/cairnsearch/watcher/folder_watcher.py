"""Folder watcher with debouncing for file changes."""
import time
import threading
import fnmatch
import logging
from pathlib import Path
from typing import Callable, Optional
from collections import defaultdict

from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileDeletedEvent,
    FileMovedEvent,
)

from cairnsearch.config import get_config
from cairnsearch.extractors import get_registry


logger = logging.getLogger(__name__)


class DebouncedEventHandler(FileSystemEventHandler):
    """
    File system event handler with debouncing.
    
    Debouncing prevents multiple rapid events for the same file
    from triggering multiple index operations.
    """

    def __init__(
        self,
        on_created: Callable[[str], None],
        on_modified: Callable[[str], None],
        on_deleted: Callable[[str], None],
        debounce_ms: int = 500,
        ignore_patterns: Optional[list[str]] = None,
    ):
        super().__init__()
        self.on_created = on_created
        self.on_modified = on_modified
        self.on_deleted = on_deleted
        self.debounce_ms = debounce_ms
        self.ignore_patterns = ignore_patterns or []
        
        self._pending: dict[str, tuple[str, float]] = {}  # path -> (event_type, timestamp)
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        
        self.registry = get_registry()

    def _should_ignore(self, path: str) -> bool:
        """Check if path matches ignore patterns."""
        path_obj = Path(path)
        
        # Ignore directories
        if path_obj.is_dir():
            return True
        
        # Check ignore patterns
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(path_obj.name, pattern):
                return True
            # Check parent directories
            for parent in path_obj.parents:
                if fnmatch.fnmatch(parent.name, pattern):
                    return True
        
        # Check if file type is supported
        if not self.registry.can_extract(path_obj):
            return True
        
        return False

    def _schedule_flush(self) -> None:
        """Schedule a flush of pending events."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            
            self._timer = threading.Timer(
                self.debounce_ms / 1000.0,
                self._flush_pending
            )
            self._timer.daemon = True
            self._timer.start()

    def _flush_pending(self) -> None:
        """Process all pending events."""
        with self._lock:
            pending = dict(self._pending)
            self._pending.clear()
        
        for path, (event_type, _) in pending.items():
            try:
                if event_type == "created":
                    self.on_created(path)
                elif event_type == "modified":
                    self.on_modified(path)
                elif event_type == "deleted":
                    self.on_deleted(path)
            except Exception as e:
                logger.exception(f"Error handling {event_type} event for {path}: {e}")

    def _add_pending(self, path: str, event_type: str) -> None:
        """Add event to pending queue."""
        if self._should_ignore(path):
            return
        
        with self._lock:
            self._pending[path] = (event_type, time.time())
        
        self._schedule_flush()

    def on_created(self, event):
        if isinstance(event, FileCreatedEvent):
            logger.debug(f"File created: {event.src_path}")
            self._add_pending(event.src_path, "created")

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent):
            logger.debug(f"File modified: {event.src_path}")
            self._add_pending(event.src_path, "modified")

    def on_deleted(self, event):
        if isinstance(event, FileDeletedEvent):
            logger.debug(f"File deleted: {event.src_path}")
            self._add_pending(event.src_path, "deleted")

    def on_moved(self, event):
        if isinstance(event, FileMovedEvent):
            logger.debug(f"File moved: {event.src_path} -> {event.dest_path}")
            self._add_pending(event.src_path, "deleted")
            self._add_pending(event.dest_path, "created")


class FolderWatcher:
    """Watches folders for file changes and triggers indexing."""

    def __init__(
        self,
        on_created: Callable[[str], None],
        on_modified: Callable[[str], None],
        on_deleted: Callable[[str], None],
        folders: Optional[list[Path]] = None,
    ):
        config = get_config()
        
        self.folders = folders or config.get_watch_folders()
        self.observer = Observer()
        self.handler = DebouncedEventHandler(
            on_created=on_created,
            on_modified=on_modified,
            on_deleted=on_deleted,
            debounce_ms=config.watcher.debounce_ms,
            ignore_patterns=config.watcher.ignore_patterns,
        )
        self._started = False

    def start(self) -> None:
        """Start watching folders."""
        if self._started:
            return
        
        for folder in self.folders:
            if not folder.exists():
                logger.warning(f"Watch folder not found: {folder}")
                continue
            
            self.observer.schedule(self.handler, str(folder), recursive=True)
            logger.info(f"Watching folder: {folder}")
        
        self.observer.start()
        self._started = True
        logger.info("Folder watcher started")

    def stop(self) -> None:
        """Stop watching folders."""
        if not self._started:
            return
        
        self.observer.stop()
        self.observer.join()
        self._started = False
        logger.info("Folder watcher stopped")

    @property
    def is_running(self) -> bool:
        return self._started
