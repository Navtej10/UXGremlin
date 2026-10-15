import os
import re
import asyncio
import base64
import json
from groq import Groq
from playwright.async_api import Page
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

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

    return {
        "thought": text.strip()[:240],
        "action": action,
        "target": target,
        "value": value
    }

async def recover_decision_from_failed_text(text: str) -> dict:
    """Uses fast text completion or regex fallback to parse unstructured tester text into decision dict."""
    try:
        res = await asyncio.to_thread(
            client.chat.completions.create,
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an action parser. Extract the intended action from the QA tester text into valid JSON. "
                        "Respond ONLY with a single JSON object: {\"thought\": \"...\", \"action\": \"click\"|\"type\"|\"scroll\"|\"done\"|\"abort\", \"target\": \"uxg-X\", \"value\": \"...\"}."
                    )
                },
                {"role": "user", "content": text}
            ],
            response_format={"type": "json_object"},
            max_tokens=800
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

MAX_AGENT_STEPS = 25

async def run_agent_loop(page: Page, task: str, persona: str, queue: asyncio.Queue, max_steps: int = MAX_AGENT_STEPS):
    persona_guide = PERSONA_GUIDES.get(persona, PERSONA_GUIDES["pro_tester"])
    await queue.put({"thought": f"Initializing agent as {persona} persona for task: '{task}' (Max Steps: {max_steps})"})

    last_error: str | None = None
    consecutive_errors = 0

    for step in range(max_steps):
        await asyncio.sleep(1.5) # allow page / animations to settle

        # 1. Take current screenshot
        screenshot_bytes = await page.screenshot(type="jpeg", quality=50)
        base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')

        # 2. Extract visible interactive elements from DOM
        visible_elements = await extract_visible_interactive_elements(page)
        
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
- If the task is already satisfied and you have completed auditing the relevant components, choose "done".
- If you are completely blocked or frustrated with no way forward, choose "abort".
- To interact, prefer using the element ID from the list (e.g. "uxg-1" or "[data-uxg-id=\"uxg-1\"]") or a visible selector.
- You can choose "scroll" to reveal more buttons, fields, or layout content.

CRITICAL FORMAT REQUIREMENT:
Respond ONLY with a single valid JSON object starting with '{{' and ending with '}}'.
Do NOT include markdown formatting (no ```json), commentary, or text before/after the JSON.

Expected JSON schema:
{{
  "thought": "[UX Observation: checked search box] Clicking Search button to verify results.",
  "action": "click",
  "target": "uxg-20",
  "value": ""
}}
Valid "action" values: "click", "type", "scroll", "done", "abort".
"""
        try:
            # Resilient Groq call with JSON mode, recovery, and rate-limit retry support
            decision = None
            for attempt in range(3):
                try:
                    req_kwargs = {
                        "model": "qwen/qwen3.8-27b",
                        "messages": [
                            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt if attempt == 0 else f"{prompt}\nCRITICAL: Output raw JSON starting with {{ only!"},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{base64_image}",
                                        }
                                    },
                                ],
                            }
                        ],
                        "max_tokens": 1200,
                    }
                    if attempt == 0:
                        req_kwargs["response_format"] = {"type": "json_object"}

                    response = await asyncio.to_thread(
                        client.chat.completions.create,
                        **req_kwargs
                    )
                    raw_content = response.choices[0].message.content or ""
                    decision = extract_and_parse_json(raw_content)
                    break
                except Exception as api_err:
                    err_str = str(api_err).lower()
                    print(f"API attempt {attempt} failed: {api_err}")

                    # 1. Groq rate limit
                    if ("429" in err_str or "rate limit" in err_str) and attempt < 2:
                        await queue.put({
                            "thought": "Groq rate limit encountered. Pausing 5 seconds before retrying...",
                            "screenshot": base64_image
                        })
                        await asyncio.sleep(5)
                        continue

                    # 2. Recover from failed_generation if model output prose instead of JSON
                    failed_gen = extract_failed_generation_text(api_err)
                    if failed_gen:
                        await queue.put({
                            "thought": "Recovering decision from tester observation...",
                            "screenshot": base64_image
                        })
                        decision = await recover_decision_from_failed_text(failed_gen)
                        if decision:
                            break

                    # 3. Retry on attempt 1/2 (subsequent attempts omit response_format to avoid 400 rejection)
                    if attempt < 2:
                        await asyncio.sleep(1)
                        continue
                    else:
                        raise api_err

            if not decision:
                raise ValueError("Could not obtain a valid decision from the model.")

            thought = decision.get("thought", "No thought provided.")
            action = decision.get("action", "abort")
            target = decision.get("target", "")
            value = decision.get("value", "")

            await queue.put({
                "thought": f"Decided: {thought}",
                "screenshot": base64_image
            })

            if action == "done":
                await queue.put({
                    "thought": "Task completed successfully.",
                    "screenshot": base64_image
                })
                break
            elif action == "abort":
                await queue.put({
                    "thought": "Aborting task due to friction or confusion.",
                    "screenshot": base64_image
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

                await queue.put({
                    "thought": f"Executing: {action_desc}",
                    "screenshot": base64_image
                })

                success, err = await perform_action(page, action, target, value)
                if success:
                    last_error = None
                    consecutive_errors = 0
                    # Wait for navigation or reaction, then capture resulting screenshot
                    await asyncio.sleep(1.5)
                    after_bytes = await page.screenshot(type="jpeg", quality=50)
                    after_base64 = base64.b64encode(after_bytes).decode('utf-8')
                    await queue.put({
                        "thought": f"Action completed: {action_desc}",
                        "screenshot": after_base64
                    })
                else:
                    last_error = err
                    consecutive_errors += 1
                    await queue.put({
                        "thought": f"Friction encountered: {err}. Adapting strategy...",
                        "screenshot": base64_image
                    })
                    if consecutive_errors >= 3:
                        await queue.put({
                            "thought": "Aborting task: Repeated interaction failures encountered.",
                            "screenshot": base64_image
                        })
                        break

        except Exception as e:
            await queue.put({
                "thought": f"Friction during agent decision: {str(e)[:160]}",
                "screenshot": base64_image
            })
            # If unexpected error occurred, continue loop unless repeated
            consecutive_errors += 1
            if consecutive_errors >= 3:
                await queue.put({
                    "thought": "Aborting task after repeated execution errors.",
                    "screenshot": base64_image
                })
                break
            await asyncio.sleep(1.5)
            continue

    await queue.put({"thought": "Agent loop finished."})
    await queue.put({"done": True})

