import io
import pytest
from unittest.mock import AsyncMock, MagicMock
from PIL import Image

from agent import (
    overlay_set_of_marks,
    format_som_element_list,
    parse_som_target,
    trim_accessibility_tree,
    capture_accessibility_snapshot,
    compute_page_state_hash,
    check_loop_detection,
    handle_cookie_banners,
    follow_new_tabs,
    handle_blocking_modals,
    evaluate_stop_rules,
    OUTCOME_COMPLETED,
    OUTCOME_ABANDONED,
    OUTCOME_GAVE_UP,
    OUTCOME_MAX_STEPS,
    OUTCOME_ERROR,
)


def _create_test_image_bytes(width=200, height=200, color="white"):
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# 1. Set-of-Marks Overlay Tests
def test_overlay_set_of_marks():
    img_bytes = _create_test_image_bytes(200, 200)
    elements = [
        {
            "num": 1,
            "role": "button",
            "name": "Submit",
            "bbox": {"x": 20, "y": 20, "width": 80, "height": 30},
        },
        {
            "num": 2,
            "role": "textbox",
            "name": "Email",
            "bbox": {"x": 20, "y": 60, "width": 120, "height": 30},
        },
    ]

    marked_bytes = overlay_set_of_marks(img_bytes, elements)
    assert isinstance(marked_bytes, bytes)
    assert len(marked_bytes) > 0

    # Ensure output can be opened as a valid PIL image with matching size
    marked_img = Image.open(io.BytesIO(marked_bytes))
    assert marked_img.size == (200, 200)


def test_format_som_element_list():
    elements = [
        {
            "num": 1,
            "role": "button",
            "name": "Submit Order",
            "bbox": {"x": 10, "y": 10, "width": 100, "height": 40},
        },
        {
            "num": 2,
            "role": "link",
            "name": "Cancel",
            "bbox": {"x": 120, "y": 10, "width": 60, "height": 20},
        },
    ]

    formatted = format_som_element_list(elements)
    assert '[1] role=button | name="Submit Order"' in formatted
    assert '[2] role=link | name="Cancel"' in formatted
    assert 'bbox={"x": 10, "y": 10, "width": 100, "height": 40}' in formatted


def test_parse_som_target():
    elements = [
        {"num": 1, "id": "uxg-1", "name": "Sign In", "role": "button"},
        {"num": 2, "id": "uxg-2", "name": "Password", "role": "textbox"},
    ]

    # Test integer
    num, target_id = parse_som_target(1, elements)
    assert num == 1
    assert target_id == "uxg-1"

    # Test string digit
    num, target_id = parse_som_target("2", elements)
    assert num == 2
    assert target_id == "uxg-2"

    # Test bracket format [1]
    num, target_id = parse_som_target("[1]", elements)
    assert num == 1
    assert target_id == "uxg-1"

    # Test uxg-id format
    num, target_id = parse_som_target("uxg-2", elements)
    assert num == 2
    assert target_id == "uxg-2"

    # Test accessible name match
    num, target_id = parse_som_target("Sign In", elements)
    assert num == 1
    assert target_id == "uxg-1"

    # Test fallback target when not found in elements
    num, target_id = parse_som_target("button#custom", elements)
    assert num is None
    assert target_id == "button#custom"


# 2. Trimmed Accessibility Tree Tests
def test_trim_accessibility_tree():
    raw_tree = "\n\n   - button 'Submit'   \n\n\n   - textbox 'Username'   \n"
    trimmed = trim_accessibility_tree(raw_tree, max_chars=500)
    assert "- button 'Submit'" in trimmed
    assert "- textbox 'Username'" in trimmed
    assert "\n\n" not in trimmed

    # Test max_chars truncation
    long_tree = "\n".join([f"- item {i}" for i in range(100)])
    truncated = trim_accessibility_tree(long_tree, max_chars=100)
    assert "[accessibility tree snapshot trimmed to conserve tokens]" in truncated


@pytest.mark.anyio
async def test_capture_accessibility_snapshot():
    # Test with native aria_snapshot available
    page = AsyncMock()
    page.aria_snapshot = AsyncMock(return_value="- button 'Accept'")
    snapshot = await capture_accessibility_snapshot(page)
    assert "- button 'Accept'" in snapshot

    # Test with fallback evaluate when aria_snapshot not present
    page_fallback = AsyncMock()
    del page_fallback.aria_snapshot
    page_fallback.evaluate = AsyncMock(return_value="[button] 'Submit'")
    snapshot_fb = await capture_accessibility_snapshot(page_fallback)
    assert "[button] 'Submit'" in snapshot_fb


# 3. State Hash & Loop Detection Tests
def test_compute_page_state_hash():
    h1 = compute_page_state_hash("https://example.com/checkout", "<div>Content</div>")
    h2 = compute_page_state_hash("https://example.com/checkout", "<div>Content</div>")
    h3 = compute_page_state_hash("https://example.com/checkout", "<div>Modified Content</div>")

    assert isinstance(h1, str) and len(h1) == 16
    assert h1 == h2
    assert h1 != h3


