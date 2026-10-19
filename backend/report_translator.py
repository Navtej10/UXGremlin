"""
Plain-language presentation layer for UXGremlin reports.
Translates raw axe-core findings, DOM metrics, and cognitive friction scores into
clear, actionable human insights for non-technical stakeholders (founders, marketers,
designers, judges).

Strict Rules:
- No raw CSS selectors in user-facing fields (humanize into location descriptions).
- No jargon, acronyms, or raw rule IDs outside technical details.
- Group by problem, not by element.
- 400px+ readable cropped screenshots with 4px red outlines and human captions.
- Zero changes to scoring numbers or deterministic penalty math.
"""

from __future__ import annotations

import base64
import html
import io
import json
import re
from typing import Any
from PIL import Image, ImageDraw


# ---------------------------------------------------------------------------
# 1. PERSONA HUMAN NAMES & LABELS
# ---------------------------------------------------------------------------

PERSONA_FIRST_NAMES: dict[str, str] = {
    "impatient": "Riley",
    "confused": "Morgan",
    "skeptic": "Sam",
    "mobile": "Taylor",
    "pro_tester": "Alex",
}

def get_user_display_name(persona: str | None) -> str:
    """Returns a friendly first name or 'The test user'."""
    p_key = (persona or "").strip().lower()
    for key, name in PERSONA_FIRST_NAMES.items():
        if key in p_key:
            return name
    return "The test user"


# ---------------------------------------------------------------------------
# 2. SCORE BREAKDOWN HUMANIZER
# ---------------------------------------------------------------------------

PENALTY_HUMAN_MAPPINGS: dict[str, dict[str, str]] = {
    "Dead Clicks": {
        "human_name": "Clicks that did nothing",
        "description": "The user clicked several buttons or links that gave no visual response or action.",
    },
    "Task Outcome Failure": {
        "human_name": "Couldn't finish the task",
        "description": "The test user was unable to complete the main goal and had to give up.",
    },
    "Reported UX Confusion": {
        "human_name": "Confusing moments",
        "description": "The test user paused or hesitated because the page layout or options were unclear.",
    },
    "Critical UI/A11y Violations": {
        "human_name": "Accessibility problems",
        "description": "Automated checks detected serious barriers for people with disabilities or visual impairments.",
    },
    "Moderate UI/A11y Violations": {
        "human_name": "Moderate accessibility problems",
        "description": "Several elements make the experience difficult for screen readers or low-vision visitors.",
    },
    "Minor UI/A11y Violations": {
        "human_name": "Minor polish issues",
        "description": "Minor layout or tagging imperfections that reduce overall polish.",
    },
    "Excess Steps": {
        "human_name": "Extra unnecessary steps",
        "description": "Reaching the goal required significantly more clicks and page loads than expected.",
    },
    "Slow Steps": {
        "human_name": "Slow page responses",
        "description": "Several interactions took longer than 2 seconds to load or update.",
    },
    "Rage Clicks": {
        "human_name": "Frustrated repeated clicks",
        "description": "The user clicked an unresponsive control multiple times in rapid succession out of frustration.",
    },
    "Audit Interrupted (System / Timeout)": {
        "human_name": "Test stopped early",
        "description": "The test session ended early due to an infrastructure timeout limit.",
    },
}

def humanize_penalty_part(part: dict[str, Any]) -> dict[str, Any]:
    """Translates a friction penalty row into plain language."""
    raw_name = part.get("name", "")
    info = PENALTY_HUMAN_MAPPINGS.get(raw_name)
    if not info:
        # Fuzzy match
        for key, val in PENALTY_HUMAN_MAPPINGS.items():
            if key.lower() in raw_name.lower():
                info = val
                break

    human_name = info["human_name"] if info else raw_name
    human_why = info["description"] if info else part.get("why", "")

    return {
        **part,
        "raw_name": raw_name,
        "name": human_name,
        "why": human_why,
    }


# ---------------------------------------------------------------------------
# 3. HUMAN NAMES FOR ELEMENTS (Never selectors, classes, or nth-child)
# ---------------------------------------------------------------------------

