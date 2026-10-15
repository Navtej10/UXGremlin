import asyncio
import json
import sys
import threading
import queue as stdlib_queue
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from agent import run_agent_loop

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

# Thread-safe queue: Playwright thread puts messages, SSE generator reads them.
message_queue: stdlib_queue.Queue | None = None


# ---------------------------------------------------------------------------
# Playwright runs in a dedicated thread with its own ProactorEventLoop so it
# can spawn subprocesses on Windows regardless of what loop uvicorn uses.
# ---------------------------------------------------------------------------

def _playwright_thread(req: LaunchRequest, q: stdlib_queue.Queue):
    """Entry point for the Playwright worker thread."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_browser(req, q))
    finally:
        loop.close()


async def _run_browser(req: LaunchRequest, q: stdlib_queue.Queue):
    """Async work that runs inside the Playwright thread's own loop."""
    print(f"Launching browser for URL: {req.url}")

    # Wrap the stdlib queue so the agent can `await queue.put()`
    class _AsyncQueueAdapter:
        """Thin adapter: makes a thread-safe stdlib Queue look like asyncio.Queue."""
        def __init__(self, sync_q: stdlib_queue.Queue):
            self._q = sync_q
        async def put(self, item):
            self._q.put(item)

    adapter = _AsyncQueueAdapter(q)

    try:
        target_url = req.url.strip()
        if not target_url.startswith(("http://", "https://")):
            target_url = "https://" + target_url

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page(viewport={"width": 1280, "height": 800})
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

            await run_agent_loop(page, req.task, req.persona, adapter)

            print("Navigation complete. Waiting 2 seconds before closing...")
            await asyncio.sleep(2)
            await browser.close()
    except Exception as e:
        print(f"Error launching browser: {e}")
        q.put({"thought": f"Fatal error: {e}"})

    # Always signal completion so the SSE generator stops.
    q.put({"done": True})


# ---------------------------------------------------------------------------
# SSE streaming – reads from the thread-safe queue on the uvicorn loop.
# ---------------------------------------------------------------------------

async def event_generator():
    global message_queue
    if message_queue is None:
        return

    loop = asyncio.get_event_loop()
    while True:
        # Non-blocking read from the stdlib queue, yielding control back to
        # the event loop between checks so uvicorn stays responsive.
        data = await loop.run_in_executor(None, message_queue.get)
        yield f"data: {json.dumps(data)}\n\n"
        if data.get("done"):
            break


@app.get("/api/stream")
async def stream_events(request: Request):
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/launch")
async def launch_agent(req: LaunchRequest):
    global message_queue
    # Fresh queue for each run.
    message_queue = stdlib_queue.Queue()
    t = threading.Thread(target=_playwright_thread, args=(req, message_queue), daemon=True)
    t.start()
    return {"status": "started", "message": f"Browser launching for {req.url}"}


if __name__ == "__main__":
    import uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)

