"""roundtable Web UI — 本地 Web 服务,自动打开浏览器。"""

import asyncio
import json
import os
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse

# 把项目根目录加入 path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roundtable import PANEL, _anon, _gather, _facilitator, _adversary, _report


class Handler(SimpleHTTPRequestHandler):
    """处理静态文件 + API 请求。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent / "static"), **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        if self.path == "/api/run":
            self._handle_run()
        else:
            self.send_error(404)

    def _handle_run(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            question = body.get("question", "").strip()
            if not question:
                self._json_error(400, "问题不能为空")
                return
        except Exception as e:
            self._json_error(400, str(e))
            return

        try:
            result = asyncio.run(self._analyze(question))
            self._json_ok(result)
        except SystemExit as e:
            self._json_error(500, f"分析终止: 存活意见不足")
        except Exception as e:
            self._json_error(500, str(e))

    async def _analyze(self, question: str) -> dict:
        takes = await _gather(question)
        anon = _anon(takes)
        decision_map, adversary_report = await asyncio.gather(
            _facilitator(anon),
            _adversary(anon),
        )
        from datetime import datetime
        return {
            "question": question,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "panel": [f"{t.model}{'⚠' if t.error else '✓'}" for t in takes],
            "takes": [{"model": t.model, "text": t.text, "error": t.error} for t in takes],
            "decision_map": decision_map,
            "adversary": adversary_report,
        }

    def _json_ok(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, code, msg):
        body = json.dumps({"error": msg}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # 静默日志


def main():
    import argparse
    parser = argparse.ArgumentParser(description="roundtable Web UI")
    parser.add_argument("--port", type=int, default=7800, help="端口号(默认 7800)")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"

    try:
        print(f"◉ Roundtable Web UI")
        print(f"  {url}")
        print(f"  Ctrl+C 退出")
    except UnicodeEncodeError:
        sys.stdout.reconfigure(encoding="utf-8")
        print(f"◉ Roundtable Web UI")
        print(f"  {url}")
        print(f"  Ctrl+C 退出")

    if not args.no_browser:
        Thread(target=lambda: webbrowser.open(url), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
        server.server_close()


if __name__ == "__main__":
    main()
