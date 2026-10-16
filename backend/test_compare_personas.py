from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from main import (
    app,
    sessions,
    _PersonaQueueAdapter,
    _aggregate_comparison,
    _extract_top_finding,
    _clean_report_cycles,
)
from scoring import Step


@pytest.fixture
def client():
    return TestClient(app)


def test_launch_compare_mode_endpoint(client):
    """Verifies /api/start-session accepts a list of personas and sets up compare mode."""
    with patch("main._playwright_thread"):
        res = client.post("/api/start-session", json={
            "url": "https://example.com/checkout",
            "task": "Complete checkout",
            "personas": ["impatient", "confused", "skeptic"],
        })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "started"
    assert data["is_compare"] is True
    assert data["personas"] == ["impatient", "confused", "skeptic"]
    assert data["persona"] == "impatient"
    session_id = data["session_id"]

    assert session_id in sessions
    sess = sessions[session_id]
    assert sess["is_compare"] is True
    assert sess["personas"] == ["impatient", "confused", "skeptic"]


def test_launch_single_persona_backwards_compatible(client):
    """Verifies /api/start-session works when single persona is passed."""
    with patch("main._playwright_thread"):
        res = client.post("/api/start-session", json={
            "url": "https://example.com/login",
            "task": "Log in",
            "persona": "mobile",
        })
    assert res.status_code == 200
    data = res.json()
    assert data["persona"] == "mobile"
    assert data["personas"] == ["mobile"]
    assert data["is_compare"] is False


def test_persona_queue_adapter_event_tagging():
    """Verifies that _PersonaQueueAdapter tags all streamed events with persona_id."""
    import asyncio

    class MockParentQueue:
        def __init__(self):
            self.items = []
        async def put(self, item):
            self.items.append(item)

    mock_parent = MockParentQueue()
    adapter = _PersonaQueueAdapter(mock_parent, persona_id="impatient", session_id="test-session-456")

    async def run_puts():
        await adapter.put({"thought": "Thinking fast", "screenshot": "base64_data"})
        await adapter.put({"step": 2, "action": "click", "thought": "Clicked button"})

    asyncio.run(run_puts())

    assert len(mock_parent.items) == 2
    for item in mock_parent.items:
        assert item["persona_id"] == "impatient"
        assert item["session_id"] == "test-session-456"
        assert item["persona"] == "impatient"


def test_extract_top_finding():
    """Verifies extraction of highest severity finding as top_finding."""
    findings = [
        {"title": "Low contrast text", "severity": "medium", "what_happened": "Hard to read"},
        {"title": "Unresponsive rage-click target", "severity": "critical", "what_happened": "Button did not respond"},
        {"title": "Small touch target", "severity": "high", "what_happened": "30px height"},
    ]
    top = _extract_top_finding(findings)
    assert top == "Unresponsive rage-click target"

    assert _extract_top_finding([]) == "No critical friction found"


def test_aggregate_comparison():
    """
    Verifies that _aggregate_comparison aggregates a comparison object
    with the exact shape: {persona: score, outcome, steps, top_finding}.
    """
    fake_reports = {
        "impatient": {
            "score": {"total": 65, "steps_taken": 4},
            "outcome": "abandoned",
            "findings": [
                {"title": "Rage-click on CTA", "severity": "critical"}
            ],
            "actions": [{}, {}, {}, {}],
        },
        "confused": {
            "score": {"total": 42, "steps_taken": 7},
            "outcome": "completed",
            "findings": [
                {"title": "Icon-only button without text label", "severity": "high"}
            ],
            "actions": [{}, {}, {}, {}, {}, {}, {}],
        },
        "mobile": {
            "score": {"total": 20, "steps_taken": 3},
            "outcome": "completed",
            "findings": [],
            "actions": [{}, {}, {}],
        },
    }

    personas = ["impatient", "confused", "mobile"]
    comparison, comparison_summary = _aggregate_comparison(fake_reports, personas)

    # Check mapping
    for p_id in personas:
        assert p_id in comparison
        entry = comparison[p_id]
        assert "persona" in entry
        assert "score" in entry
        assert "outcome" in entry
        assert "steps" in entry
        assert "top_finding" in entry

    # Verify values
    assert comparison["impatient"]["score"] == 65
    assert comparison["impatient"]["outcome"] == "abandoned"
    assert comparison["impatient"]["steps"] == 4
    assert comparison["impatient"]["top_finding"] == "Rage-click on CTA"

    assert comparison["confused"]["score"] == 42
    assert comparison["confused"]["outcome"] == "completed"
    assert comparison["confused"]["steps"] == 7
    assert comparison["confused"]["top_finding"] == "Icon-only button without text label"

    assert comparison["mobile"]["score"] == 20
    assert comparison["mobile"]["outcome"] == "completed"
    assert comparison["mobile"]["steps"] == 3
    assert comparison["mobile"]["top_finding"] == "No critical friction found"

    # Verify summary array
    assert len(comparison_summary) == 3
    assert comparison_summary[0]["persona"] == "impatient"
    assert comparison_summary[1]["persona"] == "confused"
    assert comparison_summary[2]["persona"] == "mobile"


