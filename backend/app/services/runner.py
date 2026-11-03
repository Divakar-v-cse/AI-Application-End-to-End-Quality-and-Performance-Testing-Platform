"""Test execution and result ingestion.

The API suite is executed for real against the running ASGI app, the DB suite
runs real SQL, and the UI suite is executed through Playwright when enabled
(``ENABLE_UI_RUNNER=true``) or ingested from a CI run.
"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import tempfile
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import PROJECT_ROOT, settings
from ..database import utcnow
from ..models import ApiMetric, DataValidationResult, LoadTestRun, TestResult, TestRun
from . import gates as gate_service
from .checks import API_CHECKS, DB_CHECKS, ApiContext, CheckFailure, execute_db_check


def new_run_key(prefix: str = "RUN") -> str:
    return f"{prefix}-{datetime.utcnow():%Y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"


def _new_run(db: Session, suite: str, trigger: str, branch: str, commit: str, source: str) -> TestRun:
    run = TestRun(
        run_key=new_run_key(),
        suite=suite,
        trigger=trigger,
        branch=branch,
        commit_sha=commit,
        source=source,
        environment=settings.environment,
        status="running",
        started_at=utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _add_result(
    db: Session,
    run: TestRun,
    *,
    case_key: str,
    name: str,
    suite: str,
    module: str,
    status: str,
    duration_ms: float,
    error_message: str = "",
    stack_trace: str = "",
    evidence: str = "",
) -> None:
    db.add(
        TestResult(
            run_id=run.id,
            case_key=case_key,
            name=name,
            suite=suite,
            module=module,
            status=status,
            duration_ms=int(duration_ms),
            error_message=error_message[:2000],
            stack_trace=stack_trace[:8000],
            evidence=evidence[:4000],
        )
    )


def finalize_run(db: Session, run: TestRun, duration_ms: int | None = None) -> TestRun:
    db.flush()
    counts = dict(
        db.execute(
            select(TestResult.status, func.count()).where(TestResult.run_id == run.id).group_by(TestResult.status)
        ).all()
    )
    run.total = int(sum(counts.values()))
    run.passed = int(counts.get("passed", 0))
    run.failed = int(counts.get("failed", 0) + counts.get("error", 0))
    run.skipped = int(counts.get("skipped", 0))
    run.finished_at = utcnow()
    run.duration_ms = int(duration_ms if duration_ms is not None else (run.finished_at - run.started_at).total_seconds() * 1000)
    db.commit()

    # Gates are persisted on the run and exposed by /api/quality-gates. The run
    # status reports what this run executed, so a platform-wide regression (for
    # example a failing load test) cannot relabel historical runs.
    gate_service.replace_gates(db, run)
    if run.failed:
        run.status = "failed"
    elif run.total == 0:
        run.status = "skipped"
    else:
        run.status = "passed"
    db.commit()
    db.refresh(run)
    return run


async def _run_api_checks(db: Session, run: TestRun, app) -> None:
    transport = httpx.ASGITransport(app=app)
    started = time.perf_counter()
    async with httpx.AsyncClient(transport=transport, base_url="http://quality.local", timeout=30) as client:
        ctx = ApiContext(client=client)
        recorded: set[str] = set()
        for check in API_CHECKS:
            check_started = time.perf_counter()
            status, error, trace, evidence = "passed", "", "", ""
            try:
                evidence = await check.fn(ctx)
            except CheckFailure as exc:
                status, error, trace = "failed", str(exc), traceback.format_exc()
            except Exception as exc:  # noqa: BLE001 - unexpected failures are reported, not raised
                status, error, trace = "error", f"{exc.__class__.__name__}: {exc}", traceback.format_exc()
            elapsed = round((time.perf_counter() - check_started) * 1000, 2)
            _add_result(
                db,
                run,
                case_key=check.key,
                name=check.name,
                suite="api",
                module=check.module,
                status=status,
                duration_ms=elapsed,
                error_message=error,
                stack_trace=trace,
                evidence=evidence,
            )
            for url, latency in ctx.latencies.items():
                if url not in recorded:
                    recorded.add(url)
                    method = "POST" if url.startswith("/api/chat") or "login" in url else "GET"
                    db.add(
                        ApiMetric(
                            run_id=run.id,
                            endpoint=url.split("?")[0],
                            method=method,
                            status_code=200 if status == "passed" else 500,
                            response_time_ms=float(latency),
                            payload_bytes=0,
                            ok=status == "passed",
                            source="platform",
                        )
                    )
            db.commit()
    _ = time.perf_counter() - started


def _run_db_checks(db: Session, run: TestRun) -> None:
    for check in DB_CHECKS:
        outcome = execute_db_check(db, check)
        db.add(
            DataValidationResult(
                run_id=run.id,
                check_key=outcome["check_key"],
                name=outcome["name"],
                table_name=outcome["table_name"],
                severity=outcome["severity"],
                status=outcome["status"],
                failing_rows=outcome["failing_rows"],
                total_rows=outcome["total_rows"],
                query=outcome["query"],
                message=outcome["message"],
                sample=outcome["sample"],
                duration_ms=int(outcome["duration_ms"]),
            )
        )
        _add_result(
            db,
            run,
            case_key=check.key,
            name=check.name,
            suite="db",
            module=check.table,
            status="passed" if outcome["status"] == "passed" else "failed",
            duration_ms=outcome["duration_ms"],
            error_message="" if outcome["status"] == "passed" else outcome["message"],
            evidence=json.dumps({"failing_rows": outcome["failing_rows"], "sample": json.loads(outcome["sample"])})[:1000],
        )
        db.commit()


def parse_playwright_report(report: dict) -> list[dict[str, Any]]:
    """Flatten Playwright's JSON reporter into result rows."""
    rows: list[dict[str, Any]] = []

    def walk(suites: list[dict], prefix: str = "") -> None:
        for suite in suites or []:
            title = suite.get("title", "")
            path = suite.get("file", "") or suite.get("title", "")
            for spec in suite.get("specs", []) or []:
                tests = spec.get("tests", []) or []
                status = "skipped"
                duration = 0
                error = ""
                module = Path(path).stem or "ui"
                # ``login.spec.js`` -> ``login`` so case keys stay ``ui.<module>.<title>``.
                if module.endswith(".spec") or module.endswith(".test"):
                    module = module.rsplit(".", 1)[0]
                for test in tests:
                    for result in test.get("results", []) or []:
                        duration = max(duration, int(result.get("duration", 0)))
                        raw = result.get("status", "skipped")
                        mapped = {"passed": "passed", "failed": "failed", "timedOut": "failed", "skipped": "skipped", "interrupted": "error"}.get(raw, "error")
                        if mapped == "failed":
                            status = "failed"
                            error_obj = result.get("error") or {}
                            error = (error_obj.get("message") or error_obj.get("value") or "Playwright assertion failed")[:1500]
                        elif mapped == "passed" and status != "failed":
                            status = "passed"
                rows.append(
                    {
                        "case_key": f"ui.{module}.{spec.get('title', 'test')}"[:80],
                        "name": spec.get("title", "UI spec"),
                        "module": module,
                        "status": status,
                        "duration_ms": duration,
                        "error_message": error,
                    }
                )
            walk(suite.get("suites", []) or [], prefix + title)

    walk(report.get("suites", []) or [])
    return rows


