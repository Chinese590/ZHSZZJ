from __future__ import annotations

from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import secrets
from typing import Any

from .distribution import DistributionService


def validate_bind_host(host: str) -> str:
    address = ipaddress.ip_address(host)
    if not (address.is_loopback or address.is_private):
        raise ValueError("服务只能绑定本机或局域网私有地址")
    return str(address)


class DistributionHttpServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], service: DistributionService):
        super().__init__(address, DistributionRequestHandler)
        self.service = service
        self.sessions: dict[str, str] = {}


class DistributionRequestHandler(BaseHTTPRequestHandler):
    server: DistributionHttpServer

    def log_message(self, *_: Any) -> None:
        return

    def _json(self, status: int, body: dict[str, Any], cookie: str | None = None) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers(); self.wfile.write(payload)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def _member(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookie.get("distribution_session")
        return self.server.sessions.get(token.value) if token else None

    def do_POST(self) -> None:
        try:
            body = self._body()
            if self.path == "/api/login":
                member = str(body.get("member_id", ""))
                if not self.server.service.authenticate(member, str(body.get("password", ""))):
                    self._json(HTTPStatus.UNAUTHORIZED, {"error": "账号或密码错误"}); return
                token = secrets.token_urlsafe(32); self.server.sessions[token] = member
                self._json(HTTPStatus.OK, {"member_id": member}, f"distribution_session={token}; HttpOnly; SameSite=Strict; Path=/")
                return
            member = self._member()
            if not member:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录"}); return
            if self.path == "/api/tasks/start":
                task = self.server.service.start(str(body["task_id"]), member)
                self._json(HTTPStatus.OK, task.to_dict()); return
            if self.path == "/api/admin/recall" and member == "admin":
                task = self.server.service.recall(str(body["task_id"]), member, str(body["reason"]))
                self._json(HTTPStatus.OK, task.to_dict()); return
            self._json(HTTPStatus.FORBIDDEN, {"error": "无权执行此操作"})
        except (KeyError, ValueError, PermissionError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_GET(self) -> None:
        member = self._member()
        if self.path == "/":
            self.send_response(HTTPStatus.OK); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write("<h1>图片分发中心</h1><p>请使用局域网客户端登录。</p>".encode("utf-8")); return
        if not member:
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录"}); return
        if self.path == "/api/my/tasks":
            self._json(HTTPStatus.OK, {"tasks": [task.to_dict() for task in self.server.service.my_tasks(member)]}); return
        self._json(HTTPStatus.NOT_FOUND, {"error": "不存在"})


def serve(project_root: Path, host: str = "127.0.0.1", port: int = 8765) -> DistributionHttpServer:
    return DistributionHttpServer((validate_bind_host(host), port), DistributionService(project_root))
