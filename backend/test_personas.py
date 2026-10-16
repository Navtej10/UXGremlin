import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from personas import (
    PersonaConfig,
    PERSONAS,
    get_persona_config,
    is_personal_data_field,
    get_fake_personal_data,
    audit_trust_signals_in_page,
)
from agent import extract_visible_interactive_elements, perform_action, run_agent_loop, OUTCOME_ABANDONED


def test_persona_configs_exist_and_conform():
    """Verify each persona config has viewport, timeouts, behavior rules, and hard rules."""
    required_personas = ["impatient", "confused", "skeptic", "pro_tester", "mobile"]
    for p in required_personas:
        cfg = get_persona_config(p)
        assert cfg.name == p
        assert isinstance(cfg.viewport, dict)
        assert "width" in cfg.viewport and "height" in cfg.viewport
        assert isinstance(cfg.timeouts, dict)
        assert "action_timeout" in cfg.timeouts
        assert "slow_step_threshold" in cfg.timeouts
        assert len(cfg.behavior_rules) > 20
        assert isinstance(cfg.hard_rules, dict)

    # Specific persona configurations:
    # 1. Impatient: wait timeout 2s, rage-click after 2 no-change clicks, abandons after 3 slow steps
    impatient = get_persona_config("impatient")
    assert impatient.timeouts["action_timeout"] == 2.0
    assert impatient.timeouts["slow_step_threshold"] == 2.0
    assert impatient.hard_rules["rage_click_no_change_threshold"] == 2
    assert impatient.hard_rules["max_slow_steps"] == 3

    # 2. Confused: ignores links under size threshold, prefers prominent buttons, hesitates on icon-only
    confused = get_persona_config("confused")
    assert confused.hard_rules["ignore_link_area_threshold"] == 1200
    assert confused.hard_rules["prefer_prominent_buttons"] is True
    assert confused.hard_rules["hesitate_on_icon_only"] is True

    # 3. Skeptic: refuses personal data, checks trust signals
    skeptic = get_persona_config("skeptic")
    assert skeptic.hard_rules["refuse_personal_data"] is True
    assert skeptic.hard_rules["check_trust_signals"] is True

    # 4. Pro Tester: systematically visits control categories
    pro = get_persona_config("pro_tester")
    assert pro.hard_rules["track_control_categories"] is True
    assert "button" in pro.hard_rules["systematic_categories"]
    assert "input" in pro.hard_rules["systematic_categories"]

    # 5. Mobile: viewport 390x844 with touch events, flags tap targets below 44px
    mobile = get_persona_config("mobile")
    assert mobile.viewport == {"width": 390, "height": 844}
    assert mobile.has_touch is True
    assert mobile.is_mobile is True
    assert mobile.hard_rules["min_tap_target_size"] == 44


def test_confused_persona_element_filtering():
    """Verify confused persona ignores links under size threshold and prefers prominent buttons."""
    raw_elements = [
        {"id": "uxg-1", "tag": "a", "text": "Tiny footer link", "width": 40, "height": 15, "area": 600, "is_icon_only": False},
        {"id": "uxg-2", "tag": "a", "text": "Large navigation banner link", "width": 200, "height": 40, "area": 8000, "is_icon_only": False},
        {"id": "uxg-3", "tag": "button", "text": "Buy Now Button", "width": 150, "height": 50, "area": 7500, "is_icon_only": False},
        {"id": "uxg-4", "tag": "input", "text": "Search input", "width": 200, "height": 35, "area": 7000, "is_icon_only": False},
    ]

    mock_page = AsyncMock()
    mock_page.evaluate.return_value = list(raw_elements)

    async def _run():
        confused_cfg = get_persona_config("confused")
        filtered = await extract_visible_interactive_elements(mock_page, persona_cfg=confused_cfg)

        # 1. Tiny link (area 600 < 1200) was ignored
        ids = [el["id"] for el in filtered]
        assert "uxg-1" not in ids
        assert "uxg-2" in ids

        # 2. Prominent buttons/inputs are sorted first
        tags = [el["tag"] for el in filtered]
        assert tags[0] in ("button", "input")
        assert tags[1] in ("button", "input")
        assert tags[2] == "a"

    asyncio.run(_run())


