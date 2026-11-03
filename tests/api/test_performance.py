"""Locust result history and load-test budget surfacing."""
from __future__ import annotations

import pytest


def test_load_run_history_contract(client, auth):
    response = client.get("/api/performance/runs", headers=auth)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"items", "summary", "trend"}
    summary = body["summary"]
    assert set(summary) == {
        "runs",
        "latest_run",
        "latest_users",
        "avg_rps",
        "worst_error_rate",
        "p95_budget_ms",
        "error_budget",
    }
    assert summary["p95_budget_ms"] == 1500
    assert summary["runs"] == len(body["items"])
    assert summary["latest_run"] == body["items"][0]["run_key"]


def test_load_run_history_is_newest_first(client, auth):
    items = client.get("/api/performance/runs?limit=5", headers=auth).json()["items"]

    assert items
    timestamps = [row["created_at"] for row in items]
    assert timestamps == sorted(timestamps, reverse=True)


def test_load_trend_is_chronological(client, auth):
    body = client.get("/api/performance/runs", headers=auth).json()

    trend = body["trend"]
    assert len(trend) == len(body["items"])
    assert trend[-1]["run_key"] == body["items"][0]["run_key"]
    assert set(trend[0]) == {"run_key", "created_at", "users", "rps", "p95_ms", "error_rate"}


def test_load_summary_aggregates_are_derived(client, auth):
    body = client.get("/api/performance/runs", headers=auth).json()
    items = body["items"]

    assert body["summary"]["latest_users"] == items[0]["users"]
    assert body["summary"]["worst_error_rate"] == pytest.approx(max(row["error_rate"] for row in items), abs=0.01)
    assert body["summary"]["avg_rps"] == pytest.approx(
        round(sum(row["rps"] for row in items) / len(items), 2), abs=0.01
    )


def test_record_load_run_creates_result(client, auth):
    response = client.post(
        "/api/performance/runs",
        headers=auth,
        json={
            "target": "http://localhost:5173",
            "scenario": "dashboard_reads",
            "users": 40,
            "spawn_rate": 4,
            "duration_s": 120,
            "requests": 5000,
            "failures": 25,
            "rps": 41.6,
            "avg_ms": 210,
            "median_ms": 190,
            "p95_ms": 480,
            "p99_ms": 760,
            "max_ms": 1800,
            "notes": "pytest sample load test",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["run_key"].startswith("LOAD-")
    assert body["users"] == 40
    assert body["requests"] == 5000
    assert body["failures"] == 25
    assert body["error_rate"] == pytest.approx(0.5)
    assert body["status"] == "passed"
    assert body["scenario"] == "dashboard_reads"

    fetched = client.get(f"/api/performance/runs/{body['run_key']}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["run_key"] == body["run_key"]


def test_record_load_run_over_budget_fails(client, auth):
    response = client.post(
        "/api/performance/runs",
        headers=auth,
        json={"users": 100, "spawn_rate": 10, "duration_s": 60, "requests": 1000, "failures": 80, "rps": 16},
    )

    assert response.status_code == 201
    assert response.json()["error_rate"] == pytest.approx(8.0)
    assert response.json()["status"] == "failed"


def test_record_load_run_without_traffic_is_skipped(client, auth):
    response = client.post(
        "/api/performance/runs",
        headers=auth,
        json={"users": 5, "spawn_rate": 1, "duration_s": 10, "requests": 0, "failures": 0},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "skipped"
    assert response.json()["error_rate"] == 0.0


@pytest.mark.parametrize(
    "payload",
    [
        {"users": 0},
        {"users": 5001},
        {"spawn_rate": 0},
        {"spawn_rate": -1},
        {"duration_s": 0},
        {"duration_s": 7201},
        {"requests": -1},
        {"failures": -5},
        {"p95_ms": -1},
        {"target": "x" * 201},
    ],
)
def test_record_load_run_validates_bounds(client, auth, payload):
    response = client.post("/api/performance/runs", headers=auth, json=payload)

    assert response.status_code == 422, response.text


def test_load_run_detail_404(client, auth):
    response = client.get("/api/performance/runs/LOAD-NOPE-0000", headers=auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Load test LOAD-NOPE-0000 not found"


def test_load_endpoints_require_auth(client):
    assert client.get("/api/performance/runs").status_code == 401
    assert client.get("/api/performance/runs/LOAD-ANY").status_code == 401
    assert client.post("/api/performance/runs", json={"users": 1}).status_code == 401
