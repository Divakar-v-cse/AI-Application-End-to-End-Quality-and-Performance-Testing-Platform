from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import current_user
from ..models import QualityGate, TestRun
from ..schemas import QualityGateOut
from ..services import gates as gate_service

router = APIRouter(prefix="/api/quality-gates", tags=["Quality gates"])


def gate_config() -> list[dict]:
    return [
        {"key": "overall_pass_rate", "name": "Overall pass rate", "operator": ">=", "threshold": settings.gate_api_pass_rate, "blocking": True, "unit": "%"},
        {"key": "api_pass_rate", "name": "API pass rate", "operator": ">=", "threshold": settings.gate_api_pass_rate, "blocking": True, "unit": "%"},
        {"key": "ui_pass_rate", "name": "UI pass rate", "operator": ">=", "threshold": settings.gate_ui_pass_rate, "blocking": True, "unit": "%"},
        {"key": "data_pass_rate", "name": "Data validation pass rate", "operator": ">=", "threshold": 100.0, "blocking": True, "unit": "%"},
        {"key": "api_p95_latency", "name": "API p95 latency", "operator": "<=", "threshold": settings.gate_api_p95_ms, "blocking": True, "unit": "ms"},
        {"key": "page_load_budget", "name": "Average page load", "operator": "<=", "threshold": settings.gate_page_load_ms, "blocking": True, "unit": "ms"},
        {"key": "load_error_rate", "name": "Load test error rate", "operator": "<=", "threshold": settings.gate_load_error_rate, "blocking": True, "unit": "%"},
        {"key": "data_failures", "name": "Data validation failures", "operator": "<=", "threshold": float(settings.gate_data_failures), "blocking": True, "unit": "rows"},
        {"key": "test_volume", "name": "Minimum executed checks", "operator": ">=", "threshold": 20.0, "blocking": False, "unit": "checks"},
    ]


@router.get("", summary="Quality gate configuration and latest results")
def list_gates(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> dict:
    latest = db.scalars(select(TestRun).order_by(TestRun.started_at.desc()).limit(1)).first()
    gates = list(latest.gates) if latest else []
    history = db.execute(
        select(TestRun.run_key, QualityGate.name, QualityGate.status, QualityGate.actual, QualityGate.threshold, TestRun.started_at)
        .join(QualityGate, QualityGate.run_id == TestRun.id)
        .where(QualityGate.status == "failed")
        .order_by(TestRun.started_at.desc())
        .limit(limit)
    ).all()
    return {
        "config": gate_config(),
        "latest_run": latest.run_key if latest else None,
        "latest_status": latest.status if latest else None,
        "evaluated_at": (latest.finished_at or latest.started_at) if latest else None,
        "items": [QualityGateOut.model_validate(g) for g in gates],
        "blocked": any(g.status == "failed" and g.blocking for g in gates),
        "recent_failures": [
            {
                "run_key": row[0],
                "gate": row[1],
                "actual": row[3],
                "threshold": row[4],
                "at": row[5],
            }
            for row in history
        ],
    }


@router.post("/evaluate/{run_key}", response_model=list[QualityGateOut], summary="Recompute gates for a run")
def evaluate(run_key: str, db: Session = Depends(get_db), _=Depends(current_user)) -> list[QualityGateOut]:
    run = db.scalar(select(TestRun).where(TestRun.run_key == run_key))
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_key} not found")
    gates = gate_service.replace_gates(db, run)
    return [QualityGateOut.model_validate(g) for g in gates]
