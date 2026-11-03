from __future__ import annotations

from datetime import timedelta
from statistics import mean

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db, utcnow
from ..deps import current_user
from ..models import ApiMetric, PageMetric
from ..schemas import ApiMetricOut, PageMetricOut
from ..services.gates import percentile

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


@router.get("/api", summary="API response time telemetry")
def api_metrics(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> dict:
    cutoff = utcnow() - timedelta(days=days)
    rows = list(
        db.scalars(
            select(ApiMetric)
            .where(ApiMetric.created_at >= cutoff)
            .order_by(ApiMetric.created_at.desc())
            .limit(limit)
        ).all()
    )
    all_values = [float(v) for v in db.scalars(select(ApiMetric.response_time_ms).where(ApiMetric.created_at >= cutoff)).all()]
    errors = int(
        sum(1 for row in rows if row.status_code >= 400)
    )
    by_endpoint: dict[str, list[float]] = {}
    for row in rows:
        by_endpoint.setdefault(row.endpoint, []).append(float(row.response_time_ms))
    return {
        "items": [ApiMetricOut.model_validate(row) for row in rows],
        "summary": {
            "calls": len(all_values),
            "avg_ms": round(mean(all_values), 2) if all_values else 0.0,
            "p95_ms": percentile(all_values, 95),
            "p99_ms": percentile(all_values, 99),
            "max_ms": round(max(all_values), 2) if all_values else 0.0,
            "error_rate": round(errors / len(rows) * 100, 2) if rows else 0.0,
            "window_days": days,
        },
        "by_endpoint": [
            {
                "endpoint": endpoint,
                "avg_ms": round(mean(values), 2),
                "p95_ms": percentile(values, 95),
                "calls": len(values),
            }
            for endpoint, values in sorted(by_endpoint.items(), key=lambda kv: len(kv[1]), reverse=True)
        ],
    }


@router.get("/pages", summary="Browser page load telemetry")
def page_metrics(
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> dict:
    cutoff = utcnow() - timedelta(days=days)
    rows = list(
        db.scalars(select(PageMetric).where(PageMetric.created_at >= cutoff).order_by(PageMetric.created_at.desc()).limit(300)).all()
    )
    values = [float(row.load_time_ms) for row in rows]
    by_page: dict[str, list[float]] = {}
    for row in rows:
        by_page.setdefault(row.page, []).append(float(row.load_time_ms))
    return {
        "items": [PageMetricOut.model_validate(row) for row in rows],
        "summary": {
            "samples": len(values),
            "avg_ms": round(mean(values), 2) if values else 0.0,
            "p95_ms": percentile(values, 95),
            "slowest_ms": round(max(values), 2) if values else 0.0,
            "budget_ms": 3000,
            "window_days": days,
        },
        "by_page": [
            {"page": page, "avg_ms": round(mean(vals), 2), "samples": len(vals)}
            for page, vals in sorted(by_page.items(), key=lambda kv: mean(kv[1]), reverse=True)
        ],
    }
