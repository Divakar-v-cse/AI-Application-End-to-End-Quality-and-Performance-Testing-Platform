"""Test run history, pagination, filters and on-demand execution."""
from __future__ import annotations

import pytest


def test_run_history_is_paginated(client, auth):
    response = client.get("/api/runs?limit=5&offset=0", headers=auth)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["limit"] == 5
    assert payload["offset"] == 0
    assert len(payload["items"]) == 5
    assert payload["total"] >= 14


def test_second_page_does_not_repeat_the_first(client, auth):
    first = client.get("/api/runs?limit=3&offset=0", headers=auth).json()["items"]
    second = client.get("/api/runs?limit=3&offset=3", headers=auth).json()["items"]

    assert {row["run_key"] for row in first}.isdisjoint({row["run_key"] for row in second})


def test_runs_are_ordered_by_start_time(client, auth):
    items = client.get("/api/runs?limit=20", headers=auth).json()["items"]

    timestamps = [row["started_at"] for row in items]
    assert timestamps == sorted(timestamps, reverse=True)


def test_run_filters_are_applied(client, auth):
    api_runs = client.get("/api/runs?suite=api&limit=100", headers=auth).json()["items"]
    assert api_runs, "the seed should contain API executions"
    assert {row["suite"] for row in api_runs} == {"api"}

    passed = client.get("/api/runs?status=passed&limit=100", headers=auth).json()["items"]
    assert passed
    assert {row["status"] for row in passed} == {"passed"}


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_pagination_bounds_are_validated(client, auth, query):
    assert client.get(f"/api/runs?{query}", headers=auth).status_code == 422


def test_run_detail_includes_results_and_gates(client, auth, latest_run_key):
    response = client.get(f"/api/runs/{latest_run_key}", headers=auth)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["run"]["run_key"] == latest_run_key
    assert payload["results"], "a run detail must list its results"
    assert payload["gates"], "a run detail must list its quality gates"
    assert {gate["status"] for gate in payload["gates"]} <= {"passed", "failed", "not_applicable"}


def test_unknown_run_returns_404(client, auth):
    response = client.get("/api/runs/RUN-19700101-0000-XXXX", headers=auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Run RUN-19700101-0000-XXXX not found"


def test_results_can_be_filtered_by_suite(client, auth, latest_run_key):
    response = client.get(f"/api/runs/{latest_run_key}/results?suite=api", headers=auth)

    assert response.status_code == 200
    rows = response.json()
    assert all(row["suite"] == "api" for row in rows)


def test_database_suite_executes_every_sql_check(client, auth):
    response = client.post("/api/runs", headers=auth, json={"suite": "db"})

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["run"]["suite"] == "db"
    assert payload["run"]["total"] == 15
    assert payload["run"]["failed"] == 0
    assert payload["run"]["status"] == "passed"
    assert len(payload["results"]) == 15
    assert payload["run"]["trigger"].startswith("manual:")


@pytest.mark.slow
def test_api_suite_executes_live_contract_checks(client, auth):
    response = client.post("/api/runs", headers=auth, json={"suite": "api", "branch": "test"})

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["run"]["total"] == 17
    assert len(payload["results"]) == 17
    assert payload["run"]["branch"] == "test"
    failed = [row for row in payload["results"] if row["status"] != "passed"]
    assert len(failed) <= 1, f"live API checks failed: {[r['case_key'] for r in failed]}"
    # Successful API checks must record latency telemetry for the dashboard.
    metrics = client.get("/api/metrics/api?days=1", headers=auth).json()
    assert metrics["summary"]["calls"] >= 17


def test_ui_suite_reports_a_helpful_error_when_runner_is_disabled(client, auth):
    response = client.post("/api/runs", headers=auth, json={"suite": "ui"})

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "ENABLE_UI_RUNNER=true" in detail
    assert "/api/ingest/playwright" in detail


def test_performance_suite_without_results_is_skipped(client, auth):
    response = client.post("/api/runs", headers=auth, json={"suite": "perf"})

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["run"]["total"] == 0
    assert payload["run"]["status"] == "skipped"


def test_unknown_suite_is_rejected(client, auth):
    response = client.post("/api/runs", headers=auth, json={"suite": "security"})

    assert response.status_code == 422


def test_run_creation_requires_authentication(client):
    assert client.post("/api/runs", json={"suite": "db"}).status_code == 401
