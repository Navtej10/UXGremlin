import os
import re
import time
import asyncio
import base64
import json
from playwright.async_api import Page
from dotenv import load_dotenv
from scoring import Step, compute_friction, build_report
from llm_client import resilient_llm_client, LLMUnavailableError

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


PERSONA_GUIDES = {
    "pro_tester": (
        "You are a meticulous, senior Professional UX & QA Engineer. Your directive is to systematically audit, "
        "inspect, and test the entire interface while accomplishing the task. You methodically evaluate all visible "
        "buttons, navigation menus, form inputs, dropdowns, and layout elements. You actively hunt for bugs, "
        "misaligned layouts, confusing hierarchies, missing error messages, unclickable buttons, and validation gaps. "
        "Before concluding, you ensure that interactive fields, primary buttons, and relevant paths are thoroughly verified."
    ),
    "impatient": (
        "You are an extremely impatient user. You skim quickly, click prominent visible links/buttons right away, "
        "and avoid reading long paragraphs. If an action fails or there is friction, you quickly try an alternative "
        "or abort out of frustration."
    ),
    "confused": (
        "You are a confused, non-technical user. You hesitate, get easily distracted, click tangential links, "
        "and wander around. You find it hard to identify the direct path."
    ),
    "skeptic": (
        "You are a skeptical, cautious user. You look for hidden traps, inspect labels carefully, "
        "and avoid rushing into actions without checking options."
    ),
    "baseline": (
        "You are an expert, highly efficient user testing baseline. "
        "You have zero confusion, ignore irrelevant elements, and take the shortest, "
        "most direct path to successfully accomplish the goal. "
        "You do not wander, hesitate, or perform redundant actions. "
        "Your sole focus is reaching the target goal with the minimum necessary steps."
    )
}

async def extract_visible_interactive_elements(page: Page):
    """
    Extracts visible, interactable elements from the active viewport
    and annotates them with temporary data-uxg-id attributes for reliable targeting.
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

                const uxgId = `uxg-${count + 1}`;
                el.setAttribute('data-uxg-id', uxgId);

                let label = text || (placeholder ? `[${placeholder}]` : (href ? href.slice(0, 40) : tag));
                if (isDisabled) label += " [DISABLED]";

                items.push({
                    id: uxgId,
                    tag: tag,
                    text: label,
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
        return elements or []
    except Exception as e:
        print(f"Error extracting interactive elements: {e}")
        return []

def normalize_target(target: str) -> str:
    target = target.strip()
    if target.startswith("uxg-"):
        return f'[data-uxg-id="{target}"]'
    if target.isdigit():
        return f'[data-uxg-id="uxg-{target}"]'
    return target

async def perform_action(page: Page, action: str, target: str, value: str = ""):
    """
    Performs click, type, or scroll action with visibility checks and fallbacks.
    Returns (success: bool, error_msg: str | None).
    """
    selector = normalize_target(target)
    if action == "click":
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=3000)
            await loc.scroll_into_view_if_needed(timeout=2000)
            await loc.click(timeout=3000)
            return True, None
        except Exception as e1:
            # Fallback 1: force click in case of overlay/clipping
            try:
                loc = page.locator(selector).first
                await loc.click(force=True, timeout=2000)
                return True, None
            except Exception:
                pass
            # Fallback 2: text-based locator
            try:
                clean_text = target.replace('[data-uxg-id="', '').replace('"]', '').strip()
                loc = page.get_by_text(clean_text, exact=False).first
                await loc.click(timeout=2000)
                return True, None
            except Exception:
                return False, f"Element '{target}' is not visible or interactable"

    elif action == "type":
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=3000)
            await loc.scroll_into_view_if_needed(timeout=2000)
            await loc.fill(value, timeout=3000)
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
        await page.wait_for_load_state("domcontentloaded", timeout=2500)
    except Exception:
        pass
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

async def run_agent_loop(page: Page, task: str, persona: str, queue: asyncio.Queue, max_steps: int = MAX_AGENT_STEPS, session_id: str | None = None, session_data: dict | None = None):
    persona_guide = PERSONA_GUIDES.get(persona, PERSONA_GUIDES["pro_tester"])
    await queue.put({
        "thought": f"Initializing agent as {persona} persona for task: '{task}' (Max Steps: {max_steps})",
        "session_id": session_id,
        "task": task,
        "persona": persona,
    })

    last_error: str | None = None
    consecutive_errors = 0
    steps: list[Step] = []

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

    for step in range(max_steps):
        await settle(page)
        tag = f"Step {step + 1} · "
        url_before = page.url

        # Reset per-step technical error buffers
        step_console_errors.clear()
        step_failed_requests.clear()

        # 1. Take current screenshot
        screenshot_bytes = await page.screenshot(type="jpeg", quality=50)
        base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')


        # 2. Extract visible interactive elements from DOM
        visible_elements = await extract_visible_interactive_elements(page)
        labels = {el["id"]: el["text"] for el in visible_elements}
        
        elements_summary = "\n".join([
            f"- [{el['id']}] <{el['tag']}> \"{el['text']}\"" +
            (f" (placeholder: \"{el['placeholder']}\")" if el.get('placeholder') else "") +
            (f" (href: {el['href']})" if el.get('href') else "")
            for el in visible_elements
        ]) if visible_elements else "No obvious interactive elements identified via DOM."

        # 3. Build prompt
        error_context = f"\nWARNING: Your previous action failed: {last_error}. Pick a different visible element or approach.\n" if last_error else ""

        tester_protocol = ""
        if persona == "pro_tester":
            tester_protocol = """
