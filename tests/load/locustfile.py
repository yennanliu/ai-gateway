"""Load test for the control plane (NFR: p50 < 15ms, p99 < 60ms gateway overhead).

Run against a running governance-api:
    uvx locust -f tests/load/locustfile.py --host http://localhost:8080
Set AIGW_ORG_ID to an existing org to exercise authenticated endpoints.
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task

ORG_ID = os.environ.get("AIGW_ORG_ID", "")
HEADERS = {"X-User-Id": "load", "X-Org-Id": ORG_ID, "X-Org-Roles": "org-admin"}


class GatewayUser(HttpUser):
    wait_time = between(0.0, 0.1)

    @task(5)
    def healthz(self) -> None:
        self.client.get("/healthz")

    @task(2)
    def version(self) -> None:
        self.client.get("/api/v1/version")

    @task(3)
    def list_models(self) -> None:
        if ORG_ID:
            self.client.get("/api/v1/models", headers=HEADERS, name="/api/v1/models")
