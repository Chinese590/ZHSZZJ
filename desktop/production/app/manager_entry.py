"""One-click Windows manager launcher for the LAN distribution service."""
from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
import sys

try:
    from .distribution_server import serve
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from distribution_server import serve


def main() -> None:
    project = input("Project root path: ").strip().strip('"')
    if not project:
        return
    server = serve(Path(project), "0.0.0.0", 8765)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Manager started: http://127.0.0.1:8765/")
    print("Members can run ImageDistribution-Client.exe to connect automatically.")
    webbrowser.open("http://127.0.0.1:8765/")
    try:
        server.serve_forever()
    finally:
        server.shutdown(); server.server_close()


if __name__ == "__main__":
    main()
