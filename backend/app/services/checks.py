"""Executable quality checks.

Two kinds of checks exist:

* API checks run against the live ASGI application through ``httpx`` and assert
  status codes, contract shape, auth behaviour and latency budgets.
* Database checks are real SQL queries (see ``sql/validation_queries.sql``) that
  return offending rows. A check passes when the offending row count is zero.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_SAMPLE_ROWS = 5


class CheckFailure(AssertionError):
    """Raised when an executable check fails."""


# --------------------------------------------------------------- API checks
@dataclass
class ApiContext:
    client: httpx.AsyncClient
    token: str = ""
    conversation_id: str = ""
    latencies: dict[str, float] = field(default_factory=dict)

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def call(
        self,
        method: str,
        url: str,
        *,
        expect: int | tuple[int, ...] = 200,
        auth: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        if auth:
            headers.update(self.auth_headers())
        started = time.perf_counter()
        response = await self.client.request(method, url, headers=headers, **kwargs)
        elapsed = round((time.perf_counter() - started) * 1000, 2)
        self.latencies[url] = elapsed
        expected = (expect,) if isinstance(expect, int) else expect
        if response.status_code not in expected:
            raise CheckFailure(
                f"{method} {url} returned {response.status_code}, expected {expected}: {response.text[:300]}"
            )
        return response


def _json(response: httpx.Response) -> dict:
    try:
        return response.json()
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise CheckFailure(f"Response is not valid JSON: {exc}") from exc


async def check_health(ctx: ApiContext) -> str:
    payload = _json(await ctx.call("GET", "/healthz"))
    if payload.get("status") != "ok":
        raise CheckFailure(f"Unexpected health payload: {payload}")
    return "status=ok, database=reachable"


async def check_login_success(ctx: ApiContext) -> str:
    payload = _json(
        await ctx.call(
            "POST",
            "/api/auth/login",
            json={"email": "qa@example.com", "password": "Passw0rd!"},
        )
    )
    for key in ("access_token", "token_type", "user"):
        if key not in payload:
            raise CheckFailure(f"Login response missing '{key}'")
    if payload["token_type"] != "bearer":
        raise CheckFailure("token_type must be 'bearer'")
    ctx.token = payload["access_token"]
    return f"token issued for {payload['user']['email']} (role={payload['user']['role']})"


async def check_login_invalid_password(ctx: ApiContext) -> str:
    response = await ctx.call(
        "POST", "/api/auth/login", expect=401, json={"email": "qa@example.com", "password": "wrong-pass"}
    )
    if "Invalid" not in response.json().get("detail", ""):
        raise CheckFailure("401 detail should explain invalid credentials")
    return "401 returned for wrong password"


async def check_login_validation(ctx: ApiContext) -> str:
    response = await ctx.call("POST", "/api/auth/login", expect=422, json={"password": "Passw0rd!"})
    detail = response.json().get("detail", [])
    if not detail or detail[0].get("loc", [])[-1] != "email":
        raise CheckFailure("422 payload should point at the missing email field")
    return "422 validation error names the missing field"


async def check_me_requires_token(ctx: ApiContext) -> str:
    response = await ctx.call("GET", "/api/auth/me", expect=401)
    if response.headers.get("www-authenticate", "").lower() != "bearer":
        raise CheckFailure("401 must send WWW-Authenticate: Bearer")
    return "401 with WWW-Authenticate header"


async def check_me_with_token(ctx: ApiContext) -> str:
    if not ctx.token:
        await check_login_success(ctx)
    payload = _json(await ctx.call("GET", "/api/auth/me", auth=True))
    if payload.get("email") != "qa@example.com":
        raise CheckFailure(f"Unexpected identity: {payload}")
    return f"authenticated as {payload['email']} ({payload['role']})"


async def check_openapi_contract(ctx: ApiContext) -> str:
    spec = _json(await ctx.call("GET", "/openapi.json"))
    paths = spec.get("paths", {})
    if len(paths) < 20:
        raise CheckFailure(f"OpenAPI document exposes only {len(paths)} paths")
    if "openapi" not in spec or "info" not in spec:
        raise CheckFailure("OpenAPI document is missing required top-level keys")
    return f"OpenAPI {spec['openapi']} documents {len(paths)} paths"


async def check_chat_requires_auth(ctx: ApiContext) -> str:
    await ctx.call("POST", "/api/chat", expect=401, json={"message": "hello"})
    return "chat is protected by bearer auth"


async def check_chat_message(ctx: ApiContext) -> str:
    if not ctx.token:
        await check_login_success(ctx)
    payload = _json(
        await ctx.call(
            "POST", "/api/chat", auth=True, json={"message": "Summarise the latest quality report"}
        )
    )
    if not payload.get("reply", {}).get("content"):
        raise CheckFailure("Chat reply has no content")
    if payload["reply"]["role"] != "assistant":
        raise CheckFailure("Reply role must be 'assistant'")
    ctx.conversation_id = payload["conversation_id"]
    return f"conversation {ctx.conversation_id} answered in {payload['latency_ms']} ms"


async def check_chat_empty_message(ctx: ApiContext) -> str:
    response = await ctx.call("POST", "/api/chat", expect=422, auth=True, json={"message": ""})
    if not response.json().get("detail"):
        raise CheckFailure("Empty message must return a validation detail")
    return "empty prompt rejected with 422"


async def check_chat_invalid_model(ctx: ApiContext) -> str:
    response = await ctx.call(
        "POST", "/api/chat", expect=400, auth=True, json={"message": "hi", "model": "gpt-unknown"}
    )
    if "model" not in response.json().get("detail", "").lower():
        raise CheckFailure("400 should mention the unsupported model")
    return "unsupported model rejected with 400"


async def check_chat_history_persisted(ctx: ApiContext) -> str:
    if not ctx.conversation_id:
        await check_chat_message(ctx)
    payload = _json(await ctx.call("GET", f"/api/chat/{ctx.conversation_id}", auth=True))
    messages = payload.get("messages", [])
    if len(messages) < 2:
        raise CheckFailure("Persisted conversation should contain the user and assistant turns")
    if messages[-1]["role"] != "assistant":
        raise CheckFailure("Last persisted message should be the assistant reply")
    return f"{len(messages)} messages persisted for {ctx.conversation_id}"


async def check_dashboard_contract(ctx: ApiContext) -> str:
    payload = _json(await ctx.call("GET", "/api/dashboard/summary", auth=True))
    required = {
        "total_tests",
        "passed",
        "failed",
        "pass_rate",
        "avg_api_ms",
        "avg_page_load_ms",
        "data_failures",
        "recent_runs",
    }
    missing = required - payload.keys()
    if missing:
        raise CheckFailure(f"Dashboard summary missing keys: {sorted(missing)}")
    return f"summary exposes {len(payload)} fields, {payload['total_tests']} tracked tests"


async def check_runs_pagination(ctx: ApiContext) -> str:
    payload = _json(await ctx.call("GET", "/api/runs?limit=3", auth=True))
    if len(payload.get("items", [])) > 3:
        raise CheckFailure("Page size limit was not honoured")
    if "total" not in payload:
        raise CheckFailure("Pagination payload must include a total")
    return f"limit honoured ({len(payload['items'])} of {payload['total']})"


async def check_unknown_route(ctx: ApiContext) -> str:
    await ctx.call("GET", "/api/this-route-does-not-exist", expect=404, auth=True)
    return "unknown route returns 404"


async def check_validation_checks_endpoint(ctx: ApiContext) -> str:
    payload = _json(await ctx.call("GET", "/api/data-quality/checks", auth=True))
    checks = payload.get("items", [])
    if len(checks) < 10:
        raise CheckFailure(f"Only {len(checks)} data checks are registered")
    return f"{len(checks)} SQL validation checks registered"


async def check_latency_budget(ctx: ApiContext) -> str:
    if not ctx.latencies:
        raise CheckFailure("No measured requests available")
    worst_url, worst = max(ctx.latencies.items(), key=lambda item: item[1])
    if worst > 800:
        raise CheckFailure(f"{worst_url} exceeded the 800 ms budget ({worst} ms)")
    return f"worst endpoint {worst_url} at {worst} ms (budget 800 ms)"


@dataclass(frozen=True)
class ApiCheck:
    key: str
    name: str
    module: str
    severity: str
    description: str
    fn: Callable[[ApiContext], Awaitable[str]]


API_CHECKS: list[ApiCheck] = [
    ApiCheck("api.health", "Health endpoint returns ok", "health", "critical", "GET /healthz returns status ok and confirms DB access.", check_health),
    ApiCheck("api.auth.login", "Login issues a bearer token", "auth", "critical", "Valid credentials return a signed token and user profile.", check_login_success),
    ApiCheck("api.auth.invalid_password", "Login rejects invalid password", "auth", "critical", "Wrong password returns 401 with an explanatory detail.", check_login_invalid_password),
    ApiCheck("api.auth.validation", "Login validates required fields", "auth", "major", "Missing email returns a 422 that names the field.", check_login_validation),
    ApiCheck("api.auth.unauthorized", "Protected endpoint rejects anonymous calls", "auth", "critical", "GET /api/auth/me without a token returns 401 + WWW-Authenticate.", check_me_requires_token),
    ApiCheck("api.auth.me", "Token resolves to the correct identity", "auth", "major", "GET /api/auth/me returns the authenticated user.", check_me_with_token),
    ApiCheck("api.contract.openapi", "OpenAPI document is complete", "contract", "major", "The published OpenAPI schema lists the platform endpoints.", check_openapi_contract),
    ApiCheck("api.chat.auth", "Chat endpoint requires authentication", "chat", "critical", "Anonymous chat requests are rejected with 401.", check_chat_requires_auth),
    ApiCheck("api.chat.create", "Chat returns an assistant reply", "chat", "critical", "POST /api/chat persists a turn pair and returns a reply.", check_chat_message),
    ApiCheck("api.chat.empty", "Chat rejects empty prompts", "chat", "major", "An empty message fails request validation with 422.", check_chat_empty_message),
    ApiCheck("api.chat.invalid_model", "Chat rejects unsupported models", "chat", "major", "Unknown model names return 400, not a server error.", check_chat_invalid_model),
    ApiCheck("api.chat.persistence", "Chat history is persisted", "chat", "major", "Conversation history is readable and ordered.", check_chat_history_persisted),
    ApiCheck("api.dashboard.contract", "Dashboard summary honours its contract", "dashboard", "major", "Summary exposes every KPI required by the dashboard.", check_dashboard_contract),
    ApiCheck("api.runs.pagination", "Run listing paginates correctly", "dashboard", "minor", "limit/total are respected by the runs endpoint.", check_runs_pagination),
    ApiCheck("api.routes.404", "Unknown routes return 404", "contract", "minor", "No route leaks a 500 for unknown paths.", check_unknown_route),
    ApiCheck("api.data.checks", "Data check catalog is exposed", "data", "major", "The SQL validation catalog is served to the UI.", check_validation_checks_endpoint),
    ApiCheck("api.performance.budget", "API latency stays inside budget", "performance", "major", "Every measured call in this run stays under 800 ms.", check_latency_budget),
]


# ---------------------------------------------------------------- DB checks
@dataclass(frozen=True)
class DbCheck:
    key: str
    name: str
    table: str
    severity: str
    description: str
    sql: str


DB_CHECKS: list[DbCheck] = [
    DbCheck(
        "db.users.unique_email",
        "User emails are unique",
        "users",
        "critical",
        "No duplicate email addresses exist across accounts.",
        "SELECT email, COUNT(*) AS occurrences FROM users GROUP BY email HAVING COUNT(*) > 1",
    ),
    DbCheck(
        "db.results.orphans",
        "Every test result belongs to a run",
        "test_results",
        "critical",
        "Referential integrity between results and runs.",
        "SELECT r.id, r.case_key FROM test_results r LEFT JOIN test_runs t ON t.id = r.run_id WHERE t.id IS NULL",
    ),
    DbCheck(
        "db.runs.required_fields",
        "Runs have non-null required fields",
        "test_runs",
        "major",
        "run_key, status and started_at must always be populated.",
        "SELECT id FROM test_runs WHERE run_key IS NULL OR TRIM(run_key) = '' OR status IS NULL OR started_at IS NULL",
    ),
    DbCheck(
        "db.results.status_domain",
        "Test result statuses are in the allowed domain",
        "test_results",
        "major",
        "Only passed/failed/skipped/error are valid statuses.",
        "SELECT id, status FROM test_results WHERE status NOT IN ('passed','failed','skipped','error')",
    ),
    DbCheck(
        "db.runs.duplicate_keys",
        "Run keys are unique",
        "test_runs",
        "critical",
        "Duplicate run keys would corrupt historical reporting.",
        "SELECT run_key, COUNT(*) AS occurrences FROM test_runs GROUP BY run_key HAVING COUNT(*) > 1",
    ),
    DbCheck(
        "db.cases.duplicate_keys",
        "Test case keys are unique",
        "test_cases",
        "major",
        "Catalog keys are the join key for results and ingestion.",
        "SELECT key, COUNT(*) AS occurrences FROM test_cases GROUP BY key HAVING COUNT(*) > 1",
    ),
    DbCheck(
        "db.eval.score_range",
        "AI evaluation scores are within 0-100",
        "evaluation_results",
        "critical",
        "Out-of-range scores break evaluation reporting and gates.",
        "SELECT id, score FROM evaluation_results WHERE score < 0 OR score > 100",
    ),
    DbCheck(
        "db.eval.integrity",
        "AI evaluations reference a real conversation",
        "evaluation_results",
        "major",
        "Each evaluation must map to at least one stored chat message.",
        """SELECT e.id, e.conversation_id FROM evaluation_results e
           WHERE e.conversation_id <> ''
             AND NOT EXISTS (SELECT 1 FROM chat_messages m WHERE m.conversation_id = e.conversation_id)""",
    ),
    DbCheck(
        "db.api.status_range",
        "API metric status codes are valid HTTP codes",
        "api_metrics",
        "major",
        "Status codes must fall inside 100-599.",
        "SELECT id, status_code FROM api_metrics WHERE status_code < 100 OR status_code > 599",
    ),
    DbCheck(
        "db.metrics.latency_positive",
        "Latency measurements are positive",
        "api_metrics",
        "major",
        "Zero or negative latencies indicate broken instrumentation.",
        "SELECT id, response_time_ms FROM api_metrics WHERE response_time_ms <= 0",
    ),
    DbCheck(
        "db.pages.load_positive",
        "Page load timings are positive",
        "page_metrics",
        "major",
        "Page load and TTFB must be greater than zero.",
        "SELECT id, load_time_ms FROM page_metrics WHERE load_time_ms <= 0 OR ttfb_ms < 0",
    ),
    DbCheck(
        "db.load.consistency",
        "Load test aggregates are consistent",
        "load_test_runs",
        "major",
        "Failures cannot exceed requests and error rate stays 0-100.",
        "SELECT id FROM load_test_runs WHERE failures > requests OR error_rate < 0 OR error_rate > 100",
    ),
    DbCheck(
        "db.runs.time_order",
        "Run timestamps are ordered",
        "test_runs",
        "minor",
        "finished_at can never precede started_at.",
        "SELECT id FROM test_runs WHERE finished_at IS NOT NULL AND finished_at < started_at",
    ),
    DbCheck(
        "db.chat.role_domain",
        "Chat message roles are valid",
        "chat_messages",
        "minor",
        "Only user/assistant/system roles are stored.",
        "SELECT id, role FROM chat_messages WHERE role NOT IN ('user','assistant','system')",
    ),
    DbCheck(
        "db.metrics.orphans",
        "API metrics reference an existing run",
        "api_metrics",
        "minor",
        "Dangling run ids break drill-down navigation.",
        "SELECT id FROM api_metrics WHERE run_id IS NOT NULL AND run_id NOT IN (SELECT id FROM test_runs)",
    ),
]


def _count(db: Session, table: str) -> int:
    try:
        return int(db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
    except Exception:  # noqa: BLE001 - table might not exist in a fresh DB
        return 0


def execute_db_check(db: Session, check: DbCheck) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        rows = db.execute(text(check.sql)).fetchall()
        failing = len(rows)
        sample = [dict(row._mapping) for row in rows[:MAX_SAMPLE_ROWS]]
        status = "passed" if failing == 0 else "failed"
        message = (
            "No offending rows detected."
            if failing == 0
            else f"{failing} row(s) violate the rule: {check.description}"
        )
        return {
            "check_key": check.key,
            "name": check.name,
            "table_name": check.table,
            "severity": check.severity,
            "status": status,
            "failing_rows": failing,
            "total_rows": _count(db, check.table),
            "query": check.sql,
            "message": message,
            "sample": json.dumps(sample, default=str),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:  # noqa: BLE001 - a broken query is an execution error
        return {
            "check_key": check.key,
            "name": check.name,
            "table_name": check.table,
            "severity": check.severity,
            "status": "error",
            "failing_rows": 0,
            "total_rows": 0,
            "query": check.sql,
            "message": f"Query failed: {exc}",
            "sample": "[]",
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }


def new_conversation_id() -> str:
    return f"conv-{uuid.uuid4().hex[:12]}"