def humanize_element_location(
    selector: str | None,
    text: str | None = None,
    aria_label: str | None = None,
    tag: str | None = None,
    role: str | None = None,
    page_context: str | None = None,
) -> str:
    """
    Turns a selector and element metadata into a natural description a person would use.
    Priority:
      1. Visible text: "the 'Subscribe' link"
      2. aria-label: "the 'Close dialog' button"
      3. Role + page area: "Footer, column heading", "Checkout form, email field"
    Never outputs class names, nth-child, or raw pixel sizes.
    """
    clean_text = (text or "").strip()
    if clean_text:
        # Trim whitespace, remove newlines, truncate nicely
        clean_text = re.sub(r"\s+", " ", clean_text)
        if len(clean_text) > 32:
            clean_text = clean_text[:28].rstrip() + "…"
        # Strip outer quotes if any
        clean_text = clean_text.strip("\"'")

    clean_aria = (aria_label or "").strip()
    if clean_aria:
        clean_aria = re.sub(r"\s+", " ", clean_aria)
        if len(clean_aria) > 32:
            clean_aria = clean_aria[:28].rstrip() + "…"
        clean_aria = clean_aria.strip("\"'")

    sel_str = (selector or "").lower()

    # 1. Determine Page Area
    area = None
    if "footer" in sel_str or (page_context and "footer" in page_context.lower()):
        area = "Footer"
    elif "header" in sel_str or "nav" in sel_str or (page_context and "header" in page_context.lower()):
        area = "Header"
    elif any(k in sel_str for k in ("modal", "popup", "dialog", "overlay", "cookie")):
        area = "Popup dialog"
    elif any(k in sel_str for k in ("checkout", "cart", "payment", "order")):
        area = "Checkout form"
    elif any(k in sel_str for k in ("sidebar", "aside")):
        area = "Sidebar"
    elif any(k in sel_str for k in ("hero", "banner")):
        area = "Top banner"
    elif "form" in sel_str:
        area = "Form"

    # 2. Determine Element Type
    elem_type = "element"
    if "button" in sel_str or role == "button" or tag == "button":
        elem_type = "button"
    elif "link" in sel_str or role == "link" or tag == "a" or sel_str.endswith(" a"):
        elem_type = "link"
    elif "input" in sel_str or tag == "input":
        if "email" in sel_str:
            elem_type = "email field"
        elif "password" in sel_str:
            elem_type = "password field"
        elif "checkbox" in sel_str:
            elem_type = "checkbox"
        else:
            elem_type = "input field"
    elif "select" in sel_str or tag == "select":
        elem_type = "dropdown menu"
    elif any(h in sel_str for h in ("h1", "h2", "h3", "h4", "h5", "h6")) or tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
        elem_type = "heading"
    elif "img" in sel_str or tag == "img":
        elem_type = "image"
    elif "body" in sel_str:
        return "Main page view"

    # 3. Construct Plain-Language Description
    if clean_text:
        desc = f"'{clean_text}' {elem_type}"
    elif clean_aria:
        desc = f"'{clean_aria}' {elem_type}"
    else:
        # No visible text or aria-label
        if elem_type == "heading":
            desc = "section heading"
        elif elem_type == "button":
            if "submit" in sel_str:
                desc = "submit button"
            else:
                desc = "action button"
        elif elem_type == "link":
            desc = "navigation link"
        elif elem_type == "input field":
            desc = "entry field"
        else:
            desc = f"interactive {elem_type}"

    if area:
        # e.g., "Footer, 'Subscribe' link"
        return f"{area}, {desc}"
    else:
        # Capitalize first letter
        return desc[0].upper() + desc[1:] if desc else "Interactive element"


# ---------------------------------------------------------------------------
# 4. DETERMINISTIC TRANSLATION MAP FOR KNOWN AUTOMATED CHECKS
# ---------------------------------------------------------------------------

