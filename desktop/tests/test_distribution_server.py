from __future__ import annotations

import pytest

from app.distribution_server import validate_bind_host
from app.distribution_server import DistributionRequestHandler


def test_server_bind_is_limited_to_loopback_or_private_networks():
    assert validate_bind_host("127.0.0.1") == "127.0.0.1"
    assert validate_bind_host("192.168.1.20") == "192.168.1.20"
    with pytest.raises(ValueError):
        validate_bind_host("8.8.8.8")


def test_ui_contains_separate_user_and_admin_workflows():
    source = DistributionRequestHandler.do_GET.__code__.co_consts
    page = " ".join(item for item in source if isinstance(item, str))
    assert "我的任务" in page
    assert "管理端" in page
    assert "/api/admin/import" in page
    assert "/api/admin/distribute" in page
    assert "/api/tasks/upload" in page
