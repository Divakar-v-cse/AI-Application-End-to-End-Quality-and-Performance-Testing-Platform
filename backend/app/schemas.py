from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ---------------------------------------------------------------- catalog
class TestCaseOut(ORMModel):
    id: int
    key: str
    name: str
    suite: str
    module: str
    description: str
    severity: str
    enabled: bool
    executor: str


class TestResultOut(ORMModel):
    id: int
    case_key: str
    name: str
    suite: str
    module: str
    status: str
    duration_ms: int
    error_message: str
    stack_trace: str
    evidence: str
    created_at: datetime


class QualityGateOut(ORMModel):
    id: int
    gate_key: str
    name: str
    metric: str
    operator: str
    threshold: float
    actual: float
    status: str
    blocking: bool
    message: str


class TestRunOut(ORMModel):
    id: int
    run_key: str
    suite: str
    trigger: str
    status: str
    environment: str
    branch: str
    commit_sha: str
    source: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int
    total: int
    passed: int
    failed: int
    skipped: int
    notes: str


class TestRunDetail(BaseModel):
    run: TestRunOut
    results: list[TestResultOut]
    gates: list[QualityGateOut] = []


class TestRunPage(BaseModel):
    items: list[TestRunOut]
    total: int
    limit: int
    offset: int


class RunCreateRequest(BaseModel):
    suite: str = Field(default="all", pattern="^(all|api|ui|db|perf)$")
    trigger: str = Field(default="manual", max_length=40)
    branch: str = Field(default="main", max_length=120)
    commit_sha: str = Field(default="local", max_length=40)


# ---------------------------------------------------------------- metrics
class ApiMetricOut(ORMModel):
    id: int
    run_id: int | None
    endpoint: str
    method: str
    status_code: int
    response_time_ms: float
    payload_bytes: int
    ok: bool
    source: str
    created_at: datetime


class PageMetricOut(ORMModel):
    id: int
    page: str
    load_time_ms: float
    ttfb_ms: float
    dom_interactive_ms: float
    network_idle_ms: float
    created_at: datetime


class LoadTestOut(ORMModel):
    id: int
    run_key: str
    target: str
    scenario: str
    users: int
    spawn_rate: float
    duration_s: int
    requests: int
    failures: int
    error_rate: float
    rps: float
    avg_ms: float
    median_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    status: str
    notes: str
    created_at: datetime


class DataValidationOut(ORMModel):
    id: int
    check_key: str
    name: str
    table_name: str
    severity: str
    status: str
    failing_rows: int
    total_rows: int
    query: str
    message: str
    sample: str
    duration_ms: int
    created_at: datetime


class EndpointLatency(BaseModel):
    endpoint: str
    avg_ms: float
    p95_ms: float
    calls: int
    error_rate: float


class TrendPoint(BaseModel):
    date: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    avg_api_ms: float
    page_load_ms: float
    data_failures: int


class DashboardSummary(BaseModel):
    generated_at: datetime
    total_tests: int
    passed: int
    failed: int
    skipped: int
    pass_rate: float
    suites: dict[str, dict[str, float]]
    avg_api_ms: float
    p95_api_ms: float
    avg_page_load_ms: float
    load_error_rate: float
    load_rps: float
    data_failures: int
    data_checks: int
    active_gates_failed: int
    latest_run: TestRunOut | None
    endpoint_latency: list[EndpointLatency]
    recent_runs: list[TestRunOut]


# ---------------------------------------------------------------- demo app
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = Field(default=None, max_length=64)
    model: str = Field(default="accio-mini", max_length=60)


class ChatMessageOut(ORMModel):
    id: int
    conversation_id: str
    role: str
    content: str
    model: str
    latency_ms: int
    tokens: int
    flagged: bool
    created_at: datetime


class ChatReply(BaseModel):
    conversation_id: str
    reply: ChatMessageOut
    messages: list[ChatMessageOut]
    latency_ms: int
    flagged: bool


class EvaluationCreate(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    score: int = Field(ge=0, le=100)
    model: str = Field(default="accio-mini", max_length=60)
    conversation_id: str = Field(default="", max_length=64)
    reviewer: str = Field(default="qa@example.com", max_length=120)


class EvaluationOut(ORMModel):
    id: int
    conversation_id: str
    model: str
    prompt: str
    score: int
    verdict: str
    latency_ms: int
    reviewer: str
    created_at: datetime


class DemoOverview(BaseModel):
    total_conversations: int
    total_messages: int
    avg_latency_ms: float
    success_rate: float
    flagged_messages: int
    avg_eval_score: float
    evaluations: int
    recent_evaluations: list[EvaluationOut]
    conversations: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------- aws / artifacts
class ArtifactOut(ORMModel):
    id: int
    run_key: str
    filename: str
    storage: str
    location: str
    size_bytes: int
    content_type: str
    created_at: datetime


class AwsStatus(BaseModel):
    enabled: bool
    region: str
    configured: dict[str, bool]
    storage_mode: str
    message: str


class AthenaRequest(BaseModel):
    query: str = Field(min_length=5, max_length=4000)


class AthenaResult(BaseModel):
    mode: str
    query: str
    columns: list[str]
    rows: list[list[str]]
    scanned_bytes: int
    duration_ms: int
    message: str


class LambdaRequest(BaseModel):
    payload: dict = Field(default_factory=dict)


class LambdaResult(BaseModel):
    mode: str
    function: str
    status_code: int
    duration_ms: int
    payload: dict
    message: str
