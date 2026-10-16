import json
import time
from dataclasses import dataclass, field
from typing import Any
from evidence import (
    detect_findings_from_evidence,
    attach_screenshots_with_bounding_boxes,
    generate_suggested_fixes,
)

# ---------------------------------------------------------------------------
# Scoring Constants: Weights, Caps, and Thresholds
# ---------------------------------------------------------------------------

# Steps taken vs expected steps
WEIGHT_EXCESS_STEPS = 5
CAP_EXCESS_STEPS = 20

# Backtracks (returning to a previously visited URL)
WEIGHT_BACKTRACK = 8
CAP_BACKTRACK = 24

# Repeated actions (same action on same element 2+ times)
WEIGHT_REPEATED_ACTION = 6
CAP_REPEATED_ACTION = 18

# Dead clicks (click with no DOM or URL change)
WEIGHT_DEAD_CLICK = 7
CAP_DEAD_CLICK = 21

# Slow steps (time between action and stable page above threshold)
WEIGHT_SLOW_STEP = 5
CAP_SLOW_STEP = 15
SLOW_STEP_THRESHOLD_SECONDS = 3.0

# Console errors and failed network requests during the step
WEIGHT_CONSOLE_ERROR = 4
WEIGHT_NETWORK_FAILURE = 6
CAP_ERRORS = 20

# Task failure penalty based on outcome status
PENALTY_OUTCOME_ABANDONED = 35
PENALTY_OUTCOME_GAVE_UP = 35
PENALTY_OUTCOME_ERROR = 40
PENALTY_OUTCOME_MAX_STEPS = 30
PENALTY_OUTCOME_INCOMPLETE = 30
CAP_TASK_FAILURE = 40

# LLM-reported confusion points (small weight only)
WEIGHT_CONFUSION_POINT = 3
CAP_CONFUSION_POINT = 12

# Score Label Thresholds
# 0-20: Smooth, 21-45: Minor, 46-70: Moderate, 71-100: Severe
LABEL_SMOOTH_MAX = 20
LABEL_MINOR_MAX = 45
LABEL_MODERATE_MAX = 70

# Critical automated accessibility and layout violations
WEIGHT_CRITICAL_VIOLATION = 4
CAP_CRITICAL_VIOLATIONS = 20


@dataclass
class Step:
    n: int
    url: str
    action: str
    label: str
    ok: bool
    thought: str = ""
    url_after: str = ""
    friction_type: str | None = None
    friction_note: str = ""
    screenshot: str | None = None
    target: str = ""
    duration: float = 0.0
    dead_click: bool = False
    console_errors: list[str] = field(default_factory=list)
    failed_requests: list[str] = field(default_factory=list)
    dom_changed: bool | None = None
    axe_violations: list[dict] = field(default_factory=list)
    tap_targets: list[dict] = field(default_factory=list)
    contrast_issues: list[dict] = field(default_factory=list)
    overlapping_elements: list[dict] = field(default_factory=list)


def score_to_label(score: int) -> str:
    """
    Maps 0-100 deterministic friction score to standard label:
    0-20: Smooth
    21-45: Minor
    46-70: Moderate
    71-100: Severe
    """
    if score <= LABEL_SMOOTH_MAX:
        return "Smooth"
    elif score <= LABEL_MINOR_MAX:
        return "Minor"
    elif score <= LABEL_MODERATE_MAX:
        return "Moderate"
    else:
        return "Severe"


def _estimate_expected_steps(steps_taken: int) -> int:
    """Heuristic expected step budget when no baseline is provided."""
    if steps_taken <= 3:
        return max(1, steps_taken)
    return max(3, min(6, round(steps_taken * 0.6)))


