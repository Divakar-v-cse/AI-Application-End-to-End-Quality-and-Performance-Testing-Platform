"""Quality gate evaluation: configuration, thresholds and pass/fail behaviour."""
from __future__ import annotations

import pytest

EXPECTED_KEYS = [
    "overall_pass_rate",
    "api_pass_rate",
    "ui_pass_rate",
    "data_pass_rate",
    "api_p95_latency",
    "page_load_budget",
    "load_error_rate",
    "data_failures",
    "test_volume",
]


def test_gate_configuration_contract(client, auth):
    body = client.get("/api/quality-gates", headers=auth).json()

    config = body["config"]
    assert [row["key"] for row in config] == EXPECTED_KEYS
    for row in config:
        assert set(row) == {"key", "name", "operator", "threshold", "blocking", "unit"}
        assert row["operator"] in {">=", "<="}

    thresholds = {row["key"]: row["threshold"] for row in config}
    assert thresholds["overall_pass_rate"] == 95.0
    assert thresholds["api_pass_rate"] == 95.0
    assert thresholds["ui_pass_rate"] == 90.0
    assert thresholds["data_pass_rate"] == 100.0
    assert thresholds["api_p95_latency"] == 800.0
    assert thresholds["page_load_budget"] == 3000.0
    assert thresholds["load_error_rate"] == 1.0
    assert thresholds["data_failures"] == 0.0
    assert thresholds["test_volume"] == 20.0

    blocking = {row["key"]: row["blocking"] for row in config}
    assert blocking["test_volume"] is False
    assert sum(1 for value in blocking.values() if value) == 8


def test_gate_payload_shape(client, auth):
    body = client.get("/api/quality-gates", headers=auth).json()

    assert set(body) == {"config", "latest_run", "latest_status", "evaluated_at", "items", "blocked", "recent_failures"}
    assert isinstance(body["blocked"], bool)
    assert body["latest_run"]
    assert body["latest_status"] in {"passed", "failed", "skipped", "running"}
    for item in body["items"]:
        assert set(item) >= {"gate_key", "name", "metric", "operator", "threshold", "actual", "status", "blocking", "message"}
        assert item["status"] in {"passed", "failed", "not_applicable"}
    expected_blocked = any(i["status"] == "failed" and i["blocking"] for i in body["items"])
    assert body["blocked"] is expected_blocked


def test_gate_history_is_bounded(client, auth):
    body = client.get("/api/quality-gates?limit=3", headers=auth).json()

    assert len(body["recent_failures"]) <= 3
    for failure in body["recent_failures"]:
        assert set(failure) == {"run_key", "gate", "actual", "threshold", "at"}


def test_data_run_satisfies_data_gates(client, auth):
    """A clean database-suite run must satisfy every data gate."""
    created = client.post("/api/runs", headers=auth, json={"suite": "db", "branch": "main"})
    assert created.status_code == 201, created.text
    run_key = created.json()["run"]["run_key"]

    gates = client.post(f"/api/quality-gates/evaluate/{run_key}", headers=auth)
    assert gates.status_code == 200, gates.text
    by_key = {gate["gate_key"]: gate for gate in gates.json()}

    assert set(by_key) == set(EXPECTED_KEYS)
    assert by_key["data_pass_rate"]["status"] == "passed"
    assert by_key["data_pass_rate"]["actual"] == 100.0
    assert by_key["data_failures"]["status"] == "passed"
    assert by_key["data_failures"]["actual"] == 0.0
    assert by_key["overall_pass_rate"]["status"] == "passed"
    assert by_key["test_volume"]["status"] == "passed"

    # Suites with no results are reported as not_applicable rather than failing.
    assert by_key["api_pass_rate"]["status"] == "not_applicable"
    assert by_key["ui_pass_rate"]["status"] == "not_applicable"


def test_evaluate_replaces_gates_without_duplicating(client, auth, db):
    from app.models import QualityGate, TestRun

    created = client.post("/api/runs", headers=auth, json={"suite": "db"})
    run_key = created.json()["run"]["run_key"]

    client.post(f"/api/quality-gates/evaluate/{run_key}", headers=auth)
    client.post(f"/api/quality-gates/evaluate/{run_key}", headers=auth)

    run = db.query(TestRun).filter(TestRun.run_key == run_key).one()
    count = db.query(QualityGate).filter(QualityGate.run_id == run.id).count()
    assert count == len(EXPECTED_KEYS)


def test_failing_run_blocks_pipeline(client, auth, db):
    """A run with injected failures must fail the blocking gates."""
    from app.models import QualityGate, TestResult, TestRun
    from app.services import gates as gate_service

    created = client.post("/api/runs", headers=auth, json={"suite": "db"})
    run_key = created.json()["run"]["run_key"]

    run = db.query(TestRun).filter(TestRun.run_key == run_key).one()
    victim = db.query(TestResult).filter(TestResult.run_id == run.id).first()
    victim.status = "failed"
    victim.error_message = "injected failure for gate verification"
    db.commit()

    gates = gate_service.replace_gates(db, run)
    statuses = {gate.gate_key: gate.status for gate in gates}
    assert statuses["data_pass_rate"] == "failed"
    assert statuses["overall_pass_rate"] == "failed"
    assert gate_service.run_is_blocked(gates) is True

    body = client.get("/api/quality-gates", headers=auth).json()
    assert body["blocked"] is True

    # Restore the row so later tests still see a clean database.
    victim.status = "passed"
    victim.error_message = ""
    db.commit()
    gate_service.replace_gates(db, run)


def test_evaluate_unknown_run_404(client, auth):
    response = client.post("/api/quality-gates/evaluate/RUN-19990101-0000-NONE", headers=auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Run RUN-19990101-0000-NONE not found"


@pytest.mark.parametrize("limit", [0, 51])
def test_gate_limit_bounds(client, auth, limit):
    assert client.get(f"/api/quality-gates?limit={limit}", headers=auth).status_code == 422


def test_gates_require_auth(client):
    assert client.get("/api/quality-gates").status_code == 401
    assert client.post("/api/quality-gates/evaluate/RUN-ANY").status_code == 401
