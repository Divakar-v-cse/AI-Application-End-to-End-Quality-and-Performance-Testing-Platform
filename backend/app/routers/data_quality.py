from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import DataValidationResult, TestRun
from ..schemas import DataValidationOut, TestRunOut
from ..services import analytics, runner

router = APIRouter(prefix="/api/data-quality", tags=["Data validation"])


@router.get("/checks", summary="Latest SQL validation results")
def checks(db: Session = Depends(get_db), _=Depends(current_user)) -> dict:
    latest_run = analytics.latest_run_for_suite(db, "db")
    rows = (
        list(
            db.scalars(
                select(DataValidationResult)
                .where(DataValidationResult.run_id == latest_run.id)
                .order_by(DataValidationResult.severity, DataValidationResult.check_key)
            ).all()
        )
        if latest_run
        else []
    )
    failed = [row for row in rows if row.status != "passed"]
    severity_counts = {}
    for row in failed:
        severity_counts[row.severity] = severity_counts.get(row.severity, 0) + 1
    return {
        "items": [DataValidationOut.model_validate(row) for row in rows],
        "summary": {
            "total": len(rows),
            "passed": len(rows) - len(failed),
            "failed": len(failed),
            "rows_scanned": sum(row.total_rows for row in rows),
            "severity_counts": severity_counts,
            "run_key": latest_run.run_key if latest_run else None,
            "checked_at": latest_run.finished_at or latest_run.started_at if latest_run else None,
        },
    }


@router.post("/run", summary="Execute every SQL validation check")
async def run_checks(request: Request, db: Session = Depends(get_db), user=Depends(current_user)) -> dict:
    run = await runner.execute_run(
        request.app, db, suite="db", trigger=f"data-quality:{user.email}"
    )
    results = list(db.scalars(select(DataValidationResult).where(DataValidationResult.run_id == run.id)).all())
    return {
        "run": TestRunOut.model_validate(run),
        "items": [DataValidationOut.model_validate(row) for row in results],
        "failed": sum(1 for row in results if row.status != "passed"),
    }


@router.get("/history", summary="Data validation history")
def history(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> dict:
    runs = list(
        db.scalars(
            select(TestRun)
            .join(DataValidationResult, DataValidationResult.run_id == TestRun.id)
            .group_by(TestRun.id)
            .order_by(TestRun.started_at.desc())
            .limit(limit)
        ).all()
    )
    points = []
    for run in runs:
        total = int(
            db.scalar(select(func.count()).select_from(DataValidationResult).where(DataValidationResult.run_id == run.id)) or 0
        )
        failed = int(
            db.scalar(
                select(func.count())
                .select_from(DataValidationResult)
                .where(DataValidationResult.run_id == run.id, DataValidationResult.status != "passed")
            )
            or 0
        )
        points.append(
            {
                "run_key": run.run_key,
                "checked_at": run.finished_at or run.started_at,
                "checks": total,
                "failed": failed,
                "pass_rate": round((total - failed) / total * 100, 2) if total else 0.0,
            }
        )
    return {"items": points}
