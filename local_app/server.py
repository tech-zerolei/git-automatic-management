"""Session-only localhost UI. Repository data never travels to a model service."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit

from core import PlannerError, fail, repository, make_plan, review_plan, report, safe_export

STATIC = Path(__file__).resolve().parent / "static"


class App:
    def __init__(self):
        self.snapshot = None
        self.plan = None
        self.running = True

    def public_snapshot(self):
        if not self.snapshot: return None
        return {k:v for k,v in self.snapshot.items() if k not in {"commits", "gitdir", "common", "protected"}}

    def fresh(self):
        if not self.snapshot: fail("selection", "请先选择仓库。")
        try:
            current = repository(self.snapshot["root"])
        except PlannerError:
            self.plan = None
            raise
        if current["fingerprint"] != self.snapshot["fingerprint"]:
            self.snapshot = current
            self.plan = None
            fail("stale", "仓库已变化，计划和人工确认已失效。请刷新并重新生成。")
        return current

    def require_plan(self, data):
        if not self.plan: fail("plan", "请先生成版本计划。")
        if data.get("planFingerprint") != self.plan["planFingerprint"]:
            fail("stale", "当前计划已更新，请重新生成并复核后操作。")

    def dialog(self, save=False):
        args = ["/usr/bin/zenity", "--file-selection", "--title=" + ("导出版本报告" if save else "选择本地 Git 工作树")]
        args += ["--save", "--filename=version-plan.md"] if save else ["--directory"]
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            output, _ = p.communicate(timeout=120)
            return output.decode("utf-8").rstrip("\n") if p.returncode == 0 else None
        except subprocess.TimeoutExpired:
            fail("dialog_timeout", "文件选择超时，请重试。")
        finally:
            try: os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            p.wait()

    def action(self, action, data):
        if action == "state":
            return {"snapshot": self.public_snapshot(), "plan": self.plan}
        if action == "choose":
            return {"path": self.dialog()}
        if action == "discard":
            self.plan = None
            return {"plan": None}
        if action in {"open", "refresh"}:
            path = data.get("path") if action == "open" else self.snapshot["root"] if self.snapshot else None
            self.plan = None
            if action == "open": self.snapshot = None
            self.snapshot = repository(path)
            return {"snapshot": self.public_snapshot(), "plan": None}
        if action == "plan":
            if data.get("confirmed") is not True: fail("baseline", "请显式确认基线或首次版本。")
            snap = self.fresh()
            self.plan = make_plan(snap, data.get("baseline"), data.get("initial"))
            return {"plan": self.plan}
        if action == "review":
            if not self.plan: fail("plan", "请先生成版本计划。")
            if data.get("planFingerprint") != self.plan["planFingerprint"]: fail("stale", "当前计划已更新，请重试。")
            self.plan = review_plan(self.plan, self.fresh(), data.get("override", ""), data.get("reason", ""))
            return {"plan": self.plan}
        if action == "preview":
            self.require_plan(data)
            self.fresh()
            self.require_plan(data)
            return {"content": report(self.plan, data.get("format", "md"))}
        if action == "export":
            self.require_plan(data)
            self.fresh()
            target = self.dialog(save=True) if data.get("dialog") is True else data.get("path")
            if not target: return {"cancelled": True}
            if not isinstance(target, str) or len(target) > 4096: fail("export_path", "无效导出路径。")
            kind = data.get("format", "md")
            if not target.endswith("." + kind): target += "." + kind
            self.fresh()
            self.require_plan(data)
            safe_export(target, report(self.plan, kind), self.snapshot["protected"])
            return {"saved": True, "path": target}
        if action == "quit":
            self.running = False
            self.plan = None; self.snapshot = None
            return {"closed": True}
        fail("action", "未知操作。")


class LocalServer(HTTPServer):
    allow_reuse_address = False
    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(10)
        return sock, address


def create_server(port=0):
    app = App()
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *_): pass

        def send(self, code, body, kind="application/json; charset=utf-8"):
            if isinstance(body, dict): body = json.dumps(body, ensure_ascii=False).encode()
            elif isinstance(body, str): body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass

        def valid_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.valid_host(): return self.send(403, {"error":"禁止跨主机访问。"})
            path = urlsplit(self.path).path
            names = {"/":"index.html", "/app.js":"app.js", "/style.css":"style.css",
                     "/vendor/lucide.min.js":"vendor/lucide.min.js", "/icon.svg":"icon.svg"}
            if path not in names: return self.send(404, {"error":"不存在。"})
            file = STATIC / names[path]
            self.send(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")

        def do_POST(self):
            origin = f"http://127.0.0.1:{self.server.server_port}"
            auth = self.headers.get("X-Planner-Token", "")
            if not self.valid_host() or self.headers.get("Origin") != origin or not secrets.compare_digest(auth, token):
                return self.send(403, {"error":"会话校验失败。请从启动入口重新打开。", "code":"auth"})
            if self.headers.get("Content-Type") != "application/json" or self.headers.get("Transfer-Encoding"):
                return self.send(415, {"error":"请求格式无效。"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536: raise ValueError()
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict): raise ValueError()
            except (ValueError, UnicodeError):
                return self.send(400, {"error":"请求无效或过大。"})
            self.server.last_used = time.monotonic()
            try:
                result = app.action(urlsplit(self.path).path.removeprefix("/api/"), data)
                self.send(200, result)
            except PlannerError as exc:
                self.send(400, {"code":exc.code, "error":exc.message, "planInvalidated": app.plan is None})
            except Exception:
                app.plan = None
                self.send(500, {"code":"internal", "error":"操作未完成，结果已作废。请重新选择仓库。", "planInvalidated":True})

    server = LocalServer(("127.0.0.1", port), Handler)
    server.token = token; server.app = app; server.last_used = time.monotonic(); server.timeout = 1
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--daemonize", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ready-file", help=argparse.SUPPRESS)
    args = parser.parse_args()
    server = create_server(args.port)
    if args.daemonize:
        pid = os.fork()
        if pid:
            server.server_close()
            return
        os.setsid()
        with open(os.devnull, "rb", buffering=0) as inp, open(os.devnull, "ab", buffering=0) as out:
            os.dup2(inp.fileno(), 0); os.dup2(out.fileno(), 1); os.dup2(out.fileno(), 2)
    url = f"http://127.0.0.1:{server.server_port}/#{server.token}"
    if args.ready_file:
        ready = Path(args.ready_file)
        fd = os.open(ready, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"url":url,"pid":os.getpid()},stream)
    if args.no_browser:
        print(url, flush=True)
    else:
        chrome = "/usr/bin/google-chrome"
        command = [chrome, "--app=" + url] if Path(chrome).exists() else ["/usr/bin/xdg-open", url]
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        while server.app.running and time.monotonic() - server.last_used < 1800:
            server.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.app.plan = None; server.app.snapshot = None


if __name__ == "__main__": main()
