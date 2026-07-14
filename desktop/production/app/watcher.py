from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


class _ChangeHandler(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def on_any_event(self, event: FileSystemEvent) -> None:
        # Ignore the tool's own append-only log to prevent unnecessary refreshes.
        path = str(getattr(event, "src_path", ""))
        if ".质检工具" in path:
            return
        self.callback()


class DirectoryWatcher(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None):
        super().__init__(parent)
        self._observer: Observer | None = None

    def start(self, root: Path | str) -> None:
        self.stop()
        root_path = Path(root)
        if not root_path.is_dir():
            return
        handler = _ChangeHandler(self.changed.emit)
        observer = Observer()
        observer.schedule(handler, str(root_path), recursive=True)
        observer.daemon = True
        observer.start()
        self._observer = observer

    def stop(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()
        self._observer.join(timeout=2)
        self._observer = None
