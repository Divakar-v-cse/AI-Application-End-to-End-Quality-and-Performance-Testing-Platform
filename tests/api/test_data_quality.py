"""SQL / data-quality validation endpoints."""
from __future__ import annotations

import pytest

EXPECTED_TABLES = {
    "users",
    "test_runs",
    "test_results",
    "test_cases",
    "evaluation_results",
    "api_metrics",
    "page_metrics",
    "load_test_runs",
    "chat_messages",
}


def test_check_catalog(client, auth):
    response = client.get("/api/data-quality/checks", headers=auth)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"items", "summary"}
    assert len(body["items"]) == 15

    keys = [item["check_key"] for item in body["items"]]
    assert len(set(keys)) == 15
    for item in body["items"]:
        assert set(item) >= {"check_key", "name", "table_name", "severity", "status", "failing_rows", "query", "message"}
        assert item["table_name"] in EXPECTED_TABLES
        assert item["severity"] in {"critical", "major", "minor"}
        assert item["query"].strip().upper().startswith("SELECT")


def test_summary_matches_items(client, auth):
    body = client.get("/api/data-quality/checks", headers=auth).json()
    summary = body["summary"]

    assert set(summary) == {"total", "passed", "failed", "rows_scanned", "severity_counts", "run_key", "checked_at"}
    assert summary["total"] == len(body["items"])
    assert summary["passed"] + summary["failed"] == summary["total"]
    assert summary["run_key"]
    assert summary["rows_scanned"] == sum(item["total_rows"] for item in body["items"])


def test_seeded_database_is_clean(client, auth):
    body = client.get("/api/data-quality/checks", headers=auth).json()

    assert body["summary"]["failed"] == 0
    assert all(item["status"] == "passed" for item in body["items"])
    assert all(item["failing_rows"] == 0 for item in body["items"])


def test_run_checks_executes_every_query(client, auth):
    response = client.post("/api/data-quality/run", headers=auth)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"run", "items", "failed"}
    assert body["failed"] == 0
    assert len(body["items"]) == 15
    assert body["run"]["suite"] == "db"
    assert body["run"]["trigger"].startswith("data-quality:")
    assert body["run"]["total"] == 15
    assert body["run"]["status"] == "passed"


def test_run_checks_records_durations(client, auth):
    items = client.post("/api/data-quality/run", headers=auth).json()["items"]

    for item in items:
        assert item["duration_ms"] >= 0
        assert item["message"]


def test_history_contract(client, auth):
    body = client.get("/api/data-quality/history?limit=5", headers=auth).json()

    assert set(body) == {"items"}
    assert 0 < len(body["items"]) <= 5
    for point in body["items"]:
        assert set(point) == {"run_key", "checked_at", "checks", "failed", "pass_rate"}
        assert point["checks"] == 15
        assert point["pass_rate"] == pytest.approx((point["checks"] - point["failed"]) / point["checks"] * 100, abs=0.01)

    timestamps = [point["checked_at"] for point in body["items"]]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.parametrize("limit", [0, 51])
def test_history_limit_bounds(client, auth, limit):
    assert client.get(f"/api/data-quality/history?limit={limit}", headers=auth).status_code == 422


def test_data_quality_requires_auth(client):
    assert client.get("/api/data-quality/checks").status_code == 401
    assert client.post("/api/data-quality/run").status_code == 401
    assert client.get("/api/data-quality/history").status_code == 401
