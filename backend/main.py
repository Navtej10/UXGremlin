import asyncio
import json
import sys
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from agent import run_agent_loop

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LaunchRequest(BaseModel):
    url: str
    task: str
    persona: str

# Global queue for the POC to stream messages
message_queue = None

async def event_generator():
    global message_queue
    if message_queue is None:
        message_queue = asyncio.Queue()
        
    while True:
        data = await message_queue.get()
        if data.get("done"):
            break
        yield f"data: {json.dumps(data)}\n\n"

@app.get("/api/stream")
async def stream_events(request: Request):
    return StreamingResponse(event_generator(), media_type="text/event-stream")

async def launch_browser_task(req: LaunchRequest):
    global message_queue
    if message_queue is None:
        message_queue = asyncio.Queue()
        
    print(f"Launching browser for URL: {req.url}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            await page.goto(req.url)
            
            await run_agent_loop(page, req.task, req.persona, message_queue)
            
            print("Navigation complete. Waiting 2 seconds before closing...")
            await asyncio.sleep(2)
            await browser.close()
    except Exception as e:
        print(f"Error launching browser: {e}")
        await message_queue.put({"thought": f"Fatal error: {e}", "done": True})

@app.post("/api/launch")
async def launch_agent(req: LaunchRequest, background_tasks: BackgroundTasks):
    global message_queue
    # Clear the queue for a new run
    message_queue = asyncio.Queue()
    background_tasks.add_task(launch_browser_task, req)
    return {"status": "started", "message": f"Browser launching for {req.url}"}

if __name__ == "__main__":
    import uvicorn
    # This guarantees the policy is set before Uvicorn creates any event loops
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