def test_get_report_compare_mode(client):
    """Verifies /api/report returns aggregated comparison object for compare sessions."""
    with patch("main._playwright_thread"):
        res = client.post("/api/start-session", json={
            "url": "https://example.com/pricing",
            "task": "Select team tier",
            "personas": ["pro_tester", "skeptic"],
        })
    session_id = res.json()["session_id"]
    sess = sessions[session_id]

    # Mock finished report
    fake_reports = {
        "pro_tester": {
            "score": {"total": 15, "steps_taken": 5, "parts": []},
            "outcome": "completed",
            "findings": [{"title": "Minor alignment gap", "severity": "medium"}],
            "actions": [{}, {}, {}, {}, {}],
        },
        "skeptic": {
            "score": {"total": 55, "steps_taken": 4, "parts": []},
            "outcome": "gave_up",
            "findings": [{"title": "Missing privacy link on payment form", "severity": "critical"}],
            "actions": [{}, {}, {}, {}],
        },
    }
    comp, comp_summary = _aggregate_comparison(fake_reports, ["pro_tester", "skeptic"])
    sess["report"] = {
        "session_id": session_id,
        "is_compare": True,
        "personas": ["pro_tester", "skeptic"],
        "comparison": comp,
        "comparison_summary": comp_summary,
        "persona_reports": fake_reports,
        "score": fake_reports["pro_tester"]["score"],
        "verdict": "Comparison completed",
        "findings": [],
        "actions": [],
    }

    report_res = client.get(f"/api/report?session_id={session_id}")
    assert report_res.status_code == 200
    rep = report_res.json()
    assert rep["is_compare"] is True
    assert "comparison" in rep
    assert rep["comparison"]["skeptic"]["score"] == 55
    assert rep["comparison"]["skeptic"]["top_finding"] == "Missing privacy link on payment form"
    assert rep["comparison"]["pro_tester"]["score"] == 15


def test_single_persona_report_no_circular_recursion(client):
    """Verifies single-persona reports can be serialized and fetched without RecursionError."""
    session_id = "single_test_123"
    sessions[session_id] = {
        "session_id": session_id,
        "url": "https://example.com",
        "task": "Test single",
        "persona": "pro_tester",
        "personas": ["pro_tester"],
        "is_compare": False,
        "status": "completed",
    }
    
    # Simulate the single-persona report structure constructed in _run_browser
    final_report = {
        "session_id": session_id,
        "url": "https://example.com",
        "task": "Test single",
        "persona": "pro_tester",
        "score": {"total": 85, "steps_taken": 4, "parts": []},
        "verdict": "Single run finished",
        "findings": [{"title": "Button too small", "severity": "medium"}],
        "actions": [{"step_number": 1, "action": "click"}],
        "outcome": "completed",
    }
    single_rep = dict(final_report)
    single_rep.pop("persona_reports", None)
    comp, comp_summary = _aggregate_comparison({"pro_tester": single_rep}, ["pro_tester"])
    final_report["comparison"] = comp
    final_report["comparison_summary"] = comp_summary
    final_report["persona_reports"] = {"pro_tester": single_rep}
    final_report["personas"] = ["pro_tester"]
    final_report["is_compare"] = False

    sessions[session_id]["report"] = final_report

    res = client.get(f"/api/report?session_id={session_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == session_id
    assert data["score"]["total"] == 85
    assert "persona_reports" in data
    assert "pro_tester" in data["persona_reports"]
    assert data["persona_reports"]["pro_tester"]["score"]["total"] == 85


def test_clean_report_cycles_breaks_self_reference(client):
    """Verifies that if a self-referential cycle is ever present, _clean_report_cycles breaks it."""
    cyclic_rep = {
        "session_id": "cycle_test_456",
        "score": {"total": 70},
        "findings": [],
        "actions": [],
    }
    # Deliberately create the direct cycle that caused RecursionError
    cyclic_rep["persona_reports"] = {"pro_tester": cyclic_rep}

    cleaned = _clean_report_cycles(cyclic_rep)
    assert cleaned["persona_reports"]["pro_tester"] is not cyclic_rep
    assert "persona_reports" not in cleaned["persona_reports"]["pro_tester"]
    assert cleaned["persona_reports"]["pro_tester"]["score"]["total"] == 70

    # Verify FastAPI serializes it cleanly without crashing
    sessions["cycle_test_456"] = {
        "session_id": "cycle_test_456",
        "report": cyclic_rep,
        "status": "completed",
    }
    res = client.get("/api/report?session_id=cycle_test_456")
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == "cycle_test_456"

