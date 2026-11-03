"""Environment-driven configuration.

Every integration is optional: the platform runs fully offline with SQLite and
local disk storage. AWS settings are only used when ``AWS_ENABLED=true`` and the
matching resource variables are present.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent

# Load project .env first, then backend/.env (backend wins).
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env", override=True)


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _paths(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = "AI Application End-to-End Quality and Performance Testing Platform"
    version: str = "1.0.0"
    environment: str = os.getenv("APP_ENV", "local")

    data_dir: Path = Path(os.getenv("DATA_DIR", str(BACKEND_DIR / "data")))
    database_url: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{(BACKEND_DIR / 'data' / 'quality.db').as_posix()}"
    )
    artifact_dir: Path = Path(os.getenv("ARTIFACT_DIR", str(BACKEND_DIR / "data" / "artifacts")))

    secret_key: str = os.getenv("SECRET_KEY", "local-dev-secret-change-me")
    token_ttl_minutes: int = _int("TOKEN_TTL_MINUTES", 480)

    cors_origins: list[str] = field(
        default_factory=lambda: _paths(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"
        )
    )

    # Quality gates (all blocking unless noted).
    gate_api_pass_rate: float = _float("GATE_API_PASS_RATE", 95.0)
    gate_ui_pass_rate: float = _float("GATE_UI_PASS_RATE", 90.0)
    gate_api_p95_ms: float = _float("GATE_API_P95_MS", 800.0)
    gate_page_load_ms: float = _float("GATE_PAGE_LOAD_MS", 3000.0)
    gate_load_error_rate: float = _float("GATE_LOAD_ERROR_RATE", 1.0)
    gate_data_failures: int = _int("GATE_DATA_FAILURES", 0)

    # Demo AI application under test.
    demo_user_email: str = os.getenv("DEMO_USER_EMAIL", "qa@example.com")
    demo_user_password: str = os.getenv("DEMO_USER_PASSWORD", "Passw0rd!")

    # Optional browser runner (disabled by default: needs Playwright browsers).
    enable_ui_runner: bool = _bool("ENABLE_UI_RUNNER", False)
    ui_runner_command: str = os.getenv("UI_RUNNER_COMMAND", "npx playwright test --reporter=json")
    ui_runner_timeout_s: int = _int("UI_RUNNER_TIMEOUT_S", 600)
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # AWS (optional).
    aws_enabled: bool = _bool("AWS_ENABLED", False)
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    s3_bucket: str = os.getenv("S3_BUCKET", "")
    s3_prefix: str = os.getenv("S3_PREFIX", "quality-artifacts")
    lambda_function: str = os.getenv("LAMBDA_FUNCTION", "")
    athena_database: str = os.getenv("ATHENA_DATABASE", "")
    athena_table: str = os.getenv("ATHENA_TABLE", "")
    athena_workgroup: str = os.getenv("ATHENA_WORKGROUP", "primary")
    athena_output: str = os.getenv("ATHENA_OUTPUT", "")
    cloudwatch_namespace: str = os.getenv("CLOUDWATCH_NAMESPACE", "AIQualityPlatform")

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
