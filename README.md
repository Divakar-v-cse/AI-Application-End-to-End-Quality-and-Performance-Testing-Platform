# AI Application End-to-End Quality and Performance Testing Platform

A self-contained QA platform for AI applications: it **executes** API, UI, SQL and load
tests, stores every result, evaluates release gates and renders the whole picture in a
React dashboard.

* **Backend** — FastAPI + SQLAlchemy + SQLite (Python 3.11+)
* **Frontend** — React 18 + Vite + Recharts
* **UI automation** — Playwright (11 catalogued cases)
* **API automation** — pytest + httpx (17 live contract checks)
* **Data validation** — 15 read-only SQL rules
* **Load testing** — Locust (with CI publishing of the statistics)
* **API collection** — Postman/Newman
* **Packaging** — Docker, Docker Compose, GitHub Actions quality gates
* **AWS hooks** — optional S3 / Lambda / Athena / CloudWatch, with local fallbacks

Everything works offline: no AWS account, no external service and no paid API is required.

---

## 1. Quick start (local, Windows PowerShell)

```powershell
# from the repository root
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt

# seed the demo database (43 catalogued cases, 17 runs, 3 load tests)
cd backend
..\.venv\Scripts\python.exe -m app.seed
cd ..

# terminal 1 - API
cd backend; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# terminal 2 - dashboard
cd frontend; npm install; npm run dev
```

