from __future__ import annotations

from http.client import HTTPConnection
import json
from threading import Thread

import pytest

from app.distribution_server import DistributionRequestHandler
from app.distribution_server import serve, validate_bind_host


def request(server, method: str, path: str, body: dict | None = None, cookie: str = ""):
    connection = HTTPConnection(*server.server_address)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if cookie:
        headers["Cookie"] = cookie
    connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    response = connection.getresponse()
    return response.status, json.loads(response.read()), response.getheader("Set-Cookie")


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
    assert "/api/admin/initialize" in page
    assert "/api/admin/members" in page
    assert "/api/admin/daily" in page
    assert "一键初始化" in page
    assert "批量添加成员" in page
    assert "日终统计" in page
    assert "/api/tasks/upload" in page


def test_admin_setup_bulk_member_and_daily_api(tmp_path):
    server = serve(tmp_path, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body, _ = request(server, "POST", "/api/admin/initialize", {"member_id": "admin", "display_name": "管理员", "password": "admin-password"})
        assert (status, body) == (201, {"initialized": True})
        status, body, cookie = request(server, "POST", "/api/login", {"member_id": "admin", "password": "admin-password"})
        assert status == 200 and body["admin"]
        status, body, _ = request(server, "POST", "/api/admin/members", {"members": [{"member_id": "member", "display_name": "成员", "password": "member-password", "role": "member"}]}, cookie.split(";", 1)[0])
        assert (status, body) == (201, {"created": 1})
        status, body, _ = request(server, "GET", "/api/admin/daily", cookie=cookie.split(";", 1)[0])
        assert status == 200 and body["actions"]["MEMBER_CREATE"] == 2
    finally:
        server.shutdown(); server.server_close(); thread.join()
