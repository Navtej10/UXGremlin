import asyncio
import json
import sys
import threading
import queue as stdlib_queue
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, Response
import uuid
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from agent import run_agent_loop, LAST_REPORT
from scoring import aggregate_run_reports, compute_friction
from evidence import detect_findings_from_evidence, attach_screenshots_with_bounding_boxes
from personas import get_persona_config, PERSONAS
from security import (
    validate_target_url,
    setup_route_interception,
    setup_download_and_file_guards,
    session_rate_limiter,
    apply_session_security_caps,
    MAX_STEPS_CAP,
    MAX_SESSION_DURATION_SECONDS,
)
from storage import (
    init_db,
    save_session,
    save_report,
    get_session as get_db_session,
    get_report as get_db_report,
    compute_report_delta,
)
from export_html import generate_printable_html

# Initialize SQLite database
init_db()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_client_ip(request: Request) -> str:
    """Extracts client IP, respecting X-Forwarded-For if behind a proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class LaunchRequest(BaseModel):
    url: str
    task: str
    persona: str | None = None
    personas: list[str] | None = None
    session_id: str | None = None
    previous_session_id: str | None = None
    baseline: bool = True
    runs: int = 1
    max_steps: int | None = None
    max_duration: float | None = None

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
    await setup_route_interception(baseline_page)
    await setup_download_and_file_guards(baseline_page)
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


class _PersonaQueueAdapter:
    """Queue adapter that enriches every event with persona_id, persona, and session_id."""
    def __init__(self, parent_adapter, persona_id: str, session_id: str):
        self._parent = parent_adapter
        self.persona_id = persona_id
        self.session_id = session_id

    async def put(self, item: dict):
        enriched = dict(item)
        enriched.setdefault("persona_id", self.persona_id)
        enriched.setdefault("persona", self.persona_id)
        enriched.setdefault("session_id", self.session_id)
        await self._parent.put(enriched)


def _extract_top_finding(findings: list[dict]) -> str:
    if not findings:
        return "No critical friction found"
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_f = sorted(findings, key=lambda f: severity_rank.get(str(f.get("severity", "medium")).lower(), 4))
    top = sorted_f[0]
    return top.get("title") or top.get("what_happened", "Friction encountered")


def _aggregate_comparison(persona_reports: dict, personas: list[str]) -> tuple[dict, list]:
    """Aggregates a comparison object {persona: score, outcome, steps, top_finding}."""
    comparison = {}
    comparison_summary = []
    for p_id in personas:
        rep = persona_reports.get(p_id, {})
        p_cfg = get_persona_config(p_id)

        if isinstance(rep.get("score"), dict):
            score_val = rep["score"].get("total", 0)
        elif isinstance(rep.get("score"), (int, float)):
            score_val = int(rep["score"])
        else:
            score_val = 0

        outcome_val = rep.get("outcome", "completed")
        actions = rep.get("actions", [])
        if isinstance(rep.get("score"), dict) and "steps_taken" in rep["score"]:
            steps_count = rep["score"]["steps_taken"]
        else:
            steps_count = len(actions)

        top_finding = _extract_top_finding(rep.get("findings", []))

        entry = {
            "persona": p_id,
            "persona_label": p_cfg.label if p_cfg else p_id,
            "score": score_val,
            "outcome": outcome_val,
            "steps": steps_count,
            "top_finding": top_finding,
        }
        comparison[p_id] = entry
        comparison_summary.append(entry)
    return comparison, comparison_summary


def _handle_run_exception(p_id: str, exc: Exception, steps: list, target_url: str) -> dict:
    err_str = str(exc)
    is_timeout = "timeout" in err_str.lower()
    is_beginning = (len(steps) == 0)

    if is_beginning:
        return {
            "persona": p_id,
            "status": "error_at_beginning",
            "error_at_beginning": True,
            "prompt_rerun": True,
            "rerun_prompt": f"The test could not start due to an error: {err_str}. Please verify that the target URL is accessible and rerun the test.",
            "error": err_str,
            "outcome": "error",
            "outcome_reason": f"Failed to start: {err_str}",
            "score": {
                "score": 0,
                "total": 0,
                "label": "Error",
                "parts": [],
                "breakdown": [],
                "steps_taken": 0,
                "ideal_steps": 1,
            },
            "findings": [{
                "title": "Test Failed to Start",
                "severity": "critical",
                "evidence_steps": [],
                "what_happened": f"An error occurred before testing could begin: {err_str}",
                "impact": "No steps could be executed on the target application.",
                "recommendation": "Check that the target server is running and accessible, then rerun the test.",
            }],
            "actions": [],
            "verdict": f"The test failed to start: {err_str}. Please check the target application and rerun the test.",
        }
    else:
        # Score based strictly on findings and evidence up to then!
        score = compute_friction({
            "steps": steps,
            "outcome": "timeout" if is_timeout else "system_error",
            "outcome_reason": err_str,
            "is_system_error": True,
        })
        findings = detect_findings_from_evidence({"steps": steps})
        attach_screenshots_with_bounding_boxes(findings, steps)
        findings.append({
            "title": f"Audit Interrupted: {'Timeout' if is_timeout else 'System Error'}",
            "severity": "info",
            "evidence_steps": [getattr(s, "n", i + 1) if not isinstance(s, dict) else s.get("n", i + 1) for i, s in enumerate(steps)],
            "what_happened": f"Audit concluded early at step {len(steps)} due to {'timeout' if is_timeout else 'system error'}: {err_str}",
            "impact": f"Evaluated UX through {len(steps)} step(s). Score reflects findings up to this point.",
            "recommendation": f"Review findings up to step {len(steps)} or rerun test to proceed further.",
        })
        actions = [
            {
                "step_number": getattr(s, "n", i + 1) if not isinstance(s, dict) else s.get("n", i + 1),
                "action": getattr(s, "action", "") if not isinstance(s, dict) else s.get("action", ""),
                "target": getattr(s, "label", "") if not isinstance(s, dict) else s.get("label", ""),
                "thought": getattr(s, "thought", "") if not isinstance(s, dict) else s.get("thought", ""),
                "screenshot": getattr(s, "screenshot", None) if not isinstance(s, dict) else s.get("screenshot"),
                "ok": getattr(s, "ok", False) if not isinstance(s, dict) else s.get("ok", False),
                "url": getattr(s, "url", "") if not isinstance(s, dict) else s.get("url", ""),
                "url_after": getattr(s, "url_after", "") if not isinstance(s, dict) else s.get("url_after", ""),
                "friction_type": getattr(s, "friction_type", None) if not isinstance(s, dict) else s.get("friction_type"),
                "friction_note": getattr(s, "friction_note", "") if not isinstance(s, dict) else s.get("friction_note", ""),
            }
            for i, s in enumerate(steps)
        ]
        return {
            "persona": p_id,
            "status": "timeout" if is_timeout else "system_error",
            "outcome": "timeout" if is_timeout else "system_error",
            "outcome_reason": f"Interrupted at step {len(steps)}: {err_str}",
            "score": score,
            "findings": findings,
            "actions": actions,
            "verdict": f"The test concluded early at step {len(steps)} due to {'timeout' if is_timeout else 'system error'}. Score ({score['total']}/100) is based on findings up to that point.",
        }


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
    personas = req.personas if (req.personas and len(req.personas) > 0) else [req.persona or "pro_tester"]
    is_compare_mode = len(personas) > 1

    try:
        target_url = req.url.strip()
        if not target_url.startswith(("http://", "https://")):
            target_url = "https://" + target_url

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)

            # Optional baseline phase (default True)
            if getattr(req, "baseline", True):
                await _run_baseline_phase(browser, target_url, req.task, adapter, session_id, sess)

            if is_compare_mode:
                # Concurrency cap of 3 to respect LLM limits
                sem = asyncio.Semaphore(3)
                persona_reports: dict[str, dict] = {}
                all_steps = []

                async def _run_single_persona(p_id: str):
                    async with sem:
                        p_adapter = _PersonaQueueAdapter(adapter, p_id, session_id)
                        persona_cfg = get_persona_config(p_id)

                        await p_adapter.put({
                            "thought": f"Initializing agent as {persona_cfg.label} ({p_id})...",
                            "phase": "attack",
                            "persona_id": p_id,
                            "persona": p_id,
                            "session_id": session_id,
                        })

                        context = await browser.new_context(
                            viewport=persona_cfg.viewport,
                            is_mobile=persona_cfg.is_mobile,
                            has_touch=persona_cfg.has_touch,
                        )
                        page = await context.new_page()
                        await setup_route_interception(page)
                        await setup_download_and_file_guards(page)

                        persona_sess = {
                            "session_id": session_id,
                            "url": target_url,
                            "task": req.task,
                            "persona": p_id,
                            "expected_steps": sess.get("expected_steps") if sess else None,
                            "baseline_failed": sess.get("baseline_failed", False) if sess else False,
                            "baseline_note": sess.get("baseline_note", "") if sess else "",
                            "baseline_path": sess.get("baseline_path", []) if sess else [],
                            "steps": [],
                        }

                        try:
                            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                            rep = await run_agent_loop(
                                page,
                                req.task,
                                p_id,
                                p_adapter,
                                max_steps=getattr(req, "max_steps", None) or 15,
                                max_duration=getattr(req, "max_duration", None) or MAX_SESSION_DURATION_SECONDS,
                                session_id=session_id,
                                session_data=persona_sess,
                                emit_done=False,
                            )
                            await p_adapter.put({
                                "thought": f"Completed audit for {persona_cfg.label} ({p_id}).",
                                "phase": "persona_done",
                                "persona_id": p_id,
                                "persona": p_id,
                                "persona_done": True,
                                "session_id": session_id,
                            })
                            return p_id, rep, persona_sess
                        except Exception as e:
                            print(f"Error in persona {p_id}: {e}")
                            steps = persona_sess.get("steps", [])
                            err_rep = _handle_run_exception(p_id, e, steps, target_url)
                            await p_adapter.put({
                                "thought": f"Persona {p_id} encountered {'error' if len(steps) == 0 else 'early ending'}: {e}",
                                "error": str(e),
                                "error_at_beginning": err_rep.get("error_at_beginning", False),
                                "prompt_rerun": err_rep.get("prompt_rerun", False),
                                "rerun_prompt": err_rep.get("rerun_prompt"),
                                "persona_id": p_id,
                                "persona": p_id,
                                "persona_done": True,
                                "session_id": session_id,
                            })
                            return p_id, err_rep, persona_sess
                        finally:
                            try:
                                await page.close()
                            except Exception:
                                pass
                            try:
                                await context.close()
                            except Exception:
                                pass

                persona_tasks = [_run_single_persona(p) for p in personas]
                results = await asyncio.gather(*persona_tasks, return_exceptions=True)

                for res in results:
                    if isinstance(res, Exception):
                        print(f"Persona task returned exception: {res}")
                        continue
                    p_id, p_rep, p_sess = res
                    if p_rep:
                        persona_reports[p_id] = p_rep
                    if p_sess.get("steps"):
                        all_steps.extend(p_sess["steps"])

                comparison, comparison_summary = _aggregate_comparison(persona_reports, personas)

                primary_id = personas[0]
                primary_rep = persona_reports.get(primary_id, {})

                all_findings = []
                seen_titles = set()
                for p_id in personas:
                    r = persona_reports.get(p_id, {})
                    for f in r.get("findings", []):
                        t = f.get("title", "")
                        if t and t not in seen_titles:
                            seen_titles.add(t)
                            f_copy = dict(f)
                            f_copy.setdefault("discovered_by", p_id)
                            all_findings.append(f_copy)

                final_report = {
                    "session_id": session_id,
                    "url": target_url,
                    "task": req.task,
                    "persona": primary_id,
                    "personas": personas,
                    "is_compare": True,
                    "comparison": comparison,
                    "comparison_summary": comparison_summary,
                    "persona_reports": persona_reports,
                    "score": primary_rep.get("score", {"total": 0, "label": "Low", "parts": [], "steps_taken": 0, "ideal_steps": 1}),
                    "verdict": f"Comparison across {len(personas)} personas completed.",
                    "findings": all_findings if all_findings else primary_rep.get("findings", []),
                    "actions": primary_rep.get("actions", []),
                    "outcome": "completed" if any(r.get("outcome") == "completed" for r in persona_reports.values()) else primary_rep.get("outcome", "completed"),
                    "outcome_reason": primary_rep.get("outcome_reason", ""),
                    "claimed_outcome": primary_rep.get("claimed_outcome", "completed"),
                    "verified_outcome": primary_rep.get("verified_outcome", "completed"),
                    "baseline_failed": sess.get("baseline_failed", False) if sess else False,
                    "baseline_note": sess.get("baseline_note", "") if sess else "",
                }

                is_all_beginning_error = all(r.get("error_at_beginning") for r in persona_reports.values()) if persona_reports else False
                if is_all_beginning_error:
                    first_err = next((r.get("error") for r in persona_reports.values() if r.get("error")), "An error occurred before testing could start.")
                    final_report["status"] = "error_at_beginning"
                    final_report["error_at_beginning"] = True
                    final_report["prompt_rerun"] = True
                    final_report["error"] = first_err
                    final_report["rerun_prompt"] = f"The test could not start due to an error: {first_err}. Please check your target URL and rerun the test."
                    final_report["verdict"] = f"The test could not start: {first_err}. Please verify the target application and rerun the test."
            else:
                p_id = personas[0]
                total_runs = max(1, min(3, int(getattr(req, "runs", 1) or 1)))
                run_reports = []
                all_steps = []
                p_adapter = _PersonaQueueAdapter(adapter, p_id, session_id)

                for run_idx in range(1, total_runs + 1):
                    if total_runs > 1:
                        await p_adapter.put({
                            "thought": f"--- Starting Run {run_idx} of {total_runs} (Persona: {p_id}) ---",
                            "phase": "attack",
                            "run": run_idx,
                            "total_runs": total_runs,
                            "session_id": session_id,
                            "persona_id": p_id,
                        })

                    persona_cfg = get_persona_config(p_id)
                    context = await browser.new_context(
                        viewport=persona_cfg.viewport,
                        is_mobile=persona_cfg.is_mobile,
                        has_touch=persona_cfg.has_touch,
                    )
                    page = await context.new_page()
                    await setup_route_interception(page)
                    await setup_download_and_file_guards(page)

                    run_sess = {
                        "session_id": session_id,
                        "url": target_url,
                        "task": req.task,
                        "persona": p_id,
                        "expected_steps": sess.get("expected_steps") if sess else None,
                        "baseline_failed": sess.get("baseline_failed", False) if sess else False,
                        "baseline_note": sess.get("baseline_note", "") if sess else "",
                        "baseline_path": sess.get("baseline_path", []) if sess else [],
                        "steps": [],
                    }

                    try:
                        await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                        report = await run_agent_loop(
                            page,
                            req.task,
                            p_id,
                            p_adapter,
                            max_steps=getattr(req, "max_steps", None) or 15,
                            max_duration=getattr(req, "max_duration", None) or MAX_SESSION_DURATION_SECONDS,
                            session_id=session_id,
                            session_data=run_sess,
                            emit_done=False,
                        )
                    except Exception as e:
                        print(f"Error in single run: {e}")
                        steps = run_sess.get("steps", [])
                        report = _handle_run_exception(p_id, e, steps, target_url)
                        await p_adapter.put({
                            "thought": f"Run encountered {'error' if len(steps) == 0 else 'early ending'}: {e}",
                            "error": str(e),
                            "error_at_beginning": report.get("error_at_beginning", False),
                            "prompt_rerun": report.get("prompt_rerun", False),
                            "rerun_prompt": report.get("rerun_prompt"),
                            "session_id": session_id,
                        })

                    if report:
                        run_reports.append(report)
                    if run_sess.get("steps"):
                        all_steps.extend(run_sess["steps"])

                    try:
                        await page.close()
                    except Exception:
                        pass
                    try:
                        await context.close()
                    except Exception:
                        pass

                    if run_idx < total_runs:
                        await asyncio.sleep(1)

                if total_runs > 1 and run_reports:
                    final_report = aggregate_run_reports(run_reports, runs=total_runs)
                elif run_reports:
                    final_report = run_reports[-1]
                else:
                    final_report = sess.get("report") if sess else {}

                if any(r.get("error_at_beginning") for r in run_reports) and not any(len(r.get("actions", [])) > 0 for r in run_reports):
                    first_err = next((r.get("error") for r in run_reports if r.get("error")), "An error occurred before testing could start.")
                    final_report["status"] = "error_at_beginning"
                    final_report["error_at_beginning"] = True
                    final_report["prompt_rerun"] = True
                    final_report["error"] = first_err
                    final_report["rerun_prompt"] = f"The test could not start due to an error: {first_err}. Please check your target URL and rerun the test."

                # Shallow copy to avoid self-referential circular cycles in persona_reports
                single_persona_rep = dict(final_report)
                single_persona_rep.pop("persona_reports", None)
                single_persona_rep.pop("comparison", None)
                single_persona_rep.pop("comparison_summary", None)

                comparison, comparison_summary = _aggregate_comparison({p_id: single_persona_rep}, [p_id])
                final_report["comparison"] = comparison
                final_report["comparison_summary"] = comparison_summary
                final_report["persona_reports"] = {p_id: single_persona_rep}
                final_report["personas"] = [p_id]
                final_report["is_compare"] = False

            if sess is not None:
                sess["report"] = final_report
                sess["comparison"] = final_report.get("comparison", {})
                sess["comparison_summary"] = final_report.get("comparison_summary", [])
                sess["persona_reports"] = final_report.get("persona_reports", {})
                sess["steps"] = all_steps if all_steps else sess.get("steps", [])
                sess["status"] = final_report.get("status", "completed")
                sess["error_at_beginning"] = final_report.get("error_at_beginning", False)
                sess["prompt_rerun"] = final_report.get("prompt_rerun", False)
                sess["rerun_prompt"] = final_report.get("rerun_prompt")
                sess["error"] = final_report.get("error")
                sess["outcome"] = final_report.get("outcome", "completed")
                sess["outcome_reason"] = final_report.get("outcome_reason", "")
                sess["claimed_outcome"] = final_report.get("claimed_outcome", "completed")
                sess["verified_outcome"] = final_report.get("verified_outcome", "completed")

            # Delta calculation if linked to a previous session
            prev_id = getattr(req, "previous_session_id", None) or (sess.get("previous_session_id") if sess else None)
            if prev_id and final_report:
                prev_rep = get_db_report(prev_id)
                if not prev_rep and prev_id in sessions:
                    prev_rep = sessions[prev_id].get("report")
                if prev_rep:
                    delta = compute_report_delta(prev_rep, final_report)
                    final_report["delta"] = delta
                    final_report["previous_session_id"] = prev_id
                    if sess is not None:
                        sess["delta"] = delta

            if final_report:
                _clean_report_cycles(final_report)
                try:
                    save_report(session_id, final_report)
                except Exception as ex:
                    print(f"Error saving report to SQLite: {ex}")

            LAST_REPORT.clear()
            if final_report:
                LAST_REPORT.update(final_report)

            print("Navigation complete. Waiting 2 seconds before closing...")
            await asyncio.sleep(2)
            await browser.close()
    except Exception as e:
        print(f"Error launching browser: {e}")
        err_str = str(e)
        q.put({
            "thought": f"Fatal browser error: {err_str}",
            "error": err_str,
            "error_at_beginning": True,
            "prompt_rerun": True,
            "rerun_prompt": f"Failed to start browser or navigate to target: {err_str}. Please verify that the target URL is accessible and rerun the test.",
            "session_id": session_id,
        })
        if sess is not None:
            sess["status"] = "error_at_beginning"
            sess["error_at_beginning"] = True
            sess["outcome"] = "error"
            sess["outcome_reason"] = f"Fatal browser error: {err_str}"
            sess["error"] = err_str
            sess["prompt_rerun"] = True
            sess["rerun_prompt"] = f"Failed to start browser or navigate to target: {err_str}. Please verify that the target URL is accessible and rerun the test."
            if not final_report:
                final_report = {
                    "session_id": session_id,
                    "url": req.url,
                    "task": req.task,
                    "persona": personas[0],
                    "personas": personas,
                    "status": "error_at_beginning",
                    "error_at_beginning": True,
                    "error": err_str,
                    "outcome": "error",
                    "outcome_reason": f"Fatal browser error: {err_str}",
                    "prompt_rerun": True,
                    "rerun_prompt": f"Failed to start browser or navigate to target: {err_str}. Please verify that the target URL is accessible and rerun the test.",
                    "score": {"score": 0, "total": 0, "label": "Error", "parts": [], "steps_taken": 0, "ideal_steps": 1},
                    "findings": [{
                        "title": "Test Failed to Start",
                        "severity": "critical",
                        "evidence_steps": [],
                        "what_happened": f"An error occurred before testing could begin: {err_str}",
                        "impact": "No steps could be executed on the target application.",
                        "recommendation": "Check that the target server is running and accessible, then rerun the test.",
                    }],
                    "actions": [],
                    "verdict": f"The test failed to start: {err_str}. Please check the target application and rerun the test.",
                }
            sess["report"] = final_report
            try:
                save_session(session_id, sess)
                if sess.get("report"):
                    save_report(session_id, sess["report"])
            except Exception:
                pass

    # Always signal completion so the SSE generator stops.
    q.put({
        "done": True,
        "session_id": session_id,
        "comparison": sess.get("comparison", {}) if sess else {},
        "comparison_summary": sess.get("comparison_summary", []) if sess else [],
        "outcome": sess.get("outcome", "error") if sess else "error",
        "outcome_reason": sess.get("outcome_reason", "") if sess else "",
        "claimed_outcome": sess.get("claimed_outcome", "error") if sess else "error",
        "verified_outcome": sess.get("verified_outcome", "error") if sess else "error",
        "error_at_beginning": sess.get("error_at_beginning", False) if sess else False,
        "prompt_rerun": sess.get("prompt_rerun", False) if sess else False,
        "rerun_prompt": sess.get("rerun_prompt") if sess else None,
        "error": sess.get("error") if sess else None,
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


def _clean_report_cycles(rep: dict) -> dict:
    """Safeguards against circular self-references in report dictionaries."""
    if not isinstance(rep, dict):
        return rep
    persona_reps = rep.get("persona_reports")
    if isinstance(persona_reps, dict):
        for pid, prep in list(persona_reps.items()):
            if prep is rep:
                # Break circular self-reference by creating a clean copy without persona_reports
                persona_reps[pid] = {k: v for k, v in rep.items() if k != "persona_reports"}
    return rep


def _fetch_report_dict(session_id: str | None = None) -> dict:
    if session_id:
        # 1. In-memory completed report
        sess = sessions.get(session_id)
        if sess and sess.get("report"):
            return _clean_report_cycles(sess["report"])
        # 2. SQLite persisted report
        db_rep = get_db_report(session_id)
        if db_rep:
            return _clean_report_cycles(db_rep)
        # 3. SQLite session metadata (in-progress or non-report status)
        db_sess = get_db_session(session_id)
        if db_sess:
            if db_sess.get("report"):
                return _clean_report_cycles(db_sess["report"])
            return {
                "session_id": session_id,
                "status": db_sess.get("status", "running"),
                "outcome": db_sess.get("outcome"),
                "outcome_reason": "",
                "url": db_sess.get("url"),
                "task": db_sess.get("task"),
                "persona": db_sess.get("persona"),
                "personas": db_sess.get("personas", []),
                "is_compare": db_sess.get("is_compare", False),
                "comparison": {},
                "comparison_summary": [],
                "persona_reports": {},
                "score": None,
                "actions": [],
                "findings": [],
            }
        # 4. In-memory session metadata (in-progress)
        if sess:
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
                "personas": sess.get("personas", []),
                "is_compare": sess.get("is_compare", False),
                "comparison": sess.get("comparison", {}),
                "comparison_summary": sess.get("comparison_summary", []),
                "persona_reports": sess.get("persona_reports", {}),
                "score": None,
                "actions": [],
                "findings": [],
            }
        return {"error": "Session not found", "session_id": session_id}

    # Fallback to LAST_REPORT or the latest session report
    if LAST_REPORT:
        return _clean_report_cycles(LAST_REPORT)
    for sess in reversed(list(sessions.values())):
        if sess.get("report"):
            return _clean_report_cycles(sess["report"])
    return {}


@app.get("/api/report")
async def get_report_query(session_id: str | None = None):
    return _fetch_report_dict(session_id)


@app.get("/api/report/{session_id}")
async def get_report_path(session_id: str):
    res = _fetch_report_dict(session_id)
    if res.get("error") == "Session not found":
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return res


@app.get("/api/report/{session_id}/export/json")
async def export_report_json(session_id: str):
    res = _fetch_report_dict(session_id)
    if res.get("error") == "Session not found" or (not res.get("score") and not res.get("comparison")):
        raise HTTPException(status_code=404, detail=f"Report not found for session '{session_id}'")
    
    json_bytes = json.dumps(res, indent=2).encode("utf-8")
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="uxgremlin-report-{session_id}.json"'
        }
    )


@app.get("/api/report/{session_id}/export/html")
async def export_report_html(session_id: str):
    res = _fetch_report_dict(session_id)
    if res.get("error") == "Session not found" or (not res.get("score") and not res.get("comparison")):
        raise HTTPException(status_code=404, detail=f"Report not found for session '{session_id}'")
    
    html_content = generate_printable_html(res)
    return HTMLResponse(content=html_content)


@app.get("/report/{session_id}")
async def view_report_direct(session_id: str):
    res = _fetch_report_dict(session_id)
    if res.get("error") == "Session not found":
        raise HTTPException(status_code=404, detail=f"Report not found for session '{session_id}'")
    return HTMLResponse(content=generate_printable_html(res))


@app.post("/api/launch")
@app.post("/api/start-session")
async def launch_agent(req: LaunchRequest, request: Request):
    # 1. Per-IP rate limit check
    client_ip = get_client_ip(request)
    allowed, remaining, reset_in = session_rate_limiter.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for IP '{client_ip}'. Try again in {int(reset_in)}s."
        )

    # 2. Target URL validation
    is_safe, error_msg = validate_target_url(req.url)
    if not is_safe:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid or forbidden target URL: {error_msg}"
        )

    # 3. Security caps on steps and duration
    capped_steps, capped_duration = apply_session_security_caps(req.max_steps, req.max_duration)
    req.max_steps = capped_steps
    req.max_duration = capped_duration

    # 4. Persona normalization
    valid_personas = []
    if req.personas and len(req.personas) > 0:
        for p in req.personas:
            p_clean = str(p).strip()
            if p_clean in PERSONAS and p_clean not in valid_personas:
                valid_personas.append(p_clean)
        if not valid_personas:
            raise HTTPException(
                status_code=400,
                detail=f"No valid personas provided in 'personas' list. Valid personas: {list(PERSONAS.keys())}"
            )
        req.personas = valid_personas
        if not req.persona or req.persona not in valid_personas:
            req.persona = valid_personas[0]
    elif req.persona:
        p_clean = str(req.persona).strip()
        if p_clean not in PERSONAS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid persona '{req.persona}'. Valid personas: {list(PERSONAS.keys())}"
            )
        req.persona = p_clean
        req.personas = [p_clean]
    else:
        req.persona = "pro_tester"
        req.personas = ["pro_tester"]

    global message_queue
    # Short 8-char hex session ID for clean shareable URLs
    session_id = req.session_id or uuid.uuid4().hex[:8]
    q = stdlib_queue.Queue()
    message_queue = q  # Backwards compatibility

    runs = max(1, min(3, int(getattr(req, "runs", 1) or 1)))
    is_compare = len(req.personas) > 1

    sessions[session_id] = {
        "session_id": session_id,
        "previous_session_id": req.previous_session_id,
        "url": req.url,
        "task": req.task,
        "persona": req.persona,
        "personas": req.personas,
        "is_compare": is_compare,
        "baseline": req.baseline,
        "runs": runs,
        "max_steps": capped_steps,
        "max_duration": capped_duration,
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
        "comparison": {},
        "comparison_summary": [],
        "persona_reports": {},
        "queue": q,
    }

    try:
        save_session(session_id, sessions[session_id])
    except Exception as ex:
        print(f"Error persisting session to SQLite: {ex}")

    LAST_REPORT.clear()
    t = threading.Thread(target=_playwright_thread, args=(req, q, session_id), daemon=True)
    t.start()
    return {
        "status": "started",
        "session_id": session_id,
        "previous_session_id": req.previous_session_id,
        "url": req.url,
        "task": req.task,
        "persona": req.persona,
        "personas": req.personas,
        "is_compare": is_compare,
        "baseline": req.baseline,
        "runs": runs,
        "max_steps": capped_steps,
        "max_duration": capped_duration,
        "message": f"Browser launching for {req.url} ({len(req.personas)} persona(s))",
    }


if __name__ == "__main__":
    import uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)

