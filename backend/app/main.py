from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from .config import settings
from .database import SessionLocal, init_db
from .routers import api_aws, api_data_quality, api_dashboard, api_demo_ai, api_gates, api_ingest, api_metrics, api_performance, api_reports, api_runs, api_auth

DESCRIPTION = """
End-to-end quality and performance testing platform for AI applications.

**Suites**
* `api` — pytest-style HTTP contract, auth, validation and latency checks executed against this service.
* `ui` — Playwright specs for login, navigation, forms, dashboard, error handling and chatbot flows.
* `db` — SQL validation queries for duplicates, orphans, nulls, domain and AI-evaluation integrity.
* `perf` — Locust load-test summaries with RPS, p95 and error-rate gates.

OpenAPI is published at `/openapi.json`; an interactive console is available at `/docs`.
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if os.getenv("SEED_ON_STARTUP", "true").lower() in {"1", "true", "yes"}:
        from .seed import ensure_seed_data

        with SessionLocal() as db:
            ensure_seed_data(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=DESCRIPTION,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Authentication", "description": "Bearer token issuance and identity."},
        {"name": "Quality dashboard", "description": "Aggregated KPIs and historical trends."},
        {"name": "Test execution", "description": "Catalog, runs and on-demand execution."},
        {"name": "Metrics", "description": "API and browser timing telemetry."},
        {"name": "Data validation", "description": "SQL quality checks."},
        {"name": "Performance", "description": "Locust load-test results."},
        {"name": "Quality gates", "description": "Release thresholds and pass/fail decisions."},
        {"name": "Reports", "description": "Markdown, HTML, JUnit, CSV and JSON exports."},
        {"name": "CI ingestion", "description": "Push results from GitHub Actions, pytest, Playwright and Locust."},
        {"name": "Demo AI application", "description": "The application under test."},
        {"name": "AWS integration", "description": "Optional S3, Lambda, Athena and CloudWatch hooks."},
        {"name": "Artifacts", "description": "Test artifact storage (S3 or local)."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

for router in (
    api_auth.router,
    api_dashboard.router,
    api_runs.router,
    api_metrics.router,
    api_data_quality.router,
    api_performance.router,
    api_gates.router,
    api_reports.router,
    api_ingest.router,
    api_demo_ai.router,
    api_aws.router,
    api_aws.artifacts_router,
):
    app.include_router(router)


@app.get("/healthz", tags=["Health"], summary="Liveness and database probe")
def healthz() -> dict:
    status = "ok"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - report degraded instead of crashing
        status = "degraded"
    return {
        "status": status,
        "service": "ai-quality-platform",
        "version": settings.version,
        "environment": settings.environment,
    }


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")
