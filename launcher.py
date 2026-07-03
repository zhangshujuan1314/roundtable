"""roundtable 桌面启动器 — 双击即用。"""

import asyncio
import json
import os
import sys
import webbrowser
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread

# 路径修正
if getattr(sys, 'frozen', False):
    BASE = Path(sys._MEIPASS)
    EXE_DIR = Path(sys.executable).parent
else:
    BASE = Path(__file__).resolve().parent
    EXE_DIR = BASE

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(EXE_DIR / ".env")
    load_dotenv(BASE / ".env")
except Exception:
    pass

# 导入核心模块
sys.path.insert(0, str(BASE))
from roundtable import PANEL, _anon, _gather, _facilitator, _adversary

STATIC = BASE / "web" / "static"
PORT = 7800


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def do_GET(self):
        if self.path == "/":
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
        except SystemExit:
            self._json_error(500, "分析终止: 存活意见不足")
        except Exception as e:
            self._json_error(500, str(e))

    async def _analyze(self, question):
        takes = await _gather(question)
        anon = _anon(takes)
        decision_map, adversary_report = await asyncio.gather(
            _facilitator(anon), _adversary(anon),
        )
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
        pass


def main():
    # 检查 .env
    env_file = EXE_DIR / ".env"
    if not env_file.exists():
        example = BASE / ".env.example"
        if example.exists():
            import shutil
            shutil.copy(example, env_file)
        if sys.platform == "win32":
            os.startfile(str(env_file))
        try:
            import tkinter as tk
            from tkinter import messagebox
            r = tk.Tk(); r.withdraw()
            messagebox.showinfo("Roundtable", "请在 .env 中填入 API Key,保存后重启")
            r.destroy()
        except Exception:
            pass
        return

    # 启动服务器
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    Thread(target=server.serve_forever, daemon=True).start()

    url = f"http://127.0.0.1:{PORT}"
    Thread(target=lambda: webbrowser.open(url), daemon=True).start()

    # tkinter 窗口
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title("Roundtable")
        root.geometry("320x180")
        root.resizable(False, False)
        root.configure(bg="#0d1117")
        tk.Label(root, text="◉ ROUNDTABLE", font=("Consolas", 16, "bold"),
                 fg="#39d353", bg="#0d1117").pack(pady=(20, 5))
        tk.Label(root, text=f"运行中: {url}", font=("Consolas", 10),
                 fg="#8b949e", bg="#0d1117").pack()
        tk.Label(root, text="关闭此窗口停止服务", font=("Consolas", 9),
                 fg="#30363d", bg="#0d1117").pack(pady=(20, 0))
        root.protocol("WM_DELETE_WINDOW", lambda: (server.server_close(), root.destroy()))
        root.mainloop()
    except Exception:
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.server_close()


if __name__ == "__main__":
    main()
