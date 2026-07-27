from __future__ import annotations

import pytest

from app.distribution_server import validate_bind_host


def test_server_bind_is_limited_to_loopback_or_private_networks():
    assert validate_bind_host("127.0.0.1") == "127.0.0.1"
    assert validate_bind_host("192.168.1.20") == "192.168.1.20"
    with pytest.raises(ValueError):
        validate_bind_host("8.8.8.8")
