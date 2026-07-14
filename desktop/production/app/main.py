from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
        from PySide6 import QtGui, QtWidgets
        from app.ui.main_window import MainWindow

        app = QtWidgets.QApplication([sys.argv[0]])
        app.setApplicationName("数据堂质检工具")
        app.setOrganizationName("DataTang")
        app.setStyle("Fusion")
        app.setFont(QtGui.QFont("Microsoft YaHei UI", 10))
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
