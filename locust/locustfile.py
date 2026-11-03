"""Locust load profile for the AI Quality Platform.

Two ways to use this file:

  # Interactive UI on http://localhost:8089
  locust -f locust/locustfile.py --host http://127.0.0.1:8000

  # Headless burst for CI (30 s, 20 users, 4 users/s spawn rate)
  locust -f locust/locustfile.py --host http://127.0.0.1:8000 \
      --headless -u 20 -r 4 -t 30s --csv locust/out/ci --only-summary

Then publish the numbers so the quality gates see them:

  python scripts/push_locust_stats.py --csv-prefix locust/out/ci --users 20 \
      --spawn-rate 4 --duration 30

Weighting mirrors production traffic: the dashboard and run history dominate,
the chatbot is the slowest call, and writes are rare.
"""
from __future__ import annotations

import os
import random

from locust import HttpUser, between, tag, task


class QualityPlatformUser(HttpUser):
    """An authenticated QA engineer browsing the quality platform."""

    wait_time = between(0.5, 2.0)
    host = os.getenv("LOCUST_HOST", "http://127.0.0.1:8000")

    email = os.getenv("DEMO_USER_EMAIL", "qa@example.com")
    password = os.getenv("DEMO_USER_PASSWORD", "Passw0rd!")

    def on_start(self) -> None:
        with self.client.post(
            "/api/auth/login",
            json={"email": self.email, "password": self.password},
            name="POST /api/auth/login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login failed with HTTP {response.status_code}")
                self.token = ""
                return
            self.token = response.json().get("access_token", "")
            response.success()

        self.run_keys: list[str] = []
        listing = self.client.get("/api/runs?limit=10", headers=self._auth, name="GET /api/runs (warm-up)")
        if listing.status_code == 200:
            self.run_keys = [row["run_key"] for row in listing.json().get("items", [])]

    @property
    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # ---------------------------------------------------------------- reads
    @tag("read", "dashboard")
    @task(6)
    def dashboard_summary(self) -> None:
        with self.client.get(
            "/api/dashboard/summary", headers=self._auth, name="GET /api/dashboard/summary", catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
            elif "pass_rate" not in response.json():
                response.failure("summary payload is missing pass_rate")
            else:
                response.success()

    @tag("read", "dashboard")
    @task(3)
    def dashboard_trend(self) -> None:
        self.client.get("/api/dashboard/trend?days=14", headers=self._auth, name="GET /api/dashboard/trend")

    @tag("read", "runs")
    @task(5)
    def run_history(self) -> None:
        self.client.get("/api/runs?limit=12", headers=self._auth, name="GET /api/runs")

    @tag("read", "runs")
    @task(4)
    def run_detail(self) -> None:
        if not self.run_keys:
            self.run_keys = ["RUN-19700101-0000-XXXX"]
        run_key = random.choice(self.run_keys)
        # A 404 for an unknown key is a client error, not a server failure, so
        # only unexpected statuses are recorded as failures.
        with self.client.get(
            f"/api/runs/{run_key}", headers=self._auth, name="GET /api/runs/[run_key]", catch_response=True
        ) as response:
            if response.status_code in {200, 404}:
                response.success()
            else:
                response.failure(f"HTTP {response.status_code}")

    @tag("read", "metrics")
    @task(3)
    def api_metrics(self) -> None:
        self.client.get("/api/metrics/api?days=7", headers=self._auth, name="GET /api/metrics/api")

    @tag("read", "metrics")
    @task(2)
    def page_metrics(self) -> None:
        self.client.get("/api/metrics/pages", headers=self._auth, name="GET /api/metrics/pages")

    @tag("read", "data")
    @task(2)
    def data_quality(self) -> None:
        self.client.get("/api/data-quality/checks", headers=self._auth, name="GET /api/data-quality/checks")

    @tag("read", "performance")
    @task(2)
    def performance_summary(self) -> None:
        self.client.get("/api/performance/runs", headers=self._auth, name="GET /api/performance/runs")

    @tag("read", "gates")
    @task(2)
    def quality_gates(self) -> None:
        self.client.get("/api/quality-gates", headers=self._auth, name="GET /api/quality-gates")

    @tag("read", "docs")
    @task(1)
    def openapi(self) -> None:
        self.client.get("/openapi.json", name="GET /openapi.json")

    # --------------------------------------------------------------- writes
    @tag("write", "chat")
    @task(2)
    def chat(self) -> None:
        prompt = random.choice(
            [
                "What is the current API p95 latency?",
                "Which suite covers database integrity?",
                "Summarise the last load test",
                "How do quality gates block a release?",
            ]
        )
        with self.client.post(
            "/api/chat",
            json={"message": prompt, "model": "accio-mini"},
            headers=self._auth,
            name="POST /api/chat",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
            elif not response.json().get("reply", {}).get("content"):
                response.failure("empty assistant reply")
            else:
                response.success()

    @tag("write", "runs")
    @task(1)
    def execute_database_suite(self) -> None:
        with self.client.post(
            "/api/runs",
            json={"suite": "db", "branch": "load-test"},
            headers=self._auth,
            name="POST /api/runs (db suite)",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"HTTP {response.status_code}")
            else:
                body = response.json()
                self.run_keys = [body["run"]["run_key"], *self.run_keys][:20]
                response.success()