macOS / Linux:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r backend/requirements-dev.txt
(cd backend && ../.venv/bin/python -m app.seed)
(cd backend && ../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
(cd frontend && npm install && npm run dev)
```

### Where to look

| Surface | URL |
| --- | --- |
| Dashboard (SPA) | <http://127.0.0.1:5173> |
| Swagger / OpenAPI | <http://127.0.0.1:8000/docs> · <http://127.0.0.1:8000/openapi.json> |
| Liveness probe | <http://127.0.0.1:8000/healthz> |
| Docker deployment | <http://localhost:8080> (nginx → API) |

**Demo login:** `qa@example.com` / `Passw0rd!` (configurable through
`DEMO_USER_EMAIL` / `DEMO_USER_PASSWORD`).

The seed is idempotent: it only creates rows when a table is empty. Delete
`backend/data/quality.db` to start from scratch.

---

## 2. What the platform does

### Quality dashboard (`/dashboard`)
Totals, pass/fail counts, pass rate, API p95 latency, average page load, load-test error
rate, data-validation failures, active gate failures, a 14-day execution trend, latency by
endpoint, page-load and data-integrity panels, suite breakdown and recent executions.
The toolbar can execute a suite (`all`, `api`, `db`, `perf`, `ui`) on demand.

### Reusable Playwright suite (`frontend/tests/ui`)
| Spec | Catalog key | What it proves |
| --- | --- | --- |
| `login.spec.js` | `ui.login.valid_credentials` | Valid credentials reach the dashboard and persist a token |
| `login.spec.js` | `ui.login.invalid_credentials` | Bad password shows the server's error, no token stored |
| `login.spec.js` | `ui.login.empty_form` | Empty / malformed input is rejected client-side |
| `navigation.spec.js` | `ui.navigation.all_views` | All seven views render with the right title, no page errors |
| `dashboard.spec.js` | `ui.dashboard.kpis` | Every KPI is populated from live data |
| `dashboard.spec.js` | `ui.dashboard.run_detail` | Run detail shows gates, results and re-evaluation |
| `forms.spec.js` | `ui.forms.run_validation` | Suite selection is valid, execution outcome is reported |
| `errors.spec.js` | `ui.errors.unknown_run` | Unknown run / route degrades to a recoverable error |
| `chatbot.spec.js` | `ui.chatbot.answer` | The demo AI app answers with telemetry |
| `chatbot.spec.js` | `ui.chatbot.guardrail` | Prompt injection is flagged by the guardrail |
| `reports.spec.js` | `ui.reports.download` | All five report formats download with the right filename |

### API automation (`tests/api`, 17 live checks in the catalog)
Status codes, request/response contracts, auth (401/403), invalid input (422), error
responses (404/400), response time budgets and full OpenAPI schema validation
(`jsonschema` with inlined `$ref`s, plus a deliberate-drift negative control).

### SQL data validation (`tests/db`, 15 rules, also in `sql/validation_queries.sql`)
| Category | Checks |
| --- | --- |
| Missing records | `db.results.orphans`, `db.metrics.orphans` |
| Duplicates | `db.users.unique_email`, `db.runs.duplicate_keys`, `db.cases.duplicate_keys` |
| Invalid data types / domains | `db.results.status_domain`, `db.api.status_range`, `db.chat.role_domain` |
| Null values | `db.runs.required_fields` |
| Consistency | `db.load.consistency`, `db.runs.time_order`, `db.metrics.latency_positive` |
| AI evaluation integrity | `db.eval.score_range`, `db.eval.integrity` |

Each query returns the offending rows; a check passes when it returns zero rows.

### Performance (`locust/locustfile.py`)
Weighted read/write profile (dashboard, run history, metrics, gates, chatbot, ad-hoc suite
runs). Results are published with `scripts/push_locust_stats.py` so the load gate sees them.

### Reports
Markdown, HTML, JUnit XML, CSV and JSON per run, from the run detail page or
`GET /api/reports/{run_key}/{fmt}`.

---

## 3. Quality gates

Nine gates are evaluated per run and stored with it; the same engine feeds the dashboard,
the API and CI.

| Gate | Metric | Operator | Threshold | Blocking |
| --- | --- | --- | --- | --- |
| `overall_pass_rate` | all suites | ≥ | 95 % | yes |
| `api_pass_rate` | API suite | ≥ | 95 % | yes |
| `ui_pass_rate` | UI suite | ≥ | 90 % | yes |
| `data_pass_rate` | SQL suite | ≥ | 100 % | yes |
| `api_p95_latency` | p95 API latency | ≤ | 800 ms | yes |
| `page_load_budget` | mean page load | ≤ | 3000 ms | yes |
| `load_error_rate` | latest Locust error rate | ≤ | 1 % | yes |
| `data_failures` | failing SQL checks | ≤ | 0 | yes |
| `test_volume` | automated checks defined | ≥ | 20 | no (advisory) |

* Gates with no evidence for a run are reported as `not_applicable` instead of failing.
* `run_is_blocked()` is `true` when any **blocking** gate failed; `scripts/evaluate_gates.py`
  turns that into a non-zero exit code for CI.
* Thresholds are environment variables (`GATE_API_PASS_RATE`, `GATE_UI_PASS_RATE`,
  `GATE_API_P95_MS`, `GATE_PAGE_LOAD_MS`, `GATE_LOAD_ERROR_RATE`, `GATE_DATA_FAILURES`), so a
  stricter or looser policy needs no code change.

---

## 4. Running the tests

### pytest (API + SQL)

```powershell
.\.venv\Scripts\python.exe -m pytest -q                 # whole suite
.\.venv\Scripts\python.exe -m pytest tests/db -v        # SQL validation only
.\.venv\Scripts\python.exe -m pytest --cov=backend.app  # with coverage
```

The suite uses a throwaway SQLite database under `.pytest-data/`, so it never touches your
demo data. 17 API checks, 15 SQL validations, negative controls, OpenAPI contract tests,
ingestion, reports and AWS fallbacks are all covered.

### Playwright (UI)

```powershell
cd frontend
npx playwright install chromium   # first run only
npm run test:e2e                  # starts API + Vite automatically, 11 cases
npx playwright test --reporter=json   # machine-readable report for ingestion
```

The config starts uvicorn and Vite for you (`webServer`), reuses already-running servers,
authenticates once in a `setup` project and stores the session in
`frontend/tests/ui/.auth/state.json` (git-ignored).

### Postman / Newman

```powershell
newman run postman\quality-platform.postman_collection.json `
  -e postman\quality-platform.postman_environment.json `
  --reporters cli,json --reporter-json-export reports\newman.json
```

The login request stores the bearer token in a collection variable, so every folder runs
authenticated.

### Locust

```powershell
locust -f locust\locustfile.py --host http://127.0.0.1:8000 --headless -u 20 -r 4 -t 30s `
  --csv locust\out\ci --only-summary
.\.venv\Scripts\python.exe scripts\push_locust_stats.py --csv-prefix locust\out\ci `
  --users 20 --spawn-rate 4 --duration 30
```

`push_locust_stats.py` accepts Locust CSV output (`--csv-prefix`) or a JSON summary
(`--json`) and posts it to `/api/ingest/locust`.

### Gate evaluation

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_gates.py --output reports\quality-gates.json
```

Exit code `0` = every blocking gate passed, `1` = blocked (or the API is unreachable).
Add `--run-key RUN-...` to evaluate a specific run, `--no-fail-on-blocked` to report only.

---

## 5. Docker

```bash
docker compose up --build
# dashboard  http://localhost:8080
# API        http://localhost:8000/docs
```

* `backend/Dockerfile` — python:3.11-slim, non-root user, `curl` healthcheck on `/healthz`.
* `frontend/Dockerfile` — multi-stage node build + nginx runtime.
* `frontend/nginx.conf` — SPA fallback, gzip, asset caching, `/api`, `/docs`, `/healthz` proxied.
* `docker-compose.yml` — named volume `ai-quality-data` for SQLite and artifacts, health-gated
  startup order, every secret taken from the environment.

---

## 6. CI/CD

`.github/workflows/quality-gates.yml` runs four jobs:

1. **pytest** — the full suite, JUnit XML and coverage uploaded as artifacts.
2. **Playwright** — Chromium, the UI suite, then the JSON report is POSTed to
   `/api/ingest/playwright` so UI results land in the same database as everything else.
3. **Locust** — a 30 s headless smoke load, published through `scripts/push_locust_stats.py`.
4. **Quality gates** — records a run, evaluates the gates, uploads `quality-gates.json` and
   **fails the workflow** when a blocking gate fails.

A Docker build job verifies both images on every push.

---

## 7. AWS integration (optional)

Set `AWS_ENABLED=true` plus the resource variables to use real AWS; otherwise every call
degrades to a working local equivalent and reports it in the response:

| Capability | Configured | Local fallback | `mode` |
| --- | --- | --- | --- |
| Athena query | `ATHENA_DATABASE`, `ATHENA_OUTPUT` | SQLite mirror (`/api/aws/athena/query`) | `local-sqlite` |
| Lambda audit | `LAMBDA_FUNCTION` | In-process audit | `local-fallback` |
| CloudWatch metrics | credentials | Local metric rollup | `local-mirror` |
| S3 artifacts | `S3_BUCKET` | `backend/data/artifacts` | `local` |

Only `SELECT` / `WITH` statements are accepted by the Athena endpoint; anything else is a
`400`. Invalid SQL is also a `400` (client error), never a silent pass.

---

## 8. Project layout

```
backend/
  app/
    main.py            FastAPI app factory, lifespan, /healthz
    config.py          env-driven settings (all optional)
    models.py          SQLAlchemy models
    schemas.py         Pydantic contracts (also the OpenAPI surface)
    seed.py            demo data: catalog, 17 runs, metrics, load tests, gates
    routers/           auth, dashboard, runs, metrics, data-quality, performance,
                       gates, reports, ingest, demo AI, AWS
    services/          runner, checks (17 API + 15 DB), gates, reports, analytics, aws
  Dockerfile
frontend/
  src/pages/           Login, Dashboard, Runs, RunDetail, ApiMetrics, DataQuality,
                       Performance, Gates, Chatbot, NotFound
  tests/ui/            11 Playwright cases + auth setup
  playwright.config.js
  nginx.conf
  Dockerfile
tests/
  api/                 13 pytest modules (auth, runs, gates, ingest, metrics, aws, ...)
  db/                  SQL validation suite + negative controls
  conftest.py          throwaway database, TestClient, auth fixture
locust/locustfile.py
postman/               collection + environment
scripts/               gen_sql_queries.py, evaluate_gates.py, push_locust_stats.py
sql/validation_queries.sql
.github/workflows/quality-gates.yml
docker-compose.yml
pytest.ini
```

---

## 9. Configuration

Copy `.env.example` to `.env` (or `backend/.env`) when you need to override defaults.
`backend/.env` wins over the project root `.env`. Never commit a real `.env`; `.gitignore`
already excludes it together with the virtualenv, `node_modules`, build output, local
databases, Playwright artifacts and the captured auth state.

---

## 10. API reference (short)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/login` | Bearer token + user |
| GET | `/api/auth/me` | Current identity |
| GET | `/api/dashboard/summary`, `/trend` | KPIs and 14-day history |
| GET | `/api/tests/catalog` | 43 automated cases |
| GET/POST | `/api/runs` | History / execute a suite |
| GET | `/api/runs/{run_key}`, `/results` | Run detail, per-case results |
| GET | `/api/metrics/api`, `/pages` | Latency and browser timings |
| GET/POST | `/api/data-quality/checks`, `/run` | SQL validation results |
| GET | `/api/data-quality/history` | Validation trend |
| GET/POST | `/api/performance/runs` | Load-test summaries |
| GET/POST | `/api/quality-gates`, `/evaluate/{run_key}` | Gate config and evaluation |
| GET | `/api/reports/{run_key}/{fmt}` | `markdown\|html\|junit\|csv\|json` |
| POST | `/api/chat` | Demo AI application (guard-railed) |
| GET | `/api/demo/overview`, `/evaluations` | Demo app telemetry |
| POST | `/api/ingest/{junit\|playwright\|locust\|page-metrics}` | CI result ingestion |
| GET/POST | `/api/aws/*`, `/api/artifacts` | Optional AWS integrations |

Interactive documentation: <http://127.0.0.1:8000/docs>.

---

## 11. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Cannot reach the API ... Is the backend running?` | Start uvicorn on port 8000; the Vite/nginx proxy targets `127.0.0.1:8000`. |
| `ENABLE_UI_RUNNER=false` when triggering the `ui` suite | Expected: run `npx playwright test` and POST the JSON report, or set `ENABLE_UI_RUNNER=true`. |
| Playwright: `Executable doesn't exist ... chromium_headless_shell` | `npx playwright install chromium`. |
| `database is locked` | SQLite allows one writer; stop duplicate `uvicorn --reload` processes. |
| Port already in use | `--port 8001` for the API and set `VITE_API_BASE`/proxy accordingly. |
| Gates blocked unexpectedly | `python scripts/evaluate_gates.py` prints every gate's actual value, threshold and message. |

---

## 12. Verified locally (2026-11-03)

Every number below comes from an executed run on Windows 11 / Python 3.11 / Node 22.

| Verification | Command | Result |
| --- | --- | --- |
| Backend starts | `uvicorn app.main:app --port 8000` | `/healthz` → `{"status":"ok"}` |
| Frontend starts | `npm run dev` | <http://127.0.0.1:5173> → HTTP 200 |
| pytest | `python -m pytest -q` | **209 passed** in 7.08 s (13 modules, 17 API + 15 SQL checks + negative controls) |
| SQL validation | `POST /api/data-quality/run` | 15/15 checks passed, 0 failing rows |
| Playwright | `npx playwright test` | **12 passed** in 32.5 s (setup + 11 catalogued UI cases) |
| Locust | `locust --headless -u 10 -r 3 -t 15s` | 116 requests, 0 failures (0.00 %), 8.58 req/s, p95 210 ms |
| Locust ingest | `scripts/push_locust_stats.py` | `LOAD-20261103-154046-476B` → `passed`, 0.0 % error rate |
| Gates — pass | `scripts/evaluate_gates.py` | 9 gates evaluated, **exit 0**, "All blocking gates passed" |
| Gates — fail | same script, `GATE_API_PASS_RATE=99` | `overall_pass_rate FAIL 97.67 < 99.0` → **exit 1**, blocked |
