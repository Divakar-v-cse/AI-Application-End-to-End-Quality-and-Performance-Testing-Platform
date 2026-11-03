"""OpenAPI contract validation.

The published schema is the contract between the backend and every consumer
(React dashboard, Postman collection, CI). These tests assert the document is
complete and that live responses actually validate against it.
"""
from __future__ import annotations

import pytest

jsonschema = pytest.importorskip("jsonschema")

REQUIRED_PATH_PREFIXES = {
    "/healthz",
    "/api/auth/login",
    "/api/auth/me",
    "/api/dashboard/summary",
    "/api/dashboard/trend",
    "/api/runs",
    "/api/runs/{run_key}",
    "/api/reports/{run_key}/{fmt}",
    "/api/chat",
    "/api/demo/overview",
    "/api/demo/evaluations",
    "/api/metrics/api",
    "/api/metrics/pages",
    "/api/data-quality/checks",
    "/api/data-quality/run",
    "/api/performance/runs",
    "/api/quality-gates",
    "/api/aws/status",
    "/api/aws/athena/query",
    "/api/aws/lambda/invoke",
    "/api/artifacts",
    "/api/ingest/junit",
    "/api/ingest/playwright",
    "/api/ingest/locust",
    "/api/ingest/page-metrics",
}


def _deref(node, spec, depth=0):
    """Inline local ``$ref`` pointers so jsonschema can validate without a registry."""
    if depth > 12:
        return node
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            target = spec
            for part in ref[2:].split("/"):
                target = target[part]
            return _deref(target, spec, depth + 1)
        return {key: _deref(value, spec, depth + 1) for key, value in node.items()}
    if isinstance(node, list):
        return [_deref(item, spec, depth + 1) for item in node]
    return node


def _response_schema(spec, path, method, status_code=200):
    operation = spec["paths"][path][method]
    content = operation["responses"][str(status_code)]["content"]
    return _deref(content["application/json"]["schema"], spec)


def _validate(payload, schema):
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator_cls(schema).validate(payload)


@pytest.fixture(scope="module")
def spec(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_openapi_document_metadata(spec):
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"]
    assert spec["info"]["version"] == "1.0.0"
    assert spec.get("tags")


def test_openapi_documents_every_feature_area(spec):
    documented = set(spec["paths"])
    missing = sorted(REQUIRED_PATH_PREFIXES - documented)

    assert not missing, f"Undocumented endpoints: {missing}"
    assert len(documented) >= 24


def test_openapi_declares_bearer_security(spec):
    schemes = spec.get("components", {}).get("securitySchemes", {})

    bearer = [
        value
        for value in schemes.values()
        if value.get("type") == "http" and value.get("scheme") == "bearer"
    ]
    assert bearer, f"No bearer scheme declared: {schemes}"

    chat = spec["paths"]["/api/chat"]["post"]
    assert chat.get("security"), "POST /api/chat must declare a security requirement"


def test_openapi_protected_endpoints_are_marked(spec):
    for path in ("/api/dashboard/summary", "/api/runs", "/api/quality-gates"):
        operation = spec["paths"][path]["get"]
        assert operation.get("security"), f"{path} must be documented as protected"


def test_dashboard_response_matches_schema(client, auth, spec):
    payload = client.get("/api/dashboard/summary", headers=auth).json()

    _validate(payload, _response_schema(spec, "/api/dashboard/summary", "get"))


def test_run_list_response_matches_schema(client, auth, spec):
    payload = client.get("/api/runs?limit=2", headers=auth).json()

    _validate(payload, _response_schema(spec, "/api/runs", "get"))


def test_gates_response_matches_schema(client, auth, spec):
    payload = client.get("/api/quality-gates", headers=auth).json()

    _validate(payload, _response_schema(spec, "/api/quality-gates", "get"))


def test_login_response_matches_schema(client, spec):
    from app.config import settings

    payload = client.post(
        "/api/auth/login",
        json={"email": settings.demo_user_email, "password": settings.demo_user_password},
    ).json()

    _validate(payload, _response_schema(spec, "/api/auth/login", "post"))


def test_chat_reply_matches_schema(client, auth, spec):
    payload = client.post("/api/chat", headers=auth, json={"message": "openapi contract check"}).json()

    _validate(payload, _response_schema(spec, "/api/chat", "post"))


def test_data_quality_response_matches_schema(client, auth, spec):
    payload = client.get("/api/data-quality/checks", headers=auth).json()

    _validate(payload, _response_schema(spec, "/api/data-quality/checks", "get"))


def test_schema_rejects_contract_drift(client, auth, spec):
    """Guard against the validator silently accepting anything."""
    schema = _response_schema(spec, "/api/dashboard/summary", "get")
    broken = {"total_tests": 1}

    with pytest.raises(jsonschema.exceptions.ValidationError):
        _validate(broken, schema)