def run_playwright_suite(timeout_s: int | None = None) -> tuple[list[dict], str]:
    """Execute the Playwright project and return parsed rows plus raw log."""
    report_path = Path(tempfile.gettempdir()) / f"playwright-report-{secrets.token_hex(4)}.json"
    env = os.environ.copy()
    env["PLAYWRIGHT_JSON_OUTPUT_NAME"] = str(report_path)
    env["CI"] = "true"
    try:
        completed = subprocess.run(  # noqa: S602 - command is operator configured
            settings.ui_runner_command,
            cwd=str(PROJECT_ROOT),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_s or settings.ui_runner_timeout_s,
            env=env,
        )
        log = (completed.stdout or "") + (completed.stderr or "")
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            return parse_playwright_report(report), log[-4000:]
        return [], log[-4000:] or "Playwright produced no JSON report."
    except subprocess.TimeoutExpired:
        return [], f"Playwright timed out after {timeout_s or settings.ui_runner_timeout_s}s"
    except Exception as exc:  # noqa: BLE001 - report any runner failure as execution error
        return [], f"Playwright runner failed: {exc.__class__.__name__}: {exc}"
    finally:
        report_path.unlink(missing_ok=True)


async def execute_run(app, db: Session, suite: str = "all", trigger: str = "manual", branch: str = "main", commit: str = "local") -> TestRun:
    run = _new_run(db, suite, trigger, branch, commit, source="platform")
    started = time.perf_counter()

    if suite in {"all", "api"}:
        await _run_api_checks(db, run, app)
    if suite in {"all", "db"}:
        _run_db_checks(db, run)
    if suite in {"all", "ui"} and settings.enable_ui_runner:
        rows, log = await asyncio.to_thread(run_playwright_suite)
        if not rows:
            _add_result(
                db,
                run,
                case_key="ui.runner",
                name="Playwright suite executed",
                suite="ui",
                module="runner",
                status="error",
                duration_ms=0,
                error_message="Playwright produced no results",
                stack_trace=log,
            )
        for row in rows:
            _add_result(db, run, suite="ui", **row)
        db.commit()

    return finalize_run(db, run, int((time.perf_counter() - started) * 1000))


