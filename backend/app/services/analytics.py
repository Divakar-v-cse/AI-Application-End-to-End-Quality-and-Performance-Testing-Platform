"""Read-model helpers shared by the dashboard, gates and reports."""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import utcnow
from ..models import (
    ApiMetric,
    DataValidationResult,
    LoadTestRun,
    PageMetric,
    QualityGate,
    TestCase,
    TestResult,
    TestRun,
)
from .gates import percentile


def latest_run_for_suite(db: Session, suite: str) -> TestRun | None:
    return db.scalars(
        select(TestRun)
        .join(TestResult, TestResult.run_id == TestRun.id)
        .where(TestResult.suite == suite)
        .order_by(TestRun.started_at.desc())
        .limit(1)
    ).first()


def suite_counts(db: Session, run_id: int, suite: str) -> dict[str, int]:
    rows = db.execute(
        select(TestResult.status, func.count())
        .where(TestResult.run_id == run_id, TestResult.suite == suite)
        .group_by(TestResult.status)
    ).all()
    return {status: int(count) for status, count in rows}


def snapshot(db: Session) -> dict:
    suites: dict[str, dict[str, float]] = {}
    total = passed = failed = skipped = 0
    for suite in ("api", "ui", "db"):
        run = latest_run_for_suite(db, suite)
        if not run:
            suites[suite] = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "pass_rate": 0.0, "avg_ms": 0.0}
            continue
        counts = suite_counts(db, run.id, suite)
        s_total = sum(counts.values())
        s_passed = counts.get("passed", 0)
        s_failed = counts.get("failed", 0) + counts.get("error", 0)
        durations = db.scalars(
            select(TestResult.duration_ms).where(TestResult.run_id == run.id, TestResult.suite == suite)
        ).all()
        suites[suite] = {
            "total": s_total,
            "passed": s_passed,
            "failed": s_failed,
            "skipped": counts.get("skipped", 0),
            "pass_rate": round(s_passed / s_total * 100, 2) if s_total else 0.0,
            "avg_ms": round(mean(durations), 1) if durations else 0.0,
        }
        total += s_total
        passed += s_passed
        failed += s_failed
        skipped += counts.get("skipped", 0)

    catalog_tests = db.scalar(select(func.count()).select_from(TestCase)) or 0

    cutoff = utcnow() - timedelta(days=7)
    latencies = [float(v) for v in db.scalars(select(ApiMetric.response_time_ms).where(ApiMetric.created_at >= cutoff)).all()]
    page_times = [float(v) for v in db.scalars(select(PageMetric.load_time_ms).where(PageMetric.created_at >= cutoff)).all()]

    latest_db_run = latest_run_for_suite(db, "db")
    data_failures = 0
    data_checks = 0
    if latest_db_run:
        data_checks = int(
            db.scalar(select(func.count()).select_from(DataValidationResult).where(DataValidationResult.run_id == latest_db_run.id)) or 0
        )
        data_failures = int(
            db.scalar(
                select(func.count())
                .select_from(DataValidationResult)
                .where(
                    DataValidationResult.run_id == latest_db_run.id,
                    DataValidationResult.status.in_(["failed", "error"]),
                )
            )
            or 0
        )

    latest_load = db.scalars(select(LoadTestRun).order_by(LoadTestRun.created_at.desc()).limit(1)).first()
    latest_run = db.scalars(select(TestRun).order_by(TestRun.started_at.desc()).limit(1)).first()
    recent_runs = list(db.scalars(select(TestRun).order_by(TestRun.started_at.desc()).limit(8)).all())

    gate_failures = 0
    if latest_run:
        gate_failures = int(
            db.scalar(
                select(func.count())
                .select_from(QualityGate)
                .where(QualityGate.run_id == latest_run.id, QualityGate.status == "failed")
            )
            or 0
        )

    # Endpoint latency profile (top 8 by call volume).
    rows = db.execute(
        select(ApiMetric.endpoint, ApiMetric.response_time_ms, ApiMetric.status_code)
        .where(ApiMetric.created_at >= cutoff)
        .order_by(ApiMetric.created_at.desc())
        .limit(3000)
    ).all()
    buckets: dict[str, list[float]] = {}
    errors: dict[str, int] = {}
    for endpoint, latency, status_code in rows:
        buckets.setdefault(endpoint, []).append(float(latency))
        if status_code >= 400:
            errors[endpoint] = errors.get(endpoint, 0) + 1
    endpoint_latency = [
        {
            "endpoint": endpoint,
            "avg_ms": round(mean(values), 2),
            "p95_ms": percentile(values, 95),
            "calls": len(values),
            "error_rate": round(errors.get(endpoint, 0) / len(values) * 100, 2),
        }
        for endpoint, values in sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True)[:8]
    ]

    from ..schemas import TestRunOut  # local import avoids a cycle at module import time

    return {
        "generated_at": utcnow(),
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": round(passed / total * 100, 2) if total else 0.0,
        "catalog_tests": int(catalog_tests),
        "suites": suites,
        "avg_api_ms": round(mean(latencies), 2) if latencies else 0.0,
        "p95_api_ms": percentile(latencies, 95),
        "avg_page_load_ms": round(mean(page_times), 2) if page_times else 0.0,
        "load_error_rate": float(latest_load.error_rate) if latest_load else 0.0,
        "load_rps": float(latest_load.rps) if latest_load else 0.0,
        "data_failures": data_failures,
        "data_checks": data_checks,
        "active_gates_failed": gate_failures,
        "latest_run": TestRunOut.model_validate(latest_run) if latest_run else None,
        "endpoint_latency": endpoint_latency,
        "recent_runs": [TestRunOut.model_validate(r) for r in recent_runs],
    }


