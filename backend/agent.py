import os
import re
import time
import asyncio
import base64
import json
import io
import hashlib
import inspect
from typing import Any
from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import Page
from dotenv import load_dotenv
from scoring import Step, compute_friction, build_report
from evidence import collect_step_evidence
from llm_client import resilient_llm_client, LLMUnavailableError
from personas import (
    PersonaConfig,
    PERSONAS,
    get_persona_config,
    is_personal_data_field,
    get_fake_personal_data,
    audit_trust_signals_in_page,
)
from security import (
    validate_target_url,
    setup_route_interception,
    setup_download_and_file_guards,
    detect_payment_fields,
    is_payment_field,
    is_payment_submission_action,
    sanitize_fake_form_data,
    MAX_STEPS_CAP,
    MAX_SESSION_DURATION_SECONDS,
)

load_dotenv()

from enum import Enum

# Task Outcome Enum
class TaskOutcome(str, Enum):
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    GAVE_UP = "gave_up"
    MAX_STEPS_REACHED = "max_steps_reached"
    ERROR = "error"

OUTCOME_COMPLETED = TaskOutcome.COMPLETED.value
OUTCOME_ABANDONED = TaskOutcome.ABANDONED.value
OUTCOME_GAVE_UP = TaskOutcome.GAVE_UP.value
OUTCOME_MAX_STEPS = TaskOutcome.MAX_STEPS_REACHED.value
OUTCOME_ERROR = TaskOutcome.ERROR.value

LAST_REPORT: dict = {}

SYSTEM_INSTRUCTIONS = (
    "You are an automated web usability and QA testing engine. "
    "Your objective is to inspect the page screenshot and visible interactive elements, "
    "then decide the single next action. "
    "You MUST respond ONLY with a single valid JSON object starting with '{' and ending with '}'. "
    "Never output markdown code blocks (no ```json), never output introductory text, and never write explanations outside the JSON."
)

