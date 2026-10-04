import os
import asyncio
import base64
import json
from groq import Groq
from playwright.async_api import Page
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

async def run_agent_loop(page: Page, task: str, persona: str, queue: asyncio.Queue):
    await queue.put({"thought": f"Initializing agent as {persona} persona for task: '{task}'"})
    
    for step in range(10): # limit to 10 steps for POC
        await asyncio.sleep(2) # wait for page to settle
        
        # Take screenshot
        screenshot_bytes = await page.screenshot(type="jpeg", quality=50)
        base64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        await queue.put({"thought": "Analyzing page structure and taking screenshot..."})
        
        # Build prompt
        prompt = f"""
You are testing a website. 
Task: {task}
Persona: {persona} (act according to this persona's behavior)

Analyze the screenshot and decide the next action.
Respond ONLY in valid JSON format with the following keys:
- "thought": A short explanation of your reasoning.
- "action": One of ["click", "type", "done", "abort"].
- "target": A CSS selector for the element to interact with (or empty string if done/abort).
- "value": The text to type (if action is "type").
"""
        try:
            # We run the synchronous Groq client in a thread pool to avoid blocking the event loop
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model="llama-3.2-90b-vision-preview",
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
            
            await queue.put({"thought": f"Decided: {thought}"})
            
            if action == "done":
                await queue.put({"thought": "Task completed successfully."})
                break
            elif action == "abort":
                await queue.put({"thought": "Aborting task due to friction or confusion."})
                break
            elif action == "click":
                await queue.put({"thought": f"Executing: Clicking element '{target}'"})
                if target:
                    await page.click(target, timeout=5000)
            elif action == "type":
                await queue.put({"thought": f"Executing: Typing '{value}' into '{target}'"})
                if target:
                    await page.fill(target, value, timeout=5000)
                    
        except Exception as e:
            await queue.put({"thought": f"Error during decision or execution: {str(e)}"})
            break
            
    await queue.put({"thought": "Agent loop finished."})
    await queue.put({"done": True})
