import os
import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app
from storage import (
    init_db,
    save_session,
    save_report,
    get_session as get_db_session,
    get_report as get_db_report,
    compute_report_delta,
)
from export_html import generate_printable_html


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_uxgremlin.db")
    monkeypatch.setenv("DATABASE_PATH", test_db)
    monkeypatch.setattr("storage.DB_PATH", test_db)
    init_db()
    yield test_db


def test_sqlite_storage_lifecycle():
    session_id = "test_abc123"
    session_data = {
        "url": "https://example.com/login",
        "task": "Log in with email",
        "persona": "impatient",
        "personas": ["impatient"],
        "is_compare": False,
        "status": "running",
        "previous_session_id": "prev_001",
    }
    save_session(session_id, session_data)

    fetched = get_db_session(session_id)
    assert fetched is not None
    assert fetched["id"] == session_id
    assert fetched["url"] == "https://example.com/login"
    assert fetched["persona"] == "impatient"
    assert fetched["previous_session_id"] == "prev_001"
    assert fetched["status"] == "running"

    # Now save a final report
    report_data = {
        "session_id": session_id,
        "url": "https://example.com/login",
        "task": "Log in with email",
        "persona": "impatient",
        "score": {"total": 45, "label": "Medium", "parts": []},
        "outcome": "completed",
        "verdict": "Completed with mild friction",
        "findings": [{"title": "Slow Spinner", "severity": "medium", "what_happened": "Spinner took 3s"}],
    }
    save_report(session_id, report_data)

    rep = get_db_report(session_id)
    assert rep is not None
    assert rep["score"]["total"] == 45
    assert rep["outcome"] == "completed"
    assert len(rep["findings"]) == 1

    updated_sess = get_db_session(session_id)
    assert updated_sess["status"] == "completed"
    assert updated_sess["outcome"] == "completed"


def test_compute_report_delta():
    prev_report = {
        "session_id": "session_v1",
        "score": {"total": 60, "label": "High"},
        "outcome": "abandoned",
        "findings": [
            {"title": "Unclear button label", "severity": "high"},
            {"title": "Broken link in footer", "severity": "medium"},
        ],
    }

    new_report = {
        "session_id": "session_v2",
        "score": {"total": 20, "label": "Low"},
        "outcome": "completed",
        "findings": [
            {"title": "Broken link in footer", "severity": "medium"},
            {"title": "Contrast too low in dark mode", "severity": "medium"},
        ],
    }

    delta = compute_report_delta(prev_report, new_report)
    assert delta["previous_session_id"] == "session_v1"
    assert delta["previous_score"] == 60
    assert delta["new_score"] == 20
    assert delta["score_delta"] == -40  # 40 points improvement!
    assert delta["previous_outcome"] == "abandoned"
    assert delta["new_outcome"] == "completed"

    resolved_titles = [f["title"] for f in delta["resolved_findings"]]
    assert resolved_titles == ["Unclear button label"]

    new_titles = [f["title"] for f in delta["new_findings"]]
    assert new_titles == ["Contrast too low in dark mode"]

    persistent_titles = [f["title"] for f in delta["persistent_findings"]]
    assert persistent_titles == ["Broken link in footer"]


def test_generate_printable_html():
    report = {
        "session_id": "89abcdef",
        "url": "https://example.com/checkout",
        "task": "Complete purchase",
        "persona": "pro_tester",
        "outcome": "completed",
        "score": {
            "total": 35,
            "label": "Moderate",
            "parts": [
                {"name": "Form Friction", "points": 15, "why": "Too many required fields"},
            ],
            "steps_taken": 8,
            "ideal_steps": 4,
        },
        "verdict": "Checkout flow has minor layout issues.",
        "findings": [
            {
                "title": "Hidden CVV input",
                "severity": "critical",
                "what_happened": "CVV field was hidden below the fold",
                "impact": "User struggled to locate security code input",
                "recommendation": "Bring CVV next to card number",
                "screenshot": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
            }
        ],
        "actions": [
            {"step_number": 1, "action": "click", "target": "Cart Button", "thought": "Navigating to checkout"}
        ]
    }

    html_out = generate_printable_html(report)
    assert "<!DOCTYPE html>" in html_out
    assert "89abcdef" in html_out
    assert "Complete purchase" in html_out
    assert "35" in html_out
    assert "Hidden CVV input" in html_out
    assert "Bring CVV next to card number" in html_out
    assert "data:image/jpeg;base64," in html_out
    assert "@media print" in html_out


def test_endpoints_export_and_share():
    client = TestClient(app)

    # Launch a mock session
    with patch("main._playwright_thread"):
        res = client.post("/api/start-session", json={
            "url": "https://example.com",
            "task": "Search for documentation",
            "persona": "pro_tester",
            "previous_session_id": "prior_999",
        })
        assert res.status_code == 200
        data = res.json()
        session_id = data["session_id"]
        # Assert short 8-char ID
        assert len(session_id) == 8
        assert data["previous_session_id"] == "prior_999"

    # Persist report for this session in SQLite
    mock_report = {
        "session_id": session_id,
        "url": "https://example.com",
        "task": "Search for documentation",
        "persona": "pro_tester",
        "score": {"total": 15, "label": "Low", "parts": []},
        "outcome": "completed",
        "verdict": "Flawless search interaction",
        "findings": [],
        "actions": [],
    }
    save_report(session_id, mock_report)

    # 1. Read-only query by path
    rep_res = client.get(f"/api/report/{session_id}")
    assert rep_res.status_code == 200
    assert rep_res.json()["score"]["total"] == 15

    # 2. JSON export endpoint
    export_json = client.get(f"/api/report/{session_id}/export/json")
    assert export_json.status_code == 200
    assert "application/json" in export_json.headers["content-type"]
    assert f'filename="uxgremlin-report-{session_id}.json"' in export_json.headers["content-disposition"]
    payload = export_json.json()
    assert payload["session_id"] == session_id
    assert payload["score"]["total"] == 15

    # 3. HTML export endpoint
    export_html = client.get(f"/api/report/{session_id}/export/html")
    assert export_html.status_code == 200
    assert "text/html" in export_html.headers["content-type"]
    assert "UXGremlin Sabotage Report" in export_html.text
    assert session_id in export_html.text

    # 4. Direct report page
    direct_page = client.get(f"/report/{session_id}")
    assert direct_page.status_code == 200
    assert "UXGremlin Sabotage Report" in direct_page.text

    # 5. Non-existent report returns 404
    missing_res = client.get("/api/report/nonexistent123")
    assert missing_res.status_code == 404
