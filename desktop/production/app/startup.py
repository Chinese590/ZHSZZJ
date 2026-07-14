from __future__ import annotations

import ctypes
import datetime as _dt
import os
import traceback
from pathlib import Path


def write_startup_error(exc: BaseException, root: Path | str | None = None) -> Path:
    base = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    base.mkdir(parents=True, exist_ok=True)
    path = base / "startup_error.log"
    content = (
        f"Time: {_dt.datetime.now().isoformat(timespec='seconds')}\n"
        f"Working directory: {Path.cwd()}\n"
        f"Exception: {type(exc).__name__}: {exc}\n\n"
        + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    )
    path.write_text(content, encoding="utf-8")
    return path


def show_startup_error(message: str) -> None:
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(0, message, "DataTang QC Tool", 0x10)
            return
        except Exception:
            pass
    print(message)
