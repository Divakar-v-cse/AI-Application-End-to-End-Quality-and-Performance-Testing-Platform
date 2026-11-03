"""Database validation suite.

Every SQL check declared in ``app.services.checks.DB_CHECKS`` (the same catalog
that powers ``/api/data-quality`` and ``sql/validation_queries.sql``) is executed
against the seeded SQLite database. A check passes when it returns no rows.

The negative-control tests then inject bad data to prove the checks actually
detect violations instead of trivially passing.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from app.services.checks import DB_CHECKS, execute_db_check

ROOT = Path(__file__).resolve().parents[2]
SQL_FILE = ROOT / "sql" / "validation_queries.sql"

COVERAGE = {
    "missing records": {"db.results.orphans", "db.metrics.orphans"},
    "duplicate records": {"db.users.unique_email", "db.runs.duplicate_keys", "db.cases.duplicate_keys"},
    "invalid data types": {"db.results.status_domain", "db.api.status_range", "db.chat.role_domain"},
    "null values": {"db.runs.required_fields"},
    "data consistency": {"db.load.consistency", "db.runs.time_order", "db.metrics.latency_positive"},
    "AI evaluation integrity": {"db.eval.score_range", "db.eval.integrity"},
}


def test_catalog_has_fifteen_checks():
    assert len(DB_CHECKS) == 15
    keys = [check.key for check in DB_CHECKS]
    assert len(set(keys)) == 15
    assert all(key.startswith("db.") for key in keys)


def test_catalog_covers_every_required_category():
    keys = {check.key for check in DB_CHECKS}
    for category, expected in COVERAGE.items():
        missing = expected - keys
        assert not missing, f"{category} coverage missing: {sorted(missing)}"


def test_checks_are_read_only():
    for check in DB_CHECKS:
        statement = check.sql.strip().upper()
        assert statement.startswith("SELECT"), f"{check.key} must be a SELECT"
        for keyword in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER "):
            assert keyword not in statement, f"{check.key} contains a write: {keyword}"


def test_checks_declare_metadata():
    for check in DB_CHECKS:
        assert check.name and check.description
        assert check.table
        assert check.severity in {"critical", "major", "minor"}


@pytest.mark.parametrize("check", DB_CHECKS, ids=[check.key for check in DB_CHECKS])
def test_check_passes_on_seeded_data(db, check):
    outcome = execute_db_check(db, check)

    assert outcome["status"] == "passed", f"{check.key}: {outcome['message']} sample={outcome['sample']}"
    assert outcome["failing_rows"] == 0
    assert outcome["total_rows"] > 0, f"{check.key} scanned an empty table"
    assert outcome["duration_ms"] >= 0
    assert outcome["query"]


def test_sql_file_exists_and_lists_every_check():
    assert SQL_FILE.exists(), f"Missing {SQL_FILE}"
    sql = SQL_FILE.read_text(encoding="utf-8")

    for check in DB_CHECKS:
        assert check.key in sql, f"{check.key} missing from sql/validation_queries.sql"
        normalized = " ".join(check.sql.split())
        assert normalized in " ".join(sql.split()), f"{check.key} SQL drifted from the catalog"


def test_sql_file_is_read_only():
    sql = SQL_FILE.read_text(encoding="utf-8")
    upper = sql.upper()

    for keyword in ("INSERT INTO", "DELETE FROM", "DROP TABLE", "ALTER TABLE", "TRUNCATE"):
        assert keyword not in upper, f"validation_queries.sql must not contain {keyword}"


def _run(db, key: str):
    check = next(item for item in DB_CHECKS if item.key == key)
    return execute_db_check(db, check)


def test_detects_duplicate_email(tmp_path):
    """Negative control: duplicate users must fail db.users.unique_email.

    The production schema enforces ``UNIQUE(email)``, so a duplicate cannot be
    inserted into the shared database. The check is therefore exercised against
    an isolated copy of the ``users`` table that intentionally omits that
    constraint - exactly the state a bad migration would leave behind.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(f"sqlite:///{(tmp_path / 'duplicates.db').as_posix()}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL, "
                "full_name VARCHAR(120) NOT NULL, role VARCHAR(40) NOT NULL, "
                "password_hash VARCHAR(255) NOT NULL, is_active BOOLEAN NOT NULL, "
                "created_at DATETIME NOT NULL)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (email, full_name, role, password_hash, is_active, created_at) VALUES "
                "('qa@example.com', 'First', 'qa', 'x', 1, CURRENT_TIMESTAMP), "
                "('qa@example.com', 'Second', 'qa', 'x', 1, CURRENT_TIMESTAMP)"
            )
        )

    with Session(engine) as session:
        outcome = _run(session, "db.users.unique_email")
    engine.dispose()

    assert outcome["status"] == "failed"
    assert outcome["failing_rows"] == 1
    assert "qa@example.com" in outcome["sample"]