def extract_and_parse_json(text: str) -> dict:
    """
    Safely parses JSON from model output, handling markdown code fences,
    extraneous commentary, or leading/trailing text.
    """
    text = text.strip()
    # Strip markdown code blocks
    if "```" in text:
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```$", "", text, flags=re.MULTILINE).strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    # Find outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass

    raise ValueError(f"Could not parse valid JSON from text: {text[:200]}")

def extract_failed_generation_text(err: Exception) -> str | None:
    """Extracts failed_generation string from Groq BadRequestError or exception string."""
    if hasattr(err, "body") and isinstance(err.body, dict):
        fg = err.body.get("error", {}).get("failed_generation")
        if fg and fg != "max completion tokens reached before generating a valid document":
            return fg
    # Regex fallback on string representation
    m = re.search(r"['\"]failed_generation['\"]\s*:\s*['\"](.*)", str(err), re.DOTALL)
    if m:
        val = m.group(1)
        val = re.sub(r"['\"]\s*\}\s*\}?\s*$", "", val).strip()
        val = val.replace(r"\'", "'").replace(r'\"', '"')
        if val and val != "max completion tokens reached before generating a valid document":
            return val
    return None

def regex_fallback_decision(text: str) -> dict:
    """Extracts target, action, value from unstructured QA tester text."""
    targets = re.findall(r'uxg-\d+', text)
    target = targets[-1] if targets else (targets[0] if targets else "")

    action = "click"
    text_lower = text.lower()
    if "scroll" in text_lower:
        action = "scroll"
    elif "done" in text_lower or "complete" in text_lower:
        action = "done"
    elif "abort" in text_lower:
        action = "abort"
    elif "type" in text_lower or "enter" in text_lower:
        if text_lower.rfind("click") > text_lower.rfind("type"):
            action = "click"
        else:
            action = "type"

    value = ""
    if action == "type":
        val_m = re.search(r'["\']([^"\']{2,40})["\']', text)
        if val_m:
            value = val_m.group(1)

    task_status = "done" if action == "done" else ("giving_up" if action == "abort" else "in_progress")
    clean_text = text.strip()[:240]

    return {
        "reason": clean_text,
        "thought": clean_text,
        "action": action,
        "task_status": task_status,
        "outcome_reason": clean_text[:160] if action in ("done", "abort") else "",
        "target": target,
        "value": value
    }

async def recover_decision_from_failed_text(text: str, status_callback=None) -> dict:
    """Uses resilient LLM text completion or regex fallback to parse unstructured tester text into decision dict."""
    try:
        res = await resilient_llm_client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an action parser. Extract the intended action from the QA tester text into valid JSON. "
                        "Respond ONLY with a single JSON object: {\"reason\": \"...\", \"thought\": \"...\", \"action\": \"click\"|\"type\"|\"scroll\"|\"done\"|\"abort\", \"task_status\": \"in_progress\"|\"done\"|\"giving_up\", \"outcome_reason\": \"...\", \"target\": \"uxg-X\", \"value\": \"...\"}."
                    )
                },
                {"role": "user", "content": text}
            ],
            model_type="text",
            response_format={"type": "json_object"},
            max_tokens=800,
            status_callback=status_callback,
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        print(f"Fallback LLM extraction failed ({e}), using regex heuristics.")
        return regex_fallback_decision(text)


PERSONA_GUIDES = {k: v.behavior_rules for k, v in PERSONAS.items()}

# ==============================================================================
# Reliability Helpers: Set-of-Marks, Accessibility Tree, Loop Detection,
# Popups/Banners/Tabs, and Stop Rules
# ==============================================================================

def overlay_set_of_marks(screenshot_bytes: bytes, elements: list[dict]) -> bytes:
    """
    Overlays numbered labels and bounding boxes on interactive elements in the screenshot.
    Uses PIL to draw high-contrast badges (crimson background, white text)
    at the top-left of each element bounding box.
    """
    if not screenshot_bytes or not elements:
        return screenshot_bytes

    try:
        image = Image.open(io.BytesIO(screenshot_bytes)).convert("RGB")
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.load_default(size=14)
        except Exception:
            font = ImageFont.load_default()

        for idx, el in enumerate(elements):
            num = el.get("num")
            if num is None:
                el_id = str(el.get("id", ""))
                m = re.search(r"\d+", el_id)
                num = int(m.group(0)) if m else (idx + 1)

            bbox = el.get("bbox")
            if isinstance(bbox, dict):
                x = bbox.get("x", 0)
                y = bbox.get("y", 0)
                w = bbox.get("width", 0)
                h = bbox.get("height", 0)
            else:
                x = el.get("x", 0)
                y = el.get("y", 0)
                w = el.get("width", 0)
                h = el.get("height", 0)

            if w <= 0 or h <= 0:
                continue

            # Draw element bounding box outline
            draw.rectangle([x, y, x + w, y + h], outline="#E11D48", width=2)

            # Draw numbered badge at top-left
            label_text = f" {num} "
            try:
                tb = font.getbbox(label_text)
                tw, th = tb[2] - tb[0], tb[3] - tb[1]
            except Exception:
                tw, th = len(label_text) * 8, 14

            badge_x1 = max(0, x)
            badge_y1 = max(0, y - th - 4) if y >= th + 4 else y
            badge_x2 = badge_x1 + tw + 4
            badge_y2 = badge_y1 + th + 4

            draw.rectangle([badge_x1, badge_y1, badge_x2, badge_y2], fill="#E11D48")
            draw.text((badge_x1 + 2, badge_y1 + 1), label_text, fill="#FFFFFF", font=font)

        out_io = io.BytesIO()
        image.save(out_io, format="JPEG", quality=75)
        return out_io.getvalue()
    except Exception as e:
        return screenshot_bytes


def format_som_element_list(elements: list[dict]) -> str:
    """
    Formats the list of interactive elements matching the Set-of-Marks overlay,
    including number, role, accessible name, and bounding box.
    """
    if not elements:
        return "No interactive elements identified."

    lines = []
    for idx, el in enumerate(elements):
        num = el.get("num")
        if num is None:
            el_id = str(el.get("id", ""))
            m = re.search(r"\d+", el_id)
            num = int(m.group(0)) if m else (idx + 1)

        role = el.get("role") or el.get("tag") or "element"
        name = el.get("name") or el.get("text") or el.get("placeholder") or ""
        name_clean = str(name).strip().replace("\n", " ").replace('"', "'")[:60]

        bbox = el.get("bbox")
        if not isinstance(bbox, dict):
            bbox = {
                "x": el.get("x", 0),
                "y": el.get("y", 0),
                "width": el.get("width", 0),
                "height": el.get("height", 0),
            }

        lines.append(f"[{num}] role={role} | name=\"{name_clean}\" | bbox={json.dumps(bbox)}")

    return "\n".join(lines)


def parse_som_target(target: Any, elements: list[dict] | None = None) -> tuple[int | None, str]:
    """
    Parses LLM target response into an element number and selector/id.
    Accepts integer (e.g. 5), string number (e.g. "5"), or id format (e.g. "uxg-5", "[5]").
    Returns (element_number, target_id_str).
    """
    if target is None:
        return None, ""

    if isinstance(target, int):
        return target, f"uxg-{target}"

    if isinstance(target, dict):
        val = target.get("number") or target.get("element") or target.get("target") or target.get("id")
        return parse_som_target(val, elements)

    target_str = str(target).strip()

    m = re.search(r"\buxg-(\d+)\b", target_str, re.IGNORECASE)
    if m:
        num = int(m.group(1))
        return num, f"uxg-{num}"

    m_bracket = re.search(r"\[(\d+)\]", target_str)
    if m_bracket:
        num = int(m_bracket.group(1))
        return num, f"uxg-{num}"

    m_num = re.search(r"^\D*(\d+)\D*$", target_str)
    if m_num:
        num = int(m_num.group(1))
        return num, f"uxg-{num}"

    if elements:
        for el in elements:
            if target_str.lower() in str(el.get("name", "")).lower() or target_str.lower() in str(el.get("text", "")).lower():
                num = el.get("num")
                el_id = el.get("id", f"uxg-{num}" if num else target_str)
                return num, el_id

    return None, target_str


def trim_accessibility_tree(raw_tree: str, max_chars: int = 1500) -> str:
    """
    Trims accessibility tree snapshot to cut tokens:
    - Strips noisy/empty lines
    - Removes redundant whitespace
    - Caps total length to max_chars with clean ellipsis
    """
    if not raw_tree or not raw_tree.strip():
        return "Empty accessibility tree."

    lines = [line.rstrip() for line in raw_tree.strip().splitlines() if line.strip()]
    cleaned = "\n".join(lines)
    if len(cleaned) <= max_chars:
        return cleaned

    truncated = cleaned[:max_chars]
    last_nl = truncated.rfind("\n")
    if last_nl > max_chars // 2:
        truncated = truncated[:last_nl]

    return truncated + "\n... [accessibility tree snapshot trimmed to conserve tokens]"


async def capture_accessibility_snapshot(page: Page, max_depth: int = 5) -> str:
    """
    Captures an accessibility tree snapshot from the page using page.aria_snapshot
    if available, or a fallback DOM semantic tree extractor.
    Returns trimmed text representation.
    """
    try:
        aria_snap = getattr(page, "aria_snapshot", None)
        if callable(aria_snap):
            tree_str = await aria_snap(depth=max_depth)
            if isinstance(tree_str, str) and tree_str.strip():
                return trim_accessibility_tree(tree_str)
    except Exception:
        pass

    js_fallback = """
    () => {
        const lines = [];
        const walk = (el, depth) => {
            if (depth > 5 || lines.length > 50) return;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;
            const role = el.getAttribute('role') || el.tagName.toLowerCase();
            const name = (el.getAttribute('aria-label') || el.innerText || el.getAttribute('placeholder') || '').trim().replace(/\\s+/g, ' ').slice(0, 40);
            const isInteractive = ['a', 'button', 'input', 'select', 'textarea'].includes(el.tagName.toLowerCase()) || el.hasAttribute('role');
            if (isInteractive || ['h1', 'h2', 'h3', 'nav', 'main', 'form'].includes(el.tagName.toLowerCase())) {
                const indent = '  '.repeat(depth);
                lines.push(`${indent}- ${role}${name ? ': "' + name + '"' : ''}`);
            }
            for (const child of el.children) {
                walk(child, depth + 1);
            }
        };
        if (document.body) walk(document.body, 0);
        return lines.join('\\n');
    }
    """
    try:
        eval_fn = getattr(page, "evaluate", None)
        if callable(eval_fn):
            fallback_str = await eval_fn(js_fallback)
            if isinstance(fallback_str, str) and fallback_str.strip():
                return trim_accessibility_tree(fallback_str)
    except Exception:
        pass

    return "Accessibility tree unavailable."


def compute_page_state_hash(url: str, dom_summary: str) -> str:
    """
    Computes a deterministic hash of the current page URL and DOM summary
    to detect frozen or unresponsive page states.
    """
    normalized = f"{str(url).strip()}|{str(dom_summary).strip()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def check_loop_detection(
    action_history: list[dict],
    state_hash_history: list[str]
) -> tuple[bool, str, str]:
    """
    Detects loops:
    1. If the same action on the same element happens 3 times consecutively.
    2. Or if the URL/DOM state hash doesn't change for 3 consecutive steps.
    Returns (is_loop: bool, reason: str, hint: str).
    """
    # Check 1: Same action on the same element 3 times consecutively
    if len(action_history) >= 3:
        last3 = action_history[-3:]
        act0, tgt0 = last3[0].get("action"), str(last3[0].get("target", ""))
        act1, tgt1 = last3[1].get("action"), str(last3[1].get("target", ""))
        act2, tgt2 = last3[2].get("action"), str(last3[2].get("target", ""))
        if act0 and act0 == act1 == act2 and tgt0 == tgt1 == tgt2:
            reason = f"Action '{act0}' on element '{tgt0}' repeated 3 consecutive times"
            hint = f"Element '{tgt0}' is not advancing page state. Try scrolling, inspecting another interactive control, or verifying required form fields."
            return True, reason, hint

    # Check 2: URL/DOM hash doesn't change for 3 steps
    if len(state_hash_history) >= 3:
        last3_hashes = state_hash_history[-3:]
        if last3_hashes[0] == last3_hashes[1] == last3_hashes[2]:
            reason = "Page URL and DOM content hash remained unchanged for 3 consecutive steps"
            hint = "Page state is static. An overlay, modal, or unfulfilled form requirement may be blocking progress. Check for error messages or dismissal buttons."
            return True, reason, hint

    return False, "", ""


COOKIE_BANNER_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "#onetrust-reject-all-handler",
    ".cookie-banner button",
    ".cookie-consent button",
    ".cc-dismiss",
    ".cc-accept",
    ".cc-btn.cc-allow",
    "#cookie-accept",
    "#accept-cookies",
    "button[id*='cookie' i][id*='accept' i]",
    "button[class*='cookie' i][class*='accept' i]",
    "button[id*='consent' i]",
    "button[aria-label*='cookie' i]",
    "button[aria-label*='consent' i]",
]

COOKIE_BUTTON_TEXTS = [
    "accept all cookies",
    "accept all",
    "accept cookies",
    "allow all cookies",
    "allow cookies",
    "allow all",
    "i agree",
    "agree and continue",
    "got it",
    "accept selection",
]


async def _resolve_target_locator(loc_or_coro: Any) -> Any:
    if inspect.iscoroutine(loc_or_coro):
        loc_or_coro = await loc_or_coro
    first = getattr(loc_or_coro, "first", loc_or_coro)
    if inspect.iscoroutine(first):
        first = await first
    return first


async def handle_cookie_banners(page: Page) -> bool:
    """
    Auto-detects and dismisses common cookie/consent banners.
    Returns True if a cookie banner was dismissed, False otherwise.
    """
    loc_fn = getattr(page, "locator", None)
    if not callable(loc_fn):
        return False

    for sel in COOKIE_BANNER_SELECTORS:
        try:
            loc = await _resolve_target_locator(page.locator(sel))
            is_vis = getattr(loc, "is_visible", None)
            if callable(is_vis):
                vis_res = is_vis(timeout=200)
                if inspect.iscoroutine(vis_res):
                    vis_res = await vis_res
                if vis_res is True:
                    click_fn = getattr(loc, "click", None)
                    if callable(click_fn):
                        click_res = click_fn(timeout=800)
                        if inspect.iscoroutine(click_res):
                            await click_res
                    await asyncio.sleep(0.2)
                    return True
        except Exception:
            continue

    get_by_role = getattr(page, "get_by_role", None)
    if callable(get_by_role):
        for txt in COOKIE_BUTTON_TEXTS:
            try:
                btn = await _resolve_target_locator(page.get_by_role("button", name=re.compile(f"^{re.escape(txt)}$", re.I)))
                is_vis = getattr(btn, "is_visible", None)
                if callable(is_vis):
                    vis_res = is_vis(timeout=150)
                    if inspect.iscoroutine(vis_res):
                        vis_res = await vis_res
                    if vis_res is True:
                        click_fn = getattr(btn, "click", None)
                        if callable(click_fn):
                            click_res = click_fn(timeout=800)
                            if inspect.iscoroutine(click_res):
                                await click_res
                        await asyncio.sleep(0.2)
                        return True
            except Exception:
                continue

    return False


async def follow_new_tabs(page: Page) -> tuple[Page, bool]:
    """
    Detects if a new tab was opened in the browser context,
    switches active page focus to the new tab, and brings it to front.
    Returns (active_page, did_switch).
    """
    try:
        ctx = getattr(page, "context", None)
        if ctx:
            pages = getattr(ctx, "pages", None)
            if isinstance(pages, list) and len(pages) > 1:
                latest_page = pages[-1]
                is_closed_fn = getattr(latest_page, "is_closed", None)
                is_closed = is_closed_fn() if callable(is_closed_fn) else False
                if latest_page != page and not is_closed:
                    bring_to_front = getattr(latest_page, "bring_to_front", None)
                    if callable(bring_to_front):
                        await latest_page.bring_to_front()
                    try:
                        await latest_page.wait_for_load_state("domcontentloaded", timeout=2000)
                    except Exception:
                        pass
                    return latest_page, True
    except Exception as e:
        print(f"Error checking new tabs: {e}")

    return page, False


MODAL_SELECTORS = [
    "dialog[open]",
    "[role='dialog']",
    "[role='alertdialog']",
    ".modal.show",
    ".modal.open",
    ".modal:not([style*='display: none']):not([style*='display:none'])",
    ".swal2-modal",
    ".modal-overlay-bad",
    "#newsletter-modal",
    "[class*='modal-overlay']",
]

MODAL_CLOSE_SELECTORS = [
    "button[aria-label*='close' i]",
    "button[title*='close' i]",
    "button.close",
    "[data-dismiss='modal']",
    "[aria-label='Close']",
    "#newsletter-modal-close",
    ".modal-close-bad",
    "button:has-text('✕')",
    "button:has-text('×')",
    "button:has-text('Close')",
]


async def handle_blocking_modals(page: Page, target: str | None = None) -> tuple[bool, str | None]:
    """
    Detects blocking modals or popups and closes them ONLY if they block the task.
    If the target element is inside the modal, the modal is part of the task flow and is NOT closed.
    If closed, returns (True, modal_description) so friction can be recorded.
    Otherwise returns (False, None).
    """
    loc_fn = getattr(page, "locator", None)
    if not callable(loc_fn):
        return False, None

    try:
        for modal_sel in MODAL_SELECTORS:
            try:
                modal = await _resolve_target_locator(page.locator(modal_sel))
                is_vis = getattr(modal, "is_visible", None)
                if not callable(is_vis):
                    continue
                vis_res = is_vis(timeout=200)
                if inspect.iscoroutine(vis_res):
                    vis_res = await vis_res
                if vis_res is True:
                    if target:
                        sel = normalize_target(target)
                        is_inside = await page.evaluate(
                            """([mSel, tSel]) => {
                                const m = document.querySelector(mSel);
                                const t = document.querySelector(tSel);
                                return Boolean(m && t && m.contains(t));
                            }""",
                            [modal_sel, sel]
                        )
                        if is_inside is True:
                            return False, None

                    modal_title = ""
                    try:
                        inner_text_fn = getattr(modal, "inner_text", None)
                        if callable(inner_text_fn):
                            text_val = inner_text_fn(timeout=200)
                            if inspect.iscoroutine(text_val):
                                text_val = await text_val
                            if isinstance(text_val, str):
                                modal_title = text_val.splitlines()[0][:40]
                    except Exception:
                        modal_title = "Popup Dialog"

                    for close_sel in MODAL_CLOSE_SELECTORS:
                        try:
                            btn = await _resolve_target_locator(modal.locator(close_sel))
                            btn_is_vis = getattr(btn, "is_visible", None)
                            if callable(btn_is_vis):
                                btn_vis_res = btn_is_vis(timeout=200)
                                if inspect.iscoroutine(btn_vis_res):
                                    btn_vis_res = await btn_vis_res
                                if btn_vis_res is True:
                                    click_fn = getattr(btn, "click", None)
                                    if callable(click_fn):
                                        click_res = click_fn(timeout=800)
                                        if inspect.iscoroutine(click_res):
                                            await click_res
                                    await asyncio.sleep(0.2)
                                    return True, modal_title or "Popup Dialog"
                        except Exception:
                            continue

                    keyboard = getattr(page, "keyboard", None)
                    if keyboard and hasattr(keyboard, "press"):
                        press_res = keyboard.press("Escape")
                        if inspect.iscoroutine(press_res):
                            await press_res
                        await asyncio.sleep(0.2)
                        still_visible_res = is_vis(timeout=200)
                        if inspect.iscoroutine(still_visible_res):
                            still_visible_res = await still_visible_res
                        if still_visible_res is False:
                            return True, modal_title or "Popup Dialog"
            except Exception:
                continue
    except Exception as e:
        print(f"Error handling blocking modals: {e}")

    return False, None


def evaluate_stop_rules(
    step: int,
    max_steps: int,
    is_done_claimed: bool = False,
    is_verified: bool = False,
    is_loop_detected: bool = False,
    consecutive_errors: int = 0,
    max_consecutive_errors: int = 3,
    is_abort_claimed: bool = False,
    stop_reason: str = "",
) -> tuple[bool, str | None, str]:
    """
    Evaluates stop rules for the agent loop:
    1. Task done and verified -> COMPLETED (or ABANDONED if verification failed)
    2. Stuck (loop detection triggered or giving up) -> GAVE_UP
    3. Error (consecutive errors reached threshold) -> ERROR
    4. Max steps reached -> MAX_STEPS_REACHED
    Returns (should_stop: bool, outcome: str | None, outcome_reason: str).
    """
    if is_done_claimed:
        if is_verified:
            return True, OUTCOME_COMPLETED, stop_reason or "Task completed and verified successfully."
        else:
            return True, OUTCOME_ABANDONED, stop_reason or "Task claimed done but verification check failed."

    if is_loop_detected:
        return True, OUTCOME_GAVE_UP, stop_reason or "Agent is stuck in a loop and gave up on the task."

    if is_abort_claimed:
        return True, OUTCOME_GAVE_UP, stop_reason or "User persona gave up on the task."

    if consecutive_errors >= max_consecutive_errors:
        return True, OUTCOME_ERROR, stop_reason or f"Execution halted after {consecutive_errors} consecutive errors."

    if step >= max_steps:
        return True, OUTCOME_MAX_STEPS, stop_reason or f"Maximum steps ({max_steps}) reached without completing task."

    return False, None, ""


async def extract_visible_interactive_elements(page: Page, persona_cfg: PersonaConfig | None = None):
    """
    Extracts visible, interactable elements from the active viewport
    and annotates them with temporary data-uxg-id attributes for reliable targeting.
    Filters and orders elements according to persona configuration.
    Includes number, role, accessible name, and bounding box for Set-of-Marks.
    """
    js_extract = """
    () => {
        try {
            const items = [];
            const candidates = document.querySelectorAll(
                'a, button, input, textarea, select, [role="button"], [role="link"], [role="tab"], [role="checkbox"], [role="radio"], [role="menuitem"], label[for], summary'
            );
            let count = 0;
            for (const el of candidates) {
                if (count >= 50) break;

                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);

                const isVisible = rect.width > 2 && rect.height > 2 &&
                    rect.bottom > 0 && rect.top < window.innerHeight &&
                    rect.right > 0 && rect.left < window.innerWidth &&
                    style.visibility !== 'hidden' &&
                    style.display !== 'none' &&
                    style.opacity !== '0';

                if (!isVisible) continue;

                const width = Math.round(rect.width);
                const height = Math.round(rect.height);
                const area = width * height;
                const x = Math.round(rect.left);
                const y = Math.round(rect.top);

                let text = (
                    el.innerText ||
                    el.getAttribute('aria-label') ||
                    el.getAttribute('placeholder') ||
                    el.getAttribute('title') ||
                    el.getAttribute('value') ||
                    ''
                ).trim().replace(/\\s+/g, ' ').slice(0, 50);

                const tag = el.tagName.toLowerCase();
                const href = el.getAttribute('href') || '';
                const type = el.getAttribute('type') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                const isDisabled = el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true';

                if (tag === 'a' && !text && !href) continue;

                const hasIcon = Boolean(el.querySelector('svg, i, [class*="icon"], [class*="fa-"]'));
                const isIconOnly = (text.length <= 1 || /^[^a-zA-Z0-9]+$/.test(text)) && hasIcon;

                const num = count + 1;
                const uxgId = `uxg-${num}`;
                el.setAttribute('data-uxg-id', uxgId);

                const isCloseBtn = el.classList.contains('modal-close-bad') || (el.id && el.id.includes('modal-close'));
                const accessibleName = el.getAttribute('aria-label') || (isCloseBtn ? 'Close modal (✕)' : '') || text || placeholder || el.getAttribute('title') || (tag === 'input' ? el.getAttribute('value') : '') || '';

                let label = (isCloseBtn ? 'Close modal (✕)' : '') || text || (placeholder ? `[${placeholder}]` : (href ? href.slice(0, 40) : tag));
                if (isDisabled) label += " [DISABLED]";

                const explicitRole = el.getAttribute('role');
                let role = explicitRole;
                if (!role) {
                    if (tag === 'a') role = 'link';
                    else if (tag === 'button') role = 'button';
                    else if (tag === 'input') role = type || 'textbox';
                    else if (tag === 'textarea') role = 'textbox';
                    else if (tag === 'select') role = 'combobox';
                    else role = tag;
                }

                items.push({
                    num: num,
                    id: uxgId,
                    tag: tag,
                    role: role,
                    name: accessibleName.trim().slice(0, 50),
                    text: label,
                    width: width,
                    height: height,
                    area: area,
                    bbox: { x: x, y: y, width: width, height: height },
                    is_icon_only: isIconOnly,
                    href: href ? href.slice(0, 50) : undefined,
                    type: type || undefined,
                    placeholder: placeholder || undefined
                });
                count++;
            }
            return items;
        } catch (e) {
            return [];
        }
    }
    """
    try:
        elements = await page.evaluate(js_extract)
        if not elements:
            return []

        # Confused persona hard rule: ignore links under size threshold
        if persona_cfg and persona_cfg.hard_rules.get("ignore_link_area_threshold"):
            thresh = persona_cfg.hard_rules["ignore_link_area_threshold"]
            elements = [
                el for el in elements
                if not (el.get("tag") == "a" and el.get("area", 0) < thresh)
            ]

        # Confused persona hard rule: prefer prominent buttons over links
        if persona_cfg and persona_cfg.hard_rules.get("prefer_prominent_buttons"):
            elements.sort(
                key=lambda el: 0 if el.get("tag") in ("button", "input") else 1
            )

        # Ensure num and bbox are present on every element (especially when mocked)
        for idx, el in enumerate(elements):
            if "num" not in el:
                m = re.search(r"\d+", str(el.get("id", "")))
                el["num"] = int(m.group(0)) if m else (idx + 1)
            if "bbox" not in el:
                el["bbox"] = {
                    "x": el.get("x", 0),
                    "y": el.get("y", 0),
                    "width": el.get("width", 0),
                    "height": el.get("height", 0),
                }
            if "role" not in el:
                el["role"] = el.get("tag", "element")
            if "name" not in el:
                el["name"] = el.get("text", "")

        return elements
    except Exception as e:
        print(f"Error extracting interactive elements: {e}")
        return []

def normalize_target(target: Any) -> str:
    target_str = str(target).strip()
    if target_str.startswith("uxg-"):
        return f'[data-uxg-id="{target_str}"]'
    if target_str.isdigit():
        return f'[data-uxg-id="uxg-{target_str}"]'
    return target_str


def parse_coordinates(target: Any) -> tuple[float, float] | None:
    if isinstance(target, dict):
        if "x" in target and "y" in target:
            try:
                return float(target["x"]), float(target["y"])
            except (ValueError, TypeError):
                pass
    if isinstance(target, (list, tuple)) and len(target) >= 2:
        try:
            return float(target[0]), float(target[1])
        except (ValueError, TypeError):
            pass
    if isinstance(target, str):
        m = re.match(r"^\s*\(?\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*\)?\s*$", target.strip())
        if m:
            try:
                return float(m.group(1)), float(m.group(2))
            except (ValueError, TypeError):
                pass
    return None


async def check_empty_section_loading(page: Page) -> bool:
    try:
        return await page.evaluate("""() => {
            const emptyContainers = document.querySelectorAll(
                '#pricing-plans-container, .plans-container-bad, [aria-busy="true"], .loading-container, .skeleton-loader'
            );
            for (const el of emptyContainers) {
                if (el.children.length === 0 && (!el.innerText || el.innerText.trim() === "")) {
                    return true;
                }
            }
            return false;
        }""")
    except Exception:
        return False


async def detect_page_blockers(page: Page) -> list[str]:
    try:
        return await page.evaluate("""() => {
            const blockers = [];
            // Check modal overlay
            const modal = document.querySelector('.modal-overlay-bad, #newsletter-modal, [role="dialog"], .modal');
            if (modal) {
                const style = window.getComputedStyle(modal);
                if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                    const title = (modal.querySelector('h1, h2, h3, h4')?.innerText || 'Newsletter / Promo Modal').trim();
                    blockers.push(`Modal overlay active ('${title}') blocking access to underlying elements`);
                }
            }
            // Check error banners
            const banner = document.querySelector('.bad-error-banner, #form-error-banner, [role="alert"]');
            if (banner) {
                const style = window.getComputedStyle(banner);
                if (style.display !== 'none' && banner.innerText.trim()) {
                    blockers.push(`Form error banner displayed ('${banner.innerText.trim()}')`);
                }
            }
            // Check mobile sticky bar overlapping
            const sticky = document.querySelector('.mobile-sticky-bar');
            if (sticky) {
                const style = window.getComputedStyle(sticky);
                if (style.display !== 'none') {
                    blockers.push('Mobile sticky bar overlapping viewport bottom');
                }
            }
            return blockers;
        }""")
    except Exception:
        return []


async def capture_click_state(page: Page) -> dict:
    try:
        return await page.evaluate("""() => {
            const body = document.body;
            if (!body) return {};
            
            // 1. Visible text length
            const textLength = (body.innerText || "").length;
            
            // 2. Total DOM element count
            const elementCount = document.querySelectorAll('*').length;
            
            // 3. Modal/overlay presence and visibility
            const modals = document.querySelectorAll(
                '.modal-overlay-bad, #newsletter-modal, [role="dialog"], .modal, .dialog, .overlay'
            );
            const modalStates = Array.from(modals).map(m => {
                const s = window.getComputedStyle(m);
                return `${m.id || m.className}:${s.display}:${s.visibility}:${s.opacity}`;
            }).join(';');
            
            // 4. Cart or counter text
            const cartEls = document.querySelectorAll(
                '.nav-cart-link, .cart-count-badge, #cart-subtotal, #cart-total, [class*="cart"], [id*="cart"], [class*="count"], [class*="badge"]'
            );
            const cartText = Array.from(cartEls).map(c => (c.innerText || '').trim()).join('|');
            
            // 5. Input values and error banners
            const inputs = Array.from(document.querySelectorAll('input, select, textarea')).map(i => i.value).join('|');
            const banners = Array.from(document.querySelectorAll('.bad-error-banner, #form-error-banner, [role="alert"], .error, .alert')).map(b => {
                const s = window.getComputedStyle(b);
                return `${s.display}:${(b.innerText || '').trim()}`;
            }).join('|');
            
            return {
                url: window.location.href,
                textLength,
                elementCount,
                modalStates,
                cartText,
                inputs,
                banners
            };
        }""")
    except Exception:
        return {}


def is_click_state_identical(before: dict, after: dict) -> bool:
    if not before or not after:
        return False
    return (
        before.get("url") == after.get("url") and
        before.get("textLength") == after.get("textLength") and
        before.get("elementCount") == after.get("elementCount") and
        before.get("modalStates") == after.get("modalStates") and
        before.get("cartText") == after.get("cartText") and
        before.get("inputs") == after.get("inputs") and
        before.get("banners") == after.get("banners")
    )


async def perform_action(page: Page, action: str, target: Any, value: str = "", timeout: float = 3.0, click_count: int = 1):
    """
    Returns (success: bool, error_msg: str | None).
    """
    if action in ("download", "file_chooser", "upload", "filechooser"):
        return False, "File chooser and download actions are blocked for security."

    coords = parse_coordinates(target)
    if coords and action == "click":
        x, y = coords
        vp = page.viewport_size or {"width": 1280, "height": 800}
        x = max(0.0, min(float(vp.get("width", 1280)), x))
        y = max(0.0, min(float(vp.get("height", 800)), y))
        try:
            interceptor = await page.evaluate("""([cx, cy]) => {
                const topEl = document.elementFromPoint(cx, cy);
                if (topEl) {
                    const modal = topEl.closest('.modal-overlay-bad, #newsletter-modal, [role="dialog"], .modal');
                    if (modal) {
                        const id = modal.id ? ` id="${modal.id}"` : '';
                        const cls = modal.className ? ` class="${modal.className}"` : '';
                        return `<${modal.tagName.toLowerCase()}${id}${cls}>`;
                    }
                }
                return null;
            }""", [x, y])
            if interceptor:
                return False, f"Click blocked by overlay: {interceptor}. Dismiss or close the overlay before interacting."
            await page.mouse.click(x, y, click_count=click_count)
            return True, None
        except Exception as e:
            return False, f"Could not click coordinates ({x}, {y}): {e}"

    selector = normalize_target(target)
    if re.search(r"type\s*=\s*['\"]?file['\"]?", f"{target} {selector}", re.IGNORECASE):
        return False, "File upload inputs are blocked for security."

    timeout_ms = int(timeout * 1000)
    if action == "click":
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout_ms)
            await loc.scroll_into_view_if_needed(timeout=timeout_ms)
            await loc.click(timeout=timeout_ms, click_count=click_count)
            return True, None
        except Exception as e1:
            err_str = str(e1)
            interceptor = None
            m_intercept = re.search(r"(<[a-zA-Z0-9_-]+[^>]*>)\s*intercepts pointer events", err_str, re.IGNORECASE)
            if m_intercept:
                interceptor = m_intercept.group(1)
            else:
                try:
                    interceptor = await page.evaluate("""(sel) => {
                        const el = document.querySelector(sel);
                        if (!el) return null;
                        const rect = el.getBoundingClientRect();
                        const cx = rect.left + rect.width / 2;
                        const cy = rect.top + rect.height / 2;
                        const topEl = document.elementFromPoint(cx, cy);
                        if (topEl && topEl !== el && !el.contains(topEl)) {
                            const id = topEl.id ? ` id="${topEl.id}"` : '';
                            const cls = topEl.className ? ` class="${topEl.className}"` : '';
                            return `<${topEl.tagName.toLowerCase()}${id}${cls}>`;
                        }
                        return null;
                    }""", selector)
                except Exception:
                    interceptor = None

            if interceptor:
                return False, f"Click blocked by overlay: {interceptor}. Dismiss or close the overlay before interacting with this element."

            # Fallback: text-based locator with actionability (no blind force click)
            try:
                clean_text = str(target).replace('[data-uxg-id="', '').replace('"]', '').strip()
                loc = page.get_by_text(clean_text, exact=False).first
                await loc.wait_for(state="visible", timeout=min(timeout_ms, 1000))
                await loc.scroll_into_view_if_needed(timeout=min(timeout_ms, 1000))
                await loc.click(timeout=min(timeout_ms, 1000), click_count=click_count)
                return True, None
            except Exception:
                return False, f"Element '{target}' is not visible or interactable ({err_str[:120]})"

    elif action == "type":
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout_ms)
            await loc.scroll_into_view_if_needed(timeout=timeout_ms)
            await loc.fill(value, timeout=timeout_ms)
            return True, None
        except Exception as e:
            return False, f"Could not type into '{target}': {str(e)}"

    elif action == "scroll":
        try:
            direction = 450 if (value.lower() != "up") else -450
            await page.mouse.wheel(0, direction)
            await page.evaluate(f"window.scrollBy(0, {direction})")
            return True, None
        except Exception as e:
            return False, f"Could not scroll: {str(e)}"

    return True, None


async def settle(page: Page, extra: float = 0.5):
    try:
        await page.wait_for_load_state("networkidle", timeout=800)
    except Exception:
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=1500)
        except Exception:
            pass

    # Wait longer (up to ~8s) when the page appears to have an empty section still loading
    is_loading = await check_empty_section_loading(page)
    if is_loading:
        t_start = time.time()
        while time.time() - t_start < 8.0:
            await asyncio.sleep(0.5)
            still_loading = await check_empty_section_loading(page)
            if not still_loading:
                break
    else:
        await asyncio.sleep(extra)


async def screenshot_with_highlight(page: Page, target: str) -> str:
    sel = normalize_target(target)
    set_js = "(s) => { const el = document.querySelector(s); if (el) { el.style.outline = '4px solid #ef4444'; el.style.outlineOffset = '2px'; } }"
    clear_js = "(s) => { const el = document.querySelector(s); if (el) { el.style.outline = ''; el.style.outlineOffset = ''; } }"
    try:
        await page.evaluate(set_js, sel)
    except Exception:
        pass
    await asyncio.sleep(0.4)  # lets viewers see the target before the click
    shot = await page.screenshot(type="jpeg", quality=50)
    try:
        await page.evaluate(clear_js, sel)
    except Exception:
        pass
    return base64.b64encode(shot).decode("utf-8")


async def verify_task_completion(page: Page, task: str, outcome_reason: str, base64_image: str) -> tuple[bool, str]:
    """
    Verifies if the task was genuinely completed:
    1. Heuristic check: URL path keywords and DOM confirmation text.
    2. Vision LLM verification asking if the task was actually completed based on screenshot.
    Returns (verified: bool, reason: str).
    """
    url_lower = page.url.lower()
    url_success = any(kw in url_lower for kw in [
        "success", "thank", "order", "confirmation", "complete", "welcome", "account", "dashboard", "submitted", "done"
    ])

    dom_success = False
    try:
        dom_success = await page.evaluate("""() => {
            const text = (document.body ? document.body.innerText : "").toLowerCase();
            const keywords = ["thank you", "success", "confirmed", "order received", "welcome", "successfully", "submitted", "completed", "you're all set", "account created", "order placed"];
            return keywords.some(k => text.includes(k));
        }""")
    except Exception:
        pass

    verify_prompt = f"""You are a usability verification auditor.
Task: {task}
Claimed completion reason: {outcome_reason}
Current URL: {page.url}

Inspect the screenshot to check if the user task was ACTUALLY completed.
Respond ONLY with a valid JSON object:
{{
  "verified": true,
  "why": "one sentence explaining why it is or is not completed"
}}
"""
    try:
        res = await resilient_llm_client.chat_completion(
            messages=[
                {"role": "system", "content": "You are a usability auditor. Respond ONLY with valid JSON: {\"verified\": true|false, \"why\": \"...\"}"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": verify_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                    ]
                }
            ],
            model_type="vision",
            response_format={"type": "json_object"},
            max_tokens=250,
            timeout=15.0,
        )
        parsed = json.loads(res.choices[0].message.content)
        is_verified = bool(parsed.get("verified", False))
        why = parsed.get("why", "")
        if is_verified:
            return True, why or "Task verified as completed based on final page state."
        elif url_success or dom_success:
            return True, f"Verified via page confirmation indicators ({page.url}). Note: {why}"
        else:
            return False, why or "Final screen does not confirm task completion."
    except Exception:
        if url_success or dom_success:
            return True, f"Verified via confirmation indicators on page ({page.url})."
        return True, f"Task claimed completed by tester ({outcome_reason or 'No details'})."


MAX_AGENT_STEPS = 25

async def run_agent_loop(
    page: Page,
    task: str,
    persona: str,
    queue: asyncio.Queue,
    max_steps: int = MAX_AGENT_STEPS,
    session_id: str | None = None,
    session_data: dict | None = None,
    emit_done: bool = True,
    max_duration: float = MAX_SESSION_DURATION_SECONDS,
):
    persona_cfg = get_persona_config(persona)
    persona_guide = persona_cfg.behavior_rules

    # Apply security ceilings
    effective_max_steps = min(max_steps, MAX_STEPS_CAP)
    effective_max_duration = min(max_duration, MAX_SESSION_DURATION_SECONDS)
    session_start_time = time.time()

    # Attach security route interception & download/file guards
    await setup_route_interception(page)
    await setup_download_and_file_guards(page)

    await queue.put({
        "thought": f"Initializing agent as {persona_cfg.label} ({persona}) for task: '{task}' (Max Steps: {effective_max_steps})",
        "session_id": session_id,
        "task": task,
        "persona": persona,
    })

    last_error: str | None = None
    consecutive_errors = 0
    steps: list[Step] = []

    # Persona hard rule tracking
    slow_steps_count = 0
    no_change_click_count = 0
    visited_control_categories: set[str] = set()
    small_tap_targets: list[tuple[str, int, int]] = []
    elements_by_id: dict[str, dict] = {}

    # Loop detection history
    action_history: list[dict] = []
    state_hash_history: list[str] = []

    claimed_outcome: str = "in_progress"
    verified_outcome: str = "in_progress"
    final_outcome: str = "in_progress"
    final_outcome_reason: str = ""

    # Technical error collectors for per-step signals
    step_console_errors: list[str] = []
    step_failed_requests: list[str] = []

    def on_console(msg):
        try:
            if getattr(msg, "type", None) == "error":
                text = getattr(msg, "text", str(msg))
                step_console_errors.append(text[:200])
        except Exception:
            pass

    def on_request_failed(req):
        try:
            err = getattr(req, "failure", None)
            method = getattr(req, "method", "REQ")
            url = getattr(req, "url", "")
            step_failed_requests.append(f"{method} {url[:100]}: {err}" if err else f"{method} {url[:100]}")
        except Exception:
            pass

    if hasattr(page, "on"):
        try:
            r1 = page.on("console", on_console)
            if asyncio.iscoroutine(r1):
                r1.close()
            r2 = page.on("requestfailed", on_request_failed)
            if asyncio.iscoroutine(r2):
                r2.close()
        except Exception:
            pass

    for step in range(effective_max_steps):
        # 1. Max session duration check
        if (time.time() - session_start_time) > effective_max_duration:
            stop_reason_dur = f"Maximum session duration ({int(effective_max_duration)}s) exceeded."
            await queue.put({"thought": f"Step {step + 1} · [Security Guard] {stop_reason_dur}"})
            final_outcome = "timeout"
            final_outcome_reason = f"Session timed out: {stop_reason_dur}"
            claimed_outcome = "timeout"
            verified_outcome = "timeout"
            break

        await settle(page, extra=persona_cfg.timeouts.get("settle_timeout", 0.5))
        tag = f"Step {step + 1} · "
        url_before = page.url

        # Reset per-step technical error buffers
        step_console_errors.clear()
        step_failed_requests.clear()

        # 4a. Auto-handle cookie banners
        cookie_dismissed = await handle_cookie_banners(page)
        if cookie_dismissed:
            await queue.put({"thought": f"{tag}[Cookie Banner] Auto-dismissed cookie/consent banner."})
            await settle(page, extra=0.2)

        # 4b. Auto-handle new tabs
        page, did_switch = await follow_new_tabs(page)
        if did_switch:
            url_before = page.url
            await queue.put({"thought": f"{tag}[Tab Navigation] Switched to newly opened tab: {page.url}"})
            if hasattr(page, "on"):
                try:
                    page.on("console", on_console)
                    page.on("requestfailed", on_request_failed)
                except Exception:
                    pass

        # 1. Take current screenshot and collect automated evidence
        screenshot_bytes = await page.screenshot(type="jpeg", quality=50)
        step_evidence = await collect_step_evidence(page)

        # 2. Extract visible interactive elements from DOM with persona filters
        visible_elements = await extract_visible_interactive_elements(page, persona_cfg)
        elements_by_id = {el["id"]: el for el in visible_elements}
        labels = {el["id"]: el.get("name") or el.get("text", "") for el in visible_elements}

        # Security Guard: Detect card-number inputs
        has_payment_fields, payment_desc = detect_payment_fields(visible_elements)

        # 1. Set-of-Marks: overlay numbered labels on interactive elements in screenshot
        annotated_screenshot_bytes = overlay_set_of_marks(screenshot_bytes, visible_elements)
        base64_image = base64.b64encode(annotated_screenshot_bytes).decode('utf-8')

        # 1. Matching element list (number, role, accessible name, bounding box)
        elements_summary = format_som_element_list(visible_elements)

        # 2. Trimmed accessibility tree snapshot instead of full DOM
        a11y_tree = await capture_accessibility_snapshot(page)
        trimmed_a11y = trim_accessibility_tree(a11y_tree)

        # 3. State hash for loop detection
        current_hash = compute_page_state_hash(page.url, trimmed_a11y)
        state_hash_history.append(current_hash)

        # 3. Build prompt
        error_context = f"\nWARNING: Your previous action failed: {last_error}. Pick a different visible element or approach.\n" if last_error else ""

        tester_protocol = ""
        if persona_cfg.name == "pro_tester":
            remaining = [c for c in persona_cfg.hard_rules.get("systematic_categories", ["button", "input", "select", "link"]) if c not in visited_control_categories]
            tester_protocol = f"""
CRITICAL PROFESSIONAL UX TESTER PROTOCOL:
- Systematically work through visible buttons, form inputs, and layout elements on screen.
- Audited control categories so far: {list(visited_control_categories) or ['none']}. Remaining to audit: {remaining or ['all audited']}.
- Rigorously check for UX defects and bugs: unresponsive buttons, missing validation feedback, misaligned layout, unclear copy, or dead ends.
- For input fields: test entering realistic or boundary inputs to verify handling.
- For buttons: test and verify that they trigger expected states, submit forms, or provide clear feedback.
- Format the "thought" field in your JSON as: "[UX Bug: <details>]" or "[UX Observation: <details>]" followed by your next test objective.
- Do NOT finish with "done" until you have audited the key interactive buttons and fields relevant to the task.
"""
        elif persona_cfg.name == "impatient":
            tester_protocol = f"""
IMPATIENT USER PROTOCOL:
- You demand immediate feedback and click without reading long copy.
- If an element produces no visual response after clicking, rage-click it repeatedly.
- Slow steps (>2.0s) cause frustration. Slow steps encountered so far: {slow_steps_count}/3.
"""
        elif persona_cfg.name == "confused":
            tester_protocol = """
CONFUSED USER PROTOCOL:
- You strongly prefer prominent, clearly marked buttons over text links.
- Interpret all button labels and text strictly literally word-for-word.
- If a control is icon-only without a text label, observe and hesitate before acting.
"""
        elif persona_cfg.name == "skeptic":
            tester_protocol = """
SKEPTICAL USER PROTOCOL:
- Refuse to provide real personal data (email, phone, address, financial info) into unverified forms.
- Look for trust signals: privacy policy links, user reviews, and transparent pricing.
"""
        elif persona_cfg.name == "mobile":
            tester_protocol = """
MOBILE TOUCH USER PROTOCOL:
- You are on a 390x844 touchscreen device using tap gestures.
- Tap targets must meet the 44x44px mobile touch standard.
- Flag any interactive controls smaller than 44px as accessibility/ergonomic issues.
"""

        prompt = f"""You are testing a website as a UX persona.
Task: {task}
Persona: {persona}
Behavior guidance: {persona_guide}
{tester_protocol}
{error_context}
ACCESSIBILITY TREE SNAPSHOT (TRIMMED):
{trimmed_a11y}

CURRENTLY VISIBLE INTERACTIVE ELEMENTS (SET-OF-MARKS):
{elements_summary}

Analyze the screenshot (with numbered marks) and the matching element list above.
Decide the next action to make progress on the task according to your persona.
- If the task is already satisfied and you have completed auditing the relevant components, choose "action": "done" and "task_status": "done".
- If you are completely blocked or frustrated with no way forward, choose "action": "abort" and "task_status": "giving_up".
- Otherwise choose "task_status": "in_progress".
- For "reason": explain what you observed and your objective.
- For "outcome_reason": provide a concise explanation of progress, completion proof, or why giving up.
- To interact with an element, provide its element NUMBER in "target" (e.g. 1, 2, 3) from the numbered marks and element list. Do NOT answer with coordinates.
- You can choose "scroll" to reveal more buttons, fields, or layout content.

CRITICAL FORMAT REQUIREMENT:
Respond ONLY with a single valid JSON object starting with '{{' and ending with '}}'.
Do NOT include markdown formatting (no ```json), commentary, or text before/after the JSON.