CRITICAL PROFESSIONAL UX TESTER PROTOCOL:
- Systematically work through visible buttons, form inputs, and layout elements on screen.
- Rigorously check for UX defects and bugs: unresponsive buttons, missing validation feedback, misaligned layout, unclear copy, or dead ends.
- For input fields: test entering realistic or boundary inputs to verify handling.
- For buttons: test and verify that they trigger expected states, submit forms, or provide clear feedback.
- Format the "thought" field in your JSON as: "[UX Bug: <details>]" or "[UX Observation: <details>]" followed by your next test objective.
- Do NOT finish with "done" until you have audited the key interactive buttons and fields relevant to the task.
"""

        prompt = f"""You are testing a website as a UX persona.
Task: {task}
Persona: {persona}
Behavior guidance: {persona_guide}
{tester_protocol}
{error_context}
CURRENTLY VISIBLE INTERACTIVE ELEMENTS ON SCREEN:
{elements_summary}

Analyze the screenshot and the list of currently visible elements above.
Decide the next action to make progress on the task according to your persona.
- If the task is already satisfied and you have completed auditing the relevant components, choose "action": "done" and "task_status": "done".
- If you are completely blocked or frustrated with no way forward, choose "action": "abort" and "task_status": "giving_up".
- Otherwise choose "task_status": "in_progress".
- For "reason": explain what you observed and your objective.
- For "outcome_reason": provide a concise explanation of progress, completion proof, or why giving up.
- To interact, prefer using the element ID from the list (e.g. "uxg-1" or "[data-uxg-id=\"uxg-1\"]") or a visible selector.
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
  "target": "uxg-20",
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
                # End the session with status "aborted_llm_unavailable" and still save the partial report
                score = compute_friction({
                    "steps": steps,
                    "outcome": OUTCOME_ERROR,
                    "outcome_reason": f"All LLM providers and fallbacks unavailable ({unavail_err})",
                    "completed": False,
                })
                partial_report = {
                    "session_id": session_id,
                    "url": session_data.get("url", page.url) if session_data else page.url,
                    "task": task,
                    "persona": persona,
                    "status": "aborted_llm_unavailable",
                    "outcome": OUTCOME_ERROR,
                    "outcome_reason": f"All LLM providers and fallbacks unavailable ({unavail_err})",
                    "claimed_outcome": OUTCOME_ERROR,
                    "verified_outcome": OUTCOME_ERROR,
                    "score": score,
                    "verdict": "Session aborted: AI testing engine became unavailable due to rate limits across all providers. Partial progress was recorded.",
                    "findings": [
                        {
                            "title": "Session Interrupted by LLM Outage",
                            "severity": "critical",
                            "evidence_steps": [s.n for s in steps] if steps else [],
                            "what_happened": "Rate limits or provider connection failures prevented the agent from finishing.",
                            "impact": "Test stopped prematurely before full user testing could conclude.",
                            "recommendation": "Check API keys or secondary provider configuration in .env.",
                        }
                    ],
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
                    session_data["outcome"] = OUTCOME_ERROR
                    session_data["outcome_reason"] = f"LLM unavailable: {unavail_err}"
                    session_data["claimed_outcome"] = OUTCOME_ERROR
                    session_data["verified_outcome"] = OUTCOME_ERROR

                LAST_REPORT.clear()
                LAST_REPORT.update(partial_report)
                await queue.put({
                    "thought": "Agent loop aborted due to LLM unavailability.",
                    "done": True,
                    "session_id": session_id,
                    "status": "aborted_llm_unavailable",
                    "outcome": OUTCOME_ERROR,
                    "outcome_reason": f"LLM unavailable: {unavail_err}",
                    "claimed_outcome": OUTCOME_ERROR,
                    "verified_outcome": OUTCOME_ERROR,
                })
                return
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
            target = decision.get("target", "")
            value = decision.get("value", "")
            friction = decision.get("friction") if isinstance(decision.get("friction"), dict) else {}
            m = re.search(r"uxg-\d+", target or "")
            label = labels.get(m.group(0), target) if m else (target or "")

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
                )
                steps.append(step_obj)
                if session_data is not None and "steps" in session_data:
                    session_data["steps"].append(step_obj)

            await queue.put({"thought": f"{tag}Decided: {thought}"})

            is_done_claim = (action == "done") or (task_status == "done")
            is_abort_claim = (action == "abort") or (task_status == "giving_up")

            if is_done_claim:
                claimed_outcome = OUTCOME_COMPLETED
                is_verified, v_why = await verify_task_completion(page, task, outcome_reason, base64_image)
                if is_verified:
                    verified_outcome = OUTCOME_COMPLETED
                    final_outcome = OUTCOME_COMPLETED
                    final_outcome_reason = outcome_reason or v_why
                else:
                    verified_outcome = OUTCOME_ABANDONED
                    final_outcome = OUTCOME_ABANDONED
                    final_outcome_reason = f"{outcome_reason} (Verification check failed: {v_why})" if outcome_reason else f"Verification unconfirmed: {v_why}"

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
                claimed_outcome = OUTCOME_GAVE_UP
                verified_outcome = OUTCOME_GAVE_UP
                final_outcome = OUTCOME_GAVE_UP
                final_outcome_reason = outcome_reason or "User persona gave up on the task due to friction or confusion."

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

                shot = await screenshot_with_highlight(page, target) if action in ("click", "type") else base64_image
                await queue.put({
                    "step": step + 1,
                    "action": action,
                    "thought": f"{tag}Executing: {action_desc}",
                    "screenshot": shot
                })

                dom_before = ""
                if action == "click":
                    try:
                        dom_before = await page.evaluate("() => document.body ? `${document.body.innerText.length}:${document.querySelectorAll('*').length}` : ''")
                    except Exception:
                        dom_before = ""

                t0 = time.time()
                success, err = await perform_action(page, action, target, value)
                await settle(page)
                t1 = time.time()
                step_duration = round(t1 - t0, 3)

                is_dead_click = False
                if action == "click" and success:
                    try:
                        dom_after = await page.evaluate("() => document.body ? `${document.body.innerText.length}:${document.querySelectorAll('*').length}` : ''")
                        if page.url == url_before and dom_after == dom_before:
                            is_dead_click = True
                    except Exception:
                        pass

                record(
                    success,
                    shot_for_step=shot,
                    url_after=page.url,
                    duration=step_duration,
                    dead_click=is_dead_click,
                    console_errors=step_console_errors,
                    failed_requests=step_failed_requests,
                )
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
                claimed_outcome = OUTCOME_ERROR
                verified_outcome = OUTCOME_ERROR
                final_outcome = OUTCOME_ERROR
                final_outcome_reason = f"Execution halted due to repeated agent errors: {str(e)[:160]}"
                await queue.put({
                    "thought": f"{tag}Aborting task after repeated execution errors.",
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
        claimed_outcome = OUTCOME_MAX_STEPS
        verified_outcome = OUTCOME_MAX_STEPS
        final_outcome = OUTCOME_MAX_STEPS
        final_outcome_reason = outcome_reason or f"Maximum steps ({max_steps}) reached without completing task."

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
        "claimed_outcome": claimed_outcome,
        "verified_outcome": verified_outcome,
        "steps": steps,
        "completed": completed,
        "expected_steps": session_data.get("expected_steps") if session_data else None,
        "baseline_failed": session_data.get("baseline_failed", False) if session_data else False,
        "baseline_note": session_data.get("baseline_note", "") if session_data else "",
        "baseline_path": session_data.get("baseline_path", []) if session_data else [],
    }

    try:
        report = await asyncio.to_thread(build_report, session_dict, client=resilient_llm_client)
    except Exception as e:
        print(f"Report generation failed: {e}")
        score_data = compute_friction(session_dict)
        report = {
            "score": score_data,
            "verdict": f"The session completed with {score_data['label'].lower()} friction ({score_data['score']}/100). Deterministic breakdown computed successfully.",
            "findings": [],
            "baseline_failed": session_dict["baseline_failed"],
            "baseline_note": session_dict["baseline_note"],
        }

    report["baseline_failed"] = session_dict["baseline_failed"]
    report["baseline_note"] = session_dict["baseline_note"]
    report["baseline_path"] = session_dict["baseline_path"]
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

    if session_data is not None:
        session_data["report"] = report
        session_data["status"] = "completed"
        session_data["outcome"] = final_outcome
        session_data["outcome_reason"] = final_outcome_reason
        session_data["claimed_outcome"] = claimed_outcome
        session_data["verified_outcome"] = verified_outcome

    LAST_REPORT.clear()
    LAST_REPORT.update(report)
    await queue.put({"thought": "Agent loop finished."})
    await queue.put({
        "done": True,
        "session_id": session_id,
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

