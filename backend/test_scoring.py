import pytest
from unittest.mock import MagicMock
from scoring import (
    Step,
    compute_friction,
    build_report,
    score_to_label,
    WEIGHT_EXCESS_STEPS,
    CAP_EXCESS_STEPS,
    WEIGHT_BACKTRACK,
    CAP_BACKTRACK,
    WEIGHT_REPEATED_ACTION,
    CAP_REPEATED_ACTION,
    WEIGHT_DEAD_CLICK,
    CAP_DEAD_CLICK,
    WEIGHT_SLOW_STEP,
    CAP_SLOW_STEP,
    SLOW_STEP_THRESHOLD_SECONDS,
    WEIGHT_CONSOLE_ERROR,
    CAP_ERRORS,
    PENALTY_OUTCOME_ABANDONED,
    PENALTY_OUTCOME_ERROR,
    PENALTY_OUTCOME_GAVE_UP,
    PENALTY_OUTCOME_MAX_STEPS,
    WEIGHT_CONFUSION_POINT,
    CAP_CONFUSION_POINT,
)


# =============================================================================
# Hand-made Session 1: Smooth Flow (Score 0-20 -> "Smooth")
# Direct 3-step successful signup, no hesitation, no errors, fast execution
# =============================================================================

def test_hand_made_session_1_smooth():
    """
    Session 1: Completely smooth interaction.
    - 3 steps taken, 3 expected
    - Clean navigation: /landing -> /signup -> /dashboard
    - Successful actions, no repeated clicks, no dead clicks
    - Fast response times (< 1.0s)
    - No console errors or network failures
    - Outcome: completed
    Expected Score: 0 -> Label: Smooth
    """
    steps = [
        Step(
            n=1,
            url="https://app.test/landing",
            url_after="https://app.test/signup",
            action="click",
            label="Sign Up Free",
            target="uxg-1",
            ok=True,
            duration=0.8,
            dead_click=False,
            console_errors=[],
            failed_requests=[],
            thought="Step 1 · Decided: Click Sign Up Free",
        ),
        Step(
            n=2,
            url="https://app.test/signup",
            url_after="https://app.test/signup",
            action="type",
            label="Email Input",
            target="uxg-2",
            ok=True,
            duration=0.6,
            dead_click=False,
            console_errors=[],
            failed_requests=[],
            thought="Step 2 · Decided: Enter tester email address",
        ),
        Step(
            n=3,
            url="https://app.test/signup",
            url_after="https://app.test/dashboard",
            action="done",
            label="Submit Button",
            target="uxg-3",
            ok=True,
            duration=0.0,
            dead_click=False,
            console_errors=[],
            failed_requests=[],
            thought="Step 3 · Decided: Registration confirmed on dashboard",
        ),
    ]

    session = {
        "session_id": "sess-smooth-01",
        "steps": steps,
        "expected_steps": 3,
        "outcome": "completed",
        "outcome_reason": "Welcome dashboard verified",
        "task": "sign up for an account",
        "persona": "pro_tester",
    }

    result = compute_friction(session)

    assert result["score"] <= 20
    assert result["score"] == 0
    assert result["total"] == 0
    assert result["label"] == "Smooth"
    assert result["breakdown"] == []
    assert result["steps_taken"] == 3
    assert result["expected_steps"] == 3

    # Verify explanation_inputs structure
    expl = result["explanation_inputs"]
    assert expl["score"] == 0
    assert expl["label"] == "Smooth"
    assert expl["outcome"] == "completed"
    assert expl["primary_friction"] == "None"
    assert expl["breakdown"] == []


# =============================================================================
# Hand-made Session 2: Minor Friction (Score 21-45 -> "Minor")
# Exploratory user wandering: excess steps, 1 backtrack, 1 repeated action,
# 1 slow step, 1 confusion point, but completed successfully.
# =============================================================================

