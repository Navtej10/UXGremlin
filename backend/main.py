from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
import asyncio
import json

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

# Mock stream logic for Slice 3
async def event_generator():
    messages = [
        "Analyzing page structure...",
        "Identifying primary navigation elements...",
        "Decided: Clicking 'Sign up' button in top right.",
        "Waiting for next page to load...",
        "Looking for pricing plans..."
    ]
    for msg in messages:
        await asyncio.sleep(2)
        yield f"data: {json.dumps({'thought': msg})}\n\n"

@app.get("/api/stream")
async def stream_events(request: Request):
    return StreamingResponse(event_generator(), media_type="text/event-stream")

async def launch_browser_task(req: LaunchRequest):
    print(f"Launching browser for URL: {req.url}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            await page.goto(req.url)
            print("Navigation complete. Waiting 10 seconds before closing...")
            await page.wait_for_timeout(10000)
            await browser.close()
    except Exception as e:
        print(f"Error launching browser: {e}")

@app.post("/api/launch")
async def launch_agent(req: LaunchRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(launch_browser_task, req)
    return {"status": "started", "message": f"Browser launching for {req.url}"}
