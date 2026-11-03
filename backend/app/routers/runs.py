from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import current_user
from ..models import TestCase, TestResult, TestRun
from ..schemas import (
    QualityGateOut,
    RunCreateRequest,
    TestCaseOut,
    TestResultOut,
    TestRunDetail,
    TestRunOut,
    TestRunPage,
)
from ..services import runner

router = APIRouter(prefix="/api", tags=["Test execution"])


@router.get("/tests/catalog", summary="List automated test cases")
def catalog(db: Session = Depends(get_db), _=Depends(current_user)) -> dict:
    items = list(db.scalars(select(TestCase).order_by(TestCase.suite, TestCase.module, TestCase.key)).all())
    by_suite: dict[str, int] = {}
    for item in items:
        by_suite[item.suite] = by_suite.get(item.suite, 0) + 1
    return {
        "items": [TestCaseOut.model_validate(item) for item in items],
        "by_suite": by_suite,
        "total": len(items),
    }


@router.get("/runs", response_model=TestRunPage, summary="List historical test runs")
def list_runs(
    suite: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> TestRunPage:
    query = select(TestRun)
    count_query = select(func.count()).select_from(TestRun)
    if suite:
        query = query.where(TestRun.suite == suite)
        count_query = count_query.where(TestRun.suite == suite)
    if status_filter:
        query = query.where(TestRun.status == status_filter)
        count_query = count_query.where(TestRun.status == status_filter)
    total = int(db.scalar(count_query) or 0)
    rows = list(db.scalars(query.order_by(TestRun.started_at.desc()).limit(limit).offset(offset)).all())
    return TestRunPage(
        items=[TestRunOut.model_validate(row) for row in rows], total=total, limit=limit, offset=offset
    )


@router.get("/runs/{run_key}", response_model=TestRunDetail, summary="Full run detail with results and gates")
def run_detail(run_key: str, db: Session = Depends(get_db), _=Depends(current_user)) -> TestRunDetail:
    run = db.scalar(select(TestRun).where(TestRun.run_key == run_key))
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_key} not found")
    return TestRunDetail(
        run=TestRunOut.model_validate(run),
        results=[TestResultOut.model_validate(r) for r in run.results],
        gates=[QualityGateOut.model_validate(g) for g in run.gates],
    )


@router.post(
    "/runs",
    response_model=TestRunDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Execute a test suite and evaluate quality gates",
)
async def trigger_run(
    payload: RunCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(current_user),
) -> TestRunDetail:
    if payload.suite == "ui" and not settings.enable_ui_runner:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The Playwright runner is disabled. Set ENABLE_UI_RUNNER=true (and install browsers), "
                "or run `npx playwright test` and POST the JSON report to /api/ingest/playwright."
            ),
        )
    run = await runner.execute_run(
        request.app,
        db,
        suite=payload.suite,
        trigger=f"{payload.trigger}:{user.email}",
        branch=payload.branch,
        commit=payload.commit_sha,
    )
    return TestRunDetail(
        run=TestRunOut.model_validate(run),
        results=[TestResultOut.model_validate(r) for r in run.results],
        gates=[QualityGateOut.model_validate(g) for g in run.gates],
    )


@router.get("/runs/{run_key}/results", response_model=list[TestResultOut], summary="Results for a run")
def run_results(
    run_key: str,
    suite: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> list[TestResultOut]:
    run = db.scalar(select(TestRun).where(TestRun.run_key == run_key))
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_key} not found")
    query = select(TestResult).where(TestResult.run_id == run.id)
    if suite:
        query = query.where(TestResult.suite == suite)
    return [TestResultOut.model_validate(r) for r in db.scalars(query.order_by(TestResult.id)).all()]