def compute_friction(session: dict | list[Step] | Any, completed: bool | None = None) -> dict:
    """
    Pure deterministic scoring function.
    Accepts a session dict (or list of Step objects for backwards compatibility).
    Returns:
    {
        "score": int (0-100),
        "total": int (alias for score),
        "label": str ("Smooth" | "Minor" | "Moderate" | "Severe"),
        "breakdown": [...],
        "parts": [...] (alias for breakdown),
        "explanation_inputs": {...},
        "steps_taken": int,
        "expected_steps": int,
        "ideal_steps": int (alias for expected_steps),
    }
    """
    # 1. Normalize session input
    if isinstance(session, list):
        steps = session
        is_completed = completed if completed is not None else True
        outcome = "completed" if is_completed else "abandoned"
        outcome_reason = ""
        expected_steps_override = None
        baseline_failed = False
        baseline_note = ""
    elif isinstance(session, dict):
        steps = session.get("steps", [])
        outcome = session.get("outcome")
        if outcome is None and completed is not None:
            outcome = "completed" if completed else "abandoned"
        elif outcome is None:
            if session.get("status") == "completed" or session.get("completed") is True:
                outcome = "completed"
            elif session.get("status") == "failed":
                outcome = "error"
            else:
                outcome = "completed" if (completed is not False) else "abandoned"
        outcome_reason = session.get("outcome_reason", "")
        expected_steps_override = session.get("expected_steps") or session.get("baseline_steps")
        baseline_failed = session.get("baseline_failed", False)
        baseline_note = session.get("baseline_note", "")
    else:
        steps = getattr(session, "steps", [])
        outcome = getattr(session, "outcome", None)
        if outcome is None and completed is not None:
            outcome = "completed" if completed else "abandoned"
        elif outcome is None:
            outcome = "completed" if getattr(session, "completed", True) else "abandoned"
        outcome_reason = getattr(session, "outcome_reason", "")
        expected_steps_override = getattr(session, "expected_steps", None) or getattr(session, "baseline_steps", None)
        baseline_failed = getattr(session, "baseline_failed", False)
        baseline_note = getattr(session, "baseline_note", "")

    if baseline_failed and not baseline_note:
        baseline_note = "task may be unreachable or unclear"

    steps_taken = len(steps)
    # If baseline failed, fall back to heuristic. Otherwise use baseline expected_steps if available.
    if (not baseline_failed) and expected_steps_override and isinstance(expected_steps_override, int) and expected_steps_override > 0:
        expected_steps = expected_steps_override
    else:
        expected_steps = _estimate_expected_steps(steps_taken)

    breakdown: list[dict] = []

    # -------------------------------------------------------------------------
    # Signal 1: steps_taken vs expected_steps
    # -------------------------------------------------------------------------
    excess_steps = max(0, steps_taken - expected_steps)
    if excess_steps > 0:
        pts = min(CAP_EXCESS_STEPS, excess_steps * WEIGHT_EXCESS_STEPS)
        evidence_steps = [
            getattr(s, "n", idx + 1) if not isinstance(s, dict) else s.get("n", idx + 1)
            for idx, s in enumerate(steps[expected_steps:])
        ]
        desc = f"{excess_steps} extra step(s) taken beyond expected path ({expected_steps} expected vs {steps_taken} taken)."
        breakdown.append({
            "name": "Excess Steps",
            "points": pts,
            "description": desc,
            "why": desc,
            "step_numbers": evidence_steps,
            "evidence": evidence_steps,
        })

    # -------------------------------------------------------------------------
    # Signal 2: backtracks (returning to a previously visited URL)
    # -------------------------------------------------------------------------
    visited_urls: set[str] = set()
    backtrack_steps: list[int] = []
    for s in steps:
        url = (getattr(s, "url", "") if not isinstance(s, dict) else s.get("url", "")) or ""
        url_after = (getattr(s, "url_after", "") if not isinstance(s, dict) else s.get("url_after", "")) or ""
        step_n = getattr(s, "n", 0) if not isinstance(s, dict) else s.get("n", 0)

        url_norm = url.rstrip("/")
        url_after_norm = url_after.rstrip("/")

        if url_norm:
            visited_urls.add(url_norm)
        if url_after_norm and url_after_norm != url_norm and url_after_norm in visited_urls:
            backtrack_steps.append(step_n)
        if url_after_norm:
            visited_urls.add(url_after_norm)

    if backtrack_steps:
        pts = min(CAP_BACKTRACK, len(backtrack_steps) * WEIGHT_BACKTRACK)
        desc = f"Returned to previously visited pages {len(backtrack_steps)} time(s), indicating disorientation."
        breakdown.append({
            "name": "Navigation Backtracks",
            "points": pts,
            "description": desc,
            "why": desc,
            "step_numbers": backtrack_steps,
            "evidence": backtrack_steps,
        })

    # -------------------------------------------------------------------------
    # Signal 3: repeated actions (same action on same element 2+ times)
    # -------------------------------------------------------------------------
    seen_actions: set[tuple[str, str]] = set()
    repeated_steps: list[int] = []
    for s in steps:
        action = (getattr(s, "action", "") if not isinstance(s, dict) else s.get("action", "")) or ""
        target = (getattr(s, "target", "") or getattr(s, "label", "")) if not isinstance(s, dict) else (s.get("target") or s.get("label", ""))
        step_n = getattr(s, "n", 0) if not isinstance(s, dict) else s.get("n", 0)

        if not action or action.lower() in ("done", "abort"):
            continue

        target_norm = (target or "").strip().lower()
        action_norm = action.strip().lower()
        if not target_norm and action_norm != "scroll":
            continue

        action_key = (action_norm, target_norm)
        if action_key in seen_actions:
            repeated_steps.append(step_n)
        else:
            seen_actions.add(action_key)

    if repeated_steps:
        pts = min(CAP_REPEATED_ACTION, len(repeated_steps) * WEIGHT_REPEATED_ACTION)
        desc = f"Repeated identical actions on the same element {len(repeated_steps)} time(s)."
        breakdown.append({
            "name": "Repeated Actions",
            "points": pts,
            "description": desc,
            "why": desc,
            "step_numbers": repeated_steps,
            "evidence": repeated_steps,
        })

    # -------------------------------------------------------------------------
    # Signal 4: dead clicks (click with no DOM or URL change)
    # -------------------------------------------------------------------------
    dead_click_steps: list[int] = []
    for s in steps:
        action = (getattr(s, "action", "") if not isinstance(s, dict) else s.get("action", "")) or ""
        step_n = getattr(s, "n", 0) if not isinstance(s, dict) else s.get("n", 0)
        is_dead = getattr(s, "dead_click", False) if not isinstance(s, dict) else s.get("dead_click", False)

        url = getattr(s, "url", "") if not isinstance(s, dict) else s.get("url", "")
        url_after = getattr(s, "url_after", "") if not isinstance(s, dict) else s.get("url_after", "")
        dom_changed = getattr(s, "dom_changed", None) if not isinstance(s, dict) else s.get("dom_changed", None)

        if is_dead or (action == "click" and dom_changed is False and url == url_after):
            dead_click_steps.append(step_n)

    if dead_click_steps:
        pts = min(CAP_DEAD_CLICK, len(dead_click_steps) * WEIGHT_DEAD_CLICK)
        desc = f"{len(dead_click_steps)} click(s) resulted in no DOM or URL change, indicating unresponsive elements."
        breakdown.append({
            "name": "Dead Clicks",
            "points": pts,
            "description": desc,
            "why": desc,
            "step_numbers": dead_click_steps,
            "evidence": dead_click_steps,
        })

    # -------------------------------------------------------------------------
    # Signal 5: slow steps (time between action and stable page above threshold)
    # -------------------------------------------------------------------------
    slow_steps: list[int] = []
    for s in steps:
        step_n = getattr(s, "n", 0) if not isinstance(s, dict) else s.get("n", 0)
        duration = getattr(s, "duration", 0.0) if not isinstance(s, dict) else s.get("duration", 0.0)
        is_slow = getattr(s, "is_slow", False) if not isinstance(s, dict) else s.get("is_slow", False)

        if duration >= SLOW_STEP_THRESHOLD_SECONDS or is_slow:
            slow_steps.append(step_n)

    if slow_steps:
        pts = min(CAP_SLOW_STEP, len(slow_steps) * WEIGHT_SLOW_STEP)
        desc = f"{len(slow_steps)} step(s) took over {SLOW_STEP_THRESHOLD_SECONDS}s to settle and become interactive."
        breakdown.append({
            "name": "Slow Transitions",
            "points": pts,
            "description": desc,
            "why": desc,
            "step_numbers": slow_steps,
            "evidence": slow_steps,
        })

    # -------------------------------------------------------------------------
    # Signal 6: console errors and failed network requests during the step
    # -------------------------------------------------------------------------
    error_steps: list[int] = []
    total_tech_failures = 0
    for s in steps:
        step_n = getattr(s, "n", 0) if not isinstance(s, dict) else s.get("n", 0)
        c_errs = (
            getattr(s, "console_errors", []) if not isinstance(s, dict) else s.get("console_errors", [])
        ) or []
        n_errs = (
            (getattr(s, "failed_requests", []) or getattr(s, "network_failures", []))
            if not isinstance(s, dict)
            else (s.get("failed_requests", []) or s.get("network_failures", []))
        ) or []

        c_count = len(c_errs) if isinstance(c_errs, list) else int(bool(c_errs))
        n_count = len(n_errs) if isinstance(n_errs, list) else int(bool(n_errs))
        total_in_step = c_count + n_count

        if total_in_step > 0:
            error_steps.append(step_n)
            total_tech_failures += total_in_step

    if error_steps:
        pts = min(CAP_ERRORS, total_tech_failures * WEIGHT_CONSOLE_ERROR)
        desc = f"Encountered {total_tech_failures} technical failure(s) (console errors or failed requests) across {len(error_steps)} step(s)."
        breakdown.append({
            "name": "Console & Network Errors",
            "points": pts,
            "description": desc,
            "why": desc,
            "step_numbers": error_steps,
            "evidence": error_steps,
        })

    # -------------------------------------------------------------------------
    # Signal 7: task failure penalty based on outcome status
    # -------------------------------------------------------------------------
    is_completed_success = (outcome == "completed")
    if not is_completed_success:
        if outcome == "abandoned":
            failure_pts = PENALTY_OUTCOME_ABANDONED
        elif outcome == "gave_up":
            failure_pts = PENALTY_OUTCOME_GAVE_UP
        elif outcome == "error":
            failure_pts = PENALTY_OUTCOME_ERROR
        elif outcome == "max_steps_reached":
            failure_pts = PENALTY_OUTCOME_MAX_STEPS
        else:
            failure_pts = PENALTY_OUTCOME_INCOMPLETE

        pts = min(CAP_TASK_FAILURE, failure_pts)
        last_step_num = []
        if steps:
            last_s = steps[-1]
            last_step_num = [getattr(last_s, "n", len(steps)) if not isinstance(last_s, dict) else last_s.get("n", len(steps))]

        reason_suffix = f": {outcome_reason}" if outcome_reason else ""
        desc = f"Task was not completed successfully (outcome: '{outcome or 'incomplete'}'){reason_suffix}."
        breakdown.append({
            "name": "Task Outcome Failure",
            "points": pts,
            "description": desc,
            "why": desc,
            "step_numbers": last_step_num,
            "evidence": last_step_num,
        })

    # -------------------------------------------------------------------------
    # Signal 8: LLM-reported confusion points (small weight only)
    # -------------------------------------------------------------------------
    confusion_steps: list[int] = []
    for s in steps:
        step_n = getattr(s, "n", 0) if not isinstance(s, dict) else s.get("n", 0)
        ft = getattr(s, "friction_type", None) if not isinstance(s, dict) else s.get("friction_type")
        if ft and str(ft).strip().lower() not in ("none", "null", ""):
            confusion_steps.append(step_n)

    if confusion_steps:
        pts = min(CAP_CONFUSION_POINT, len(confusion_steps) * WEIGHT_CONFUSION_POINT)
        desc = f"User persona flagged confusion, ambiguous CTAs, or interface friction at {len(confusion_steps)} point(s)."
        breakdown.append({
            "name": "Reported UX Confusion",
            "points": pts,
            "description": desc,
            "why": desc,
            "step_numbers": confusion_steps,
            "evidence": confusion_steps,
        })

    # -------------------------------------------------------------------------
    # Signal 9: Critical automated accessibility and layout violations
    # -------------------------------------------------------------------------
    critical_violation_steps: list[int] = []
    total_critical_violations = 0
    for s in steps:
        step_n = getattr(s, "n", 0) if not isinstance(s, dict) else s.get("n", 0)
        axes = (getattr(s, "axe_violations", []) if not isinstance(s, dict) else s.get("axe_violations", [])) or []
        taps = (getattr(s, "tap_targets", []) if not isinstance(s, dict) else s.get("tap_targets", [])) or []
        contrasts = (getattr(s, "contrast_issues", []) if not isinstance(s, dict) else s.get("contrast_issues", [])) or []
        overlaps = (getattr(s, "overlapping_elements", []) if not isinstance(s, dict) else s.get("overlapping_elements", [])) or []

        crit_axes = [v for v in axes if v.get("impact") in ("critical", "serious")]
        crit_taps = [t for t in taps if t.get("width", 44) < 32 or t.get("height", 44) < 32]
        crit_contrasts = [c for c in contrasts if c.get("contrast_ratio", 4.5) < 3.0]
        crit_overlaps = [o for o in overlaps if o.get("overlap_area", 0) > 80]

        step_crit_count = len(crit_axes) + len(crit_taps) + len(crit_contrasts) + len(crit_overlaps)
        if step_crit_count > 0:
            critical_violation_steps.append(step_n)
            total_critical_violations += step_crit_count

    if critical_violation_steps:
        pts = min(CAP_CRITICAL_VIOLATIONS, total_critical_violations * WEIGHT_CRITICAL_VIOLATION)
        desc = f"Encountered {total_critical_violations} critical automated accessibility or layout defect(s) across {len(critical_violation_steps)} step(s)."
        breakdown.append({
            "name": "Critical UI/A11y Violations",
            "points": pts,
            "description": desc,
            "why": desc,
            "step_numbers": critical_violation_steps,
            "evidence": critical_violation_steps,
        })

    # -------------------------------------------------------------------------
    # Final Score & Label Normalization
    # -------------------------------------------------------------------------
    raw_points = sum(item["points"] for item in breakdown)
    total_score = max(0, min(100, raw_points))
    label = score_to_label(total_score)

    explanation_inputs = {
        "score": total_score,
        "label": label,
        "raw_points": raw_points,
        "steps_taken": steps_taken,
        "expected_steps": expected_steps,
        "outcome": outcome,
        "outcome_reason": outcome_reason,
        "baseline_failed": baseline_failed,
        "baseline_note": baseline_note,
        "breakdown": [
            {
                "name": item["name"],
                "points": item["points"],
                "description": item["description"],
                "step_numbers": item["step_numbers"],
            }
            for item in breakdown
        ],
        "signal_names": [item["name"] for item in breakdown],
        "primary_friction": breakdown[0]["name"] if breakdown else "None",
    }

    return {
        "score": total_score,
        "total": total_score,          # Alias for Report.tsx compatibility
        "label": label,
        "breakdown": breakdown,
        "parts": breakdown,            # Alias for Report.tsx compatibility
        "explanation_inputs": explanation_inputs,
        "steps_taken": steps_taken,
        "expected_steps": expected_steps,
        "ideal_steps": expected_steps, # Alias for Report.tsx compatibility
        "baseline_failed": baseline_failed,
        "baseline_note": baseline_note,
    }


