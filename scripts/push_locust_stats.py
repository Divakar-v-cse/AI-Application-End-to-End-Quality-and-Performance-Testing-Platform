#!/usr/bin/env python
"""Publish Locust statistics to the platform so the load gate can see them.

Locust is usually run headless with CSV output:

    locust -f locust/locustfile.py --host http://127.0.0.1:8000 \
        --headless -u 20 -r 4 -t 30s --csv locust/out/ci --only-summary

    python scripts/push_locust_stats.py --csv-prefix locust/out/ci \
        --users 20 --spawn-rate 4 --duration 30

A JSON summary is also accepted (either a flat dict or the ``{"stats": [...]}``
shape that Locust's JSON listeners produce):

    python scripts/push_locust_stats.py --json locust/out/stats.json

Exit codes: 0 = stats ingested, 1 = the platform rejected them / was
unreachable, 2 = the input file could not be parsed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


def _percentile_index(header: list[str], name: str) -> int | None:
    for index, column in enumerate(header):
        if column.strip().rstrip("%") == name:
            return index
    return None


def _number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    raw = row.get(key, "")
    try:
        return float(str(raw).strip() or default)
    except ValueError:
        return default


def parse_csv(prefix: Path) -> dict[str, Any]:
    stats_file = Path(f"{prefix}_stats.csv")
    if not stats_file.exists():
        raise FileNotFoundError(f"Locust stats CSV not found: {stats_file}")

    with stats_file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        header = reader.fieldnames or []

    if not rows:
        raise ValueError(f"{stats_file} contains no rows")

    # Locust writes one row per endpoint plus an "Aggregated" row.
    aggregated = next((row for row in rows if row.get("Name", "").strip() == "Aggregated"), None)
    selected = aggregated or max(rows, key=lambda row: _number(row, "Request Count"))

    p95_index = _percentile_index(header, "95")
    p99_index = _percentile_index(header, "99")
    p95_column = header[p95_index] if p95_index is not None else None
    p99_column = header[p99_index] if p99_index is not None else None

    def from_column(row: dict[str, str], column: str | None) -> float:
        return _number(row, column) if column else 0.0

    requests = int(_number(selected, "Request Count"))
    failures = int(_number(selected, "Failure Count"))
    per_endpoint = [
        {
            "name": row.get("Name", ""),
            "num_requests": int(_number(row, "Request Count")),
            "num_failures": int(_number(row, "Failure Count")),
            "avg_response_time": _number(row, "Average Response Time"),
            "median_response_time": _number(row, "Median Response Time"),
            "max_response_time": _number(row, "Max Response Time"),
        }
        for row in rows
        if row.get("Name", "").strip() != "Aggregated"
    ]

    return {
        "requests": requests,
        "failures": failures,
        "rps": _number(selected, "Requests/s"),
        "avg_ms": _number(selected, "Average Response Time"),
        "median_ms": _number(selected, "Median Response Time"),
        "p95_ms": from_column(selected, p95_column),
        "p99_ms": from_column(selected, p99_column),
        "max_ms": _number(selected, "Max Response Time"),
        "stats": per_endpoint,
        "source": str(stats_file),
    }


def parse_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    payload.setdefault("source", str(path))
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Push Locust statistics to /api/ingest/locust.")
    parser.add_argument("--base-url", default=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--email", default=os.getenv("DEMO_USER_EMAIL", "qa@example.com"))
    parser.add_argument("--password", default=os.getenv("DEMO_USER_PASSWORD", "Passw0rd!"))
    parser.add_argument("--csv-prefix", default=None, help="Locust --csv prefix, e.g. locust/out/ci")
    parser.add_argument("--json", dest="json_path", default=None, help="JSON summary instead of CSV")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--spawn-rate", type=float, default=2.0)
    parser.add_argument("--duration", type=int, default=60, help="Run duration in seconds")
    parser.add_argument("--target", default=os.getenv("FRONTEND_URL", "http://localhost:5173"))
    parser.add_argument("--scenario", default="mixed_read_write")
    parser.add_argument("--notes", default="")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    if not args.csv_prefix and not args.json_path:
        parser.error("provide either --csv-prefix or --json")

    try:
        if args.json_path:
            stats = parse_json(Path(args.json_path))
        else:
            stats = parse_csv(Path(args.csv_prefix))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Could not read Locust statistics: {exc}", file=sys.stderr)
        return 2

    payload = {
        "target": args.target,
        "scenario": args.scenario,
        "users": args.users,
        "spawn_rate": args.spawn_rate,
        "duration_s": args.duration,
        "notes": args.notes or f"Locust statistics from {stats.get('source', 'locust')}",
        **{key: stats[key] for key in ("requests", "failures") if key in stats},
    }
    for key in ("rps", "avg_ms", "median_ms", "p95_ms", "p99_ms", "max_ms", "stats"):
        if key in stats:
            payload[key] = stats[key]

    try:
        with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
            login = client.post("/api/auth/login", json={"email": args.email, "password": args.password})
            if login.status_code != 200:
                print(f"Login failed with HTTP {login.status_code}: {login.text[:300]}", file=sys.stderr)
                return 1
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            response = client.post("/api/ingest/locust", json=payload, headers=headers)
    except httpx.HTTPError as exc:
        print(f"Could not reach the API at {args.base_url}: {exc}", file=sys.stderr)
        return 1

    if response.status_code != 200:
        print(f"Ingest failed with HTTP {response.status_code}: {response.text[:400]}", file=sys.stderr)
        return 1

    body = response.json()
    print(
        f"Ingested {payload.get('requests', 0)} requests "
        f"({payload.get('failures', 0)} failures, "
        f"{body.get('error_rate')}% error rate) as {body.get('run_key')} -> {body.get('status')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
