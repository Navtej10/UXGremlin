import json
import pytest
from fastapi.testclient import TestClient

from main import app, sessions
from scoring import Step, compute_friction


@pytest.fixture
def client():
    return TestClient(app)


def test_session_consistency_stream_and_report(client):
    """
    Runs a fake 3-step session and asserts:
    - Step count is identical between live stream events, score.steps_taken, and saved actions
    - Task string is identical and not overwritten by stale sessions
    - Persona is identical across live stream and report
    - Screenshot list length matches step count
    """
    task_name = "sign up"
    persona_name = "pro_tester"
    target_url = "https://example.com/signup"

    # 1. Launch attack
    launch_res = client.post("/api/launch", json={
        "url": target_url,
        "task": task_name,
        "persona": persona_name,
    })
    assert launch_res.status_code == 200
    launch_data = launch_res.json()
    session_id = launch_data["session_id"]
    assert session_id in sessions

    sess = sessions[session_id]
    q = sess["queue"]

    # 2. Simulate 3-step agent loop execution
    fake_steps = [
        Step(
            n=1,
            url=target_url,
            url_after="https://example.com/form",
            action="click",
            label="Sign Up CTA",
            ok=True,
            thought="Step 1 · Decided: Click Sign Up CTA",
            screenshot="data:image/jpeg;base64,fake_step_1_screenshot",
        ),
        Step(
            n=2,
            url="https://example.com/form",
            url_after="https://example.com/form",
            action="type",
            label="Email Input Field",
            ok=True,
            thought="Step 2 · Decided: Type user email",
            screenshot="data:image/jpeg;base64,fake_step_2_screenshot",
        ),
        Step(
            n=3,
            url="https://example.com/form",
            url_after="https://example.com/welcome",
            action="done",
            label="Submit Button",
            ok=True,
            thought="Step 3 · Decided: Task completed successfully",
            screenshot="data:image/jpeg;base64,fake_step_3_screenshot",
        ),
    ]

    # Populate session steps and queue
    for s in fake_steps:
        sess["steps"].append(s)
        q.put({
            "step": s.n,
            "action": s.action,
            "thought": s.thought,
            "screenshot": s.screenshot,
            "session_id": session_id,
            "task": task_name,
            "persona": persona_name,
        })

    # Build report from the backend's saved action list (single source of truth)
    score = compute_friction(fake_steps, completed=True)
    report = {
        "session_id": session_id,
        "url": target_url,
        "task": task_name,
        "persona": persona_name,
        "status": "completed",
        "score": score,
        "verdict": "Completed registration cleanly in 3 steps.",
        "findings": [],
        "bugs": 0,
        "actions": [
            {
                "step_number": s.n,
                "action": s.action,
                "target": s.label,
                "thought": s.thought,
                "screenshot": s.screenshot,
                "ok": s.ok,
                "url": s.url,
                "url_after": s.url_after,
            }
            for s in fake_steps
        ],
    }
    sess["report"] = report
    sess["status"] = "completed"
    q.put({"done": True, "session_id": session_id})

    # 3. Read live SSE stream for this session
    stream_steps = []
    stream_tasks = set()
    stream_personas = set()

    with client.stream("GET", f"/api/stream?session_id={session_id}") as stream_res:
        for line in stream_res.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if payload.get("step"):
                    stream_steps.append(payload)
                if payload.get("task"):
                    stream_tasks.add(payload["task"])
                if payload.get("persona"):
                    stream_personas.add(payload["persona"])
                if payload.get("done"):
                    break

    stream_step_count = len(stream_steps)
    assert stream_step_count == 3
    assert task_name in stream_tasks
    assert persona_name in stream_personas

    # 4. Fetch the final report for this session
    report_res = client.get(f"/api/report?session_id={session_id}")
    assert report_res.status_code == 200
    report_data = report_res.json()

    # 5. Assert step count, task and persona are identical across stream & report
    assert report_data["session_id"] == session_id
    assert report_data["task"] == task_name
    assert report_data["persona"] == persona_name

    # Step counts match exactly across all representations
    assert report_data["score"]["steps_taken"] == 3
    assert len(report_data["actions"]) == 3
    assert stream_step_count == report_data["score"]["steps_taken"]
    assert stream_step_count == len(report_data["actions"])

    # Screenshot list length matches step count exactly
    screenshots = [a["screenshot"] for a in report_data["actions"] if a["screenshot"] is not None]
    assert len(screenshots) == 3

    # Task and persona consistency check
    assert report_data["task"] == list(stream_tasks)[0]
    assert report_data["persona"] == list(stream_personas)[0]