def build_report(
    session: dict | list[Step] | Any,
    completed: bool | None = None,
    task: str = "",
    persona: str = "",
    client: Any = None,
    model: str | None = None,
) -> dict:
    """
    Builds the usability audit report.
    The friction score and breakdown are strictly computed deterministically by compute_friction.
    The LLM is kept OUT of detection: findings are derived automatically from evidence.
    The LLM is invoked solely to produce suggested fixes (CSS/copy) and the summary paragraph ('verdict').
    """
    score_data = compute_friction(session, completed=completed)

    # Extract steps list for log representation
    if isinstance(session, list):
        steps = session
    elif isinstance(session, dict):
        steps = session.get("steps", [])
        task = task or session.get("task", "")
        persona = persona or session.get("persona", "")
    else:
        steps = getattr(session, "steps", [])
        task = task or getattr(session, "task", "")
        persona = persona or getattr(session, "persona", "")

    # 1. Automated finding detection from collected step evidence (LLM out of detection)
    findings = detect_findings_from_evidence(session if not isinstance(session, list) else {"steps": steps})

    # 2. Attach step screenshot with red bounding box drawn on offending element
    attach_screenshots_with_bounding_boxes(findings, steps)

    # 3. Invoke LLM strictly to write concrete suggested fixes (CSS / copy change) from evidence
    generate_suggested_fixes(findings, client=client, model=model)

    baseline_failed = (
        session.get("baseline_failed", False) if isinstance(session, dict)
        else getattr(session, "baseline_failed", False)
    )
    baseline_note = (
        session.get("baseline_note", "") if isinstance(session, dict)
        else getattr(session, "baseline_note", "")
    ) or ("task may be unreachable or unclear" if baseline_failed else "")

    steps_log = "\n".join([
        f"Step {getattr(s, 'n', i+1) if not isinstance(s, dict) else s.get('n', i+1)}: "
        f"Action={getattr(s, 'action', '') if not isinstance(s, dict) else s.get('action', '')}, "
        f"Target/Label='{getattr(s, 'label', '') if not isinstance(s, dict) else s.get('label', '')}', "
        f"URL='{getattr(s, 'url', '') if not isinstance(s, dict) else s.get('url', '')}', "
        f"OK={getattr(s, 'ok', True) if not isinstance(s, dict) else s.get('ok', True)}"
        for i, s in enumerate(steps)
    ])

    baseline_prompt_section = (
        f"\nCRITICAL BASELINE AUDIT NOTE:\nThe direct baseline agent failed this task ({baseline_note}). "
        f"The task may be unreachable or unclear. Explicitly state in the verdict that the task may be unreachable or unclear.\n"
        if baseline_failed else ""
    )

    verdict_prompt = f"""You are an expert UX auditor writing a Sabotage Report summary.

Task: {task}
Persona: {persona}
Task Status: {score_data['explanation_inputs']['outcome']}
Friction Score: {score_data['score']}/100 ({score_data['label']} friction)
{baseline_prompt_section}
Execution Steps:
{steps_log}

Deterministic Friction Breakdown:
{json.dumps(score_data['breakdown'], indent=2)}

Detected Usability Findings:
{json.dumps([{'title': f['title'], 'what_happened': f['what_happened']} for f in findings], indent=2)}

CRITICAL INSTRUCTIONS:
- Write a concise, 2-3 sentence human-readable summary paragraph ('verdict') explaining why this score was reached based on the breakdown.
- Do NOT generate or alter findings.

Respond ONLY with a valid JSON object matching:
{{
  "verdict": "2-3 concise sentences summarizing the primary friction points and overall outcome."
}}
"""

    verdict = ""

    try:
        if client is not None:
            if hasattr(client, "sync_chat_completion"):
                resp = client.sync_chat_completion(
                    messages=[{"role": "user", "content": verdict_prompt}],
                    model_type="text",
                    temperature=0.2,
                    max_tokens=600,
                    response_format={"type": "json_object"},
                )
                narrative = json.loads(resp.choices[0].message.content)
            elif hasattr(client, "chat") and hasattr(client.chat, "completions"):
                resp = client.chat.completions.create(
                    model=model or "openai/gpt-oss-120b",
                    temperature=0.2,
                    max_tokens=600,
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": verdict_prompt}],
                )
                narrative = json.loads(resp.choices[0].message.content)
            else:
                narrative = {}
            verdict = narrative.get("verdict", "")
            if not findings and narrative.get("findings"):
                findings = narrative.get("findings")
    except Exception as e:
        print(f"LLM narrative generation exception: {e}")

    # Fallback human-readable summary if LLM was unavailable or produced empty verdict
    if not verdict:
        prefix = f"Note: Baseline run failed ({baseline_note}). " if baseline_failed else ""
        if score_data["score"] <= LABEL_SMOOTH_MAX:
            verdict = f"{prefix}The user experienced a smooth interaction flow ({score_data['score']}/100, {score_data['label']}). The direct path was completed with minimal hesitation or blockers."
        elif score_data["score"] <= LABEL_MINOR_MAX:
            sig_list = ", ".join(p["name"] for p in score_data["breakdown"])
            verdict = f"{prefix}The user encountered minor friction ({score_data['score']}/100, {score_data['label']}). Identified factors: {sig_list}."
        elif score_data["score"] <= LABEL_MODERATE_MAX:
            sig_list = ", ".join(p["name"] for p in score_data["breakdown"])
            verdict = f"{prefix}The user experienced moderate friction ({score_data['score']}/100, {score_data['label']}) across {score_data['steps_taken']} steps. Primary contributors: {sig_list}."
        else:
            sig_list = ", ".join(p["name"] for p in score_data["breakdown"])
            verdict = f"{prefix}Severe usability friction was encountered ({score_data['score']}/100, {score_data['label']}). Key blockers: {sig_list}."

    if baseline_failed and "unreachable or unclear" not in verdict.lower():
        verdict = f"Note: Baseline run failed ({baseline_note}). {verdict}"

    # State in report that fake form data was used
    fake_data_note = "Clearly fake form data (for example test@example.com) was used during this test session."
    if not client and "fake data" not in verdict.lower():
        verdict = f"{verdict.rstrip()} {fake_data_note}"

    # Validate evidence steps in findings
    valid_step_numbers = {
        getattr(s, "n", i+1) if not isinstance(s, dict) else s.get("n", i+1)
        for i, s in enumerate(steps)
    }
    for f in findings:
        f["evidence_steps"] = [
            n for n in f.get("evidence_steps", []) if isinstance(n, int) and n in valid_step_numbers
        ]

    security_notes = []
    if isinstance(session, dict):
        security_notes.extend(session.get("security_notes", []))
    if fake_data_note not in security_notes:
        security_notes.append(fake_data_note)

    # Return final report: score numbers remain strictly deterministic and unaltered
    return {
        "score": score_data,
        "verdict": verdict,
        "findings": findings,
        "baseline_failed": baseline_failed,
        "baseline_note": baseline_note,
        "fake_data_used": True,
        "security_notes": security_notes,
    }