def test_hand_made_session_2_minor():
    """
    Session 2: Minor friction during product search.
    - 6 steps taken vs 3 expected -> Excess Steps = 3 * 5 = 15 pts (evidence: [4, 5, 6])
    - Step 3 returns to /catalog -> Backtrack = 1 * 8 = 8 pts (evidence: [3])
    - Step 5 repeats click on Filter CTA -> Repeated Action = 1 * 6 = 6 pts (evidence: [5])
    - Step 4 duration 4.2s (> 3.0s threshold) -> Slow Transition = 1 * 5 = 5 pts (evidence: [4])
    - Step 5 reports confusion -> Confusion = 1 * 3 = 3 pts (evidence: [5])
    - Outcome: completed -> 0 failure penalty
    Total = 15 + 8 + 6 + 5 + 3 = 37 pts -> Label: Minor
    """
    steps = [
        Step(
            n=1,
            url="https://shop.test/catalog",
            url_after="https://shop.test/item/101",
            action="click",
            label="Product Card 101",
            target="uxg-10",
            ok=True,
            duration=1.2,
        ),
        Step(
            n=2,
            url="https://shop.test/item/101",
            url_after="https://shop.test/reviews",
            action="click",
            label="Reviews Tab",
            target="uxg-15",
            ok=True,
            duration=0.9,
        ),
        Step(
            n=3,
            url="https://shop.test/reviews",
            url_after="https://shop.test/catalog",  # Backtrack to catalog!
            action="click",
            label="Back to Catalog",
            target="uxg-20",
            ok=True,
            duration=1.1,
        ),
        Step(
            n=4,
            url="https://shop.test/catalog",
            url_after="https://shop.test/catalog",
            action="scroll",
            label="Catalog Scroll",
            target="uxg-30",
            ok=True,
            duration=4.2,  # Slow step!
        ),
        Step(
            n=5,
            url="https://shop.test/catalog",
            url_after="https://shop.test/catalog",
            action="click",
            label="Filter Button",
            target="uxg-35",  # First time clicking filter button
            ok=True,
            duration=1.0,
            friction_type="cta",
            friction_note="Filter drawer was slow to appear and had ambiguous labels",
        ),
        Step(
            n=6,
            url="https://shop.test/catalog",
            url_after="https://shop.test/catalog",
            action="click",
            label="Filter Button",
            target="uxg-35",  # Repeated action on same element!
            ok=True,
            duration=1.0,
        ),
    ]

    session = {
        "session_id": "sess-minor-02",
        "steps": steps,
        "expected_steps": 3,
        "outcome": "completed",
        "outcome_reason": "Item found after filtering",
        "task": "filter and view product details",
        "persona": "confused",
    }

    result = compute_friction(session)

    # Assert deterministic points: 15 (excess) + 8 (backtrack) + 6 (repeat) + 5 (slow) + 3 (confusion) = 37
    assert result["score"] == 37
    assert result["label"] == "Minor"
    assert 21 <= result["score"] <= 45

    # Check breakdown signals
    breakdown_map = {item["name"]: item for item in result["breakdown"]}
    assert "Excess Steps" in breakdown_map
    assert breakdown_map["Excess Steps"]["points"] == 15
    assert breakdown_map["Excess Steps"]["step_numbers"] == [4, 5, 6]

    assert "Navigation Backtracks" in breakdown_map
    assert breakdown_map["Navigation Backtracks"]["points"] == 8
    assert breakdown_map["Navigation Backtracks"]["step_numbers"] == [3]

    assert "Repeated Actions" in breakdown_map
    assert breakdown_map["Repeated Actions"]["points"] == 6
    assert breakdown_map["Repeated Actions"]["step_numbers"] == [6]

    assert "Slow Transitions" in breakdown_map
    assert breakdown_map["Slow Transitions"]["points"] == 5
    assert breakdown_map["Slow Transitions"]["step_numbers"] == [4]

    assert "Reported UX Confusion" in breakdown_map
    assert breakdown_map["Reported UX Confusion"]["points"] == 3
    assert breakdown_map["Reported UX Confusion"]["step_numbers"] == [5]

    # Verify Report.tsx card compatibility fields
    for part in result["parts"]:
        assert "name" in part
        assert "points" in part
        assert "why" in part
        assert "description" in part
        assert "evidence" in part
        assert "step_numbers" in part
        assert part["why"] == part["description"]
        assert part["evidence"] == part["step_numbers"]


