import base64
import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image

from scoring import Step, compute_friction, build_report
from evidence import (
    collect_axe_violations,
    collect_dom_violations,
    collect_step_evidence,
    draw_red_bounding_box,
    detect_findings_from_evidence,
    generate_suggested_fixes,
    normalize_selector_pattern,
    union_bboxes,
)


def _create_dummy_b64_image(width: int = 200, height: int = 100, color: str = "white") -> str:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def test_draw_red_bounding_box():
    """Verify that draw_red_bounding_box draws a red box on the screenshot and returns base64."""
    base_shot = _create_dummy_b64_image(200, 100, "white")
    bbox = {"x": 20, "y": 20, "width": 60, "height": 30}
    
    highlighted = draw_red_bounding_box(base_shot, bbox)
    assert highlighted is not None
    assert len(highlighted) > 0
    
    # Decode and check that red color (#ef4444 -> RGB 239, 68, 68) was painted
    img_bytes = base64.b64decode(highlighted)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    pixels = img.load()
    # Check near the top border of the bounding box (20, 20)
    found_red = False
    for x in range(20, 80):
        for y in range(18, 25):
            r, g, b = pixels[x, y]
            if r > 200 and g < 100 and b < 100:
                found_red = True
                break
        if found_red:
            break
    assert found_red, "Red bounding box border pixels should be present"


def test_collect_dom_violations_mock():
    """Verify DOM evaluations extract tap targets, contrast issues, and overlapping elements."""
    mock_page = AsyncMock()
    mock_page.evaluate.return_value = {
        "tap_targets": [
            {
                "selector": "#small-btn",
                "text": "x",
                "width": 24,
                "height": 24,
                "bounding_box": {"x": 10, "y": 10, "width": 24, "height": 24},
                "help": "Tap target (24x24px) is under 44x44px",
            }
        ],
        "contrast_issues": [
            {
                "selector": "#subtext",
                "text": "Terms apply",
                "contrast_ratio": 2.2,
                "min_ratio": 4.5,
                "fg_color": "rgb(180, 180, 180)",
                "bounding_box": {"x": 10, "y": 50, "width": 100, "height": 20},
                "help": "Low contrast ratio 2.2:1 below 4.5:1",
            }
        ],
        "overlapping_elements": [
            {
                "selector": "#btn-a",
                "overlaps_with": "#btn-b",
                "text": "Submit / Cancel",
                "overlap_area": 120,
                "bounding_box": {"x": 50, "y": 100, "width": 40, "height": 30},
                "help": "Interactive element overlaps by 120px²",
            }
        ],
    }

    import asyncio
    async def _test():
        res = await collect_dom_violations(mock_page)
        assert len(res["tap_targets"]) == 1
        assert res["tap_targets"][0]["width"] == 24
        assert len(res["contrast_issues"]) == 1
        assert res["contrast_issues"][0]["contrast_ratio"] == 2.2
        assert len(res["overlapping_elements"]) == 1
        assert res["overlapping_elements"][0]["overlap_area"] == 120

    asyncio.run(_test())


def test_critical_violations_feed_scoring_signals():
    """Verify critical accessibility and layout violations add points to friction score via Signal 9."""
    steps = [
        Step(
            n=1,
            url="https://test.com",
            url_after="https://test.com",
            action="click",
            label="Button",
            ok=True,
            axe_violations=[
                {"id": "color-contrast", "impact": "serious", "selector": "#btn", "help": "Elements must have sufficient color contrast"}
            ],
            tap_targets=[
                {"selector": "#small-icon", "width": 20, "height": 20, "bounding_box": {"x": 0, "y": 0, "width": 20, "height": 20}}
            ],
            overlapping_elements=[
                {"selector": "#btn-1", "overlaps_with": "#btn-2", "overlap_area": 150}
            ],
        )
    ]
    session = {"steps": steps, "outcome": "completed", "expected_steps": 1}
    result = compute_friction(session)
    
    # Signal 9 should be in breakdown
    signal_names = [part["name"] for part in result["breakdown"]]
    assert "Critical UI/A11y Violations" in signal_names
    crit_part = next(p for p in result["breakdown"] if p["name"] == "Critical UI/A11y Violations")
    assert crit_part["points"] > 0
    assert 1 in crit_part["step_numbers"]