def trend(db: Session, days: int = 14) -> list[dict]:
    today = datetime.utcnow().date()
    start = today - timedelta(days=days - 1)

    runs = db.execute(
        select(func.date(TestRun.started_at), TestRun.passed, TestRun.failed, TestRun.total).where(
            TestRun.started_at >= datetime.combine(start, datetime.min.time())
        )
    ).all()
    api_rows = db.execute(
        select(func.date(ApiMetric.created_at), func.avg(ApiMetric.response_time_ms)).where(
            ApiMetric.created_at >= datetime.combine(start, datetime.min.time())
        ).group_by(func.date(ApiMetric.created_at))
    ).all()
    page_rows = db.execute(
        select(func.date(PageMetric.created_at), func.avg(PageMetric.load_time_ms)).where(
            PageMetric.created_at >= datetime.combine(start, datetime.min.time())
        ).group_by(func.date(PageMetric.created_at))
    ).all()
    data_rows = db.execute(
        select(func.date(DataValidationResult.created_at), func.count()).where(
            DataValidationResult.created_at >= datetime.combine(start, datetime.min.time()),
            DataValidationResult.status.in_(["failed", "error"]),
        ).group_by(func.date(DataValidationResult.created_at))
    ).all()

    run_map: dict[str, dict] = {}
    for day, passed, failed, total in runs:
        bucket = run_map.setdefault(str(day), {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += int(total or 0)
        bucket["passed"] += int(passed or 0)
        bucket["failed"] += int(failed or 0)
    api_map = {str(day): round(float(value or 0), 2) for day, value in api_rows}
    page_map = {str(day): round(float(value or 0), 2) for day, value in page_rows}
    data_map = {str(day): int(count or 0) for day, count in data_rows}

    points = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        key = day.isoformat()
        bucket = run_map.get(key, {"total": 0, "passed": 0, "failed": 0})
        total = bucket["total"]
        points.append(
            {
                "date": key,
                "total": total,
                "passed": bucket["passed"],
                "failed": bucket["failed"],
                "pass_rate": round(bucket["passed"] / total * 100, 2) if total else 0.0,
                "avg_api_ms": api_map.get(key, 0.0),
                "page_load_ms": page_map.get(key, 0.0),
                "data_failures": data_map.get(key, 0),
            }
        )
    return points