def test_check_loop_detection_repeated_actions():
    action_history = [
        {"action": "click", "target": "1"},
        {"action": "click", "target": "1"},
        {"action": "click", "target": "1"},
    ]
    state_hashes = ["hash1", "hash2", "hash3"]

    is_loop, reason, hint = check_loop_detection(action_history, state_hashes)
    assert is_loop is True
    assert "repeated 3" in reason
    assert len(hint) > 0
    assert "not advancing" in hint.lower() or "try" in hint.lower()


def test_check_loop_detection_unchanged_state():
    action_history = [
        {"action": "click", "target": "1"},
        {"action": "scroll_down", "target": ""},
        {"action": "click", "target": "2"},
    ]
    state_hashes = ["same_state", "same_state", "same_state"]

    is_loop, reason, hint = check_loop_detection(action_history, state_hashes)
    assert is_loop is True
    assert "remained unchanged for 3" in reason
    assert len(hint) > 0
    assert "static" in hint.lower() or "blocking" in hint.lower()


def test_check_loop_detection_normal_progression():
    action_history = [
        {"action": "click", "target": "1"},
        {"action": "type", "target": "2"},
    ]
    state_hashes = ["state1", "state2"]

    is_loop, reason, hint = check_loop_detection(action_history, state_hashes)
    assert is_loop is False
    assert reason == ""
    assert hint == ""


# 4. Auto-Handle Cookie Banners, Popups & New Tabs Tests
@pytest.mark.anyio
async def test_handle_cookie_banners():
    page = AsyncMock()
    mock_locator = AsyncMock()
    mock_locator.is_visible = AsyncMock(return_value=True)
    mock_locator.click = AsyncMock()
    mock_locator.first = mock_locator
    page.locator = MagicMock(return_value=mock_locator)

    dismissed = await handle_cookie_banners(page)
    assert dismissed is True
    assert mock_locator.click.await_count == 1


@pytest.mark.anyio
async def test_follow_new_tabs():
    page1 = AsyncMock()
    page2 = AsyncMock()
    page2.is_closed = MagicMock(return_value=False)
    page2.bring_to_front = AsyncMock()
    page2.wait_for_load_state = AsyncMock()

    ctx = MagicMock()
    ctx.pages = [page1, page2]
    page1.context = ctx

    active_page, did_switch = await follow_new_tabs(page1)
    assert did_switch is True
    assert active_page is page2
    assert page2.bring_to_front.await_count == 1


@pytest.mark.anyio
async def test_handle_blocking_modals_ignores_when_target_inside():
    page = AsyncMock()
    mock_modal = AsyncMock()
    mock_modal.is_visible = AsyncMock(return_value=True)
    mock_modal.first = mock_modal
    page.locator = MagicMock(return_value=mock_modal)
    # page.evaluate returns True -> target is inside modal
    page.evaluate = AsyncMock(return_value=True)

    closed, desc = await handle_blocking_modals(page, target="button#inner-modal-btn")
    assert closed is False
    assert desc is None


@pytest.mark.anyio
async def test_handle_blocking_modals_closes_when_target_outside():
    page = AsyncMock()
    mock_modal = AsyncMock()
    mock_modal.is_visible = AsyncMock(return_value=True)
    mock_modal.inner_text = AsyncMock(return_value="Subscribe Newsletter\nSign up for deals")
    mock_modal.first = mock_modal

    mock_close_btn = AsyncMock()
    mock_close_btn.is_visible = AsyncMock(return_value=True)
    mock_close_btn.click = AsyncMock()
    mock_close_btn.first = mock_close_btn
    mock_modal.locator = MagicMock(return_value=mock_close_btn)

    page.locator = MagicMock(return_value=mock_modal)
    # Target outside modal
    page.evaluate = AsyncMock(return_value=False)

    closed, desc = await handle_blocking_modals(page, target="button#outside-btn")
    assert closed is True
    assert desc is not None
    assert "Subscribe Newsletter" in desc
    assert mock_close_btn.click.await_count == 1


# 5. Stop Rules Tests
def test_evaluate_stop_rules():
    # 1. Done & Verified
    stop, outcome, reason = evaluate_stop_rules(step=5, max_steps=15, is_done_claimed=True, is_verified=True)
    assert stop is True
    assert outcome == OUTCOME_COMPLETED

    # 2. Done but verification failed -> Abandoned
    stop, outcome, reason = evaluate_stop_rules(step=5, max_steps=15, is_done_claimed=True, is_verified=False)
    assert stop is True
    assert outcome == OUTCOME_ABANDONED

    # 3. Stuck / Loop detected -> Gave up
    stop, outcome, reason = evaluate_stop_rules(step=5, max_steps=15, is_loop_detected=True)
    assert stop is True
    assert outcome == OUTCOME_GAVE_UP

    # 4. Error threshold reached -> Error
    stop, outcome, reason = evaluate_stop_rules(step=5, max_steps=15, consecutive_errors=3, max_consecutive_errors=3)
    assert stop is True
    assert outcome == OUTCOME_ERROR

    # 5. Max steps reached -> Max steps
    stop, outcome, reason = evaluate_stop_rules(step=15, max_steps=15)
    assert stop is True
    assert outcome == OUTCOME_MAX_STEPS

    # 6. Normal ongoing execution -> Should not stop
    stop, outcome, reason = evaluate_stop_rules(step=5, max_steps=15)
    assert stop is False
    assert outcome is None