# =============================================================================
# Hand-made Session 3: Severe Friction (Score 71-100 -> "Severe")
# Broken workflow with dead clicks, repeated clicks, console errors, slow steps,
# and abandoned task.
# =============================================================================

def test_hand_made_session_3_severe():
    """
    Session 3: Catastrophic checkout breakdown.
    - 7 steps taken, 2 expected -> Excess = 5 * 5 = 25 capped at 20 pts
    - Outcome: abandoned -> Penalty = 35 pts (evidence: [7])
    - Dead clicks at steps 3 and 4 -> Dead clicks = 2 * 7 = 14 pts (evidence: [3, 4])
    - Repeated clicks on same broken button at steps 4 and 5 -> Repeated = 2 * 6 = 12 pts (evidence: [4, 5])
    - Backtrack at step 6 returning to /checkout -> Backtrack = 1 * 8 = 8 pts (evidence: [6])
    - Console errors & network failures at steps 3 and 4 -> Errors = 4 * 4 = 16 pts (evidence: [3, 4])
    - Slow steps at steps 2 and 5 (durations 4.8s and 5.1s) -> Slow = 2 * 5 = 10 pts (evidence: [2, 5])
    - Confusion points at steps 3 and 4 -> Confusion = 2 * 3 = 6 pts (evidence: [3, 4])
    Raw total: 20 (excess) + 35 (failure) + 14 (dead clicks) + 12 (repeats) + 8 (backtrack) + 16 (errors) + 10 (slow) + 6 (confusion) = 121
    Clamped / Normalized to 100!
    Expected Score: 100 -> Label: Severe
    """
    steps = [
        Step(
            n=1,
            url="https://checkout.test/cart",
            url_after="https://checkout.test/shipping",
            action="click",
            label="Proceed to Shipping",
            target="uxg-1",
            ok=True,
            duration=1.0,
        ),
        Step(
            n=2,
            url="https://checkout.test/shipping",
            url_after="https://checkout.test/shipping",
            action="type",
            label="Address Field",
            target="uxg-2",
            ok=True,
            duration=4.8,  # Slow step!
        ),
        Step(
            n=3,
            url="https://checkout.test/shipping",
            url_after="https://checkout.test/shipping",
            action="click",
            label="Continue to Payment",
            target="uxg-3",
            ok=True,
            duration=1.5,
            dead_click=True,  # Dead click!
            console_errors=["TypeError: Cannot read property 'gateway' of undefined"],
            failed_requests=["POST /api/validate: 500 Internal Server Error"],
            friction_type="bug",
            friction_note="Continue button clicked but nothing happened",
        ),
        Step(
            n=4,
            url="https://checkout.test/shipping",
            url_after="https://checkout.test/shipping",
            action="click",
            label="Continue to Payment",
            target="uxg-3",  # Repeated action & dead click again!
            ok=True,
            duration=1.2,
            dead_click=True,
            console_errors=["TypeError: Gateway not initialized", "Uncaught NetworkError"],
            friction_type="bug",
            friction_note="Button still completely unresponsive",
        ),
        Step(
            n=5,
            url="https://checkout.test/shipping",
            url_after="https://checkout.test/shipping",
            action="click",
            label="Continue to Payment",
            target="uxg-3",  # Repeated action 3rd time!
            ok=True,
            duration=5.1,  # Slow step!
        ),
        Step(
            n=6,
            url="https://checkout.test/shipping",
            url_after="https://checkout.test/cart",  # Backtrack to cart out of frustration!
            action="click",
            label="Return to Cart",
            target="uxg-4",
            ok=True,
            duration=1.0,
        ),
        Step(
            n=7,
            url="https://checkout.test/cart",
            url_after="https://checkout.test/cart",
            action="abort",
            label="Abort",
            target="",
            ok=False,
            duration=0.0,
        ),
    ]

    session = {
        "session_id": "sess-severe-03",
        "steps": steps,
        "expected_steps": 2,
        "outcome": "abandoned",
        "outcome_reason": "Payment submission completely unresponsive due to JS errors",
        "task": "complete checkout payment",
        "persona": "impatient",
    }

    result = compute_friction(session)

    assert result["score"] >= 71
    assert result["score"] == 100
    assert result["total"] == 100
    assert result["label"] == "Severe"

    # Confirm all 8 signals triggered
    breakdown_names = [p["name"] for p in result["breakdown"]]
    assert "Excess Steps" in breakdown_names
    assert "Task Outcome Failure" in breakdown_names
    assert "Dead Clicks" in breakdown_names
    assert "Repeated Actions" in breakdown_names
    assert "Navigation Backtracks" in breakdown_names
    assert "Console & Network Errors" in breakdown_names
    assert "Slow Transitions" in breakdown_names
    assert "Reported UX Confusion" in breakdown_names

    # Check evidence on task failure
    task_fail = next(p for p in result["breakdown"] if p["name"] == "Task Outcome Failure")
    assert task_fail["points"] == 35
    assert task_fail["step_numbers"] == [7]