def test_report_attaches_step_screenshot_bounding_box_and_llm_fix():
    """
    Verify build_report:
    - Derives findings programmatically from evidence (LLM out of detection)
    - Attaches step number, screenshot with red bounding box, and bounding box
    - Uses LLM solely to generate concrete CSS/copy suggested fixes
    """
    dummy_shot = _create_dummy_b64_image(300, 150, "white")
    steps = [
        Step(
            n=1,
            url="https://test.com/catalog",
            url_after="https://test.com/catalog",
            action="click",
            label="Cart Button",
            ok=True,
            screenshot=dummy_shot,
            tap_targets=[
                {
                    "selector": "#tiny-cart-btn",
                    "text": "Cart",
                    "width": 22,
                    "height": 22,
                    "bounding_box": {"x": 30, "y": 20, "width": 22, "height": 22},
                    "help": "Touch target 22x22px is under 44x44px",
                }
            ],
        )
    ]
    session = {"steps": steps, "outcome": "completed", "expected_steps": 1}

    # Mock LLM to return suggested fixes and verdict
    mock_llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(
                content="""{
                    "verdict": "Audited catalog page with touch target friction.",
                    "fixes": [
                        {
                            "index": 0,
                            "suggested_fix": "CSS: #tiny-cart-btn { min-width: 44px; min-height: 44px; padding: 12px; }"
                        }
                    ]
                }"""
            )
        )
    ]
    mock_llm.sync_chat_completion.return_value = mock_resp

    report = build_report(session, client=mock_llm)

    assert len(report["findings"]) >= 1
    f = report["findings"][0]

    # Finding must have step_number, bounding_box, screenshot, and suggested_fix
    assert f["step_number"] == 1
    assert f["bounding_box"] == {"x": 30, "y": 20, "width": 22, "height": 22}
    assert f["screenshot"] is not None
    assert len(f["screenshot"]) > 0
    # Fix should come from LLM
    assert "min-width: 44px" in f["suggested_fix"]
    assert "CSS:" in f["suggested_fix"]
    # And verdict came from LLM
    assert "touch target friction" in report["verdict"]


def test_normalize_selector_pattern():
    """Verify that trailing :nth-child and :nth-of-type indexes are stripped to group sibling nodes."""
    raw1 = 'span:nth-child(1) > .inline-block[data-word="true"]:nth-child(1)'
    raw2 = 'span:nth-child(1) > .inline-block[data-word="true"]:nth-child(4)'
    assert normalize_selector_pattern(raw1) == 'span:nth-child(1) > .inline-block[data-word="true"]'
    assert normalize_selector_pattern(raw2) == 'span:nth-child(1) > .inline-block[data-word="true"]'

    assert normalize_selector_pattern('ul > li:nth-child(3)') == 'ul > li'
    assert normalize_selector_pattern('button[type="submit"]') == 'button[type="submit"]'


def test_union_bboxes():
    """Verify union_bboxes accurately computes the outer bounding box enclosing all sibling elements."""
    b1 = {"x": 10, "y": 20, "width": 50, "height": 30}
    b2 = {"x": 70, "y": 15, "width": 40, "height": 40}

    union = union_bboxes(b1, b2)
    assert union["x"] == 10
    assert union["y"] == 15
    # right edge is max(10+50, 70+40) = 110 -> width = 110 - 10 = 100
    assert union["width"] == 100
    # bottom edge is max(20+30, 15+40) = 55 -> height = 55 - 15 = 40
    assert union["height"] == 40


def test_grouping_split_text_color_contrast_findings():
    """
    Verify the user's exact case:
    1 button[type='submit'] missing discernible text + 4 word spans failing color-contrast.
    Must be consolidated into exactly 2 findings:
    1 for button-name, 1 for color-contrast with occurrences=4 and unioned bounding box.
    """
    word_nodes = [
        {
            "id": "color-contrast",
            "impact": "serious",
            "selector": f'span:nth-child(1) > .inline-block[data-word="true"]:nth-child({i})',
            "help": "Elements must meet minimum color contrast ratio thresholds",
            "bounding_box": {"x": 10 + i * 50, "y": 30, "width": 45, "height": 25},
        }
        for i in range(1, 5)
    ]
    button_node = {
        "id": "button-name",
        "impact": "critical",
        "selector": 'button[type="submit"]',
        "help": "Buttons must have discernible text",
        "bounding_box": {"x": 200, "y": 100, "width": 40, "height": 40},
    }

    steps = [
        Step(
            n=1,
            url="https://example.com",
            action="submit",
            label="Submit",
            ok=True,
            axe_violations=[button_node] + word_nodes,
        )
    ]
    session = {"steps": steps, "outcome": "completed"}

    findings = detect_findings_from_evidence(session)

    # Must produce exactly 2 findings (not 5)
    assert len(findings) == 2

    # Find the contrast finding
    contrast_f = next(f for f in findings if "color-contrast" in f["title"])
    assert contrast_f["occurrences"] == 4
    assert contrast_f["selector"] == 'span:nth-child(1) > .inline-block[data-word="true"]'
    assert "4 elements" in contrast_f["title"]
    assert "across 4 elements" in contrast_f["what_happened"]

    # Bounding box should span all 4 words
    assert contrast_f["bounding_box"]["x"] == 60  # 10 + 1 * 50
    assert contrast_f["bounding_box"]["width"] >= 195

    # Button finding should be separate
    btn_f = next(f for f in findings if "button-name" in f["title"])
    assert btn_f["occurrences"] == 1
    assert btn_f["selector"] == 'button[type="submit"]'

    # Verify Signal 9 scoring penalty counts unique violations
    friction = compute_friction(session)
    crit_part = next(p for p in friction["breakdown"] if p["name"] == "Critical UI/A11y Violations")
    # 2 unique violations (button-name + color-contrast), not 5!
    assert crit_part["points"] == 8  # 2 * WEIGHT_CRITICAL_VIOLATION (4)

