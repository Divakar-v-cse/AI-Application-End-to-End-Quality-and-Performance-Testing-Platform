"""Quality gate evaluation.

Gates are computed from the persisted run so the CI pipeline, the API and the
dashboard all read exactly the same numbers.
"""
from __future__ import annotations

import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
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


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = math.ceil(pct / 100 * len(ordered)) - 1
    return round(ordered[max(0, min(rank, len(ordered) - 1))], 2)


def suite_stats(db: Session, run_id: int, suite: str) -> tuple[int, int]:
    rows = db.execute(
        select(TestResult.status, func.count()).where(TestResult.run_id == run_id, TestResult.suite == suite).group_by(TestResult.status)
    ).all()
    counts = {status: count for status, count in rows}
    total = sum(counts.values())
    passed = counts.get("passed", 0)
    return total, passed


def _gate(
    key: str,
    name: str,
    metric: str,
    actual: float,
    operator: str,
    threshold: float,
    *,
    blocking: bool = True,
    applicable: bool = True,
    message: str = "",
) -> dict:
    if not applicable:
        status = "not_applicable"
    elif operator == ">=":
        status = "passed" if actual >= threshold else "failed"
    else:
        status = "passed" if actual <= threshold else "failed"
    if not message:
        comparator = "≥" if operator == ">=" else "≤"
        message = f"{metric} = {round(actual, 2)} (threshold {comparator} {threshold})"
    return {
        "gate_key": key,
        "name": name,
        "metric": metric,
        "operator": operator,
        "threshold": threshold,
        "actual": round(float(actual), 2),
        "status": status,
        "blocking": blocking,
        "message": message,
    }


def compute_gate_payload(db: Session, run: TestRun) -> list[dict]:
    api_total, api_passed = suite_stats(db, run.id, "api")
    ui_total, ui_passed = suite_stats(db, run.id, "ui")
    db_total, db_passed = suite_stats(db, run.id, "db")

    api_latencies = [
        float(v) for v in db.scalars(select(ApiMetric.response_time_ms).where(ApiMetric.run_id == run.id)).all()
    ]
    page_times = [float(v) for v in db.scalars(select(PageMetric.load_time_ms).where(PageMetric.run_id == run.id)).all()]
    api_p95 = percentile(api_latencies, 95)
    api_avg = round(sum(api_latencies) / len(api_latencies), 2) if api_latencies else 0.0

    data_failures = db.scalar(
        select(func.count())
        .select_from(DataValidationResult)
        .where(DataValidationResult.run_id == run.id, DataValidationResult.status.in_(["failed", "error"]))
    ) or 0
    data_total = db.scalar(
        select(func.count()).select_from(DataValidationResult).where(DataValidationResult.run_id == run.id)
    ) or 0

    latest_load = db.scalars(select(LoadTestRun).order_by(LoadTestRun.created_at.desc()).limit(1)).first()

    # Coverage is a property of the automated suite, not of one partial run.
    catalog_size = int(db.scalar(select(func.count()).select_from(TestCase)) or 0)

    total_results = api_total + ui_total + db_total
    total_passed = api_passed + ui_passed + db_passed
    overall_rate = round(total_passed / total_results * 100, 2) if total_results else 0.0
    api_rate = round(api_passed / api_total * 100, 2) if api_total else 0.0
    ui_rate = round(ui_passed / ui_total * 100, 2) if ui_total else 0.0
    db_rate = round(db_passed / db_total * 100, 2) if db_total else 0.0

    return [
        _gate(
            "overall_pass_rate",
            "Overall automated test pass rate",
            "overall_pass_rate",
            overall_rate,
            ">=",
            settings.gate_api_pass_rate,
            applicable=total_results > 0,
            message=(
                f"{total_passed}/{total_results} checks passed ({overall_rate}%)"
                if total_results
                else "This run executed no checks"
            ),
        ),
        _gate(
            "api_pass_rate",
            "API suite pass rate",
            "api_pass_rate",
            api_rate,
            ">=",
            settings.gate_api_pass_rate,
            applicable=api_total > 0,
            message=f"{api_passed}/{api_total} API checks passed" if api_total else "No API checks in this run",
        ),
        _gate(
            "ui_pass_rate",
            "UI suite pass rate",
            "ui_pass_rate",
            ui_rate,
            ">=",
            settings.gate_ui_pass_rate,
            applicable=ui_total > 0,
            message=f"{ui_passed}/{ui_total} UI specs passed" if ui_total else "No UI results ingested for this run",
        ),
        _gate(
            "data_pass_rate",
            "Data validation pass rate",
            "data_pass_rate",
            db_rate,
            ">=",
            100.0,
            applicable=db_total > 0,
            message=f"{db_passed}/{db_total} SQL validations passed" if db_total else "No SQL validations in this run",
        ),
        _gate(
            "api_p95_latency",
            "API p95 latency budget",
            "api_p95_ms",
            api_p95 if api_latencies else 0.0,
            "<=",
            settings.gate_api_p95_ms,
            applicable=bool(api_latencies),
            message=f"p95 {api_p95} ms, avg {api_avg} ms over {len(api_latencies)} calls",
        ),
        _gate(
            "page_load_budget",
            "Average page load budget",
            "avg_page_load_ms",
            round(sum(page_times) / len(page_times), 2) if page_times else 0.0,
            "<=",
            settings.gate_page_load_ms,
            applicable=bool(page_times),
            message=f"{len(page_times)} page samples" if page_times else "No browser page timings recorded",
        ),
        _gate(
            "load_error_rate",
            "Load test error rate",
            "load_error_rate",
            float(latest_load.error_rate) if latest_load else 0.0,
            "<=",
            settings.gate_load_error_rate,
            applicable=latest_load is not None,
            message=(
                f"{latest_load.failures}/{latest_load.requests} failed requests at {latest_load.users} users"
                if latest_load
                else "No load test recorded"
            ),
        ),
        _gate(
            "data_failures",
            "Zero data validation failures",
            "data_failures",
            float(data_failures),
            "<=",
            float(settings.gate_data_failures),
            applicable=data_total > 0,
            message=f"{data_failures} failing data checks out of {data_total}",
        ),
        _gate(
            "test_volume",
            "Minimum automated coverage",
            "total_checks",
            float(catalog_size),
            ">=",
            20.0,
            blocking=False,
            message=f"{catalog_size} automated checks defined, {total_results} executed in this run",
        ),
    ]


def replace_gates(db: Session, run: TestRun) -> list[QualityGate]:
    for existing in list(run.gates):
        db.delete(existing)
    db.flush()
    gates = []
    for payload in compute_gate_payload(db, run):
        gate = QualityGate(run_id=run.id, **payload)
        db.add(gate)
        gates.append(gate)
    db.commit()
    for gate in gates:
        db.refresh(gate)
    return gates


def run_is_blocked(gates: list[QualityGate]) -> bool:
    return any(g.status == "failed" and g.blocking for g in gates)
