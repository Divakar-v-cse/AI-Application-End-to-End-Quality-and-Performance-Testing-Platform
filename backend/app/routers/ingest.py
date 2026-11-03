from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import PageMetric, TestRun
from ..schemas import TestRunOut
from ..services import runner

router = APIRouter(prefix="/api/ingest", tags=["CI ingestion"])


async def _document(request: Request) -> str:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        upload = next((value for value in form.values() if hasattr(value, "read")), None)
        if upload is None:
            raise HTTPException(status_code=400, detail="No file part found in the multipart body")
        return (await upload.read()).decode("utf-8", errors="replace")
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty request body")
    return raw.decode("utf-8", errors="replace")


@router.post("/junit", summary="Ingest a JUnit XML report as a new run")
async def ingest_junit(
    request: Request,
    suite: str = Query(default="api"),
    branch: str = Query(default="main"),
    commit: str = Query(default="local"),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> dict:
    xml_text = await _document(request)
    try:
        run = runner.ingest_junit(db, xml_text, suite=suite, branch=branch, commit=commit)
    except Exception as exc:  # noqa: BLE001 - malformed XML is a client error
        raise HTTPException(status_code=400, detail=f"Invalid JUnit XML: {exc}") from exc
    return {"run": TestRunOut.model_validate(run), "ingested": run.total}


@router.post("/playwright", summary="Ingest a Playwright JSON report")
async def ingest_playwright(
    request: Request,
    branch: str = Query(default="main"),
    commit: str = Query(default="local"),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> dict:
    raw = await _document(request)
    try:
        report = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    run = runner.ingest_playwright(db, report, branch=branch, commit=commit)
    return {"run": TestRunOut.model_validate(run), "ingested": run.total}


@router.post("/locust", summary="Ingest Locust statistics")
async def ingest_locust(
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> dict:
    raw = await _document(request)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
    row = runner.record_load_test(db, payload)
    return {"run_key": row.run_key, "requests": row.requests, "error_rate": row.error_rate, "status": row.status}


class PageMetricItem(BaseModel):
    page: str = Field(min_length=1, max_length=120)
    load_time_ms: float = Field(gt=0)
    ttfb_ms: float = Field(default=0, ge=0)
    dom_interactive_ms: float = Field(default=0, ge=0)
    network_idle_ms: float = Field(default=0, ge=0)


class PageMetricBatch(BaseModel):
    run_key: str | None = None
    items: list[PageMetricItem]


@router.post("/page-metrics", summary="Ingest browser navigation timings")
def ingest_page_metrics(payload: PageMetricBatch, db: Session = Depends(get_db), _=Depends(current_user)) -> dict:
    run = db.scalar(select(TestRun).where(TestRun.run_key == payload.run_key)) if payload.run_key else None
    for item in payload.items:
        db.add(PageMetric(run_id=run.id if run else None, **item.model_dump()))
    db.commit()
    return {"ingested": len(payload.items), "run_key": payload.run_key}