# ------------------------------------------------------------------ ingestion
def _ingest_run(db: Session, suite: str, source: str, branch: str, commit: str) -> TestRun:
    return _new_run(db, suite, "ci", branch, commit, source=source)


def ingest_junit(db: Session, xml_text: str, suite: str = "api", branch: str = "main", commit: str = "local") -> TestRun:
    root = ET.fromstring(xml_text)
    run = _ingest_run(db, suite, "junit", branch, commit)
    started = time.perf_counter()
    cases = root.iter("testcase")
    for case in cases:
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            status, message = "failed", (failure.get("message") or failure.text or "failed")
        elif error is not None:
            status, message = "error", (error.get("message") or error.text or "error")
        elif skipped is not None:
            status, message = "skipped", skipped.get("message", "skipped")
        else:
            status, message = "passed", ""
        classname = case.get("classname", "ingested")
        _add_result(
            db,
            run,
            case_key=f"{suite}.{classname}.{case.get('name', 'case')}"[:80],
            name=case.get("name", "ingested case"),
            suite=suite,
            module=classname,
            status=status,
            duration_ms=float(case.get("time", 0) or 0) * 1000,
            error_message=message,
            evidence="Ingested from JUnit XML",
        )
    db.commit()
    return finalize_run(db, run, int((time.perf_counter() - started) * 1000))


def ingest_playwright(db: Session, report: dict, branch: str = "main", commit: str = "local") -> TestRun:
    run = _ingest_run(db, "ui", "playwright", branch, commit)
    rows = parse_playwright_report(report)
    for row in rows:
        _add_result(db, run, suite="ui", **row)
    db.commit()
    return finalize_run(db, run)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1)))))
    return round(ordered[index], 2)


def record_load_test(db: Session, payload: dict) -> LoadTestRun:
    """Accept a normalised load-test summary or a raw Locust stats payload."""
    stats = payload.get("stats")
    if isinstance(stats, list) and stats:
        requests = sum(int(s.get("num_requests", 0)) for s in stats)
        failures = sum(int(s.get("num_failures", 0)) for s in stats)
        avg = round(sum(float(s.get("avg_response_time", 0)) for s in stats) / len(stats), 2)
        p95 = max(float(s.get("p95", s.get("avg_response_time", 0))) for s in stats)
        p99 = max(float(s.get("p99", s.get("max_response_time", 0))) for s in stats)
        median = round(sum(float(s.get("median_response_time", 0)) for s in stats) / len(stats), 2)
        maximum = max(float(s.get("max_response_time", 0)) for s in stats)
        rps = float(payload.get("total_rps") or (requests / max(1, int(payload.get("duration_s", 60)))))
    else:
        requests = int(payload.get("requests", 0))
        failures = int(payload.get("failures", 0))
        avg = float(payload.get("avg_ms", 0))
        p95 = float(payload.get("p95_ms", 0))
        p99 = float(payload.get("p99_ms", 0))
        median = float(payload.get("median_ms", 0))
        maximum = float(payload.get("max_ms", 0))
        rps = float(payload.get("rps", 0))

    error_rate = round(failures / requests * 100, 2) if requests else 0.0
    error_budget = float(payload.get("error_rate_budget", settings.gate_load_error_rate))
    status = "passed" if requests and error_rate <= error_budget else ("failed" if requests else "skipped")

    load_run = LoadTestRun(
        run_key=new_run_key("LOAD"),
        target=payload.get("target", settings.frontend_url),
        scenario=payload.get("scenario", "mixed_read_write"),
        users=int(payload.get("users", 10)),
        spawn_rate=float(payload.get("spawn_rate", 2)),
        duration_s=int(payload.get("duration_s", 60)),
        requests=requests,
        failures=failures,
        error_rate=error_rate,
        rps=round(rps, 2),
        avg_ms=avg,
        median_ms=median,
        p95_ms=p95,
        p99_ms=p99,
        max_ms=maximum,
        status=status,
        notes=payload.get("notes", "Ingested load test summary"),
    )
    db.add(load_run)
    db.commit()
    db.refresh(load_run)
    return load_run
