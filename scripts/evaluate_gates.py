#!/usr/bin/env python
"""Evaluate the quality gates and fail the CI job when a blocking gate fails.

Usage
-----
    # Evaluate the newest run (the usual CI case, after results were ingested)
    python scripts/evaluate_gates.py

    # Evaluate a specific run and keep the machine-readable report
    python scripts/evaluate_gates.py --run-key RUN-20261103-120000-AB12 \
        --output reports/quality-gates.json

    # Report only, never fail the build
    python scripts/evaluate_gates.py --no-fail-on-blocked

Exit codes: 0 = every blocking gate passed, 1 = at least one blocking gate
failed (or the API could not be reached), 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

ICONS = {"passed": "PASS", "failed": "FAIL", "not_applicable": "N/A "}


def login(client: httpx.Client, email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    if response.status_code != 200:
        raise SystemExit(f"Login failed with HTTP {response.status_code}: {response.text[:300]}")
    return response.json()["access_token"]


def resolve_run_key(client: httpx.Client, headers: dict[str, str], run_key: str | None) -> str | None:
    if run_key:
        return run_key
    body = client.get("/api/quality-gates", headers=headers).json()
    return body.get("latest_run")


def evaluate(client: httpx.Client, headers: dict[str, str], run_key: str | None) -> dict[str, Any]:
    if run_key:
        response = client.post(f"/api/quality-gates/evaluate/{run_key}", headers=headers)
        if response.status_code == 404:
            raise SystemExit(f"Run {run_key} does not exist (HTTP 404).")
        if response.status_code != 200:
            raise SystemExit(f"Gate evaluation failed with HTTP {response.status_code}: {response.text[:300]}")
        items = response.json()
        return {"run_key": run_key, "items": items, "blocked": any(i["status"] == "failed" and i["blocking"] for i in items)}

    body = client.get("/api/quality-gates", headers=headers).json()
    return {
        "run_key": body.get("latest_run"),
        "items": body.get("items", []),
        "blocked": bool(body.get("blocked")),
        "config": body.get("config", []),
        "evaluated_at": body.get("evaluated_at"),
    }


def render(report: dict[str, Any]) -> str:
    lines = [
        "",
        f"Quality gates for run {report['run_key'] or '(none)'}",
        "-" * 78,
        f"{'GATE':<24}{'STATUS':<8}{'ACTUAL':>10}  THRESHOLD   MODE",
        "-" * 78,
    ]
    for gate in report["items"]:
        mode = "blocking" if gate["blocking"] else "advisory"
        threshold = f"{gate['operator']} {gate['threshold']}"
        lines.append(
            f"{gate['gate_key']:<24}{ICONS.get(gate['status'], gate['status']):<8}"
            f"{gate['actual']:>10}  {threshold:<11}{mode}"
        )
        lines.append(f"    {gate['message']}")
    lines.append("-" * 78)
    lines.append("BLOCKED: a blocking gate failed - the pipeline must stop." if report["blocked"] else "All blocking gates passed.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate quality gates for a run.")
    parser.add_argument("--base-url", default=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--email", default=os.getenv("DEMO_USER_EMAIL", "qa@example.com"))
    parser.add_argument("--password", default=os.getenv("DEMO_USER_PASSWORD", "Passw0rd!"))
    parser.add_argument("--run-key", default=None, help="Run to evaluate (default: newest run)")
    parser.add_argument("--output", default=None, help="Write the JSON report to this path")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--fail-on-blocked",
        dest="fail_on_blocked",
        action="store_true",
        default=True,
        help="Exit 1 when a blocking gate fails (default)",
    )
    parser.add_argument("--no-fail-on-blocked", dest="fail_on_blocked", action="store_false")
    args = parser.parse_args(argv)

    try:
        with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
            token = login(client, args.email, args.password)
            headers = {"Authorization": f"Bearer {token}"}
            run_key = resolve_run_key(client, headers, args.run_key)
            report = evaluate(client, headers, run_key)
    except httpx.HTTPError as exc:
        print(f"Could not reach the API at {args.base_url}: {exc}", file=sys.stderr)
        return 1

    print(render(report))

    report_path = Path(args.output) if args.output else None
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nJSON report written to {report_path}")

    if report["blocked"] and args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
