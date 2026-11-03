from __future__ import annotations

from statistics import mean

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import current_user
from ..models import LoadTestRun
from ..schemas import LoadTestOut
from ..services import runner

router = APIRouter(prefix="/api/performance", tags=["Performance"])


class LoadTestIngest(BaseModel):
    target: str = Field(default="http://localhost:5173", max_length=200)
    scenario: str = Field(default="mixed_read_write", max_length=120)
    users: int = Field(default=10, ge=1, le=5000)
    spawn_rate: float = Field(default=2, gt=0)
    duration_s: int = Field(default=60, ge=1, le=7200)
    requests: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    rps: float = Field(default=0, ge=0)
    avg_ms: float = Field(default=0, ge=0)
    median_ms: float = Field(default=0, ge=0)
    p95_ms: float = Field(default=0, ge=0)
    p99_ms: float = Field(default=0, ge=0)
    max_ms: float = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=1000)


@router.get("/runs", summary="Load test history and summary")
def list_load_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> dict:
    rows = list(db.scalars(select(LoadTestRun).order_by(LoadTestRun.created_at.desc()).limit(limit)).all())
    latest = rows[0] if rows else None
    return {
        "items": [LoadTestOut.model_validate(row) for row in rows],
        "summary": {
            "runs": len(rows),
            "latest_run": latest.run_key if latest else None,
            "latest_users": latest.users if latest else 0,
            "avg_rps": round(mean([row.rps for row in rows]), 2) if rows else 0.0,
            "worst_error_rate": round(max([row.error_rate for row in rows]), 2) if rows else 0.0,
            "p95_budget_ms": 1500,
            "error_budget": settings.gate_load_error_rate,
        },
        "trend": [
            {
                "run_key": row.run_key,
                "created_at": row.created_at,
                "users": row.users,
                "rps": row.rps,
                "p95_ms": row.p95_ms,
                "error_rate": row.error_rate,
            }
            for row in reversed(rows)
        ],
    }


@router.get("/runs/{run_key}", response_model=LoadTestOut, summary="Single load test result")
def get_load_run(run_key: str, db: Session = Depends(get_db), _=Depends(current_user)) -> LoadTestOut:
    row = db.scalar(select(LoadTestRun).where(LoadTestRun.run_key == run_key))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Load test {run_key} not found")
    return LoadTestOut.model_validate(row)


@router.post("/runs", response_model=LoadTestOut, status_code=status.HTTP_201_CREATED, summary="Record a load test result")
def record_load_run(payload: LoadTestIngest, db: Session = Depends(get_db), _=Depends(current_user)) -> LoadTestOut:
    row = runner.record_load_test(db, payload.model_dump())
    return LoadTestOut.model_validate(row)
