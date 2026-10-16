import asyncio
import json
import sys
import threading
import queue as stdlib_queue
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import uuid
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from agent import run_agent_loop, LAST_REPORT
from scoring import aggregate_run_reports
from personas import get_persona_config

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
    session_id: str | None = None
    baseline: bool = True
    runs: int = 1

# In-memory session store mapping session_id -> session data dict
sessions: dict[str, dict] = {}

# Thread-safe queue fallback
message_queue: stdlib_queue.Queue | None = None


# ---------------------------------------------------------------------------
# Playwright runs in a dedicated thread with its own ProactorEventLoop so it
# can spawn subprocesses on Windows regardless of what loop uvicorn uses.
# ---------------------------------------------------------------------------

def _playwright_thread(req: LaunchRequest, q: stdlib_queue.Queue, session_id: str):
    """Entry point for the Playwright worker thread."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_browser(req, q, session_id))
    finally:
        loop.close()


async def _run_baseline_phase(browser, target_url: str, task: str, queue_adapter, session_id: str, sess: dict | None):
    from baseline_cache import get_cached_baseline, save_baseline

    cached = get_cached_baseline(target_url, task)
    if cached is not None:
        if cached.get("completed"):
            expected_steps = cached.get("expected_steps") or 1
            if sess is not None:
                sess["expected_steps"] = expected_steps
                sess["baseline_path"] = cached.get("path", [])
                sess["baseline_failed"] = False
            await queue_adapter.put({
                "thought": f"Baseline loaded from cache ({expected_steps} steps expected).",
                "phase": "baseline",
                "cached": True,
                "expected_steps": expected_steps,
                "session_id": session_id,
            })
            return
        else:
            if sess is not None:
                sess["expected_steps"] = None
                sess["baseline_failed"] = True
                sess["baseline_note"] = "task may be unreachable or unclear"
            await queue_adapter.put({
                "thought": "Cached baseline indicates task may be unreachable or unclear. Falling back to heuristic.",
                "phase": "baseline",
                "cached": True,
                "baseline_failed": True,
                "session_id": session_id,
            })
            return

    # Stream "Running baseline..." status over SSE
    await queue_adapter.put({
        "thought": "Running baseline...",
        "phase": "baseline",
        "session_id": session_id,
    })

    baseline_page = await browser.new_page(viewport={"width": 1280, "height": 800})
    try:
        await baseline_page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        baseline_sess = {"steps": []}

        class _BaselineQueueAdapter:
            def __init__(self, parent_adapter):
                self._parent = parent_adapter
            async def put(self, item):
                thought = item.get("thought", "")
                if thought and not item.get("done"):
                    await self._parent.put({
                        "thought": f"[Baseline] {thought}",
                        "phase": "baseline",
                        "screenshot": item.get("screenshot"),
                        "session_id": session_id,
                    })

        b_adapter = _BaselineQueueAdapter(queue_adapter)
        await run_agent_loop(
            baseline_page,
            task,
            "baseline",
            b_adapter,
            max_steps=12,
            session_id=session_id,
            session_data=baseline_sess,
        )

        is_completed = (baseline_sess.get("outcome") == "completed")
        steps = baseline_sess.get("steps", [])
        path = [
            {
                "step": getattr(s, "n", i + 1) if not isinstance(s, dict) else s.get("n", i + 1),
                "action": getattr(s, "action", "") if not isinstance(s, dict) else s.get("action", ""),
                "target": getattr(s, "label", "") if not isinstance(s, dict) else s.get("label", ""),
                "url": getattr(s, "url", "") if not isinstance(s, dict) else s.get("url", ""),
            }
            for i, s in enumerate(steps)
        ]

        if is_completed:
            expected_steps = max(1, len(steps))
            save_baseline(target_url, task, expected_steps, path, completed=True)
            if sess is not None:
                sess["expected_steps"] = expected_steps
                sess["baseline_path"] = path
                sess["baseline_failed"] = False
            await queue_adapter.put({
                "thought": f"Baseline established in {expected_steps} step(s). Starting persona attack...",
                "phase": "baseline",
                "expected_steps": expected_steps,
                "session_id": session_id,
            })
        else:
            error_msg = baseline_sess.get("outcome_reason") or "task may be unreachable or unclear"
            save_baseline(target_url, task, None, path, completed=False, error=error_msg)
            if sess is not None:
                sess["expected_steps"] = None
                sess["baseline_failed"] = True
                sess["baseline_note"] = "task may be unreachable or unclear"
                sess["baseline_path"] = path
            await queue_adapter.put({
                "thought": "Baseline failed: task may be unreachable or unclear. Falling back to heuristic.",
                "phase": "baseline",
                "baseline_failed": True,
                "session_id": session_id,
            })
    except Exception as e:
        print(f"Baseline error: {e}")
        save_baseline(target_url, task, None, [], completed=False, error=str(e))
        if sess is not None:
            sess["expected_steps"] = None
            sess["baseline_failed"] = True
            sess["baseline_note"] = "task may be unreachable or unclear"
        await queue_adapter.put({
            "thought": f"Baseline error ({e}): task may be unreachable or unclear. Falling back to heuristic.",
            "phase": "baseline",
            "baseline_failed": True,
            "session_id": session_id,
        })
    finally:
        try:
            await baseline_page.close()
        except Exception:
            pass


async def _run_browser(req: LaunchRequest, q: stdlib_queue.Queue, session_id: str):
    """Async work that runs inside the Playwright thread's own loop."""
    print(f"Launching browser for URL: {req.url} (session: {session_id})")

    # Wrap the stdlib queue so the agent can `await queue.put()`
    class _AsyncQueueAdapter:
        """Thin adapter: makes a thread-safe stdlib Queue look like asyncio.Queue."""
        def __init__(self, sync_q: stdlib_queue.Queue):
            self._q = sync_q
        async def put(self, item):
            self._q.put(item)

    adapter = _AsyncQueueAdapter(q)
    sess = sessions.get(session_id)
    total_runs = max(1, min(3, int(getattr(req, "runs", 1) or 1)))

    try:
        target_url = req.url.strip()
        if not target_url.startswith(("http://", "https://")):
            target_url = "https://" + target_url

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)

            # Optional baseline phase (default True)
            if getattr(req, "baseline", True):
                await _run_baseline_phase(browser, target_url, req.task, adapter, session_id, sess)

            run_reports = []
            all_steps = []

            for run_idx in range(1, total_runs + 1):
                if total_runs > 1:
                    await adapter.put({
                        "thought": f"--- Starting Run {run_idx} of {total_runs} (Persona: {req.persona}) ---",
                        "phase": "attack",
                        "run": run_idx,
                        "total_runs": total_runs,
                        "session_id": session_id,
                    })

                persona_cfg = get_persona_config(req.persona)
                page = await browser.new_page(
                    viewport=persona_cfg.viewport,
                    is_mobile=persona_cfg.is_mobile,
                    has_touch=persona_cfg.has_touch,
                )
                await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

                run_sess = {
                    "session_id": session_id,
                    "url": target_url,
                    "task": req.task,
                    "persona": req.persona,
                    "expected_steps": sess.get("expected_steps") if sess else None,
                    "baseline_failed": sess.get("baseline_failed", False) if sess else False,
                    "baseline_note": sess.get("baseline_note", "") if sess else "",
                    "baseline_path": sess.get("baseline_path", []) if sess else [],
                    "steps": [],
                }

                report = await run_agent_loop(
                    page,
                    req.task,
                    req.persona,
                    adapter,
                    session_id=session_id,
                    session_data=run_sess,
                    emit_done=False,
                )

                if report:
                    run_reports.append(report)
                if run_sess.get("steps"):
                    all_steps.extend(run_sess["steps"])

                try:
                    await page.close()
                except Exception:
                    pass

                if run_idx < total_runs:
                    await asyncio.sleep(1)

            # Aggregate reports when runs > 1
            if total_runs > 1 and run_reports:
                final_report = aggregate_run_reports(run_reports, runs=total_runs)
            elif run_reports:
                final_report = run_reports[-1]
            else:
                final_report = sess.get("report") if sess else {}

            if sess is not None:
                sess["report"] = final_report
                sess["steps"] = all_steps if all_steps else sess.get("steps", [])
                sess["status"] = final_report.get("status", "completed")
                sess["outcome"] = final_report.get("outcome", "completed")
                sess["outcome_reason"] = final_report.get("outcome_reason", "")
                sess["claimed_outcome"] = final_report.get("claimed_outcome", "completed")
                sess["verified_outcome"] = final_report.get("verified_outcome", "completed")

            LAST_REPORT.clear()
            if final_report:
                LAST_REPORT.update(final_report)

            print("Navigation complete. Waiting 2 seconds before closing...")
            await asyncio.sleep(2)
            await browser.close()
    except Exception as e:
        print(f"Error launching browser: {e}")
        q.put({"thought": f"Fatal error: {e}", "session_id": session_id})
        if sess is not None:
            sess["status"] = "failed"
            sess["outcome"] = "error"
            sess["outcome_reason"] = f"Fatal browser error: {e}"
            sess["claimed_outcome"] = "error"
            sess["verified_outcome"] = "error"

    # Always signal completion so the SSE generator stops.
    q.put({
        "done": True,
        "session_id": session_id,
        "outcome": sess.get("outcome", "error") if sess else "error",
        "outcome_reason": sess.get("outcome_reason", "") if sess else "",
        "claimed_outcome": sess.get("claimed_outcome", "error") if sess else "error",
        "verified_outcome": sess.get("verified_outcome", "error") if sess else "error",
    })


