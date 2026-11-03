"""AWS integration endpoints must work with no AWS account configured."""
from __future__ import annotations

import pytest


def test_status_reports_local_mode(client, auth):
    response = client.get("/api/aws/status", headers=auth)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is False
    assert body["storage_mode"] == "local"
    assert body["region"]
    assert set(body["configured"]) == {"aws_enabled", "credentials", "s3_bucket", "lambda_function", "athena_database", "cloudwatch"}
    assert "not configured" in body["message"].lower()


def test_athena_runs_against_sqlite_mirror(client, auth):
    response = client.post(
        "/api/aws/athena/query",
        headers=auth,
        json={"query": "SELECT COUNT(*) AS runs FROM test_runs;"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "local-sqlite"
    assert body["columns"] == ["runs"]
    assert len(body["rows"]) == 1
    assert int(body["rows"][0][0]) > 0
    assert body["scan_bytes" if "scan_bytes" in body else "scanned_bytes"] >= 0
    assert body["duration_ms"] >= 0


def test_athena_query_is_trimmed(client, auth):
    body = client.post(
        "/api/aws/athena/query",
        headers=auth,
        json={"query": "  select status, count(*) as n from test_runs group by status  "},
    ).json()

    assert body["query"] == "select status, count(*) as n from test_runs group by status"
    assert body["columns"] == ["status", "n"]
    assert body["rows"]


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM test_runs",
        "DROP TABLE users",
        "UPDATE users SET role = 'admin'",
        "INSERT INTO users (email) VALUES ('x')",
    ],
)
def test_athena_rejects_writes(client, auth, query):
    response = client.post("/api/aws/athena/query", headers=auth, json={"query": query})

    assert response.status_code == 400
    assert response.json()["detail"] == "Only SELECT / WITH statements are allowed"


def test_athena_invalid_sql_reports_bad_request(client, auth):
    response = client.post("/api/aws/athena/query", headers=auth, json={"query": "SELECT * FROM no_such_table"})

    assert response.status_code == 400
    assert response.json()["detail"]


def test_athena_requires_query(client, auth):
    assert client.post("/api/aws/athena/query", headers=auth, json={}).status_code == 422


def test_lambda_falls_back_locally(client, auth):
    response = client.post("/api/aws/lambda/invoke", headers=auth, json={"payload": {"scope": "latest"}})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "local-fallback"
    assert body["status_code"] == 200
    payload = body["payload"]
    assert payload["audit"] == "quality-snapshot"
    assert payload["requested"] == {"scope": "latest"}
    assert payload["latest_run"]
    assert payload["generated_at"].endswith("Z")
    assert isinstance(payload["open_data_failures"], int)


def test_cloudwatch_returns_local_mirror(client, auth):
    response = client.get("/api/aws/cloudwatch/metrics?days=14", headers=auth)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["mode"] == "local-mirror"
    assert body["metric"] == "ApiLatencyMs"
    assert body["namespace"]
    assert body["points"]
    for point in body["points"]:
        assert set(point) == {"timestamp", "value", "calls"}
        assert point["calls"] >= 1
        assert point["value"] >= 0


def test_artifact_upload_and_listing(client, auth, latest_run_key):
    upload = client.post(
        "/api/artifacts",
        headers=auth,
        files={"file": ("playwright-report.json", b'{"ok": true}', "application/json")},
        data={"run_key": latest_run_key},
    )

    assert upload.status_code == 201, upload.text
    artifact = upload.json()
    assert artifact["filename"] == "playwright-report.json"
    assert artifact["storage"] == "local"
    assert artifact["size_bytes"] == len(b'{"ok": true}')
    assert artifact["run_key"] == latest_run_key
    assert artifact["location"]

    listing = client.get("/api/artifacts", headers=auth)
    assert listing.status_code == 200
    body = listing.json()
    assert body["mode"] == "local"
    assert any(item["id"] == artifact["id"] for item in body["items"])


def test_artifact_filename_is_sanitised(client, auth):
    upload = client.post(
        "/api/artifacts",
        headers=auth,
        files={"file": ("../../etc/passwd", b"root:x:0:0", "text/plain")},
    )

    assert upload.status_code == 201
    filename = upload.json()["filename"]
    assert "/" not in filename
    assert ".." not in filename


def test_empty_artifact_is_rejected(client, auth):
    response = client.post("/api/artifacts", headers=auth, files={"file": ("empty.txt", b"", "text/plain")})

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty"


def test_aws_endpoints_require_auth(client):
    assert client.get("/api/aws/status").status_code == 401
    assert client.post("/api/aws/athena/query", json={"query": "SELECT 1"}).status_code == 401
    assert client.post("/api/aws/lambda/invoke", json={"payload": {}}).status_code == 401
    assert client.get("/api/aws/cloudwatch/metrics").status_code == 401
    assert client.get("/api/artifacts").status_code == 401
