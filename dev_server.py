# -*- coding: utf-8 -*-
"""로컬 개발 서버: 정적 파일 + /api/label 을 한 포트에서 띄운다(Vercel 과 같은 모양). 실행: PYTHONUTF8=1 python dev_server.py [port]"""
import json
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "api"))
import label  # noqa: E402


class Dev(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def _json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.rstrip("/") == "/api/label":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception:  # noqa: BLE001
                return self._json(400, {"error": "bad json"})
            code, obj = label.handle(payload)
            return self._json(code, obj)
        self._json(404, {"error": "not found"})

    def do_GET(self):
        if self.path.rstrip("/") == "/api/label":
            return self._json(200, {"ok": True, "configured": bool(os.environ.get("OPENAI_API_KEY"))})
        super().do_GET()

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"http://localhost:{port}/  (Ctrl+C 로 종료)")
    ThreadingHTTPServer(("127.0.0.1", port), Dev).serve_forever()
