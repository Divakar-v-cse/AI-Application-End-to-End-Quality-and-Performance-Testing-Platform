from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="qa_engineer", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    suite: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # ui | api | db | perf
    module: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="major", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    executor: Mapped[str] = mapped_column(String(40), default="platform", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    suite: Mapped[str] = mapped_column(String(20), default="all", nullable=False)
    trigger: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="passed", nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(40), default="local", nullable=False)
    branch: Mapped[str] = mapped_column(String(120), default="main", nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), default="local", nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="platform", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    results: Mapped[list["TestResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="TestResult.id"
    )
    gates: Mapped[list["QualityGate"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="QualityGate.id"
    )


class TestResult(Base):
    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), index=True)
    case_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    suite: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(80), default="general", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="passed", nullable=False, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stack_trace: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    run: Mapped[TestRun] = relationship(back_populates="results")


class ApiMetric(Base):
    __tablename__ = "api_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("test_runs.id", ondelete="SET NULL"), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(10), default="GET", nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    payload_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="platform", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class PageMetric(Base):
    __tablename__ = "page_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("test_runs.id", ondelete="SET NULL"), nullable=True)
    page: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    load_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    ttfb_ms: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    dom_interactive_ms: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    network_idle_ms: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class LoadTestRun(Base):
    __tablename__ = "load_test_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(200), nullable=False)
    scenario: Mapped[str] = mapped_column(String(120), default="mixed_read_write", nullable=False)
    users: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    spawn_rate: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    duration_s: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    requests: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rps: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    median_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    p95_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    p99_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    max_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="passed", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class DataValidationResult(Base):
    __tablename__ = "data_validations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("test_runs.id", ondelete="SET NULL"), nullable=True)
    check_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    table_name: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="major", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="passed", nullable=False, index=True)
    failing_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    query: Mapped[str] = mapped_column(Text, default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sample: Mapped[str] = mapped_column(Text, default="", nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class QualityGate(Base):
    __tablename__ = "quality_gates"
    __table_args__ = (UniqueConstraint("run_id", "gate_key", name="uq_gate_run_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_runs.id", ondelete="CASCADE"), index=True)
    gate_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    operator: Mapped[str] = mapped_column(String(8), default=">=", nullable=False)
    threshold: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="passed", nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    run: Mapped[TestRun] = relationship(back_populates="gates")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(60), default="accio-mini", nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(60), default="accio-mini", nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), default="pass", nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reviewer: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_key: Mapped[str] = mapped_column(String(40), default="", nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    storage: Mapped[str] = mapped_column(String(20), default="local", nullable=False)  # local | s3
    location: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
