import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from main import app, sessions, _run_baseline_phase
from baseline_cache import (
    normalize_cache_key,
    save_baseline,
    get_cached_baseline,
    clear_baseline_cache,
)
from scoring import Step, compute_friction, build_report


@pytest.fixture
def client():
    return TestClient(app)


def test_baseline_cache_normalize_and_store(tmp_path):
    """Verify that (url, task) pairs are normalized, stored, and retrieved from JSON."""
    test_file = tmp_path / "baselines_test.json"
    url = "https://example.com/shop/catalog/"
    task = "  Add Blue Shirt To Cart   "

    norm_key = normalize_cache_key(url, task)
    assert norm_key == "https://example.com/shop/catalog||add blue shirt to cart"

    path_data = [
        {"step": 1, "action": "click", "target": "Category: Shirts"},
        {"step": 2, "action": "click", "target": "Blue Shirt"},
        {"step": 3, "action": "click", "target": "Add to Cart"},
    ]

    saved = save_baseline(
        url=url,
        task=task,
        expected_steps=3,
        path=path_data,
        completed=True,
        file_path=test_file,
    )
    assert saved["expected_steps"] == 3
    assert saved["completed"] is True

    # Retrieve from cache using slightly different whitespace/casing
    cached = get_cached_baseline(
        url="https://EXAMPLE.com/shop/catalog",
        task="add blue shirt to cart",
        file_path=test_file,
    )
    assert cached is not None
    assert cached["expected_steps"] == 3
    assert len(cached["path"]) == 3
    assert cached["completed"] is True


def test_baseline_expected_steps_feeds_compute_friction():
    """
    Asserts that compute_friction accurately consumes expected_steps calibrated
    by the baseline mode rather than heuristic guessing.
    """
    # 7 steps taken
    steps = [
        Step(n=i, url="https://example.com/flow", action="click", label=f"Btn {i}", ok=True)
        for i in range(1, 8)
    ]

    # Without baseline (heuristic: round(7 * 0.6) = 4)
    res_heuristic = compute_friction({"steps": steps, "outcome": "completed"})
    assert res_heuristic["steps_taken"] == 7
    assert res_heuristic["expected_steps"] == 4
    assert res_heuristic["ideal_steps"] == 4

    # With real baseline data saying direct path is exactly 3 steps
    res_baseline = compute_friction({
        "steps": steps,
        "expected_steps": 3,
        "outcome": "completed",
    })
    assert res_baseline["steps_taken"] == 7
    assert res_baseline["expected_steps"] == 3
    assert res_baseline["ideal_steps"] == 3

    # Excess steps = 7 - 3 = 4 steps (4 * 5 = 20 pts)
    breakdown_map = {item["name"]: item for item in res_baseline["breakdown"]}
    assert "Excess Steps" in breakdown_map
    assert breakdown_map["Excess Steps"]["points"] == 20
    assert "3 expected vs 7 taken" in breakdown_map["Excess Steps"]["description"]


def test_baseline_failure_records_warning_and_falls_back_to_heuristic():
    """
    If the baseline itself fails, record that in the report ('task may be unreachable or unclear')
    and fall back to the heuristic step budget.
    """
    steps = [
        Step(n=1, url="https://example.com/404", action="click", label="Dead Link", ok=False),
        Step(n=2, url="https://example.com/404", action="abort", label="Abort", ok=False),
    ]

    session_data = {
        "steps": steps,
        "outcome": "abandoned",
        "expected_steps": 10,  # Stale or invalid override should be ignored due to failure
        "baseline_failed": True,
        "baseline_note": "task may be unreachable or unclear",
        "task": "Find non-existent checkout page",
        "persona": "impatient",
    }

    # 1. Scoring falls back to heuristic (steps_taken=2 -> heuristic expected_steps=2)
    score_data = compute_friction(session_data)
    assert score_data["baseline_failed"] is True
    assert score_data["baseline_note"] == "task may be unreachable or unclear"
    # Fallen back to heuristic for 2 steps (max(1, 2) = 2)
    assert score_data["expected_steps"] == 2

    # 2. Report records baseline failure prominently
    report = build_report(session_data, client=None)
    assert report["baseline_failed"] is True
    assert "unreachable or unclear" in report["baseline_note"].lower()
    assert "unreachable or unclear" in report["verdict"].lower()

    # Finding added for designers and developers
    baseline_findings = [f for f in report["findings"] if "baseline" in f["title"].lower()]
    assert len(baseline_findings) >= 1
    assert "unreachable" in baseline_findings[0]["title"].lower()


def test_launch_api_baseline_flag(client):
    """Verify that start-session API defaults baseline to True and accepts explicit False."""
    # 1. Default launch request (no baseline field provided)
    res1 = client.post("/api/launch", json={
        "url": "https://example.com/test1",
        "task": "test default baseline",
        "persona": "pro_tester",
    })
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["baseline"] is True
    assert sessions[data1["session_id"]]["baseline"] is True

    # 2. Explicit baseline = False
    res2 = client.post("/api/launch", json={
        "url": "https://example.com/test2",
        "task": "test disabled baseline",
        "persona": "impatient",
        "baseline": False,
    })
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["baseline"] is False
    assert sessions[data2["session_id"]]["baseline"] is False


def test_run_baseline_phase_uses_cache_and_streams_status(tmp_path):
    """
    Verify that _run_baseline_phase checks the cache first, updates session data,
    and streams status messages without spawning redundant browser runs.
    """
    import asyncio
    from baseline_cache import save_baseline

    async def _run():
        target_url = "https://cachetest.com/item"
        task = "purchase item"
        session_id = "test-sess-cache-123"

        # Pre-populate cache
        save_baseline(
            url=target_url,
            task=task,
            expected_steps=4,
            path=[{"step": 1, "action": "click"}],
            completed=True,
        )

        events = []
        mock_queue = AsyncMock()
        mock_queue.put = AsyncMock(side_effect=lambda item: events.append(item))

        mock_browser = MagicMock()
        # If cache works, new_page must NEVER be called
        mock_browser.new_page = AsyncMock()

        sess = {
            "session_id": session_id,
            "url": target_url,
            "task": task,
            "expected_steps": None,
            "baseline_path": [],
            "baseline_failed": False,
        }

        await _run_baseline_phase(mock_browser, target_url, task, mock_queue, session_id, sess)

        # Browser page was NOT opened because cache was used
        mock_browser.new_page.assert_not_called()

        # Session expected_steps was populated from cache
        assert sess["expected_steps"] == 4
        assert sess["baseline_failed"] is False

        # Event stream notified that baseline was loaded from cache
        assert any("cache" in ev.get("thought", "").lower() for ev in events)
        assert any(ev.get("phase") == "baseline" for ev in events)

    asyncio.run(_run())

