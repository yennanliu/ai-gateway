#!/usr/bin/env python
"""A tiny OpenAI-compatible stub provider for local dev (no real API key needed).

Run:  uv run python scripts/stub_provider.py   # listens on :9099
Point a model deployment's api_base at it (the seed does this by default).
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello from the AI Gateway stub."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 7, "total_tokens": 15},
        }
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    port = int(os.environ.get("AIGW_STUB_PORT", "9099"))
    host = os.environ.get("AIGW_STUB_HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"stub provider listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
