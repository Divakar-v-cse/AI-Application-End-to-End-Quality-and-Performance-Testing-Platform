"""Report rendering: formats, filenames, auth fallbacks and error paths."""
from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET

import pytest

FORMATS = {
    "markdown": "md",
    "md": "md",
    "html": "html",
    "junit": "xml",
    "xml": "xml",
    "csv": "csv",
    "json": "json",
}


@pytest.fixture(scope="module")
def reportable_run(client, auth) -> str:
    """Newest run that actually carries results (ingestion may have added runs)."""
    runs = client.get("/api/runs?limit=50", headers=auth).json()["items"]
    for run in runs:
        detail = client.get(f"/api/runs/{run['run_key']}", headers=auth).json()
        if detail["results"]:
            return run["run_key"]
    pytest.fail("no run with results is available to report on")


@pytest.mark.parametrize("fmt,extension", sorted(FORMATS.items()))
def test_every_report_format_downloads(client, auth, reportable_run, fmt, extension):
    response = client.get(f"/api/reports/{reportable_run}/{fmt}", headers=auth)

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{reportable_run}-report.{extension}"'
    )
    assert response.text.strip(), "reports must not be empty"


def test_json_report_matches_the_run_detail(client, auth, reportable_run):
    detail = client.get(f"/api/runs/{reportable_run}", headers=auth).json()
    payload = json.loads(client.get(f"/api/reports/{reportable_run}/json", headers=auth).text)

    assert set(payload) == {"run", "results", "gates"}
    assert payload["run"]["run_key"] == reportable_run
    assert len(payload["results"]) == len(detail["results"])
    assert len(payload["gates"]) == len(detail["gates"])


def test_junit_report_is_well_formed_xml(client, auth, reportable_run):
    body = client.get(f"/api/reports/{reportable_run}/junit", headers=auth).text
    root = ET.fromstring(body)

    assert root.tag == "testsuites"
    assert root.get("name") == "ai-quality-platform"
    cases = list(root.iter("testcase"))
    detail = client.get(f"/api/runs/{reportable_run}", headers=auth).json()
    assert len(cases) == len(detail["results"])
    assert all(case.get("name") for case in cases)


def test_csv_report_has_a_header_and_one_row_per_result(client, auth, reportable_run):
    body = client.get(f"/api/reports/{reportable_run}/csv", headers=auth).text
    rows = list(csv.DictReader(io.StringIO(body)))
    detail = client.get(f"/api/runs/{reportable_run}", headers=auth).json()

    assert rows, "CSV export must contain data rows"
    assert len(rows) == len(detail["results"])
    assert "case_key" in rows[0]


def test_markdown_report_contains_the_run_key(client, auth, reportable_run):
    body = client.get(f"/api/reports/{reportable_run}/markdown", headers=auth).text

    assert reportable_run in body
    assert "#" in body, "markdown report should use headings"


def test_html_report_is_a_full_document(client, auth, reportable_run):
    body = client.get(f"/api/reports/{reportable_run}/html", headers=auth).text

    assert body.lstrip().lower().startswith("<!doctype html")
    assert reportable_run in body


def test_reports_accept_a_query_token_for_browser_downloads(client, reportable_run, token):
    response = client.get(f"/api/reports/{reportable_run}/json?token={token}")

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")


def test_reports_reject_anonymous_callers(client, reportable_run):
    assert client.get(f"/api/reports/{reportable_run}/json").status_code == 401


def test_unknown_format_is_rejected(client, auth, reportable_run):
    response = client.get(f"/api/reports/{reportable_run}/pdf", headers=auth)

    assert response.status_code == 400
    assert "Unsupported report format 'pdf'" in response.json()["detail"]


def test_unknown_run_is_rejected(client, auth):
    response = client.get("/api/reports/RUN-19700101-0000-XXXX/json", headers=auth)

    assert response.status_code == 404
