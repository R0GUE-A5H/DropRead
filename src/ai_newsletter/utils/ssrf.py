import ipaddress
import socket
from urllib.parse import urlparse

BLOCKED_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # AWS metadata
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),  # IPv6 link‑local (Docker internal)
]


def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)

        # only allow http/https
        if parsed.scheme not in ("http", "https"):
            return False

        # a hostname?
        if not parsed.hostname:
            return False

        # resolve and check IP
        ip = ipaddress.ip_address(socket.gethostbyname(parsed.hostname))
        if any(ip in r for r in BLOCKED_RANGES):
            return False

        return True
    except Exception:
        return False