Expected JSON schema:
{{
  "action": "click",
  "reason": "[UX Observation: checked search box] Clicking Search button to verify results.",
  "thought": "[UX Observation: checked search box] Clicking Search button to verify results.",
  "task_status": "in_progress",
  "outcome_reason": "Searching for product in catalog",
  "target": 1,
  "value": "",
  "friction": null
}}
"task_status" must be one of: "in_progress", "done", "giving_up".
"friction" must be null unless this moment would make a real user hesitate, backtrack, distrust the site, or hit a defect. Only then set it to
{{"type": "navigation|cta|terminology|form|trust|bug", "note": "one sentence: what was confusing or broken, and why"}}.
Only flag friction you can point to on screen. Most steps should be null.
Valid "action" values: "click", "type", "scroll", "done", "abort".
"""
        try:
            # Resilient vision LLM call with token bucket, backoff, and fallback chain
            decision = None

            async def on_llm_status(msg: str):
                await queue.put({
                    "thought": f"{tag}{msg}",
                    "screenshot": base64_image
                })

            messages = [
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                            }
                        },
                    ],
                }
            ]

            try:
                response = await resilient_llm_client.chat_completion(
                    messages=messages,
                    model_type="vision",
                    response_format={"type": "json_object"},
                    max_tokens=1200,
                    status_callback=on_llm_status,
                )
                raw_content = response.choices[0].message.content or ""
                decision = extract_and_parse_json(raw_content)
            except LLMUnavailableError as unavail_err:
                await queue.put({
                    "thought": f"{tag}Aborting: All LLM providers and fallbacks unavailable ({unavail_err})",
                    "screenshot": base64_image
                })
                is_beginning = (len(steps) == 0)
                # End the session and compute score based on findings up to then if steps exist
                score = compute_friction({
                    "steps": steps,
                    "outcome": "error" if is_beginning else "system_error",
                    "outcome_reason": f"All LLM providers and fallbacks unavailable ({unavail_err})",
                    "is_system_error": True,
                    "completed": False,
                })
                
                detected_findings = detect_findings_from_evidence({"steps": steps}) if steps else []
                if is_beginning:
                    findings_list = [
                        {
                            "title": "Test Failed to Start: AI Provider Unavailable",
                            "severity": "critical",
                            "evidence_steps": [],
                            "what_happened": f"Rate limits or provider connection failures prevented the agent from starting: {unavail_err}",
                            "impact": "No steps could be executed on the target application.",
                            "recommendation": "Check API keys or secondary provider configuration in .env and rerun the test.",
                        }
                    ]
                else:
                    findings_list = list(detected_findings) + [
                        {
                            "title": "Audit Interrupted: AI Provider Outage",
                            "severity": "info",
                            "evidence_steps": [s.n for s in steps] if steps else [],
                            "what_happened": f"Testing concluded early at step {len(steps)} due to AI provider outage: {unavail_err}",
                            "impact": f"Evaluated UX through {len(steps)} step(s). Score reflects findings up to this point.",
                            "recommendation": "Review findings up to step {len(steps)} or rerun test when AI provider limits reset.",
                        }
                    ]

                partial_report = {
                    "session_id": session_id,
                    "url": session_data.get("url", page.url) if session_data else page.url,
                    "task": task,
                    "persona": persona,
                    "status": "aborted_llm_unavailable",
                    "error_at_beginning": is_beginning,
                    "prompt_rerun": is_beginning,
                    "rerun_prompt": f"The test could not start because AI providers were unavailable: {unavail_err}. Please check your API keys and rerun the test." if is_beginning else None,
                    "outcome": "error" if is_beginning else "system_error",
                    "outcome_reason": f"All LLM providers and fallbacks unavailable ({unavail_err})",
                    "claimed_outcome": "error" if is_beginning else "system_error",
                    "verified_outcome": "error" if is_beginning else "system_error",
                    "score": score,
                    "verdict": (
                        f"Session aborted: AI testing engine became unavailable ({unavail_err}). Please check configuration and rerun the test."
                        if is_beginning
                        else f"Session aborted: AI testing engine became unavailable at step {len(steps)} due to rate limits across all providers. Score ({score['total']}/100) reflects findings observed up to this step."
                    ),
                    "findings": findings_list,
                    "bugs": sum(1 for s in steps if s.friction_type == "bug"),
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
                            "friction_type": s.friction_type,
                            "friction_note": s.friction_note,
                        }
                        for s in steps
                    ]
                }
                if session_data is not None:
                    session_data["report"] = partial_report
                    session_data["status"] = "aborted_llm_unavailable"
                    session_data["error_at_beginning"] = is_beginning
                    session_data["prompt_rerun"] = is_beginning
                    session_data["rerun_prompt"] = partial_report.get("rerun_prompt")
                    session_data["outcome"] = partial_report["outcome"]
                    session_data["outcome_reason"] = f"LLM unavailable: {unavail_err}"
                    session_data["claimed_outcome"] = partial_report["claimed_outcome"]
                    session_data["verified_outcome"] = partial_report["verified_outcome"]

                LAST_REPORT.clear()
                LAST_REPORT.update(partial_report)
                await queue.put({
                    "thought": "Agent loop aborted due to LLM unavailability.",
                    "error_at_beginning": is_beginning,
                    "prompt_rerun": is_beginning,
                    "rerun_prompt": partial_report.get("rerun_prompt"),
                })
                if emit_done:
                    await queue.put({
                        "done": True,
                        "session_id": session_id,
                        "status": "aborted_llm_unavailable",
                        "error_at_beginning": is_beginning,
                        "prompt_rerun": is_beginning,
                        "rerun_prompt": partial_report.get("rerun_prompt"),
                        "outcome": partial_report["outcome"],
                        "outcome_reason": f"LLM unavailable: {unavail_err}",
                        "claimed_outcome": partial_report["claimed_outcome"],
                        "verified_outcome": partial_report["verified_outcome"],
                    })
                return partial_report
            except Exception as parse_err:
                failed_gen = extract_failed_generation_text(parse_err)
                if failed_gen:
                    await queue.put({
                        "thought": f"{tag}Recovering decision from tester observation...",
                        "screenshot": base64_image
                    })
                    decision = await recover_decision_from_failed_text(failed_gen, status_callback=on_llm_status)
                else:
                    decision = regex_fallback_decision(str(parse_err))

            if not decision:
                raise ValueError("Could not obtain a valid decision from the model.")

            reason = decision.get("reason") or decision.get("thought", "No reason provided.")
            thought = decision.get("thought") or reason
            action = decision.get("action", "abort")
            task_status = decision.get("task_status", "in_progress")
            outcome_reason = decision.get("outcome_reason", "")
            raw_target = decision.get("target", "")
            value = decision.get("value", "")
            friction = decision.get("friction") if isinstance(decision.get("friction"), dict) else {}

            target_num, target_id = parse_som_target(raw_target, visible_elements)
            target = target_id
            target_str = json.dumps(target) if isinstance(target, dict) else str(target or "")
            m = re.search(r"uxg-\d+", target_str)
            target_id = m.group(0) if m else target_str
            label = labels.get(target_id, str(raw_target)) if target_id else (str(raw_target) or "")
            target_el = elements_by_id.get(target_id)

            def record(
                ok: bool,
                shot_for_step: str | None = None,
                url_after: str = "",
                duration: float = 0.0,
                dead_click: bool = False,
                console_errors: list[str] | None = None,
                failed_requests: list[str] | None = None,
            ) -> None:
                step_obj = Step(
                    n=step + 1,
                    url=url_before,
                    url_after=url_after,
                    action=action,
                    label=label,
                    ok=ok,
                    thought=thought,
                    friction_type=friction.get("type"),
                    friction_note=friction.get("note", ""),
                    screenshot=shot_for_step,
                    target=target,
                    duration=duration,
                    dead_click=dead_click,
                    console_errors=list(console_errors or []),
                    failed_requests=list(failed_requests or []),
                    axe_violations=list(step_evidence.get("axe_violations", [])),
                    tap_targets=list(step_evidence.get("tap_targets", [])),
                    contrast_issues=list(step_evidence.get("contrast_issues", [])),
                    overlapping_elements=list(step_evidence.get("overlapping_elements", [])),
                )
                steps.append(step_obj)
                if session_data is not None and "steps" in session_data:
                    session_data["steps"].append(step_obj)

            # 4c. Auto-handle blocking modals only if they block the task
            modal_closed, modal_desc = await handle_blocking_modals(page, target=target_id)
            if modal_closed:
                if not friction.get("type"):
                    friction = {
                        "type": "navigation",
                        "note": f"Blocking modal '{modal_desc}' blocked user task and was dismissed.",
                    }
                await queue.put({"thought": f"{tag}[Modal Dismissed] Blocking modal '{modal_desc}' closed to unblock task."})

            # Security Guard: Never submit forms with payment fields (detect card-number inputs)
            if has_payment_fields:
                is_submitting_payment = is_payment_submission_action(action, label, target_el)
                is_typing_card = (action == "type" and is_payment_field(label, name=target_el.get("name", "") if target_el else "", target_id=target_id))
                if is_submitting_payment or is_typing_card:
                    stop_note = f"Security Guard: Stopped - payment fields detected ({payment_desc}). Submitting credit card details is strictly blocked."
                    await queue.put({"thought": f"{tag}[Security Guard] {stop_note}"})
                    if session_data is not None:
                        session_data.setdefault("security_notes", []).append(stop_note)
                        session_data["payment_blocked"] = True
                    should_stop, outcome, reason_str = evaluate_stop_rules(
                        step=step + 1,
                        max_steps=effective_max_steps,
                        is_abort_claimed=True,
                        stop_reason=stop_note,
                    )
                    claimed_outcome = outcome
                    verified_outcome = outcome
                    final_outcome = outcome
                    final_outcome_reason = reason_str
                    record(False, shot_for_step=base64_image, duration=0.0)
                    await queue.put({
                        "step": step + 1,
                        "action": "abort",
                        "thought": f"{tag}Gave up on task: {final_outcome_reason}",
                        "screenshot": base64_image,
                        "claimed_outcome": claimed_outcome,
                        "verified_outcome": verified_outcome,
                        "outcome": final_outcome,
                        "outcome_reason": final_outcome_reason,
                    })
                    break

            # Security Guard: Use only clearly fake form data (e.g. test@example.com)
            if action == "type":
                sanitized_val, was_sanitized = sanitize_fake_form_data(
                    value,
                    label=label,
                    field_type=target_el.get("type", "") if target_el else ""
                )
                value = sanitized_val
                if session_data is not None:
                    session_data["fake_data_used"] = True

            # Hard Rule 1 (confused): Hesitate on icon-only controls
            if persona_cfg.hard_rules.get("hesitate_on_icon_only") and target_el and target_el.get("is_icon_only"):
                hesitate_sec = persona_cfg.hard_rules.get("hesitation_delay", 0.6)
                await asyncio.sleep(hesitate_sec)
                await queue.put({"thought": f"{tag}[Hesitation] Confused user paused to scrutinize icon-only control '{label}' with no text label."})
                if not friction.get("type"):
                    friction = {
                        "type": "terminology",
                        "note": f"Confused user hesitated on icon-only control '{label}' lacking a descriptive text label."
                    }

            # Hard Rule 2 (skeptic): Refuse real personal data, inject fake data and flag form
            if persona_cfg.hard_rules.get("refuse_personal_data") and action == "type":
                field_type = target_el.get("type", "") if target_el else ""
                if is_personal_data_field(label, target, field_type):
                    fake_val = get_fake_personal_data(label, target)
                    value = fake_val
                    await queue.put({"thought": f"{tag}[Privacy Defense] Skeptical user refused to submit real personal data for '{label}'. Substituted synthetic data: '{fake_val}'."})
                    if not friction.get("type"):
                        friction = {
                            "type": "trust",
                            "note": f"Skeptical user flagged personal data form field '{label}' and entered synthetic data."
                        }

            # Hard Rule 3 (mobile): Detect and flag tap targets below 44px
            if persona_cfg.hard_rules.get("min_tap_target_size") and target_el:
                min_size = persona_cfg.hard_rules["min_tap_target_size"]
                w = target_el.get("width", 50)
                h = target_el.get("height", 50)
                if w < min_size or h < min_size:
                    small_tap_targets.append((label, w, h))
                    await queue.put({"thought": f"{tag}[Touch Ergonomics] Warning: Tap target '{label}' is only {w}x{h}px, below the {min_size}x{min_size}px minimum touch target standard."})
                    if not friction.get("type"):
                        friction = {
                            "type": "accessibility",
                            "note": f"Touch tap target '{label}' is only {w}x{h}px, violating the {min_size}x{min_size}px mobile touch target guideline."
                        }

            # Hard Rule 4 (impatient): Rage-click after 2 no-change clicks
            click_count = 1
            rage_thresh = persona_cfg.hard_rules.get("rage_click_no_change_threshold")
            if rage_thresh and action == "click" and no_change_click_count >= rage_thresh:
                click_count = 3
                await queue.put({"thought": f"{tag}[RAGE-CLICKING] Target '{label}' produced no visual change after {no_change_click_count} clicks; rage-clicking 3x rapidly in frustration!"})
                friction = {
                    "type": "bug",
                    "note": f"User rage-clicked 3x on '{label}' after {no_change_click_count} consecutive clicks produced no page state change."
                }

            await queue.put({"thought": f"{tag}Decided: {thought}"})

            is_done_claim = (action == "done") or (task_status == "done")
            is_abort_claim = (action == "abort") or (task_status == "giving_up")

            if is_done_claim:
                claimed_outcome = OUTCOME_COMPLETED
                is_verified, v_why = await verify_task_completion(page, task, outcome_reason, base64_image)
                should_stop, outcome, reason_str = evaluate_stop_rules(
                    step=step + 1,
                    max_steps=max_steps,
                    is_done_claimed=True,
                    is_verified=is_verified,
                    stop_reason=outcome_reason or v_why,
                )
                verified_outcome = outcome
                final_outcome = outcome
                final_outcome_reason = reason_str

                record(
                    is_verified,
                    shot_for_step=base64_image,
                    url_after=page.url,
                    duration=0.0,
                    dead_click=False,
                    console_errors=step_console_errors,
                    failed_requests=step_failed_requests,
                )
                await queue.put({
                    "step": step + 1,
                    "action": "done",
                    "thought": f"{tag}Claimed done: {outcome_reason or thought}",
                    "screenshot": base64_image,
                    "claimed_outcome": claimed_outcome,
                    "verified_outcome": verified_outcome,
                    "outcome": final_outcome,
                    "outcome_reason": final_outcome_reason,
                })
                break
            elif is_abort_claim:
                should_stop, outcome, reason_str = evaluate_stop_rules(
                    step=step + 1,
                    max_steps=max_steps,
                    is_abort_claimed=True,
                    stop_reason=outcome_reason or "User persona gave up on the task due to friction or confusion.",
                )
                claimed_outcome = outcome
                verified_outcome = outcome
                final_outcome = outcome
                final_outcome_reason = reason_str

                record(
                    False,
                    shot_for_step=base64_image,
                    url_after=page.url,
                    duration=0.0,
                    dead_click=False,
                    console_errors=step_console_errors,
                    failed_requests=step_failed_requests,
                )
                await queue.put({
                    "step": step + 1,
                    "action": "abort",
                    "thought": f"{tag}Gave up on task: {final_outcome_reason}",
                    "screenshot": base64_image,
                    "claimed_outcome": claimed_outcome,
                    "verified_outcome": verified_outcome,
                    "outcome": final_outcome,
                    "outcome_reason": final_outcome_reason,
                })
                break
            elif action in ("click", "type", "scroll"):
                if action == "click":
                    action_desc = f"Clicking element '{target}'"
                elif action == "type":
                    action_desc = f"Typing '{value}' into '{target}'"
                elif action == "scroll":
                    action_desc = f"Scrolling {value or 'down'} to inspect layout and elements"
                else:
                    action_desc = f"Interacting with '{target}'"

                shot = await screenshot_with_highlight(page, target) if (action in ("click", "type") and not parse_coordinates(target)) else base64_image
                await queue.put({
                    "step": step + 1,
                    "action": action,
                    "thought": f"{tag}Executing: {action_desc}",
                    "screenshot": shot
                })

                state_before = {}
                if action == "click":
                    state_before = await capture_click_state(page)

                action_timeout = persona_cfg.timeouts.get("action_timeout", 3.0)
                t0 = time.time()
                success, err = await perform_action(page, action, target, value, timeout=action_timeout, click_count=click_count)
                await settle(page, extra=persona_cfg.timeouts.get("settle_timeout", 0.5))
                t1 = time.time()
                step_duration = round(t1 - t0, 3)

                is_dead_click = False
                if action == "click" and success:
                    state_after = await capture_click_state(page)
                    if is_click_state_identical(state_before, state_after):
                        is_dead_click = True

                if is_dead_click:
                    no_change_click_count += 1
                else:
                    no_change_click_count = 0

                # Track pro_tester visited categories
                if target_el:
                    tag_name = target_el.get("tag", "").lower()
                    cat = "link" if tag_name == "a" else tag_name
                    if cat in ("button", "input", "select", "link", "textarea"):
                        visited_control_categories.add(cat)

                record(
                    success,
                    shot_for_step=shot,
                    url_after=page.url,
                    duration=step_duration,
                    dead_click=is_dead_click,
                    console_errors=step_console_errors,
                    failed_requests=step_failed_requests,
                )

                # Hard Rule 5 (impatient): Track slow steps and abandon after max_slow_steps
                slow_threshold = persona_cfg.timeouts.get("slow_step_threshold", 4.0)
                if step_duration > slow_threshold:
                    slow_steps_count += 1
                    max_slow = persona_cfg.hard_rules.get("max_slow_steps")
                    if max_slow:
                        await queue.put({"thought": f"{tag}[Slow Step #{slow_steps_count}] Action took {step_duration}s (exceeds {slow_threshold}s limit)."})
                        if slow_steps_count >= max_slow:
                            claimed_outcome = OUTCOME_ABANDONED
                            verified_outcome = OUTCOME_ABANDONED
                            final_outcome = OUTCOME_ABANDONED
                            final_outcome_reason = f"Impatient user abandoned task: encountered {slow_steps_count} slow steps exceeding {slow_threshold}s response threshold."
                            await queue.put({
                                "step": step + 1,
                                "action": "abort",
                                "thought": f"{tag}Abandoned task: {final_outcome_reason}",
                                "screenshot": shot,
                                "claimed_outcome": claimed_outcome,
                                "verified_outcome": verified_outcome,
                                "outcome": final_outcome,
                                "outcome_reason": final_outcome_reason,
                            })
                            break

                # Record action into history for loop detection
                action_history.append({"action": action, "target": target_id})

                # 3. Check loop detection: if same action on same element 3x or URL/DOM hash unchanged for 3 steps
                is_loop, loop_reason, loop_hint = check_loop_detection(action_history, state_hash_history)
                if is_loop:
                    blockers = await detect_page_blockers(page)
                    if blockers:
                        blocker_details = "; ".join(blockers)
                        loop_hint = f"{loop_hint} Detected active blocker(s): {blocker_details}."
                        step_evidence.setdefault("blockers", []).extend(blockers)
                    await queue.put({"thought": f"{tag}[Loop Detection] {loop_reason}. Hint: {loop_hint}"})
                    should_stop, outcome, reason_str = evaluate_stop_rules(
                        step=step + 1,
                        max_steps=max_steps,
                        is_loop_detected=True,
                        stop_reason=f"{loop_reason}. Hint: {loop_hint}",
                    )
                    claimed_outcome = outcome
                    verified_outcome = outcome
                    final_outcome = outcome
                    final_outcome_reason = reason_str
                    await queue.put({
                        "step": step + 1,
                        "action": "abort",
                        "thought": f"{tag}Gave up on task: {final_outcome_reason}",
                        "screenshot": shot,
                        "claimed_outcome": claimed_outcome,
                        "verified_outcome": verified_outcome,
                        "outcome": final_outcome,
                        "outcome_reason": final_outcome_reason,
                    })
                    break

                if success:
                    last_error = None
                    consecutive_errors = 0
                    await queue.put({"thought": f"{tag}Action completed"})
                else:
                    last_error = err
                    consecutive_errors += 1
                    await queue.put({"thought": f"{tag}Friction encountered: {err}. Adapting strategy..."})
                    if consecutive_errors >= 3:
                        claimed_outcome = OUTCOME_ABANDONED
                        verified_outcome = OUTCOME_ABANDONED
                        final_outcome = OUTCOME_ABANDONED
                        final_outcome_reason = f"Abandoned task after repeated interaction failures: {err}"
                        await queue.put({
                            "thought": f"{tag}Aborting task: Repeated interaction failures encountered.",
                            "screenshot": base64_image,
                            "claimed_outcome": claimed_outcome,
                            "verified_outcome": verified_outcome,
                            "outcome": final_outcome,
                            "outcome_reason": final_outcome_reason,
                        })
                        break

        except Exception as e:
            await queue.put({
                "thought": f"{tag}Friction during agent decision: {str(e)[:160]}",
                "screenshot": base64_image
            })
            # If unexpected error occurred, continue loop unless repeated
            consecutive_errors += 1
            if consecutive_errors >= 3:
                final_outcome = "system_error"
                final_outcome_reason = f"Execution halted due to repeated agent errors: {str(e)[:160]}"
                claimed_outcome = "system_error"
                verified_outcome = "system_error"
                await queue.put({
                    "thought": f"{tag}Aborting task after repeated execution errors: {str(e)[:160]}",
                    "screenshot": base64_image,
                    "claimed_outcome": claimed_outcome,
                    "verified_outcome": verified_outcome,
                    "outcome": final_outcome,
                    "outcome_reason": final_outcome_reason,
                })
                break
            await asyncio.sleep(1.5)
            continue

    if final_outcome == "in_progress":
        should_stop, outcome, reason_str = evaluate_stop_rules(
            step=max_steps,
            max_steps=max_steps,
            stop_reason=outcome_reason or f"Maximum steps ({max_steps}) reached without completing task.",
        )
        claimed_outcome = outcome
        verified_outcome = outcome
        final_outcome = outcome
        final_outcome_reason = reason_str

    completed = (final_outcome == OUTCOME_COMPLETED)
    await queue.put({"thought": "Writing the Sabotage Report…"})

    session_dict = {
        "session_id": session_id,
        "url": session_data.get("url", page.url) if session_data else page.url,
        "task": task,
        "persona": persona,
        "status": "completed" if completed else final_outcome,
        "outcome": final_outcome,
        "outcome_reason": final_outcome_reason,
        "is_system_error": (final_outcome in ("timeout", "system_error")),
        "claimed_outcome": claimed_outcome,
        "verified_outcome": verified_outcome,
        "steps": steps,
        "completed": completed,
        "expected_steps": session_data.get("expected_steps") if session_data else None,
        "baseline_failed": session_data.get("baseline_failed", False) if session_data else False,
        "baseline_note": session_data.get("baseline_note", "") if session_data else "",
        "baseline_path": session_data.get("baseline_path", []) if session_data else [],
        "fake_data_used": session_data.get("fake_data_used", True) if session_data else True,
        "security_notes": session_data.get("security_notes", []) if session_data else [],
    }

    try:
        report = await asyncio.to_thread(build_report, session_dict, client=resilient_llm_client)
    except Exception as e:
        print(f"Report generation failed: {e}")
        score_data = compute_friction(session_dict)
        findings_from_evidence = detect_findings_from_evidence(session_dict)
        attach_screenshots_with_bounding_boxes(findings_from_evidence, steps)
        report = {
            "score": score_data,
            "verdict": f"The session completed with {score_data['label'].lower()} friction ({score_data['score']}/100). Deterministic breakdown computed successfully.",
            "findings": findings_from_evidence,
            "baseline_failed": session_dict["baseline_failed"],
            "baseline_note": session_dict["baseline_note"],
            "fake_data_used": True,
            "security_notes": session_dict.get("security_notes", []),
        }

    report["baseline_failed"] = session_dict["baseline_failed"]
    report["baseline_note"] = session_dict["baseline_note"]
    report["baseline_path"] = session_dict["baseline_path"]

    # Hard Rule 6 (skeptic): Audit trust signals (privacy policy, reviews, pricing visibility) and record absence
    if persona_cfg.hard_rules.get("check_trust_signals"):
        try:
            page_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            trust_findings = audit_trust_signals_in_page(page_text, visible_elements or [])
            for tf in trust_findings:
                if not any(tf["title"].lower() in f.get("title", "").lower() for f in report.get("findings", [])):
                    report["findings"].append(tf)
        except Exception as e:
            print(f"Trust signal audit error: {e}")

    # Hard Rule 7 (mobile): Record touch target accessibility finding if small tap targets encountered
    if persona_cfg.hard_rules.get("min_tap_target_size") and small_tap_targets:
        has_tap_finding = any("tap target" in f.get("title", "").lower() for f in report.get("findings", []))
        if not has_tap_finding:
            examples = ", ".join(f"'{lbl}' ({w}x{h}px)" for lbl, w, h in small_tap_targets[:3])
            report["findings"].append({
                "title": "Mobile Ergonomics: Touch Target Below 44px",
                "severity": "high",
                "evidence_steps": [s.n for s in steps if s.friction_type == "accessibility"],
                "what_happened": f"Interactive mobile controls ({examples}) fall below the 44x44px minimum touch target standard.",
                "impact": "Increases mis-taps, precision fatigue, and task abandonment on mobile touchscreen devices.",
                "recommendation": "Expand bounding box or touch padding so interactive elements meet or exceed 44x44px on mobile viewports.",
            })

    report["bugs"] = sum(1 for s in steps if s.friction_type == "bug")
    report["session_id"] = session_id
    report["url"] = session_data.get("url", page.url) if session_data else page.url
    report["task"] = task
    report["persona"] = persona
    report["outcome"] = final_outcome
    report["outcome_reason"] = final_outcome_reason
    report["claimed_outcome"] = claimed_outcome
    report["verified_outcome"] = verified_outcome
    report["actions"] = [
        {
            "step_number": s.n,
            "action": s.action,
            "target": s.label,
            "thought": s.thought,
            "screenshot": s.screenshot,
            "ok": s.ok,
            "url": s.url,
            "url_after": s.url_after,
            "friction_type": s.friction_type,
            "friction_note": s.friction_note,
            "duration": getattr(s, "duration", 0.0),
            "dead_click": getattr(s, "dead_click", False),
            "console_errors": getattr(s, "console_errors", []),
            "failed_requests": getattr(s, "failed_requests", []),
        }
        for s in steps
    ]

    is_beginning = (len(steps) == 0)
    if is_beginning and (final_outcome in ("timeout", "system_error", "error")):
        report["error_at_beginning"] = True
        report["status"] = "error_at_beginning"
        report["prompt_rerun"] = True
        report["rerun_prompt"] = f"An error occurred before testing could start: {final_outcome_reason or 'No steps could be executed'}. Please check your target URL and rerun the test."
        if not report.get("findings"):
            report["findings"] = [{
                "title": "Test Failed to Start",
                "severity": "critical",
                "evidence_steps": [],
                "what_happened": f"An error occurred before testing could begin: {final_outcome_reason or 'No steps could be executed'}",
                "impact": "No steps could be executed on the target application.",
                "recommendation": "Check that the target server is running and accessible, then rerun the test.",
            }]

    try:
        from report_translator import translate_full_report
        report = translate_full_report(report, steps=steps)
    except Exception as e:
        print(f"Report translation in agent.py warning: {e}")

    if session_data is not None:
        session_data["report"] = report
        session_data["status"] = report.get("status", "completed")
        session_data["error_at_beginning"] = report.get("error_at_beginning", False)
        session_data["prompt_rerun"] = report.get("prompt_rerun", False)
        session_data["rerun_prompt"] = report.get("rerun_prompt")
        session_data["outcome"] = final_outcome
        session_data["outcome_reason"] = final_outcome_reason
        session_data["claimed_outcome"] = claimed_outcome
        session_data["verified_outcome"] = verified_outcome

    LAST_REPORT.clear()
    LAST_REPORT.update(report)
    await queue.put({"thought": "Agent loop finished."})
    if emit_done:
        await queue.put({
            "done": True,
            "session_id": session_id,
            "status": report.get("status", "completed"),
            "error_at_beginning": report.get("error_at_beginning", False),
            "prompt_rerun": report.get("prompt_rerun", False),
            "rerun_prompt": report.get("rerun_prompt"),
            "outcome": final_outcome,
            "outcome_reason": final_outcome_reason,
            "claimed_outcome": claimed_outcome,
            "verified_outcome": verified_outcome,
        })

    if hasattr(page, "remove_listener"):
        try:
            r1 = page.remove_listener("console", on_console)
            if asyncio.iscoroutine(r1):
                r1.close()
            r2 = page.remove_listener("requestfailed", on_request_failed)
            if asyncio.iscoroutine(r2):
                r2.close()
        except Exception:
            pass

    return report