def test_detects_out_of_range_evaluation_score(db):
    """Negative control: AI evaluation integrity covers the 0-100 score domain."""
    db.execute(
        text(
            "INSERT INTO evaluation_results (conversation_id, model, prompt, score, verdict, latency_ms, reviewer, created_at) "
            "VALUES ('conv-negative', 'accio-mini', 'p', 140, 'pass', 0, 'qa', CURRENT_TIMESTAMP)"
        )
    )
    try:
        outcome = _run(db, "db.eval.score_range")
        assert outcome["status"] == "failed"
        assert outcome["failing_rows"] == 1
    finally:
        db.rollback()


def test_detects_orphan_evaluation(db):
    """Negative control: an evaluation pointing at no conversation is caught."""
    db.execute(
        text(
            "INSERT INTO evaluation_results (conversation_id, model, prompt, score, verdict, latency_ms, reviewer, created_at) "
            "VALUES ('conv-missing-reference', 'accio-pro', 'p', 80, 'pass', 0, 'qa', CURRENT_TIMESTAMP)"
        )
    )
    try:
        outcome = _run(db, "db.eval.integrity")
        assert outcome["status"] == "failed"
        assert outcome["failing_rows"] == 1
    finally:
        db.rollback()


def test_detects_inconsistent_load_aggregate(db):
    """Negative control: failures > requests is impossible and must be flagged."""
    db.execute(
        text(
            "INSERT INTO load_test_runs (run_key, target, scenario, users, spawn_rate, duration_s, requests, failures, "
            "error_rate, rps, avg_ms, median_ms, p95_ms, p99_ms, max_ms, status, notes, created_at) "
            "VALUES ('LOAD-NEGATIVE-001', 'x', 's', 1, 1, 1, 10, 99, 5, 1, 1, 1, 1, 1, 1, 'failed', '', CURRENT_TIMESTAMP)"
        )
    )
    try:
        outcome = _run(db, "db.load.consistency")
        assert outcome["status"] == "failed"
        assert outcome["failing_rows"] == 1
    finally:
        db.rollback()


def test_detects_invalid_status_domain(db):
    """Negative control: an unknown result status must break the domain check."""
    run_id = db.execute(text("SELECT id FROM test_runs LIMIT 1")).scalar()
    db.execute(
        text(
            "INSERT INTO test_results (run_id, case_key, name, suite, module, status, duration_ms, error_message, "
            "stack_trace, evidence, created_at) "
            "VALUES (:run_id, 'negative.bad.status', 'n', 'api', 'negative', 'unknown_status', 1, '', '', '', CURRENT_TIMESTAMP)"
        ),
        {"run_id": run_id},
    )
    try:
        outcome = _run(db, "db.results.status_domain")
        assert outcome["status"] == "failed"
        assert outcome["failing_rows"] == 1
    finally:
        db.rollback()


def test_broken_query_reports_error(db):
    """A query that cannot execute is an error, not a silent pass."""
    from app.services.checks import DbCheck

    broken = DbCheck("db.broken", "Always broken", "no_such_table", "minor", "n/a", "SELECT * FROM no_such_table")
    outcome = execute_db_check(db, broken)

    assert outcome["status"] == "error"
    assert outcome["failing_rows"] == 0
    assert "Query failed" in outcome["message"]