KNOWN_RULE_MAP: dict[str, dict[str, Any]] = {
    "color-contrast": {
        "title": "Some text is hard to read",
        "what_happened": "{user} looked at this section, but the text was too pale against the background.",
        "why_it_matters": "The text color is too close to the background, so people with weak eyesight or in bright light can miss it.",
        "how_to_fix": "Increase the contrast between the text color and background so everyone can easily read it.",
        "theme": "Hard to read",
        "severity": "Medium",
        "severity_label": "Slows people down",
        "wcag": "WCAG 1.4.3 Contrast (Minimum)",
    },
    "heading-order": {
        "title": "The page structure is jumbled",
        "what_happened": "{user} encountered section headings that skipped levels, making the page confusing to follow.",
        "why_it_matters": "Headings skip levels, which confuses screen readers and makes the page harder to scan.",
        "how_to_fix": "Organize headings in sequential order without skipping levels.",
        "theme": "Works for everyone (accessibility)",
        "severity": "Low",
        "severity_label": "Minor polish",
        "wcag": "WCAG 1.3.1 Info and Relationships",
    },
    "bypass": {
        "title": "Keyboard users must tab through the whole menu first",
        "what_happened": "{user} had to navigate through repetitive top menus before reaching the actual page content.",
        "why_it_matters": "Keyboard users must tab through the whole menu first before reaching the main content.",
        "how_to_fix": "Add a visible skip-to-content shortcut at the very top of the page.",
        "theme": "Works for everyone (accessibility)",
        "severity": "Medium",
        "severity_label": "Slows people down",
        "wcag": "WCAG 2.4.1 Bypass Blocks",
    },
    "skip-link": {
        "title": "Keyboard users must tab through the whole menu first",
        "what_happened": "{user} had to step through every navigation link before reaching the main content.",
        "why_it_matters": "Keyboard users must tab through the whole menu first before reaching the main content.",
        "how_to_fix": "Add a visible skip-to-content shortcut at the very top of the page.",
        "theme": "Works for everyone (accessibility)",
        "severity": "Medium",
        "severity_label": "Slows people down",
        "wcag": "WCAG 2.4.1 Bypass Blocks",
    },
    "region": {
        "title": "The page isn't divided into clear sections for assistive tools",
        "what_happened": "{user} found page content that wasn't organized into clear structural landmarks.",
        "why_it_matters": "The page isn't divided into clear sections for assistive tools, so screen readers cannot jump quickly to navigation or main content.",
        "how_to_fix": "Wrap main areas in standard section tags like header, main, and footer.",
        "theme": "Works for everyone (accessibility)",
        "severity": "Low",
        "severity_label": "Minor polish",
        "wcag": "WCAG 1.3.1 Info and Relationships",
    },
    "landmark-one-main": {
        "title": "The page isn't divided into clear sections for assistive tools",
        "what_happened": "{user} found page content without a designated main content area.",
        "why_it_matters": "The page isn't divided into clear sections for assistive tools to identify where primary content begins.",
        "how_to_fix": "Wrap the primary page content inside a main section.",
        "theme": "Works for everyone (accessibility)",
        "severity": "Low",
        "severity_label": "Minor polish",
        "wcag": "WCAG 1.3.1 Info and Relationships",
    },
    "label": {
        "title": "A form field has no clear label",
        "what_happened": "{user} encountered an input field with no visible label explaining what to enter.",
        "why_it_matters": "A form field has no clear label, leaving visitors and screen readers unsure what information is required.",
        "how_to_fix": "Add a visible, descriptive label directly beside or above the input field.",
        "theme": "Forms and errors",
        "severity": "High",
        "severity_label": "Blocks the goal",
        "wcag": "WCAG 3.3.2 Labels or Instructions",
    },
    "form-field-multiple-labels": {
        "title": "A form field has conflicting labels",
        "what_happened": "{user} encountered an input field attached to multiple conflicting labels.",
        "why_it_matters": "Conflicting labels confuse screen readers and can mislead visitors entering personal details.",
        "how_to_fix": "Attach each form input to exactly one clear, descriptive label.",
        "theme": "Forms and errors",
        "severity": "Medium",
        "severity_label": "Slows people down",
        "wcag": "WCAG 3.3.2 Labels or Instructions",
    },
    "button-name": {
        "title": "A button or link has no readable name",
        "what_happened": "{user} hovered or focused on a button that had no visible text or descriptive label.",
        "why_it_matters": "A button or link has no readable name, so visitors and screen readers cannot tell what action it triggers.",
        "how_to_fix": "Add clear, readable text or a descriptive name directly on the button.",
        "theme": "Works for everyone (accessibility)",
        "severity": "High",
        "severity_label": "Blocks the goal",
        "wcag": "WCAG 4.1.2 Name, Role, Value",
    },
    "link-name": {
        "title": "A button or link has no readable name",
        "what_happened": "{user} reached a link that contained no text explaining where it leads.",
        "why_it_matters": "A button or link has no readable name, making it impossible to know where it leads before clicking.",
        "how_to_fix": "Add clear descriptive text inside the link explaining its destination.",
        "theme": "Works for everyone (accessibility)",
        "severity": "High",
        "severity_label": "Blocks the goal",
        "wcag": "WCAG 2.4.4 Link Purpose",
    },
    "image-alt": {
        "title": "An image has no description",
        "what_happened": "{user} saw an image on the page with no descriptive text attached.",
        "why_it_matters": "An image has no description, so visitors who cannot see the picture miss its context and meaning.",
        "how_to_fix": "Add a short, descriptive summary explaining what the image depicts.",
        "theme": "Works for everyone (accessibility)",
        "severity": "Low",
        "severity_label": "Minor polish",
        "wcag": "WCAG 1.1.1 Non-text Content",
    },
    "target-size": {
        "title": "A button is too small to tap easily",
        "what_happened": "{user} tried to tap a tiny control and had trouble pressing it accurately.",
        "why_it_matters": "A button is too small to tap easily, causing frustrating mis-taps on phones and tablets.",
        "how_to_fix": "Increase the button's clickable size and padding to at least 44 by 44 points.",
        "theme": "Can't find or reach what you want",
        "severity": "Medium",
        "severity_label": "Slows people down",
        "wcag": "WCAG 2.5.8 Target Size",
    },
    "dead_click": {
        "title": "Clicks that did nothing",
        "what_happened": "{user} clicked here expecting the page to update, but nothing happened.",
        "why_it_matters": "Unresponsive clicks make visitors believe the website is broken or frozen.",
        "how_to_fix": "Ensure clicking this control triggers an immediate visual response or navigation.",
        "theme": "Slow or broken",
        "severity": "High",
        "severity_label": "Blocks the goal",
        "wcag": "Interaction Responsiveness",
    },
    "overlap": {
        "title": "Two clickable buttons overlap each other",
        "what_happened": "{user} attempted to click an option, but a neighboring element was blocking it.",
        "why_it_matters": "Overlapping controls cause visitors to accidentally trigger the wrong action.",
        "how_to_fix": "Add margin or padding between the two elements so their clickable areas do not collide.",
        "theme": "Can't find or reach what you want",
        "severity": "High",
        "severity_label": "Blocks the goal",
        "wcag": "Touch and Click Ergonomics",
    },
    "baseline_failed": {
        "title": "The test user could not finish the goal",
        "what_happened": "{user} could not complete the requested goal and was forced to give up.",
        "why_it_matters": "Real visitors encounter a complete dead end and abandon your site without converting.",
        "how_to_fix": "Clarify the main path forward and remove the confusing obstacle or dead end.",
        "theme": "Can't find or reach what you want",
        "severity": "High",
        "severity_label": "Blocks the goal",
        "wcag": "Task Completion",
    },
    "error": {
        "title": "A technical error stalled the page",
        "what_happened": "{user} encountered a background error that stopped the page from working properly.",
        "why_it_matters": "Background script failures prevent buttons and forms from submitting.",
        "how_to_fix": "Fix the underlying script error so actions can complete cleanly.",
        "theme": "Slow or broken",
        "severity": "High",
        "severity_label": "Blocks the goal",
        "wcag": "Runtime Stability",
    },
    "tap_target": {
        "title": "A button is too small to tap easily",
        "what_happened": "{user} struggled to tap a small control without accidentally hitting neighboring elements.",
        "why_it_matters": "A button is too small to tap easily, causing frustrating mis-taps on touchscreens.",
        "how_to_fix": "Increase the button's clickable area to at least 44 by 44 points.",
        "theme": "Can't find or reach what you want",
        "severity": "Medium",
        "severity_label": "Slows people down",
        "wcag": "WCAG 2.5.8 Target Size",
    },
    "contrast": {
        "title": "Some text is hard to read",
        "what_happened": "{user} tried to read this copy, but the font color blended into the background.",
        "why_it_matters": "The text color is too close to the background, so people with weak eyesight or in bright light can miss it.",
        "how_to_fix": "Darken the text or lighten the background to ensure strong, easy-to-read contrast.",
        "theme": "Hard to read",
        "severity": "Medium",
        "severity_label": "Slows people down",
        "wcag": "WCAG 1.4.3 Contrast (Minimum)",
    },
}