def test_session_isolation_prevents_stale_overwriting(client):
    """
    Asserts that multiple sessions maintain isolated state and do not overwrite
    each other's task, URL, or reports.
    """
    # Launch Session 1 ("sign up")
    s1_res = client.post("/api/launch", json={
        "url": "https://example.com/signup",
        "task": "sign up",
        "persona": "pro_tester",
    })
    s1_id = s1_res.json()["session_id"]
    sessions[s1_id]["report"] = {
        "session_id": s1_id,
        "task": "sign up",
        "persona": "pro_tester",
        "url": "https://example.com/signup",
        "score": {"total": 10, "steps_taken": 3, "label": "Low"},
        "actions": [{"step_number": 1}, {"step_number": 2}, {"step_number": 3}],
    }

    # Launch Session 2 with a different task ("navigate to one more page and abort")
    s2_res = client.post("/api/launch", json={
        "url": "https://example.com/catalog",
        "task": "navigate to one more page and abort",
        "persona": "impatient",
    })
    s2_id = s2_res.json()["session_id"]
    sessions[s2_id]["report"] = {
        "session_id": s2_id,
        "task": "navigate to one more page and abort",
        "persona": "impatient",
        "url": "https://example.com/catalog",
        "score": {"total": 85, "steps_taken": 1, "label": "High"},
        "actions": [{"step_number": 1}],
    }

    # Querying Session 1 must return Session 1's task ("sign up"), NOT Session 2's task
    s1_report = client.get(f"/api/report?session_id={s1_id}").json()
    assert s1_report["task"] == "sign up"
    assert s1_report["persona"] == "pro_tester"
    assert s1_report["score"]["steps_taken"] == 3

    # Querying Session 2 must return Session 2's task
    s2_report = client.get(f"/api/report?session_id={s2_id}").json()
    assert s2_report["task"] == "navigate to one more page and abort"
    assert s2_report["persona"] == "impatient"
    assert s2_report["score"]["steps_taken"] == 1


