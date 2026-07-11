"""M3 integration: our compiled config drives a real LiteLLM Router.

A local stub provider stands in for OpenAI (no network). Verifies a request
routes through LiteLLM using our config, and that fallback works when the
primary deployment fails.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from litellm import Router

from governance_api.db.models import ModelDeployment
from governance_api.services.config_compiler import compile_config


class _StubHandler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:  # silence
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        if "/bad" in self.path:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error": "boom"}')
            return
        tag = "good"
        body = {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "gpt-test",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": f"OK:{tag}"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
        payload = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def stub_base() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _dep(name: str, api_base: str) -> ModelDeployment:
    return ModelDeployment(
        org_id="o",
        public_name=name,
        provider="openai",
        model="gpt-test",
        api_base=api_base,
        credential_id="c1",
        routing_tags=[],
        status="active",
    )


def _router(config: dict) -> Router:  # type: ignore[type-arg]
    return Router(
        model_list=config["model_list"],
        fallbacks=config["router_settings"].get("fallbacks"),
        num_retries=0,
    )


async def test_request_routes_through_litellm(
    stub_base: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STUB_KEY", "sk-stub")
    config = compile_config([_dep("primary", f"{stub_base}/good")], secret_refs={"c1": "STUB_KEY"})
    router = _router(config)
    resp = await router.acompletion(model="primary", messages=[{"role": "user", "content": "hi"}])
    assert resp.choices[0].message.content == "OK:good"
    assert resp.usage.total_tokens == 7


async def test_fallback_when_primary_fails(stub_base: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STUB_KEY", "sk-stub")
    config = compile_config(
        [_dep("primary", f"{stub_base}/bad"), _dep("backup", f"{stub_base}/good")],
        secret_refs={"c1": "STUB_KEY"},
        routing={"fallbacks": {"primary": ["backup"]}},
    )
    router = _router(config)
    resp = await router.acompletion(model="primary", messages=[{"role": "user", "content": "hi"}])
    # Primary (bad) 500s -> LiteLLM falls back to backup (good).
    assert resp.choices[0].message.content == "OK:good"
