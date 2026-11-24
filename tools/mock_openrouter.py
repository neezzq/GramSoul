#!/usr/bin/env python3
"""Tiny stand-in for the OpenRouter API, used only by CI emulator tests.

    python3 tools/mock_openrouter.py 9009

Implements what GramSoul uses: streaming chat completions (SSE), image generation
(`modalities: ["image","text"]` → base64 PNG in message.images) and GET /api/v1/key."""
from __future__ import annotations

import base64
import io
import itertools
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

COUNTER = itertools.count(1)


def png(text: str) -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (480, 640), (40, 8, 30))
    d = ImageDraw.Draw(img)
    for i in range(0, 640, 16):
        d.rectangle([0, i, 480, i + 8], fill=(60 + i // 8 % 60, 10, 50))
    d.ellipse([140, 200, 340, 400], fill=(255, 79, 163))
    d.text((20, 600), text[:60], fill=(255, 255, 255))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, code: int, obj: dict) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.endswith("/key"):
            return self._json(200, {"data": {"limit": None, "usage": 0}})
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        if not self.headers.get("Authorization", "").startswith("Bearer sk-or-"):
            return self._json(401, {"error": {"message": "bad key"}})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        n = next(COUNTER)
        if body.get("modalities"):
            url = "data:image/png;base64," + base64.b64encode(png(f"mock image {n}")).decode()
            return self._json(200, {"choices": [{"message": {"role": "assistant", "content": "",
                                                              "images": [{"type": "image_url", "image_url": {"url": url}}]}}]})
        system = body["messages"][0]["content"]
        summary = system.startswith("Ты кратко пересказываешь")
        text = (f"Краткое содержание {n}: герои были у маяка." if summary else
                f"Рассказчик: Туман за окнами отступает, линза отражает далёкие огни (OBLAKO {n}).\n"
                f"Ива: *улыбается и поправляет косу* Облачный ответ номер {n}. Пойдём дальше?")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(b": OPENROUTER PROCESSING\n\n")
        for piece in [text[:40], text[40:]]:
            chunk = {"choices": [{"delta": {"content": piece}}]}
            self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        usage = {"choices": [{"delta": {}}], "usage": {"prompt_tokens": 500, "completion_tokens": 40}}
        self.wfile.write(f"data: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode())


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9009
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