def test_task_outcome_reported_and_streamed(client):
    """
    Tests that outcome, outcome_reason, claimed_outcome, and verified_outcome
    are preserved on the session model, streamed on the final SSE event, and
    returned in the report API.
    """
    from agent import (
        TaskOutcome,
        OUTCOME_COMPLETED,
        OUTCOME_ABANDONED,
        OUTCOME_GAVE_UP,
        OUTCOME_MAX_STEPS,
        OUTCOME_ERROR,
    )

    # Assert enum values match user requirements
    assert TaskOutcome.COMPLETED.value == "completed"
    assert TaskOutcome.ABANDONED.value == "abandoned"
    assert TaskOutcome.GAVE_UP.value == "gave_up"
    assert TaskOutcome.MAX_STEPS_REACHED.value == "max_steps_reached"
    assert TaskOutcome.ERROR.value == "error"

    launch_res = client.post("/api/launch", json={
        "url": "https://example.com/checkout",
        "task": "complete purchase",
        "persona": "pro_tester",
    })
    session_id = launch_res.json()["session_id"]
    sess = sessions[session_id]

    # Verify initial session store state
    assert sess["outcome"] is None
    assert sess["outcome_reason"] == ""
    assert sess["claimed_outcome"] is None
    assert sess["verified_outcome"] is None

    # Polling report while running includes outcome placeholders
    running_report = client.get(f"/api/report?session_id={session_id}").json()
    assert "outcome" in running_report
    assert "outcome_reason" in running_report

    # Simulate completed run with verification
    sess["outcome"] = OUTCOME_COMPLETED
    sess["outcome_reason"] = "Order confirmation page displayed with order #12345"
    sess["claimed_outcome"] = OUTCOME_COMPLETED
    sess["verified_outcome"] = OUTCOME_COMPLETED
    sess["report"] = {
        "session_id": session_id,
        "url": "https://example.com/checkout",
        "task": "complete purchase",
        "persona": "pro_tester",
        "outcome": OUTCOME_COMPLETED,
        "outcome_reason": "Order confirmation page displayed with order #12345",
        "claimed_outcome": OUTCOME_COMPLETED,
        "verified_outcome": OUTCOME_COMPLETED,
        "score": {"total": 5, "label": "Low", "parts": [], "steps_taken": 2, "ideal_steps": 2},
        "verdict": "Checkout completed seamlessly.",
        "findings": [],
        "actions": [],
    }

    sess["queue"].put({
        "done": True,
        "session_id": session_id,
        "outcome": OUTCOME_COMPLETED,
        "outcome_reason": "Order confirmation page displayed with order #12345",
        "claimed_outcome": OUTCOME_COMPLETED,
        "verified_outcome": OUTCOME_COMPLETED,
    })

    # Read SSE stream final event
    final_event = None
    with client.stream("GET", f"/api/stream?session_id={session_id}") as stream_res:
        for line in stream_res.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                if payload.get("done"):
                    final_event = payload
                    break

    assert final_event is not None
    assert final_event["outcome"] == "completed"
    assert final_event["claimed_outcome"] == "completed"
    assert final_event["verified_outcome"] == "completed"
    assert "Order confirmation" in final_event["outcome_reason"]

    # Verify report endpoint outputs outcome fields
    final_report = client.get(f"/api/report?session_id={session_id}").json()
    assert final_report["outcome"] == "completed"
    assert final_report["claimed_outcome"] == "completed"
    assert final_report["verified_outcome"] == "completed"
    assert final_report["outcome_reason"] == "Order confirmation page displayed with order #12345"


def test_decision_schema_extraction_and_fallback():
    """
    Tests that decision parser extracts action, reason, task_status, and outcome_reason
    properly across JSON and regex fallbacks.
    """
    from agent import extract_and_parse_json, regex_fallback_decision

    json_input = """
    {
      "action": "click",
      "reason": "Auditing checkout button",
      "thought": "Auditing checkout button",
      "task_status": "in_progress",
      "outcome_reason": "Moving to step 2",
      "target": "uxg-3"
    }
    """
    parsed = extract_and_parse_json(json_input)
    assert parsed["action"] == "click"
    assert parsed["reason"] == "Auditing checkout button"
    assert parsed["task_status"] == "in_progress"
    assert parsed["outcome_reason"] == "Moving to step 2"

    fallback = regex_fallback_decision("I am done with the test now uxg-5")
    assert fallback["action"] == "done"
    assert fallback["task_status"] == "done"
    assert fallback["reason"] != ""


def test_start_session_api_runs_parameter(client):
    """
    Verify that start-session and launch API accept runs (1-3, default 1)
    and store it on the session.
    """
    from unittest.mock import patch
    with patch("main.threading.Thread"):
        # 1. Default runs (not specified in request)
        res_default = client.post("/api/start-session", json={
            "url": "https://example.com/test-runs-1",
            "task": "test default runs",
            "persona": "pro_tester",
        })
        assert res_default.status_code == 200
        data_default = res_default.json()
        assert data_default["runs"] == 1
        assert sessions[data_default["session_id"]]["runs"] == 1

        # 2. Explicit runs = 3
        res_3 = client.post("/api/launch", json={
            "url": "https://example.com/test-runs-3",
            "task": "test 3 runs",
            "persona": "impatient",
            "runs": 3,
        })
        assert res_3.status_code == 200
        data_3 = res_3.json()
        assert data_3["runs"] == 3
        assert sessions[data_3["session_id"]]["runs"] == 3


