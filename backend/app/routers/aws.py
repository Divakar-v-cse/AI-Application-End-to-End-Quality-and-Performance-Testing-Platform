from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import Artifact
from ..schemas import ArtifactOut, AthenaRequest, AthenaResult, AwsStatus, LambdaRequest, LambdaResult
from ..services import aws as aws_service

router = APIRouter(prefix="/api/aws", tags=["AWS integration"])
artifacts_router = APIRouter(prefix="/api/artifacts", tags=["Artifacts"])


@router.get("/status", response_model=AwsStatus, summary="AWS integration status")
def integration_status(_=Depends(current_user)) -> AwsStatus:
    return AwsStatus.model_validate(aws_service.status())


@router.post("/athena/query", response_model=AthenaResult, summary="Run a read-only validation query on Athena")
def athena_query(payload: AthenaRequest, db: Session = Depends(get_db), _=Depends(current_user)) -> AthenaResult:
    try:
        result = aws_service.athena_query(db, payload.query)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface AWS errors without crashing the API
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Athena query failed: {exc}") from exc
    return AthenaResult.model_validate(result)


@router.post("/lambda/invoke", response_model=LambdaResult, summary="Invoke the quality-audit Lambda")
def lambda_invoke(payload: LambdaRequest, db: Session = Depends(get_db), _=Depends(current_user)) -> LambdaResult:
    try:
        result = aws_service.lambda_invoke(db, payload.payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Lambda invocation failed: {exc}") from exc
    return LambdaResult.model_validate(result)


@router.get("/cloudwatch/metrics", summary="CloudWatch latency datapoints")
def cloudwatch_metrics(days: int = 7, db: Session = Depends(get_db), _=Depends(current_user)) -> dict:
    return aws_service.cloudwatch_metrics(db, limit_days=days)


@artifacts_router.post("", response_model=ArtifactOut, status_code=201, summary="Upload a test artifact")
async def upload_artifact(
    file: UploadFile = File(...),
    run_key: str = Form(default=""),
    db: Session = Depends(get_db),
    _=Depends(current_user),
) -> ArtifactOut:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Artifact exceeds the 25 MB limit")
    artifact = aws_service.store_artifact(
        db,
        filename=file.filename or "artifact.bin",
        data=data,
        content_type=file.content_type or "application/octet-stream",
        run_key=run_key,
    )
    return ArtifactOut.model_validate(artifact)


@artifacts_router.get("", summary="List stored artifacts")
def list_artifacts(db: Session = Depends(get_db), _=Depends(current_user)) -> dict:
    rows = list(db.scalars(select(Artifact).order_by(Artifact.created_at.desc()).limit(50)).all())
    return {"items": [ArtifactOut.model_validate(row) for row in rows], "mode": aws_service.status()["storage_mode"]}
