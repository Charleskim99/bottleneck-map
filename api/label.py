# -*- coding: utf-8 -*-
"""Vercel Python 서버 함수: POST /api/label  {"sentence": "...", "field": "..."}  ->  {"kind", "theme", "quote", "model"}

API 키는 서버 환경변수 OPENAI_API_KEY 에만 둔다(프론트에 노출하지 않는 것이 이 함수가 존재하는 이유).
키가 없으면 501 로 "api key not configured" 를 돌려주고, 화면은 신호 단어 판정으로 대신한다.
표준 라이브러리만 쓴다. 로컬 시험은 dev_server.py 가 같은 handle() 을 붙인다.
"""
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

RULES = (
    "Each input is ONE sentence copied out of a published abstract. Decide kind: 'bottleneck' (something is still missing, "
    "limited, unsolved, costly, unstable or otherwise a problem), 'resolution-claim' (the sentence itself says such a problem "
    "is removed, no longer needed, overcome, mitigated or now routine), or 'neither' (a method, a capability, a measured figure, "
    "an aim, or a review sentence saying challenges are discussed). Give theme: 3-6 words naming WHAT is limited or solved. "
    "Give quote: a continuous span COPIED VERBATIM from the sentence (4-30 words) that carries the bottleneck or the claim; empty "
    "for 'neither'. Judge only the sentence; do not use outside knowledge. Return JSON only: "
    '{"kind": "...", "theme": "...", "quote": "..."}'
)


def handle(payload: dict) -> tuple[int, dict]:
    sentence = (payload.get("sentence") or "").strip()
    if not sentence or len(sentence) > 1200:
        return 400, {"error": "sentence is empty or longer than 1200 characters"}
    key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
    if not key:
        return 501, {"error": "api key not configured"}
    body = {"model": model, "input": [{"role": "developer", "content": RULES + f"\nFIELD UNDER STUDY: {payload.get('field') or 'unspecified'}"},
                                      {"role": "user", "content": sentence}],
            "text": {"format": {"type": "json_object"}}}
    req = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            out = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return 502, {"error": f"upstream {e.code}: {e.read()[:200].decode('utf-8', 'replace')}"}
    except Exception as e:        # noqa: BLE001
        return 502, {"error": f"upstream failure: {type(e).__name__}"}
    text = ""
    for item in out.get("output", []):
        for c in item.get("content", []) or []:
            if c.get("type") in ("output_text", "text"):
                text += c.get("text", "")
    try:
        res = json.loads(text)
    except Exception:             # noqa: BLE001
        return 502, {"error": "model did not return JSON", "raw": text[:200]}
    kind = res.get("kind")
    if kind not in ("bottleneck", "resolution-claim", "neither"):
        return 502, {"error": f"unknown kind {kind!r}"}
    quote = (res.get("quote") or "").strip()
    norm = lambda s: " ".join(s.lower().split())              # noqa: E731
    return 200, {"kind": kind, "theme": (res.get("theme") or "").strip(), "quote": quote,
                 "quote_verbatim": (norm(quote) in norm(sentence)) if quote else None, "model": out.get("model") or model}


class handler(BaseHTTPRequestHandler):            # Vercel looks for this name
    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:         # noqa: BLE001
            return self._send(400, {"error": "bad json"})
        code, obj = handle(payload)
        self._send(code, obj)

    def do_GET(self):
        self._send(200, {"ok": True, "usage": "POST {sentence, field}", "configured": bool(os.environ.get("OPENAI_API_KEY"))})