def test_skeptic_fake_data_and_trust_signals():
    """Verify skeptic identifies personal data fields, substitutes fake data, and audits trust signals."""
    # 1. Personal data field identification
    assert is_personal_data_field("Email Address", "uxg-1", "email") is True
    assert is_personal_data_field("Phone Number", "uxg-2", "tel") is True
    assert is_personal_data_field("First Name", "uxg-3", "text") is True
    assert is_personal_data_field("Quantity to purchase", "uxg-4", "number") is False

    # 2. Fake personal data replacement
    fake_email = get_fake_personal_data("Email Address")
    assert "@" in fake_email
    assert "fake" in fake_email.lower() or "invalid" in fake_email.lower()

    fake_phone = get_fake_personal_data("Phone Number")
    assert "555" in fake_phone

    # 3. Missing trust signals audit
    page_without_signals = "Welcome to our store. Buy items now."
    findings = audit_trust_signals_in_page(page_without_signals, [])
    assert len(findings) == 3
    finding_titles = [f["title"].lower() for f in findings]
    assert any("privacy" in t for t in finding_titles)
    assert any("reviews" in t or "social proof" in t for t in finding_titles)
    assert any("pricing" in t for t in finding_titles)

    # 4. Present trust signals recognized
    page_with_signals = "Check out our pricing: $10/month. Read our 5-star customer reviews! Read our Privacy Policy."
    links_with_privacy = [{"text": "Privacy Policy", "href": "/privacy"}]
    findings_clean = audit_trust_signals_in_page(page_with_signals, links_with_privacy)
    assert len(findings_clean) == 0


def test_impatient_persona_abandons_after_3_slow_steps():
    """Verify impatient persona abandons the task when 3 slow steps exceed the 2.0s threshold."""
    async def _run():
        mock_page = AsyncMock()
        mock_page.url = "https://example.com/checkout"
        mock_page.screenshot.return_value = b"fake_screenshot"
        mock_page.evaluate.return_value = [
            {"id": "uxg-1", "tag": "button", "text": "Submit Order", "width": 100, "height": 40, "area": 4000, "is_icon_only": False}
        ]

        queue = asyncio.Queue()
        session_data = {"steps": []}

        # Mock LLM decision to always click uxg-1
        mock_decision = {
            "action": "click",
            "target": "uxg-1",
            "thought": "Clicking slow button",
            "task_status": "in_progress",
        }

        # Simulate perform_action taking 2.5 seconds (slow step > 2.0s)
        async def slow_action(*args, **kwargs):
            await asyncio.sleep(0.01)  # fast unit test simulation
            return True, None

        with patch("agent.resilient_llm_client.chat_completion") as mock_llm, \
             patch("agent.perform_action", side_effect=slow_action), \
             patch("agent.settle", return_value=None):

            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content=str(mock_decision).replace("'", '"')))]
            mock_llm.return_value = mock_response

            # Mock time.time to simulate 3.0 second durations on each step
            t_state = [100.0]
            def fake_time():
                t_state[0] += 3.0
                return t_state[0]
            with patch("time.time", side_effect=fake_time):
                report = await run_agent_loop(
                    page=mock_page,
                    task="checkout item",
                    persona="impatient",
                    queue=queue,
                    max_steps=5,
                    session_id="sess-impatient-abandon",
                    session_data=session_data,
                    emit_done=True,
                )

        assert report["outcome"] == OUTCOME_ABANDONED
        assert "slow steps" in report["outcome_reason"].lower()
        assert len(session_data["steps"]) == 3

    asyncio.run(_run())


def test_impatient_persona_rage_clicks_after_2_no_change_clicks():
    """Verify impatient persona triggers a rage-click (click_count=3) after 2 dead clicks."""
    async def _run():
        mock_page = AsyncMock()
        mock_page.url = "https://example.com/checkout"
        mock_page.screenshot.return_value = b"fake_screenshot"
        # Mock evaluate for DOM length comparisons (same before and after = dead click)
        mock_page.evaluate.return_value = "100:10"

        queue = asyncio.Queue()
        session_data = {"steps": []}

        mock_decision = {
            "action": "click",
            "target": "uxg-1",
            "thought": "Clicking unresponsive button",
            "task_status": "in_progress",
        }

        action_click_counts = []
        async def record_clicks(page, action, target, value="", timeout=3.0, click_count=1):
            action_click_counts.append(click_count)
            return True, None

        with patch("agent.resilient_llm_client.chat_completion") as mock_llm, \
             patch("agent.perform_action", side_effect=record_clicks), \
             patch("agent.settle", return_value=None), \
             patch("agent.extract_visible_interactive_elements", return_value=[{"id": "uxg-1", "tag": "button", "text": "Stuck Button", "width": 80, "height": 40, "area": 3200, "is_icon_only": False}]):

            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content=str(mock_decision).replace("'", '"')))]
            mock_llm.return_value = mock_response

            # Run 3 steps: step 1 (click_count=1, dead), step 2 (click_count=1, dead), step 3 (click_count=3, RAGE CLICK!)
            await run_agent_loop(
                page=mock_page,
                task="test rage click",
                persona="impatient",
                queue=queue,
                max_steps=3,
                session_id="sess-impatient-rage",
                session_data=session_data,
                emit_done=True,
            )

        assert len(action_click_counts) == 3
        assert action_click_counts[0] == 1
        assert action_click_counts[1] == 1
        # Step 3 had 2 prior no-change clicks, so it rage-clicked!
        assert action_click_counts[2] == 3

    asyncio.run(_run())
