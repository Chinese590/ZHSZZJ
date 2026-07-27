from __future__ import annotations

from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import ipaddress
import json
from pathlib import Path
import secrets
import argparse
from typing import Any

from .distribution import DistributionService


def validate_bind_host(host: str) -> str:
    address = ipaddress.ip_address(host)
    if address.is_unspecified or address.is_multicast or address.is_link_local or address.is_reserved or not (address.is_loopback or address.is_private):
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
                self._json(HTTPStatus.OK, {"member_id": member, "admin": self.server.service.is_admin(member)}, f"distribution_session={token}; HttpOnly; SameSite=Strict; Path=/")
                return
            member = self._member()
            if not member:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录"}); return
            if self.path == "/api/tasks/start":
                task = self.server.service.start(str(body["task_id"]), member)
                self._json(HTTPStatus.OK, task.to_dict()); return
            if self.path == "/api/tasks/upload":
                if not body.get("task_id") or not body.get("filename") or not body.get("content_base64"):
                    raise ValueError("上传字段不完整")
                suffix = Path(str(body["filename"])).suffix.lower()
                if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
                    raise ValueError("不支持的图片格式")
                temporary = self.server.service.root / f"upload-{secrets.token_urlsafe(8)}{suffix}"
                temporary.write_bytes(base64.b64decode(str(body["content_base64"]), validate=True))
                try:
                    task = self.server.service.upload(str(body["task_id"]), member, temporary)
                finally:
                    temporary.unlink(missing_ok=True)
                self._json(HTTPStatus.OK, task.to_dict()); return
            if self.path == "/api/admin/import" and self.server.service.is_admin(member):
                result = self.server.service.import_images(Path(str(body["source"])))
                self._json(HTTPStatus.OK, {"imported": result.imported, "duplicates": result.exact_duplicates, "warnings": result.warnings}); return
            if self.path == "/api/admin/distribute" and self.server.service.is_admin(member):
                assignments = self.server.service.distribute([str(item) for item in body["member_ids"]], int(body["per_member"]))
                self._json(HTTPStatus.OK, {"assignments": [{"task_id": item.task_id, "member_id": item.member_id} for item in assignments]}); return
            if self.path == "/api/admin/recall" and self.server.service.is_admin(member):
                task = self.server.service.recall(str(body["task_id"]), member, str(body["reason"]))
                self._json(HTTPStatus.OK, task.to_dict()); return
            self._json(HTTPStatus.FORBIDDEN, {"error": "无权执行此操作"})
        except (KeyError, ValueError, PermissionError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_GET(self) -> None:
        member = self._member()
        if self.path == "/":
            self.send_response(HTTPStatus.OK); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write("""<!doctype html><meta charset='utf-8'><title>图片分发中心</title><style>body{font:16px Segoe UI;margin:32px;background:#f4f7fb;color:#1d2939}main{max-width:900px;margin:auto;background:white;padding:28px;border-radius:14px}button{margin:4px;padding:8px 14px}input{padding:7px;margin:4px}.card{border:1px solid #d0d5dd;padding:16px;margin-top:18px;border-radius:10px}.hide{display:none}pre{white-space:pre-wrap}</style>
            <main><h1>图片分发中心</h1><section id='loginCard' class='card'><h2>登录</h2><input id='member' placeholder='成员账号'><input id='password' type='password' placeholder='密码'><button onclick='login()'>登录</button></section>
            <section id='userCard' class='card hide'><h2>我的任务</h2><button onclick='loadTasks()'>刷新</button><div id='tasks'></div></section>
            <section id='adminCard' class='card hide'><h2>管理端</h2><p>导入目录：<input id='source' size='45'><button onclick='importImages()'>导入</button></p><p>成员账号（逗号分隔）：<input id='members' value='member-a'><input id='per' type='number' value='1' min='1'><button onclick='distribute()'>开始分发</button></p><pre id='adminOut'></pre></section><pre id='out'></pre></main>
            <script>const $=id=>document.getElementById(id);async function api(path,body){let r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});let j=await r.json();if(!r.ok)throw Error(j.error||r.status);return j}
            async function login(){try{let j=await api('/api/login',{member_id:$('member').value,password:$('password').value});$('loginCard').classList.add('hide');$('userCard').classList.remove('hide');if(j.admin)$('adminCard').classList.remove('hide');loadTasks()}catch(e){$('out').textContent=e}}
            async function loadTasks(){let r=await fetch('/api/my/tasks');let j=await r.json();$('tasks').innerHTML=j.tasks.map(t=>`<div class='card'><b>${t.image_name}</b>　状态：${t.state}<input type=file onchange='upload("${t.task_id}",this)'></div>`).join('')||'暂无任务'}
            async function upload(id,input){let f=input.files[0];let b=await new Promise(x=>{let r=new FileReader;r.onload=()=>x(r.result.split(',')[1]);r.readAsDataURL(f)});$('out').textContent=JSON.stringify(await api('/api/tasks/upload',{task_id:id,filename:f.name,content_base64:b}))}
            async function importImages(){try{$('adminOut').textContent=JSON.stringify(await api('/api/admin/import',{source:$('source').value}))}catch(e){$('adminOut').textContent=e}}
            async function distribute(){try{$('adminOut').textContent=JSON.stringify(await api('/api/admin/distribute',{member_ids:$('members').value.split(',').map(x=>x.trim()),per_member:Number($('per').value)}))}catch(e){$('adminOut').textContent=e}}</script>""".encode("utf-8")); return
        if not member:
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录"}); return
        if self.path == "/api/my/tasks":
            self._json(HTTPStatus.OK, {"tasks": [task.to_dict() for task in self.server.service.my_tasks(member)]}); return
        self._json(HTTPStatus.NOT_FOUND, {"error": "不存在"})


def serve(project_root: Path, host: str = "127.0.0.1", port: int = 8765) -> DistributionHttpServer:
    return DistributionHttpServer((validate_bind_host(host), port), DistributionService(project_root))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="局域网图片分发中心")
    parser.add_argument("--project", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = serve(Path(args.project), args.host, args.port)
    print(f"图片分发中心已启动：http://{args.host}:{args.port}")
    server.serve_forever()