# ---------------------------------------------------------------------------
# SSE streaming – reads from the thread-safe queue on the uvicorn loop.
# ---------------------------------------------------------------------------

async def event_generator(q: stdlib_queue.Queue):
    loop = asyncio.get_event_loop()
    while True:
        # Non-blocking read from the stdlib queue, yielding control back to
        # the event loop between checks so uvicorn stays responsive.
        data = await loop.run_in_executor(None, q.get)
        yield f"data: {json.dumps(data)}\n\n"
        if data.get("done"):
            break


@app.get("/api/stream")
async def stream_events(request: Request, session_id: str | None = None):
    q = None
    if session_id and session_id in sessions:
        q = sessions[session_id]["queue"]
    elif message_queue is not None:
        q = message_queue
    else:
        q = stdlib_queue.Queue()
        q.put({"thought": "No active session stream found.", "done": True})

    return StreamingResponse(event_generator(q), media_type="text/event-stream")


@app.get("/api/report")
async def get_report(session_id: str | None = None):
    if session_id:
        sess = sessions.get(session_id)
        if not sess:
            return {"error": "Session not found", "session_id": session_id}
        if sess.get("report"):
            return sess["report"]
        return {
            "session_id": session_id,
            "status": sess.get("status", "running"),
            "outcome": sess.get("outcome"),
            "outcome_reason": sess.get("outcome_reason", ""),
            "claimed_outcome": sess.get("claimed_outcome"),
            "verified_outcome": sess.get("verified_outcome"),
            "url": sess.get("url"),
            "task": sess.get("task"),
            "persona": sess.get("persona"),
            "score": None,
            "actions": [],
        }

    # Fallback to LAST_REPORT or the latest session report
    if LAST_REPORT:
        return LAST_REPORT
    for sess in reversed(list(sessions.values())):
        if sess.get("report"):
            return sess["report"]
    return {}


