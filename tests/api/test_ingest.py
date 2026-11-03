"""CI ingestion endpoints: JUnit XML, Playwright JSON, Locust stats, page timings."""
from __future__ import annotations

import json

import pytest

JUNIT_OK = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="ci" tests="4" failures="1" errors="1" skipped="1">
  <testsuite name="api" tests="4">
    <testcase classname="tests.api.test_auth" name="login works" time="0.120" />
    <testcase classname="tests.api.test_auth" name="login fails" time="0.250">
      <failure message="expected 401">AssertionError: expected 401</failure>
    </testcase>
    <testcase classname="tests.api.test_runs" name="runs explode" time="0.010">
      <error message="boom">RuntimeError: boom</error>
    </testcase>
    <testcase classname="tests.api.test_runs" name="pagination skipped" time="0.000">
      <skipped message="not implemented" />
    </testcase>
  </testsuite>
</testsuites>
"""


def test_ingest_junit_maps_every_status(client, auth):
    response = client.post(
        "/api/ingest/junit?suite=api&branch=main&commit=deadbeef",
        headers={**auth, "Content-Type": "application/xml"},
        content=JUNIT_OK.encode(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ingested"] == 4
    run = body["run"]
    assert run["total"] == 4
    assert run["source"] == "junit"
    assert run["trigger"] == "ci"
    assert run["commit_sha"] == "deadbeef"
    assert (run["passed"], run["failed"], run["skipped"]) == (1, 2, 1)


def test_ingest_junit_accepts_multipart_upload(client, auth):
    response = client.post(
        "/api/ingest/junit",
        headers=auth,
        files={"file": ("junit.xml", JUNIT_OK.encode(), "application/xml")},
    )

    assert response.status_code == 200, response.text
    assert response.json()["ingested"] == 4


def test_ingest_junit_rejects_malformed_xml(client, auth):
    response = client.post(
        "/api/ingest/junit",
        headers={**auth, "Content-Type": "application/xml"},
        content=b"<testsuites><oops>",
    )

    assert response.status_code == 400
    assert "Invalid JUnit XML" in response.json()["detail"]


def test_ingest_rejects_empty_body(client, auth):
    response = client.post("/api/ingest/junit", headers={**auth, "Content-Type": "application/xml"}, content=b"")

    assert response.status_code == 400
    assert response.json()["detail"] == "Empty request body"


def test_ingest_multipart_without_file_part(client, auth):
    response = client.post("/api/ingest/junit", headers=auth, data={"suite": "api"})

    assert response.status_code == 400
    assert "No file part" in response.json()["detail"]


PLAYWRIGHT_OK = {
    "suites": [
        {
            "title": "login.spec.js",
            "file": "tests/ui/login.spec.js",
            "specs": [
                {
                    "title": "valid credentials reach the dashboard",
                    "tests": [{"results": [{"status": "passed", "duration": 1200}]}],
                },
                {
                    "title": "invalid credentials show an error",
                    "tests": [
                        {
                            "results": [
                                {
                                    "status": "failed",
                                    "duration": 800,
                                    "error": {"message": "expect(locator).toBeVisible() failed"},
                                }
                            ]
                        }
                    ],
                },
                {
                    "title": "timeout is treated as a failure",
                    "tests": [{"results": [{"status": "timedOut", "duration": 30000}]}],
                },
                {"title": "skipped spec", "tests": [{"results": [{"status": "skipped", "duration": 0}]}]},
            ],
        },
        {
            "title": "chat.spec.js",
            "file": "tests/ui/chat.spec.js",
            "specs": [
                {"title": "assistant replies", "tests": [{"results": [{"status": "passed", "duration": 2200}]}]}
            ],
        },
    ]
}


def test_ingest_playwright_report(client, auth):
    response = client.post(
        "/api/ingest/playwright",
        headers={**auth, "Content-Type": "application/json"},
        content=json.dumps(PLAYWRIGHT_OK).encode(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ingested"] == 5
    run = body["run"]
    assert run["suite"] == "ui"
    assert run["source"] == "playwright"
    assert run["total"] == 5
    # timedOut is normalised to failed, so two specs fail in total.
    assert run["failed"] == 2
    assert run["skipped"] == 1
    assert run["passed"] == 2


def test_ingest_playwright_case_keys_follow_convention(client, auth):
    response = client.post(
        "/api/ingest/playwright",
        headers={**auth, "Content-Type": "application/json"},
        content=json.dumps(PLAYWRIGHT_OK).encode(),
    )
    run_key = response.json()["run"]["run_key"]

    detail = client.get(f"/api/runs/{run_key}?suite=ui", headers=auth)
    assert detail.status_code == 200
    keys = [row["case_key"] for row in detail.json()["results"]]

    assert "ui.login.valid credentials reach the dashboard" in keys
    assert all(key.startswith("ui.") for key in keys)
    assert all(len(key) <= 80 for key in keys)


def test_ingest_playwright_rejects_invalid_json(client, auth):
    response = client.post(
        "/api/ingest/playwright",
        headers={**auth, "Content-Type": "application/json"},
        content=b"{not json",
    )

    assert response.status_code == 400
    assert "Invalid JSON" in response.json()["detail"]


LOCUST_RAW = {
    "target": "http://localhost:8000",
    "users": 25,
    "spawn_rate": 5,
    "duration_s": 60,
    "total_rps": 145.5,
    "stats": [
        {
            "name": "GET /api/dashboard/summary",
            "num_requests": 8000,
            "num_failures": 40,
            "avg_response_time": 120,
            "median_response_time": 110,
            "p95": 260,
            "p99": 400,
            "max_response_time": 900,
        },
        {
            "name": "POST /api/chat",
            "num_requests": 2000,
            "num_failures": 20,
            "avg_response_time": 340,
            "median_response_time": 300,
            "p95": 700,
            "p99": 1100,
            "max_response_time": 2400,
        },
    ],
}


def test_ingest_locust_raw_stats(client, auth):
    response = client.post(
        "/api/ingest/locust",
        headers={**auth, "Content-Type": "application/json"},
        content=json.dumps(LOCUST_RAW).encode(),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requests"] == 10000
    assert body["error_rate"] == pytest.approx(0.6, abs=0.01)
    assert body["status"] == "passed"
    assert body["run_key"].startswith("LOAD-")


def test_ingest_locust_normalised_summary(client, auth):
    response = client.post(
        "/api/ingest/locust",
        headers={**auth, "Content-Type": "application/json"},
        content=json.dumps(
            {"requests": 1000, "failures": 50, "avg_ms": 200, "p95_ms": 500, "rps": 20, "users": 10}
        ).encode(),
    )

    assert response.status_code == 200, response.text
    assert response.json()["error_rate"] == pytest.approx(5.0)
    assert response.json()["status"] == "failed"


def test_ingest_locust_rejects_invalid_json(client, auth):
    response = client.post(
        "/api/ingest/locust",
        headers={**auth, "Content-Type": "application/json"},
        content=b"not-json",
    )

    assert response.status_code == 400
    assert "Invalid JSON" in response.json()["detail"]


def test_ingest_page_metrics(client, auth, latest_run_key):
    response = client.post(
        "/api/ingest/page-metrics",
        headers=auth,
        json={
            "run_key": latest_run_key,
            "items": [
                {"page": "/dashboard", "load_time_ms": 1450, "ttfb_ms": 120, "dom_interactive_ms": 900},
                {"page": "/chat", "load_time_ms": 2100, "ttfb_ms": 180},
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"ingested": 2, "run_key": latest_run_key}


@pytest.mark.parametrize(
    "items",
    [
        [{"page": "/dashboard", "load_time_ms": 0}],
        [{"page": "/dashboard", "load_time_ms": -5}],
        [{"page": "", "load_time_ms": 100}],
        [{"page": "/x", "load_time_ms": 100, "ttfb_ms": -1}],
    ],
)
def test_ingest_page_metrics_validates_payload(client, auth, items):
    response = client.post("/api/ingest/page-metrics", headers=auth, json={"items": items})

    assert response.status_code == 422


def test_ingest_endpoints_require_auth(client):
    assert client.post("/api/ingest/junit", content=b"<testsuites/>").status_code == 401
    assert client.post("/api/ingest/playwright", content=b"{}").status_code == 401
    assert client.post("/api/ingest/locust", content=b"{}").status_code == 401
    assert client.post("/api/ingest/page-metrics", json={"items": []}).status_code == 401
