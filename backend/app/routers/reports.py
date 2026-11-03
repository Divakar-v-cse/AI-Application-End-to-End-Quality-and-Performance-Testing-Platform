from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import user_from_request_or_query
from ..models import TestRun
from ..schemas import QualityGateOut, TestResultOut, TestRunOut
from ..services import reports

router = APIRouter(prefix="/api/reports", tags=["Reports"])

FORMATS = {
    "markdown": ("text/markdown; charset=utf-8", "md"),
    "md": ("text/markdown; charset=utf-8", "md"),
    "html": ("text/html; charset=utf-8", "html"),
    "junit": ("application/xml; charset=utf-8", "xml"),
    "xml": ("application/xml; charset=utf-8", "xml"),
    "csv": ("text/csv; charset=utf-8", "csv"),
    "json": ("application/json; charset=utf-8", "json"),
}


@router.get("/{run_key}/{fmt}", summary="Download a run report")
def download_report(run_key: str, fmt: str, request: Request, db: Session = Depends(get_db)) -> Response:
    user_from_request_or_query(request, db)
    run = db.scalar(select(TestRun).where(TestRun.run_key == run_key))
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_key} not found")
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported report format '{fmt}'. Use one of: {sorted(FORMATS)}",
        )
    media_type, extension = FORMATS[fmt]

    if fmt in {"markdown", "md"}:
        body = reports.build_markdown(db, run)
    elif fmt == "html":
        body = reports.build_html(db, run)
    elif fmt in {"junit", "xml"}:
        body = reports.build_junit(run)
    elif fmt == "csv":
        body = reports.build_csv(run)
    else:
        body = json.dumps(
            {
                "run": TestRunOut.model_validate(run).model_dump(mode="json"),
                "results": [TestResultOut.model_validate(r).model_dump(mode="json") for r in run.results],
                "gates": [QualityGateOut.model_validate(g).model_dump(mode="json") for g in run.gates],
            },
            indent=2,
        )

    filename = f"{run.run_key}-report.{extension}"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
