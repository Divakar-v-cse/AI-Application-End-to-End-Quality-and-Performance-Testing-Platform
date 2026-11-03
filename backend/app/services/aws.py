"""Optional AWS integrations with a fully functional offline fallback.

Set ``AWS_ENABLED=true`` plus the resource variables to use real AWS. When a
resource is not configured, each function degrades to a local equivalent and
says so in its ``mode``/``message`` fields instead of failing.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ApiMetric, Artifact, DataValidationResult, TestRun
from ..database import utcnow

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _has_credentials() -> bool:
    return bool(os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY")) or bool(
        os.getenv("AWS_PROFILE")
    )


def configured() -> dict[str, bool]:
    return {
        "aws_enabled": settings.aws_enabled,
        "credentials": _has_credentials(),
        "s3_bucket": bool(settings.s3_bucket),
        "lambda_function": bool(settings.lambda_function),
        "athena_database": bool(settings.athena_database and settings.athena_output),
        "cloudwatch": True,
    }


def status() -> dict:
    flags = configured()
    live = settings.aws_enabled and flags["credentials"]
    return {
        "enabled": settings.aws_enabled,
        "region": settings.aws_region,
        "configured": flags,
        "storage_mode": "s3" if (live and flags["s3_bucket"]) else "local",
        "message": (
            "AWS integrations are active."
            if live
            else "AWS is not configured — S3 uploads fall back to local disk, Athena queries run against SQLite, and Lambda/CloudWatch calls return local parity data."
        ),
    }


def _client(service: str):
    import boto3  # imported lazily so the app runs without AWS extras

    return boto3.client(service, region_name=settings.aws_region)


def safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME.sub("-", Path(name).name).strip("-") or "artifact.bin"
    return cleaned[:180]


def store_artifact(db: Session, filename: str, data: bytes, content_type: str, run_key: str = "") -> Artifact:
    """Upload to S3 when configured, otherwise persist locally."""
    safe = safe_filename(filename)
    flags = configured()
    storage = "local"
    location = ""

    if settings.aws_enabled and flags["credentials"] and flags["s3_bucket"]:
        key = f"{settings.s3_prefix.rstrip('/')}/{run_key or 'unscoped'}/{int(time.time())}-{safe}"
        try:
            _client("s3").put_object(
                Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type
            )
            storage = "s3"
            location = f"s3://{settings.s3_bucket}/{key}"
        except Exception as exc:  # noqa: BLE001 - fall back rather than lose the artifact
            location = f"local-fallback ({exc.__class__.__name__})"

    if storage == "local":
        target_dir = settings.artifact_dir / (run_key or "unscoped")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{int(time.time())}-{safe}"
        target.write_bytes(data)
        location = str(target)

    artifact = Artifact(
        run_key=run_key,
        filename=safe,
        storage=storage,
        location=location,
        size_bytes=len(data),
        content_type=content_type,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def athena_query(db: Session, query: str) -> dict:
    """Run a validation query on Athena, or on SQLite locally.

    Only read-only statements are accepted in either mode.
    """
    normalized = query.strip().rstrip(";")
    if not re.match(r"(?is)^(select|with)\b", normalized):
        raise ValueError("Only SELECT / WITH statements are allowed")

    flags = configured()
    if settings.aws_enabled and flags["credentials"] and flags["athena_database"]:
        client = _client("athena")
        started = time.perf_counter()
        execution = client.start_query_execution(
            QueryString=normalized,
            QueryExecutionContext={"Database": settings.athena_database},
            ResultConfiguration={"OutputLocation": settings.athena_output},
            WorkGroup=settings.athena_workgroup,
        )
        execution_id = execution["QueryExecutionId"]
        for _ in range(30):
            details = client.get_query_execution(QueryExecutionId=execution_id)["QueryExecution"]
            state = details["Status"]["State"]
            if state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                break
            time.sleep(1)
        if state != "SUCCEEDED":
            raise RuntimeError(details["Status"].get("StateChangeReason", f"Athena query {state}"))
        result = client.get_query_results(QueryExecutionId=execution_id)
        rows = [
            [col.get("VarCharValue", "") for col in row["Data"]]
            for row in result["ResultSet"]["Rows"]
        ]
        return {
            "mode": "athena",
            "query": normalized,
            "columns": rows[0] if rows else [],
            "rows": rows[1:],
            "scanned_bytes": int(details.get("Statistics", {}).get("DataScannedInBytes", 0)),
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "message": f"Executed on Athena workgroup {settings.athena_workgroup}",
        }

    started = time.perf_counter()
    try:
        result = db.execute(text(normalized))
    except SQLAlchemyError as exc:
        # A query the client wrote is a client error, not an upstream failure.
        db.rollback()
        detail = str(getattr(exc, "orig", exc)).splitlines()[0]
        raise ValueError(f"Invalid SQL: {detail}") from exc
    columns = list(result.keys())
    rows = [[str(value) for value in row] for row in result.fetchall()[:200]]
    return {
        "mode": "local-sqlite",
        "query": normalized,
        "columns": columns,
        "rows": rows,
        "scanned_bytes": len(normalized.encode()) * max(1, len(rows)),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "message": "Athena is not configured — the query ran against the local SQLite mirror.",
    }


def lambda_invoke(db: Session, payload: dict) -> dict:
    """Invoke the configured Lambda, or execute the same audit locally."""
    flags = configured()
    function_name = settings.lambda_function or "quality-audit"
    if settings.aws_enabled and flags["credentials"] and settings.lambda_function:
        client = _client("lambda")
        started = time.perf_counter()
        response = client.invoke(
            FunctionName=settings.lambda_function,
            Payload=json.dumps(payload).encode(),
            InvocationType="RequestResponse",
        )
        body = response["Payload"].read().decode()
        return {
            "mode": "lambda",
            "function": function_name,
            "status_code": response["StatusCode"],
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "payload": json.loads(body or "{}"),
            "message": "Invoked on AWS Lambda",
        }

    started = time.perf_counter()
    latest = db.scalars(select(TestRun).order_by(TestRun.started_at.desc()).limit(1)).first()
    failures = db.scalar(
        select(func.count()).select_from(DataValidationResult).where(DataValidationResult.status == "failed")
    ) or 0
    return {
        "mode": "local-fallback",
        "function": function_name,
        "status_code": 200,
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "payload": {
            "audit": "quality-snapshot",
            "requested": payload,
            "latest_run": latest.run_key if latest else None,
            "latest_status": latest.status if latest else None,
            "open_data_failures": int(failures),
            "generated_at": utcnow().isoformat() + "Z",
        },
        "message": "Lambda is not configured — the local audit handler produced this payload.",
    }


def cloudwatch_metrics(db: Session, limit_days: int = 7) -> dict:
    """Return latency/error datapoints from CloudWatch or from the local mirror."""
    flags = configured()
    if settings.aws_enabled and flags["credentials"]:
        client = _client("cloudwatch")
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - limit_days * 86400))
        response = client.get_metric_statistics(
            Namespace=settings.cloudwatch_namespace,
            MetricName="ApiLatencyMs",
            StartTime=started,
            EndTime=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            Period=86400,
            Statistics=["Average"],
        )
        points = [
            {"timestamp": point["Timestamp"].isoformat(), "value": round(point["Average"], 2)}
            for point in sorted(response.get("Datapoints", []), key=lambda p: p["Timestamp"])
        ]
        return {"mode": "cloudwatch", "namespace": settings.cloudwatch_namespace, "metric": "ApiLatencyMs", "points": points}

    rows = db.execute(
        select(
            func.date(ApiMetric.created_at).label("day"),
            func.avg(ApiMetric.response_time_ms).label("avg_ms"),
            func.count().label("calls"),
        )
        .group_by(func.date(ApiMetric.created_at))
        .order_by(func.date(ApiMetric.created_at))
    ).all()
    points = [{"timestamp": str(row.day), "value": round(float(row.avg_ms or 0), 2), "calls": int(row.calls)} for row in rows]
    return {
        "mode": "local-mirror",
        "namespace": settings.cloudwatch_namespace,
        "metric": "ApiLatencyMs",
        "points": points,
    }