def _normalize_title(t: str) -> str:
    import re
    return re.sub(r"[^\w\s]", "", t or "").strip().lower()


def _finding_tokens(t: str) -> set[str]:
    stop_words = {"the", "a", "an", "in", "on", "at", "for", "to", "of", "and", "or", "is", "was", "with"}
    words = _normalize_title(t).split()
    return {w for w in words if w not in stop_words and len(w) > 2}


def _are_findings_equivalent(f1: dict, f2: dict) -> bool:
    t1 = _normalize_title(f1.get("title", ""))
    t2 = _normalize_title(f2.get("title", ""))
    if not t1 or not t2:
        return False
    if t1 == t2:
        return True
    if (t1 in t2 or t2 in t1) and min(len(t1), len(t2)) >= 8:
        return True
    tok1 = _finding_tokens(f1.get("title", ""))
    tok2 = _finding_tokens(f2.get("title", ""))
    if tok1 and tok2:
        jaccard = len(tok1 & tok2) / len(tok1 | tok2)
        if jaccard >= 0.5:
            return True
    return False


def aggregate_run_reports(reports: list[dict], runs: int = 1) -> dict:
    """
    Aggregates reports from multiple sequential runs of the same persona/task.
    Computes:
      - score_min, score_max, score_mean
      - findings that appeared in 2+ runs are marked 'consistent'; others 'occasional'
    """
    if not reports:
        return {}

    if len(reports) <= 1 and runs <= 1:
        return reports[0] if reports else {}

    # Extract score values
    scores: list[int | float] = []
    for r in reports:
        sc = r.get("score")
        if isinstance(sc, dict):
            val = sc.get("total", sc.get("score", 0))
        elif isinstance(sc, (int, float)):
            val = sc
        else:
            val = 0
        scores.append(val)

    if not scores:
        scores = [0]

    score_min = min(scores)
    score_max = max(scores)
    mean_val = round(sum(scores) / len(scores), 1)
    score_mean = int(mean_val) if mean_val.is_integer() else mean_val

    # Cluster findings across runs to measure consistency
    clusters: list[dict] = []
    for run_idx, r in enumerate(reports, start=1):
        for f in r.get("findings", []):
            matched_cluster = None
            for c in clusters:
                if _are_findings_equivalent(f, c["representative"]):
                    matched_cluster = c
                    break
            if matched_cluster:
                matched_cluster["run_indices"].add(run_idx)
                matched_cluster["instances"].append(f)
                sev_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
                if sev_order.get(f.get("severity", ""), 0) > sev_order.get(matched_cluster["representative"].get("severity", ""), 0):
                    matched_cluster["representative"] = f
            else:
                clusters.append({
                    "representative": dict(f),
                    "run_indices": {run_idx},
                    "instances": [f],
                })

    aggregated_findings: list[dict] = []
    for c in clusters:
        item = dict(c["representative"])
        # Findings appearing in 2+ runs are marked "consistent"; others "occasional"
        is_consistent = len(c["run_indices"]) >= 2
        item["consistency"] = "consistent" if is_consistent else "occasional"
        item["runs_count"] = len(c["run_indices"])
        item["total_runs"] = runs
        aggregated_findings.append(item)

    # Sort consistent findings first, then by severity
    sev_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    aggregated_findings.sort(
        key=lambda x: (
            1 if x.get("consistency") == "consistent" else 0,
            sev_rank.get(x.get("severity", ""), 0),
        ),
        reverse=True,
    )

    # Select base representative report (closest to mean score)
    best_idx = min(range(len(reports)), key=lambda i: abs(scores[i] - score_mean))
    base = dict(reports[best_idx])
    aggregated = dict(base)

    # Update score object
    score_obj = dict(base.get("score", {})) if isinstance(base.get("score"), dict) else {}
    score_obj["score_min"] = score_min
    score_obj["score_max"] = score_max
    score_obj["score_mean"] = score_mean
    score_obj["runs"] = runs
    score_obj["total"] = round(score_mean)
    score_obj["score"] = round(score_mean)

    aggregated["score"] = score_obj
    aggregated["score_min"] = score_min
    aggregated["score_max"] = score_max
    aggregated["score_mean"] = score_mean
    aggregated["runs"] = runs
    aggregated["findings"] = aggregated_findings

    base_verdict = base.get("verdict", "")
    if f"consistent across {runs} runs" not in base_verdict and runs > 1:
        aggregated["verdict"] = (
            f"Consistency audit across {runs} runs (range {score_min}–{score_max}, mean {score_mean}). "
            + base_verdict
        )

    aggregated["runs_summary"] = [
        {
            "run": i + 1,
            "score": scores[i],
            "outcome": reports[i].get("outcome", "completed"),
            "findings_count": len(reports[i].get("findings", [])),
        }
        for i in range(len(reports))
    ]

    return aggregated
