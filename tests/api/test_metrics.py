"""API and browser telemetry endpoints used by the dashboard charts."""
from __future__ import annotations

import pytest


def test_api_metrics_summary_contract(client, auth):
    response = client.get("/api/metrics/api", headers=auth)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"items", "summary", "by_endpoint"}
    summary = body["summary"]
    assert set(summary) == {"calls", "avg_ms", "p95_ms", "p99_ms", "max_ms", "error_rate", "window_days"}
    assert summary["window_days"] == 7


def test_api_metrics_window_is_configurable(client, auth):
    body = client.get("/api/metrics/api?days=30", headers=auth).json()

    assert body["summary"]["window_days"] == 30


def test_api_metrics_percentiles_are_ordered(client, auth):
    summary = client.get("/api/metrics/api", headers=auth).json()["summary"]

    assert summary["avg_ms"] <= summary["p95_ms"] <= summary["p99_ms"] <= summary["max_ms"]


def test_api_metrics_items_are_bounded_by_limit(client, auth):
    body = client.get("/api/metrics/api?limit=5", headers=auth).json()

    assert len(body["items"]) <= 5
    # "calls" counts every sample in the window, not only the returned page.
    assert body["summary"]["calls"] >= len(body["items"])


def test_api_metrics_by_endpoint_is_ranked(client, auth):
    body = client.get("/api/metrics/api", headers=auth).json()

    by_endpoint = body["by_endpoint"]
    calls = [row["calls"] for row in by_endpoint]
    assert calls == sorted(calls, reverse=True)
    for row in by_endpoint:
        assert set(row) == {"endpoint", "avg_ms", "p95_ms", "calls"}
        assert row["avg_ms"] <= row["p95_ms"]
        assert row["endpoint"].startswith("/")


def test_api_metrics_items_are_newest_first(client, auth):
    items = client.get("/api/metrics/api?limit=20", headers=auth).json()["items"]

    timestamps = [row["created_at"] for row in items]
    assert timestamps == sorted(timestamps, reverse=True)


def test_page_metrics_summary_contract(client, auth):
    response = client.get("/api/metrics/pages", headers=auth)

    assert response.status_code == 200, response.text
    body = response.json()
    summary = body["summary"]
    assert set(summary) == {"samples", "avg_ms", "p95_ms", "slowest_ms", "budget_ms", "window_days"}
    assert summary["budget_ms"] == 3000
    assert summary["samples"] == len(body["items"])
    assert summary["avg_ms"] <= summary["p95_ms"] <= summary["slowest_ms"]


def test_page_metrics_by_page_sorted_by_slowest(client, auth):
    body = client.get("/api/metrics/pages", headers=auth).json()

    averages = [row["avg_ms"] for row in body["by_page"]]
    assert averages == sorted(averages, reverse=True)
    for row in body["by_page"]:
        assert set(row) == {"page", "avg_ms", "samples"}
        assert row["samples"] >= 1


def test_page_metrics_respect_budget_breach(client, auth):
    """Seeded slow pages must be visible so the dashboard can flag them."""
    body = client.get("/api/metrics/pages?days=90", headers=auth).json()

    assert body["summary"]["slowest_ms"] > 0
    assert any(row["page"].startswith("/") for row in body["by_page"])


@pytest.mark.parametrize(
    "url",
    [
        "/api/metrics/api?days=0",
        "/api/metrics/api?days=91",
        "/api/metrics/api?limit=0",
        "/api/metrics/api?limit=1001",
        "/api/metrics/pages?days=0",
        "/api/metrics/pages?days=91",
    ],
)
def test_metrics_query_validation(client, auth, url):
    assert client.get(url, headers=auth).status_code == 422


def test_metrics_require_auth(client):
    assert client.get("/api/metrics/api").status_code == 401
    assert client.get("/api/metrics/pages").status_code == 401
