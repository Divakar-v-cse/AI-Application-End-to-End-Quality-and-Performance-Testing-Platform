"""Quality dashboard aggregates, trends and the test catalog."""
from __future__ import annotations

import datetime as dt

REQUIRED_SUMMARY_FIELDS = {
    "generated_at",
    "total_tests",
    "passed",
    "failed",
    "skipped",
    "pass_rate",
    "suites",
    "avg_api_ms",
    "p95_api_ms",
    "avg_page_load_ms",
    "load_error_rate",
    "load_rps",
    "data_failures",
    "data_checks",
    "active_gates_failed",
    "endpoint_latency",
    "recent_runs",
}


def test_summary_exposes_every_dashboard_kpi(client, auth):
    response = client.get("/api/dashboard/summary", headers=auth)

    assert response.status_code == 200, response.text
    payload = response.json()
    missing = REQUIRED_SUMMARY_FIELDS - payload.keys()
    assert not missing, f"dashboard summary is missing {sorted(missing)}"


def test_summary_numbers_are_internally_consistent(client, auth):
    payload = client.get("/api/dashboard/summary", headers=auth).json()

    assert payload["total_tests"] == payload["passed"] + payload["failed"] + payload["skipped"]
    assert 0 <= payload["pass_rate"] <= 100
    assert payload["avg_api_ms"] >= 0
    assert payload["data_failures"] >= 0
    assert payload["active_gates_failed"] >= 0


def test_suites_cover_the_four_quality_dimensions(client, auth):
    payload = client.get("/api/dashboard/summary", headers=auth).json()

    suites = payload["suites"]
    assert {"api", "ui", "db"}.issubset(suites.keys())
    for name, stats in suites.items():
        assert {"total", "passed", "failed", "pass_rate"} <= stats.keys(), name
        assert stats["total"] == stats["passed"] + stats["failed"] + stats["skipped"]


def test_recent_runs_are_newest_first(client, auth):
    payload = client.get("/api/dashboard/summary", headers=auth).json()

    runs = payload["recent_runs"]
    assert runs, "the seeded demo must expose historical executions"
    assert len(runs) <= 8
    timestamps = [run["started_at"] for run in runs]
    assert timestamps == sorted(timestamps, reverse=True)


def test_endpoint_latency_is_ranked(client, auth):
    payload = client.get("/api/dashboard/summary", headers=auth).json()

    endpoints = payload["endpoint_latency"]
    assert endpoints, "API telemetry should be aggregated per endpoint"
    assert len(endpoints) <= 8
    for row in endpoints:
        assert {"endpoint", "avg_ms", "p95_ms", "calls"} <= row.keys()
        assert row["calls"] >= 1
        assert row["p95_ms"] >= 0


def test_trend_defaults_to_fourteen_days(client, auth):
    response = client.get("/api/dashboard/trend", headers=auth)

    assert response.status_code == 200, response.text
    points = response.json()
    assert len(points) == 14
    for point in points:
        assert {"date", "total", "passed", "failed", "pass_rate"} <= point.keys()
        dt.date.fromisoformat(point["date"])  # raises if not ISO-8601


def test_trend_window_is_parameterised(client, auth):
    response = client.get("/api/dashboard/trend?days=7", headers=auth)

    assert response.status_code == 200
    points = response.json()
    assert len(points) == 7
    dates = [point["date"] for point in points]
    assert dates == sorted(dates)
    assert dates[-1] == dt.datetime.utcnow().date().isoformat()


def test_trend_window_bounds_are_enforced(client, auth):
    assert client.get("/api/dashboard/trend?days=0", headers=auth).status_code == 422
    assert client.get("/api/dashboard/trend?days=91", headers=auth).status_code == 422


def test_dashboard_requires_authentication(client):
    assert client.get("/api/dashboard/summary").status_code == 401
    assert client.get("/api/dashboard/trend").status_code == 401


def test_catalog_lists_every_automated_case(client, auth):
    response = client.get("/api/tests/catalog", headers=auth)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == len(payload["items"]) == 43
    assert payload["by_suite"] == {"api": 17, "ui": 11, "db": 15}


def test_catalog_items_expose_execution_metadata(client, auth):
    items = client.get("/api/tests/catalog", headers=auth).json()["items"]

    keys = {item["key"] for item in items}
    assert len(keys) == len(items), "catalog keys must be unique"
    for item in items:
        assert {"key", "suite", "module", "severity", "enabled", "executor"} <= item.keys()
        assert item["suite"] in {"api", "ui", "db"}
        assert item["severity"] in {"critical", "major", "minor"}


def test_catalog_documents_the_required_ui_journeys(client, auth):
    items = client.get("/api/tests/catalog", headers=auth).json()["items"]
    ui_modules = {item["module"] for item in items if item["suite"] == "ui"}

    assert {"login", "navigation", "forms", "dashboard", "errors", "chatbot"} <= ui_modules
