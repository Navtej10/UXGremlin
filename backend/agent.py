import os
import asyncio
import base64
import json
from groq import Groq
from playwright.async_api import Page
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

PERSONA_GUIDES = {
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
                'a, button, input, textarea, select, [role="button"], [role="link"], label[for]'
            );
            let count = 0;
            for (const el of candidates) {
                if (count >= 35) break;

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

                if (tag === 'a' && !text && !href) continue;

                const uxgId = `uxg-${count + 1}`;
                el.setAttribute('data-uxg-id', uxgId);

                items.push({
                    id: uxgId,
                    tag: tag,
                    text: text || (href ? href.slice(0, 40) : tag),
                    href: href ? href.slice(0, 50) : undefined,
                    type: el.getAttribute('type') || undefined
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
    Performs click or type action with visibility checks and fallbacks.
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

    return True, None

async def run_agent_loop(page: Page, task: str, persona: str, queue: asyncio.Queue):
    persona_guide = PERSONA_GUIDES.get(persona, PERSONA_GUIDES["impatient"])
    await queue.put({"thought": f"Initializing agent as {persona} persona for task: '{task}'"})

    last_error: str | None = None
    consecutive_errors = 0

    for step in range(10): # limit to 10 steps for POC
        await asyncio.sleep(1.5) # allow page / animations to settle

        # 1. Take current screenshot
        screenshot_bytes = await page.screenshot(type="jpeg", quality=50)
        base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')

        # 2. Extract visible interactive elements from DOM
        visible_elements = await extract_visible_interactive_elements(page)
        
        elements_summary = "\n".join([
            f"- [{el['id']}] <{el['tag']}> \"{el['text']}\"" + (f" (href: {el['href']})" if el.get('href') else "")
            for el in visible_elements
        ]) if visible_elements else "No obvious interactive elements identified via DOM."

        # 3. Build prompt
        error_context = f"\nWARNING: Your previous action failed: {last_error}. Pick a different visible element or approach.\n" if last_error else ""

        prompt = f"""You are testing a website as a UX persona.
Task: {task}
Persona: {persona}
Behavior guidance: {persona_guide}
{error_context}
CURRENTLY VISIBLE INTERACTIVE ELEMENTS ON SCREEN:
{elements_summary}

Analyze the screenshot and the list of currently visible elements above.
Decide the next action to make progress on the task according to your persona.
- If the task is already satisfied on this page, choose "done".
- If you are completely blocked or frustrated with no way forward, choose "abort".
- To interact, prefer using the element ID from the list (e.g. "uxg-1" or "[data-uxg-id=\"uxg-1\"]") or a visible selector.

Respond ONLY in valid JSON format with the following keys:
- "thought": A 1-2 sentence explanation of your observation and reasoning.
- "action": One of ["click", "type", "done", "abort"].
- "target": The element ID or CSS selector (or empty string if done/abort).
- "value": The text to type (if action is "type").
"""
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model="qwen/qwen3.8-27b",
                messages=[
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
                ],
                response_format={"type": "json_object"},
                max_tokens=300,
            )

            decision = json.loads(response.choices[0].message.content)

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
            elif action in ("click", "type"):
                action_desc = f"Clicking element '{target}'" if action == "click" else f"Typing '{value}' into '{target}'"
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
                "thought": f"Error during decision or execution: {str(e)}",
                "screenshot": base64_image
            })
            break

    await queue.put({"thought": "Agent loop finished."})
    await queue.put({"done": True})