# ---------------------------------------------------------------------------
# 5. SCREENSHOT CROPPING WITH HIGHLIGHT & 400PX MINIMUM WIDTH
# ---------------------------------------------------------------------------

def crop_screenshot_with_highlight(
    base64_image: str | None,
    bbox: dict[str, Any] | None,
    padding: int = 50,
    min_width: int = 400,
) -> str | None:
    """
    Crops the screenshot around the offending element with generous padding,
    draws a 4px red outline (#ef4444), and ensures a readable crop of at least
    400px wide (upscaling or expanding if small).
    """
    if not base64_image:
        return None

    try:
        raw_b64 = base64_image
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(raw_b64)
        orig_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_w, img_h = orig_img.size

        if not bbox:
            # If no bbox, resize to at least min_width if needed and return
            if img_w < min_width:
                scale = min_width / img_w
                new_h = int(img_h * scale)
                orig_img = orig_img.resize((min_width, new_h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            orig_img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("utf-8")

        x = int(bbox.get("x", 0))
        y = int(bbox.get("y", 0))
        w = max(10, int(bbox.get("width", 20)))
        h = max(10, int(bbox.get("height", 20)))

        # Center of bounding box
        cx = x + w // 2
        cy = y + h // 2

        # Desired crop width and height
        desired_w = max(min_width, w + padding * 2)
        desired_h = max(int(desired_w * 0.55), h + padding * 2)

        # Compute crop coordinates clamped to image dimensions
        x1 = max(0, cx - desired_w // 2)
        x2 = min(img_w, x1 + desired_w)
        if x2 - x1 < desired_w and x1 > 0:
            x1 = max(0, x2 - desired_w)

        y1 = max(0, cy - desired_h // 2)
        y2 = min(img_h, y1 + desired_h)
        if y2 - y1 < desired_h and y1 > 0:
            y1 = max(0, y2 - desired_h)

        crop_w = max(10, x2 - x1)
        crop_h = max(10, y2 - y1)

        cropped = orig_img.crop((x1, y1, x2, y2))

        # Relative bounding box inside the cropped image
        rel_x1 = max(0, x - x1)
        rel_y1 = max(0, y - y1)
        rel_x2 = min(crop_w, rel_x1 + w)
        rel_y2 = min(crop_h, rel_y1 + h)

        draw = ImageDraw.Draw(cropped)
        draw.rectangle([rel_x1, rel_y1, rel_x2, rel_y2], outline="#ef4444", width=4)

        # If cropped width is still below min_width (e.g. original was narrow), upscale
        if crop_w < min_width:
            scale = min_width / crop_w
            new_h = int(crop_h * scale)
            cropped = cropped.resize((min_width, new_h), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        cropped.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"crop_screenshot_with_highlight error: {e}")
        return base64_image


# ---------------------------------------------------------------------------
# 6. TRANSLATE A SINGLE RAW FINDING INTO PLAIN-LANGUAGE SHAPE
# ---------------------------------------------------------------------------

def translate_finding(
    raw_f: dict[str, Any],
    step_shots: dict[int, str] | None = None,
    persona: str | None = None,
    client: Any = None,
    finding_id: str | None = None,
) -> dict[str, Any]:
    """
    Translates a single raw finding into the plain-language shape:
    {
      id,
      title,
      what_happened,
      why_it_matters,
      severity,
      severity_label,
      where,
      how_to_fix,
      affected_count,
      screenshot,
      screenshot_caption,
      theme,
      technical: { rule_id, selector, wcag, suggested_css_or_html, raw_evidence }
    }
    """
    # If already translated, return as is
    if raw_f.get("technical") and raw_f.get("how_to_fix") and raw_f.get("where"):
        return raw_f

    user_name = get_user_display_name(persona)
    raw_ev = raw_f.get("raw_evidence", {}) or {}
    ev_type = raw_ev.get("type", "")
    rule_id = raw_ev.get("id", "") or raw_f.get("rule_id", "")

    # Identify rule key
    matched_key = None
    if rule_id and rule_id in KNOWN_RULE_MAP:
        matched_key = rule_id
    elif ev_type and ev_type in KNOWN_RULE_MAP:
        matched_key = ev_type
    else:
        # Check title keywords
        t_low = raw_f.get("title", "").lower()
        for k in KNOWN_RULE_MAP:
            if k in t_low:
                matched_key = k
                break

    mapping = KNOWN_RULE_MAP.get(matched_key) if matched_key else None

    # Determine selector, label, and human location
    selector = raw_f.get("selector") or raw_ev.get("selector") or ""
    text_content = raw_ev.get("text") or raw_f.get("label") or raw_f.get("target") or ""
    human_where = humanize_element_location(selector, text=text_content)

    occ = raw_f.get("occurrences") or raw_ev.get("occurrences", 1) or 1
    affected_str = f"Appears {occ} times on this page" if occ > 1 else "Appears on this page"

    if mapping:
        title = mapping["title"]
        what_happened = mapping["what_happened"].format(user=user_name)
        why_it_matters = mapping["why_it_matters"]
        how_to_fix = mapping["how_to_fix"]
        theme = mapping["theme"]
        wcag = mapping.get("wcag", "")
        sev = mapping.get("severity", "Medium")
        sev_label = mapping.get("severity_label", "Slows people down")
    else:
        # Unknown rule fallback: Clean humanized title without jargon
        clean_title = raw_f.get("title", "Usability Issue")
        # Strip prefixes like "Accessibility:", "Overlapping Elements:", etc.
        clean_title = re.sub(r"^(Accessibility|Overlapping Elements|Low Contrast Text|Undersized Touch Target):\s*", "", clean_title)
        # Strip selectors and brackets
        clean_title = re.sub(r"\(.*?\)", "", clean_title).strip()
        if not clean_title or len(clean_title) < 5:
            clean_title = "Unclear layout element"

        title = f"{clean_title[:45]}"
        what_happened = f"{user_name} encountered an issue with {human_where.lower()}."
        why_it_matters = "This creates unnecessary friction and slows down visitors."
        how_to_fix = "Review this section to ensure it is clear, accessible, and responsive."
        theme = "Works for everyone (accessibility)"
        wcag = "General Accessibility"
        sev = "Medium"
        sev_label = "Slows people down"

        # One short LLM call fallback for unknown rules if client provided
        if client is not None:
            try:
                llm_prompt = f"""Rewrite this automated usability finding into plain language for a non-technical founder.
Rules:
- 5-9 words title, absolutely no jargon, no code, no selectors.
- what_happened: 1-2 sentences from user's perspective ({user_name}).
- why_it_matters: 1 sentence on business or user impact.
- how_to_fix: 1-2 plain sentences, no code.
- theme: choose one from: "Can't find or reach what you want", "Confusing wording", "Hard to read", "Forms and errors", "Interruptions (popups)", "Works for everyone (accessibility)", "Slow or broken".

Raw finding:
Title: {raw_f.get('title')}
Help text: {raw_ev.get('help')}
Description: {raw_f.get('what_happened')}
Location: {human_where}

Respond ONLY with valid JSON matching:
{{
  "title": "5-9 words title without jargon",
  "what_happened": "1-2 sentences from user's perspective",
  "why_it_matters": "1 sentence on impact",
  "how_to_fix": "1-2 plain sentences without code",
  "theme": "Works for everyone (accessibility)"
}}
"""
                if hasattr(client, "sync_chat_completion"):
                    resp = client.sync_chat_completion(
                        messages=[{"role": "user", "content": llm_prompt}],
                        model_type="text",
                        temperature=0.2,
                        max_tokens=300,
                        response_format={"type": "json_object"},
                    )
                    data = json.loads(resp.choices[0].message.content)
                elif hasattr(client, "chat") and hasattr(client.chat, "completions"):
                    resp = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        temperature=0.2,
                        max_tokens=300,
                        response_format={"type": "json_object"},
                        messages=[{"role": "user", "content": llm_prompt}],
                    )
                    data = json.loads(resp.choices[0].message.content)
                else:
                    data = {}

                if data.get("title") and data.get("what_happened"):
                    title = data["title"]
                    what_happened = data["what_happened"]
                    why_it_matters = data.get("why_it_matters", why_it_matters)
                    how_to_fix = data.get("how_to_fix", how_to_fix)
                    theme = data.get("theme", theme)
            except Exception as e:
                print(f"Unknown rule LLM rewrite fallback error: {e}")

    # Severity normalization to "High" | "Medium" | "Low"
    raw_sev = str(raw_f.get("severity", sev)).lower()
    if raw_sev in ("critical", "high"):
        severity = "High"
        severity_label = "Blocks the goal"
    elif raw_sev == "medium":
        severity = "Medium"
        severity_label = "Slows people down"
    else:
        severity = "Low"
        severity_label = "Minor polish"

    # Determine step number and cropped screenshot
    step_n = raw_f.get("step_number") or (raw_f.get("evidence_steps", [1])[0] if raw_f.get("evidence_steps") else 1)
    base_shot = raw_f.get("screenshot")
    if not base_shot and step_shots and step_n in step_shots:
        base_shot = step_shots[step_n]

    bbox = raw_f.get("bounding_box")
    cropped_shot = crop_screenshot_with_highlight(base_shot, bbox)
    caption = f"Step {step_n}: {human_where}"

    # Suggested code fix exclusively for the technical section
    raw_code_fix = raw_f.get("suggested_fix") or raw_f.get("recommendation", "")
    # If the raw code fix is just generic outline or empty, keep it clean
    if "outline-offset" in raw_code_fix and "transition" in raw_code_fix and ev_type not in ("tap_target", "contrast"):
        raw_code_fix = ""

    fid = finding_id or f"finding-{raw_f.get('step_number', 1)}-{rule_id or 'ux'}"

    # Target shape
    translated = {
        "id": fid,
        "title": title,
        "what_happened": what_happened,
        "why_it_matters": why_it_matters,
        "severity": severity,
        "severity_label": severity_label,
        "where": human_where,
        "how_to_fix": how_to_fix,
        "affected_count": affected_str,
        "screenshot": cropped_shot,
        "screenshot_caption": caption,
        "theme": theme,
        # Developer-only technical section (hidden by default)
        "technical": {
            "rule_id": rule_id or ev_type or "general-ux",
            "selector": selector,
            "wcag": wcag,
            "suggested_css_or_html": raw_code_fix,
            "raw_evidence": raw_ev,
        },
        # Backward compatibility fields for existing tests and components
        "step_number": step_n,
        "evidence_steps": raw_f.get("evidence_steps", [step_n]),
        "bounding_box": bbox,
        "suggested_fix": how_to_fix,
        "recommendation": how_to_fix,
        "impact": why_it_matters,
        "occurrences": occ,
    }

    return translated


# ---------------------------------------------------------------------------
# 7. GROUPING, SORTING, AND DEDUPLICATION BY PROBLEM
# ---------------------------------------------------------------------------

def group_and_translate_findings(
    raw_findings: list[dict[str, Any]],
    steps: list[Any] | None = None,
    persona: str | None = None,
    client: Any = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Groups raw findings by problem (not by element), translates to plain language,
    sorts by impact, and caps the main view at top 5-8 findings.
    Returns:
      (top_findings, minor_findings)
    """
    if not raw_findings:
        return [], []

    step_shots: dict[int, str] = {}
    if steps:
        for i, s in enumerate(steps):
            n = getattr(s, "n", i + 1) if not isinstance(s, dict) else s.get("n", i + 1)
            shot = getattr(s, "screenshot", None) if not isinstance(s, dict) else s.get("screenshot")
            if shot:
                step_shots[n] = shot

    # Group by problem signature: (theme, rule_id or type, normalized location)
    groups: dict[str, dict[str, Any]] = {}

    for f in raw_findings:
        raw_ev = f.get("raw_evidence", {}) or {}
        rule_id = raw_ev.get("id") or raw_ev.get("type") or f.get("rule_id", "issue")
        selector = f.get("selector") or raw_ev.get("selector") or ""
        human_where = humanize_element_location(selector, text=f.get("label") or raw_ev.get("text"))

        group_key = f"{rule_id}:{human_where}"

        if group_key in groups:
            existing = groups[group_key]
            existing["occurrences"] = existing.get("occurrences", 1) + (f.get("occurrences", 1) or 1)
            # Merge evidence steps
            for st in f.get("evidence_steps", []):
                if st not in existing["evidence_steps"]:
                    existing["evidence_steps"].append(st)
            # Union bounding boxes
            if f.get("bounding_box") and not existing.get("bounding_box"):
                existing["bounding_box"] = f.get("bounding_box")
        else:
            copied = dict(f)
            copied["occurrences"] = f.get("occurrences", 1) or 1
            copied["evidence_steps"] = list(f.get("evidence_steps", []))
            groups[group_key] = copied

    # Translate each consolidated problem group
    translated_list: list[dict[str, Any]] = []
    for idx, g in enumerate(groups.values(), 1):
        tr = translate_finding(
            g,
            step_shots=step_shots,
            persona=persona,
            client=client,
            finding_id=f"problem-{idx}",
        )
        translated_list.append(tr)

    # Sort by impact:
    # 1. Blockers / task failure first
    # 2. Findings on user's active path (matching evidence steps)
    # 3. Severity (High -> Medium -> Low)
    sev_weights = {"High": 3, "Medium": 2, "Low": 1}

    def impact_score(item: dict[str, Any]) -> tuple[int, int, int]:
        is_task_blocker = 1 if (item["severity_label"] == "Blocks the goal" or item["technical"]["rule_id"] == "baseline_failed") else 0
        has_user_steps = 1 if len(item.get("evidence_steps", [])) > 0 else 0
        sev = sev_weights.get(item["severity"], 1)
        return (is_task_blocker, has_user_steps, sev)

    translated_list.sort(key=impact_score, reverse=True)

    # Cap main view at top 5 to 8 findings; remainder go to minor issues
    main_cap = 6 if len(translated_list) <= 8 else 5
    top_findings = translated_list[:main_cap]
    minor_findings = translated_list[main_cap:]

    return top_findings, minor_findings


# ---------------------------------------------------------------------------
# 8. MASTER TRANSLATOR FOR COMPLETE REPORT
# ---------------------------------------------------------------------------

def translate_full_report(report: dict[str, Any], steps: list[Any] | None = None) -> dict[str, Any]:
    """
    Transforms the entire report into the plain-language structure:
    - Translates findings into the new shape with top_findings & minor_findings.
    - Humanizes score breakdown items.
    - Plain-language verdict and baseline failure message.
    - Preserves all underlying score numbers and calculations unchanged.
    """
    if not report:
        return report

    # 1. Findings translation & grouping
    raw_findings = report.get("findings", [])
    persona = report.get("persona", "")
    top_findings, minor_findings = group_and_translate_findings(
        raw_findings,
        steps=steps or report.get("actions", []),
        persona=persona,
    )

    all_plain_findings = top_findings + minor_findings
    report["findings"] = all_plain_findings
    report["top_findings"] = top_findings
    report["minor_findings"] = minor_findings

    # 2. Humanize Score Breakdown Parts
    score_obj = report.get("score")
    if isinstance(score_obj, dict):
        raw_parts = score_obj.get("parts") or score_obj.get("breakdown") or []
        human_parts = [humanize_penalty_part(p) for p in raw_parts]
        score_obj["parts"] = human_parts
        if "breakdown" in score_obj:
            score_obj["breakdown"] = human_parts

        # Human label for verdict card
        score_val = score_obj.get("total") or score_obj.get("score") or 0
        lbl = score_obj.get("label", "Moderate")
        if score_val >= 70:
            score_plain_label = f"{score_val}/100: Severe. A real visitor would likely give up"
        elif score_val >= 40:
            score_plain_label = f"{score_val}/100: Moderate. Visitors experience noticeable hesitation"
        elif score_val >= 15:
            score_plain_label = f"{score_val}/100: Minor friction. Usable with small speedbumps"
        else:
            score_plain_label = f"{score_val}/100: Smooth. Visitors easily reach their goal"
        score_obj["plain_label"] = score_plain_label

    # 3. Humanize Baseline Failure / Blocker Card
    if report.get("baseline_failed"):
        user_name = get_user_display_name(persona)
        note = report.get("baseline_note", "")
        blocker_desc = f" The path may be unclear or blocked ({note})." if note else ""
        report["plain_baseline_message"] = (
            f"The test user could not complete the goal. Here is where they got stuck and what was in their way.{blocker_desc}"
        )

    return report