# =============================================================================
# Additional Rigorous Unit Tests
# =============================================================================

def test_score_label_mappings():
    """Verify exact boundaries of 0-20 Smooth, 21-45 Minor, 46-70 Moderate, 71-100 Severe."""
    assert score_to_label(0) == "Smooth"
    assert score_to_label(15) == "Smooth"
    assert score_to_label(20) == "Smooth"

    assert score_to_label(21) == "Minor"
    assert score_to_label(35) == "Minor"
    assert score_to_label(45) == "Minor"

    assert score_to_label(46) == "Moderate"
    assert score_to_label(60) == "Moderate"
    assert score_to_label(70) == "Moderate"

    assert score_to_label(71) == "Severe"
    assert score_to_label(90) == "Severe"
    assert score_to_label(100) == "Severe"


def test_pure_function_deterministic_and_idempotent():
    """compute_friction must be pure: same inputs produce identical results with no mutation."""
    raw_step = {
        "n": 1,
        "url": "https://test.com/a",
        "url_after": "https://test.com/b",
        "action": "click",
        "label": "Button A",
        "ok": True,
    }
    session = {
        "steps": [raw_step],
        "outcome": "completed",
    }
    res1 = compute_friction(session)
    res2 = compute_friction(session)

    assert res1 == res2
    assert res1["score"] == 0
    assert session["steps"][0] == raw_step


def test_llm_cannot_alter_computed_numbers():
    """
    Verify that build_report strictly enforces deterministic numbers from compute_friction,
    even if the LLM hallucinated different scores or numbers in its response.
    """
    steps = [
        Step(n=1, url="https://test.com/a", url_after="https://test.com/b", action="click", label="CTA", ok=True)
    ]
    session = {"steps": steps, "outcome": "completed"}
    deterministic_score = compute_friction(session)
    assert deterministic_score["score"] == 0
    assert deterministic_score["label"] == "Smooth"

    # Mock LLM attempting to alter score and verdict
    mock_llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(
                content="""{
                    "score": 999,
                    "label": "Hallucinated",
                    "verdict": "The LLM says this is the summary paragraph.",
                    "findings": [{"title": "Test Finding", "severity": "medium", "evidence_steps": [1], "what_happened": "x", "impact": "y", "recommendation": "z"}]
                }"""
            )
        )
    ]
    mock_llm.sync_chat_completion.return_value = mock_resp

    report = build_report(session, client=mock_llm)

    # Score numbers MUST come strictly from compute_friction and cannot be overwritten
    assert report["score"]["score"] == 0
    assert report["score"]["label"] == "Smooth"
    assert report["score"]["breakdown"] == []
    # But the LLM's summary paragraph is incorporated
    assert report["verdict"] == "The LLM says this is the summary paragraph."
    assert len(report["findings"]) == 1
    assert report["findings"][0]["title"] == "Test Finding"
