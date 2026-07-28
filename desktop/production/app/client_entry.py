"""One-click Windows member launcher."""
from __future__ import annotations

import webbrowser

from .distribution_client import discover


def main() -> None:
    url = discover()
    if not url:
        print("Manager not found. Check the manager is running and UDP 8766 is allowed.")
        return
    webbrowser.open(url)
    print(f"Connected to manager: {url}")


if __name__ == "__main__":
    main()
