"""Liveness, docs redirect and 404 behaviour."""
from __future__ import annotations

import time


def test_healthz_reports_ok_and_reachable_database(client):
    started = time.perf_counter()
    response = client.get("/healthz")
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "ai-quality-platform"
    assert payload["version"] == "1.0.0"
    assert payload["environment"] == "test"
    assert elapsed_ms < 800, f"/healthz took {elapsed_ms:.0f} ms (budget 800 ms)"


def test_root_redirects_to_swagger_ui(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] in {"/docs", "http://testserver/docs"}


def test_swagger_and_redoc_are_served(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_unknown_route_returns_404_not_500(client, auth):
    response = client.get("/api/this-route-does-not-exist", headers=auth)

    assert response.status_code == 404
    assert "detail" in response.json()


def test_healthz_needs_no_authentication(client):
    assert client.get("/healthz").status_code == 200
