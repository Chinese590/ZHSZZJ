from __future__ import annotations

from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
from datetime import date
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
            if self.path == "/api/admin/initialize":
                self.server.service.initialize_admin(str(body.get("member_id", "")), str(body.get("display_name", "")), str(body.get("password", "")))
                self._json(HTTPStatus.CREATED, {"initialized": True})
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
            if self.path == "/api/admin/members" and self.server.service.is_admin(member):
                items = body.get("members")
                if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                    raise ValueError("members 必须是数组")
                self.server.service.create_members(items)
                self._json(HTTPStatus.CREATED, {"created": len(items)}); return
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
            self.wfile.write("""<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>图片分发中心</title><style>:root{font:16px/1.5 system-ui;color:#172033;background:#eef2f7}*{box-sizing:border-box}body{margin:0;padding:clamp(16px,4vw,48px)}main{max-width:980px;margin:auto}.hero{margin-bottom:24px}.hero h1{margin:0;font-size:clamp(1.7rem,4vw,2.4rem)}.hero p{margin:4px 0;color:#667085}.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px}.step,.card{background:#fff;border:1px solid #e4e7ec;border-radius:14px;padding:16px}.step{color:#667085}.step b{display:block;color:#344054}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}.card{box-shadow:0 4px 14px #1018280b}.card h2{margin:0 0 14px}.field{display:grid;gap:6px;margin:10px 0}.field label{font-size:.88rem;color:#475467}.field input,.field textarea{width:100%;padding:10px 12px;border:1px solid #d0d5dd;border-radius:9px;font:inherit}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}button{border:0;border-radius:9px;padding:10px 15px;background:#2563eb;color:white;font-weight:600;cursor:pointer}button.secondary{background:#e8eefc;color:#1d4ed8}.task{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid #eef2f6}.badge{padding:3px 9px;border-radius:999px;background:#eef4ff;color:#1d4ed8;font-size:.85rem}.status{position:sticky;bottom:16px;margin-top:18px;padding:12px 14px;border-radius:10px;background:#172033;color:white;min-height:44px}.status.error{background:#b42318}.hide{display:none!important}pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#475467}@media(max-width:600px){.steps{grid-template-columns:1fr}.task{align-items:flex-start;flex-direction:column}}</style><main><header class='hero'><h1>图片分发中心</h1><p>清晰分工，快速完成采集与回传</p></header><nav class='steps'><div class='step'><b>1 · 登录</b>使用成员账号进入工作区</div><div class='step'><b>2 · 领取任务</b>查看并上传对应图片</div><div class='step'><b>3 · 管理分发</b>管理员导入、分配与统计</div></nav><div class='grid'><section id='setupCard' class='card'><h2>初始化管理员</h2><div class='field'><label>管理员账号</label><input id='setupMember' placeholder='例如 admin'></div><div class='field'><label>姓名</label><input id='setupName' placeholder='显示名称'></div><div class='field'><label>密码</label><input id='setupPassword' type='password' placeholder='至少 8 位密码'></div><button onclick='initializeAdmin()'>一键初始化</button></section><section id='loginCard' class='card'><h2>成员登录</h2><div class='field'><label>成员账号</label><input id='member' placeholder='输入账号'></div><div class='field'><label>密码</label><input id='password' type='password' placeholder='输入密码'></div><button onclick='login()'>登录工作区</button></section></div><section id='userCard' class='card hide' style='margin-top:16px'><div class='row' style='justify-content:space-between'><h2>我的任务</h2><button class='secondary' onclick='loadTasks()'>刷新任务</button></div><div id='tasks'></div></section><section id='adminCard' class='card hide' style='margin-top:16px'><h2>管理端</h2><div class='field'><label>导入图片目录</label><div class='row'><input id='source' style='flex:1' placeholder='目录路径'><button onclick='importImages()'>导入</button></div></div><div class='field'><label>分发设置</label><div class='row'><input id='members' value='member-a' placeholder='成员账号，逗号分隔' style='flex:1'><input id='per' type='number' value='1' min='1' style='width:90px'><button onclick='distribute()'>开始分发</button></div></div><div class='field'><label>批量添加成员（每行：账号,姓名,密码[,角色]）</label><textarea id='memberBatch' rows='4'></textarea><button onclick='addMembers()'>批量添加</button></div><div class='field'><label>日终统计</label><div class='row'><input id='reportDay' type='date'><button onclick='dailyReport()'>查看统计</button></div></div><pre id='adminOut'></pre></section><div id='out' class='status' role='status' aria-live='polite'>准备就绪</div></main><script>const $=id=>document.getElementById(id);async function api(path,body){let r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),j=await r.json();if(!r.ok)throw Error(j.error||r.status);return j}function show(id,v,e=false){let x=$(id);x.textContent=typeof v==='string'?v:JSON.stringify(v,null,2);if(id==='out')x.classList.toggle('error',e)}async function initializeAdmin(){try{show('out',await api('/api/admin/initialize',{member_id:$('setupMember').value,display_name:$('setupName').value,password:$('setupPassword').value}));$('setupCard').classList.add('hide')}catch(e){show('out',e.message,true)}}async function login(){try{let j=await api('/api/login',{member_id:$('member').value,password:$('password').value});$('loginCard').classList.add('hide');$('userCard').classList.remove('hide');if(j.admin)$('adminCard').classList.remove('hide');show('out','登录成功');loadTasks()}catch(e){show('out',e.message,true)}}async function loadTasks(){let r=await fetch('/api/my/tasks'),j=await r.json();$('tasks').replaceChildren(...j.tasks.map(t=>{let d=document.createElement('div');d.className='task';let n=document.createElement('span');n.textContent=t.image_name;let b=document.createElement('span');b.className='badge';b.textContent=t.state;let i=document.createElement('input');i.type='file';i.accept='image/*';i.onchange=()=>upload(t.task_id,i);d.append(n,b,i);return d}));if(!j.tasks.length)$('tasks').textContent='暂无任务'}async function upload(id,i){try{let f=i.files[0];if(!f)return;let b=await new Promise(x=>{let r=new FileReader;r.onload=()=>x(r.result.split(',')[1]);r.readAsDataURL(f)});show('out',await api('/api/tasks/upload',{task_id:id,filename:f.name,content_base64:b}));loadTasks()}catch(e){show('out',e.message,true)}}async function importImages(){try{show('adminOut',await api('/api/admin/import',{source:$('source').value}))}catch(e){show('adminOut',e.message)}}async function distribute(){try{show('adminOut',await api('/api/admin/distribute',{member_ids:$('members').value.split(',').map(x=>x.trim()).filter(Boolean),per_member:Number($('per').value)}))}catch(e){show('adminOut',e.message)}}async function addMembers(){try{let members=$('memberBatch').value.trim().split(/\n+/).filter(Boolean).map(l=>{let [member_id,display_name,password,role='member']=l.split(',').map(x=>x.trim());return {member_id,display_name,password,role}});show('adminOut',await api('/api/admin/members',{members}))}catch(e){show('adminOut',e.message)}}async function dailyReport(){try{let r=await fetch('/api/admin/daily?day='+encodeURIComponent($('reportDay').value)),j=await r.json();if(!r.ok)throw Error(j.error||r.status);show('adminOut',j)}catch(e){show('adminOut',e.message)}}</script>""".encode("utf-8")); return
        if not member:
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "请先登录"}); return
        if self.path == "/api/my/tasks":
            self._json(HTTPStatus.OK, {"tasks": [task.to_dict() for task in self.server.service.my_tasks(member)]}); return
        if self.path.startswith("/api/admin/daily") and self.server.service.is_admin(member):
            query = self.path.partition("?")[2]
            requested_day = next((part.partition("=")[2] for part in query.split("&") if part.partition("=")[0] == "day"), "")
            try:
                report_day = date.fromisoformat(requested_day) if requested_day else date.today()
            except ValueError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "日期格式应为 YYYY-MM-DD"}); return
            self._json(HTTPStatus.OK, self.server.service.daily_summary(report_day)); return
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

