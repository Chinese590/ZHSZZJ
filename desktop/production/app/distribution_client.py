"""Zero-configuration LAN client for the image distribution web workspace."""
from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sys
import webbrowser


DISCOVERY_MESSAGE = b"DATATANG_DISCOVER_V1"


def discover(timeout: float = 2.0, port: int = 8766) -> str | None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        sock.sendto(DISCOVERY_MESSAGE, ("255.255.255.255", port))
        deadline = timeout
        while deadline > 0:
            try:
                data, (host, _) = sock.recvfrom(512)
            except socket.timeout:
                break
            try:
                info = json.loads(data.decode("utf-8"))
                address = ipaddress.ip_address(host)
                if info.get("service") == "datatang-distribution" and info.get("protocol") == 1 and address.is_private:
                    http_port = int(info.get("port", 8765))
                    if 1 <= http_port <= 65535:
                        return f"http://{host}:{http_port}/"
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="LAN image distribution client")
    parser.add_argument("--url", help="use a known server URL instead of discovery")
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()
    url = args.url or discover(args.timeout)
    if not url:
        print("No distribution server found. Use --url http://SERVER_IP:8765/.")
        return 2
    print(f"Opening {url}")
    webbrowser.open(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