def test_aggregate_run_reports_multi_run_consistency():
    """
    Verify multi-run aggregation:
    - computes score_min, score_max, score_mean
    - marks findings in 2+ runs as 'consistent', others as 'occasional'
    """
    from scoring import aggregate_run_reports

    report_1 = {
        "score": {"total": 82, "score": 82, "label": "Severe"},
        "verdict": "Run 1 encountered severe checkout friction.",
        "findings": [
            {
                "title": "Unresponsive checkout button",
                "severity": "critical",
                "evidence_steps": [1],
                "what_happened": "Button did not respond to click.",
                "impact": "Blocked user.",
                "recommendation": "Fix click event listener.",
            },
            {
                "title": "Form validation error on email",
                "severity": "medium",
                "evidence_steps": [2],
                "what_happened": "Email format was rejected without clear message.",
                "impact": "User hesitated.",
                "recommendation": "Add helper text.",
            },
        ],
        "outcome": "completed",
    }

    report_2 = {
        "score": {"total": 85, "score": 85, "label": "Severe"},
        "verdict": "Run 2 got stuck momentarily on button.",
        "findings": [
            {
                "title": "Unresponsive checkout button",
                "severity": "critical",
                "evidence_steps": [1],
                "what_happened": "Button did not respond to click.",
                "impact": "Blocked user.",
                "recommendation": "Fix click event listener.",
            },
            {
                "title": "Slow page transition",
                "severity": "medium",
                "evidence_steps": [3],
                "what_happened": "Transition took 4.5 seconds.",
                "impact": "Slowed flow.",
                "recommendation": "Optimize asset loading.",
            },
        ],
        "outcome": "completed",
    }

    report_3 = {
        "score": {"total": 89, "score": 89, "label": "Severe"},
        "verdict": "Run 3 experienced unresponsive button.",
        "findings": [
            {
                "title": "Unresponsive checkout button",
                "severity": "critical",
                "evidence_steps": [1],
                "what_happened": "Button did not respond to click.",
                "impact": "Blocked user.",
                "recommendation": "Fix click event listener.",
            },
            {
                "title": "Missing order confirmation summary",
                "severity": "high",
                "evidence_steps": [4],
                "what_happened": "No receipt displayed.",
                "impact": "User lacked confirmation.",
                "recommendation": "Show confirmation modal.",
            },
        ],
        "outcome": "completed",
    }

    aggregated = aggregate_run_reports([report_1, report_2, report_3], runs=3)

    # 1. Scores aggregation
    assert aggregated["score_min"] == 82
    assert aggregated["score_max"] == 89
    assert aggregated["score_mean"] == 85.3
    assert aggregated["runs"] == 3

    assert aggregated["score"]["score_min"] == 82
    assert aggregated["score"]["score_max"] == 89
    assert aggregated["score"]["score_mean"] == 85.3
    assert aggregated["score"]["runs"] == 3

    # 2. Findings consistency
    findings = aggregated["findings"]
    button_finding = next(f for f in findings if "unresponsive checkout" in f["title"].lower())
    assert button_finding["consistency"] == "consistent"
    assert button_finding["runs_count"] == 3

    email_finding = next(f for f in findings if "email" in f["title"].lower())
    assert email_finding["consistency"] == "occasional"
    assert email_finding["runs_count"] == 1

    transition_finding = next(f for f in findings if "transition" in f["title"].lower())
    assert transition_finding["consistency"] == "occasional"
    assert transition_finding["runs_count"] == 1

    receipt_finding = next(f for f in findings if "confirmation" in f["title"].lower())
    assert receipt_finding["consistency"] == "occasional"
    assert receipt_finding["runs_count"] == 1

    # Consistent findings sorted first
    assert findings[0]["consistency"] == "consistent"


