#!/usr/bin/env python
"""A tiny multi-provider stub for local dev (no real API keys needed).

Run:  uv run python scripts/stub_provider.py   # listens on :9099
Point a model deployment's api_base at it (the seed does this by default).

It speaks three upstream wire shapes so all the main provider families are
demoable offline. LiteLLM picks the shape from the deployment's ``provider`` and
POSTs the matching request; we branch on the request *path*:

    /v1/messages ....................... Anthropic Messages   (provider "anthropic")
    .../models/<m>:generateContent ..... Google Gemini        (provider "gemini")
    everything else (/v1/chat/...) ..... OpenAI chat.completion (provider "openai")

All three shapes also stream (Server-Sent Events) when the client streams —
OpenAI/Anthropic signal it via the body's ``stream`` flag, Gemini via a
``:streamGenerateContent`` URL — and every stream ends with token usage so
streamed calls meter correctly.

The OpenAI path echoes the received user text back in the reply content, so an
input guardrail (e.g. PII redaction) is observable end to end: send an email,
and the reply shows ``[REDACTED:email]`` rather than the address.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_MARKER = "Hello from the AI Gateway stub."


def _received_text(body: dict[str, Any]) -> str:
    """Best-effort extract of the last user turn across all three wire shapes."""
    # OpenAI / Anthropic: {"messages": [{"role","content"}]}
    for msg in reversed(body.get("messages") or []):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):  # anthropic content blocks / multimodal
                return " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict) and "text" in p
                )
    # Gemini: {"contents": [{"role","parts":[{"text"}]}]}
    for turn in reversed(body.get("contents") or []):
        if isinstance(turn, dict):
            parts = turn.get("parts") or []
            text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict))
            if text:
                return text
    return ""


def _openai_body(received: str) -> dict[str, Any]:
    content = _MARKER if not received else f"{_MARKER} [echo] {received}"
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 7, "total_tokens": 15},
    }


def _anthropic_body() -> dict[str, Any]:
    return {
        "id": "msg_stub",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": f"{_MARKER} (anthropic)"}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 8, "output_tokens": 7},
    }


def _gemini_body() -> dict[str, Any]:
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": f"{_MARKER} (gemini)"}]},
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 8,
            "candidatesTokenCount": 7,
            "totalTokenCount": 15,
        },
        "modelVersion": "gemini-stub",
    }


def _openai_stream_chunks(received: str) -> list[dict[str, Any]]:
    """SSE chunks for a streamed OpenAI completion, ending with a usage-only
    chunk (as OpenAI does when stream_options.include_usage is set). The gateway
    forces include_usage on streams so this final chunk carries the tokens that
    metering needs — without it, streamed calls under-meter."""
    content = _MARKER if not received else f"{_MARKER} [echo] {received}"
    base = {"id": "chatcmpl-stub", "object": "chat.completion.chunk", "model": "gpt-4o-mini"}
    return [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        # Final usage-only chunk: choices empty, usage populated.
        {
            **base,
            "choices": [],
            "usage": {"prompt_tokens": 8, "completion_tokens": 7, "total_tokens": 15},
        },
    ]


def _openai_stream_sse(received: str) -> bytes:
    lines = [f"data: {json.dumps(c)}\n\n" for c in _openai_stream_chunks(received)]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _anthropic_stream_sse(received: str) -> bytes:
    """Anthropic Messages streaming events. Usage rides on message_start
    (input_tokens) and message_delta (output_tokens)."""
    text = f"{_MARKER} (anthropic)"
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_stub",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-5",
                    "content": [],
                    "stop_reason": None,
                    "usage": {"input_tokens": 8, "output_tokens": 0},
                },
            },
        ),
        (
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
        (
            "content_block_delta",
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": text},
            },
        ),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 7},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    return "".join(f"event: {name}\ndata: {json.dumps(d)}\n\n" for name, d in events).encode()


def _gemini_stream_sse(received: str) -> bytes:
    """Gemini streamGenerateContent (alt=sse). One complete GenerateContentResponse
    chunk carrying content, finishReason and usageMetadata — the stub doesn't need
    to fragment, and a single well-formed chunk is what the adapter parses cleanly."""
    text = f"{_MARKER} (gemini)"
    chunk = {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": text}]},
                "finishReason": "STOP",
                "index": 0,
            }
        ],
        "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 7, "totalTokenCount": 15},
    }
    return f"data: {json.dumps(chunk)}\n\n".encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {}
        if not isinstance(body, dict):
            body = {}

        # Match case-insensitively: Gemini's streaming verb is ":streamGenerateContent"
        # (capital G), so a plain "generateContent" substring test misses the stream
        # URL and would wrongly fall through to the OpenAI branch.
        path = self.path
        lpath = path.lower()
        received = _received_text(body)
        stream = bool(body.get("stream"))
        # Streaming: all three families emit SSE (Gemini signals it via a
        # streamGenerateContent URL; OpenAI/Anthropic via the body's stream flag).
        if "generatecontent" in lpath:
            if "streamgeneratecontent" in lpath:
                self._write_sse(_gemini_stream_sse(received))
            else:
                self._write_json(_gemini_body())
        elif path.rstrip("/").endswith("/messages") or "/v1/messages" in path:
            if stream:
                self._write_sse(_anthropic_stream_sse(received))
            else:
                self._write_json(_anthropic_body())
        elif stream:
            self._write_sse(_openai_stream_sse(received))
        else:
            self._write_json(_openai_body(received))

    def _write_json(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _write_sse(self, data: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()


def main() -> None:
    port = int(os.environ.get("AIGW_STUB_PORT", "9099"))
    host = os.environ.get("AIGW_STUB_HOST", "127.0.0.1")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"stub provider listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