@app.post("/api/launch")
@app.post("/api/start-session")
async def launch_agent(req: LaunchRequest):
    global message_queue
    session_id = req.session_id or uuid.uuid4().hex[:12]
    q = stdlib_queue.Queue()
    message_queue = q  # Backwards compatibility

    runs = max(1, min(3, int(getattr(req, "runs", 1) or 1)))

    sessions[session_id] = {
        "session_id": session_id,
        "url": req.url,
        "task": req.task,
        "persona": req.persona,
        "baseline": req.baseline,
        "runs": runs,
        "expected_steps": None,
        "baseline_path": [],
        "baseline_failed": False,
        "baseline_note": "",
        "status": "running",
        "outcome": None,
        "outcome_reason": "",
        "claimed_outcome": None,
        "verified_outcome": None,
        "steps": [],
        "report": None,
        "queue": q,
    }

    LAST_REPORT.clear()
    t = threading.Thread(target=_playwright_thread, args=(req, q, session_id), daemon=True)
    t.start()
    return {
        "status": "started",
        "session_id": session_id,
        "url": req.url,
        "task": req.task,
        "persona": req.persona,
        "baseline": req.baseline,
        "runs": runs,
        "message": f"Browser launching for {req.url}",
    }


if __name__ == "__main__":
    import uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)

