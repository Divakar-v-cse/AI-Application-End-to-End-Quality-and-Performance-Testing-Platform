from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..schemas import DashboardSummary, TrendPoint
from ..services import analytics

router = APIRouter(prefix="/api/dashboard", tags=["Quality dashboard"])


@router.get("/summary", response_model=DashboardSummary, summary="Aggregated quality KPIs for the dashboard")
def summary(db: Session = Depends(get_db), _=Depends(current_user)) -> DashboardSummary:
    return DashboardSummary.model_validate(analytics.snapshot(db))


@router.get("/trend", response_model=list[TrendPoint], summary="Historical execution trend")
def execution_trend(
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> list[TrendPoint]:
    return [TrendPoint.model_validate(point) for point in analytics.trend(db, days)]
