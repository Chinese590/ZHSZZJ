"""One-click Windows member launcher."""
from __future__ import annotations

import webbrowser
import sys
from pathlib import Path
import ctypes

try:
    from .distribution_client import discover
except ImportError:
    try:
        from app.distribution_client import discover
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from distribution_client import discover


def main() -> None:
    url = discover()
    if not url:
        message = "未找到管理端。请确认管理员端已启动，并允许 UDP 8766。"
        print(message)
        ctypes.windll.user32.MessageBoxW(0, message, "图片分发客户端", 0x10)
        return
    webbrowser.open(url)
    print(f"Connected to manager: {url}")
    ctypes.windll.user32.MessageBoxW(0, f"已连接管理端：{url}", "图片分发客户端", 0x40)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(0, str(exc), "图片分发客户端启动错误", 0x10)
