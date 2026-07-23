from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.startup import show_startup_error, write_startup_error


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-root", required=True)
    return parser.parse_args(argv)


def main() -> int:
    cache_root: Path | None = None
    try:
        args = parse_args()
        cache_root = Path(args.cache_root).resolve()
        from PySide6 import QtCore, QtGui, QtWidgets
        from app.ui.main_window import MainWindow

        app = QtWidgets.QApplication([sys.argv[0]])
        app.setApplicationName("数据堂质检工具")
        app.setOrganizationName("DataTang")
        app.setStyle("Fusion")
        app.setFont(QtGui.QFont("Microsoft YaHei UI", 10))

        # DataGuard administrator mode passes the selected QC workspace through
        # the process environment. Persist it before MainWindow restores last_root.
        direct_root = os.environ.get("DATATANG_QC_ROOT", "").strip()
        if direct_root and Path(direct_root).is_dir():
            settings = QtCore.QSettings("DataTang", "QualityControlTool")
            settings.setValue("last_root", str(Path(direct_root).resolve()))

        window = MainWindow(cache_root=cache_root)
        window.show()
        return app.exec()
    except BaseException as exc:
        log_root = (cache_root / "logs") if cache_root is not None else Path(__file__).resolve().parent
        log_path = write_startup_error(exc, root=log_root)
        show_startup_error(
            "质检工具启动失败。\n\n"
            f"错误日志：{log_path}\n\n"
            "请将 startup.log 和 startup_error.log 一并发送给开发人员。"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
