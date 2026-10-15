import json
from dataclasses import dataclass, field
from groq import Groq


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


def compute_friction(steps: list[Step], completed: bool) -> dict:
    acts = [s for s in steps if s.action in ("click", "type", "scroll", "back", "navigate")]
    visited: set[str] = set()
    backtracks: list[int] = []
    for s in acts:
        visited.add(s.url)
        if s.url_after and s.url_after != s.url and s.url_after in visited:
            backtracks.append(s.n)

    failures: list[int] = [s.n for s in steps if not s.ok]
    friction_steps: list[int] = [s.n for s in steps if s.friction_type and s.friction_type != "none"]

    steps_taken = len(steps)
    # Estimate an ideal step budget for a direct flow
    ideal_steps = max(3, min(6, round(steps_taken * 0.6))) if steps_taken > 3 else max(1, steps_taken)
    excess_steps = max(0, steps_taken - ideal_steps)

    parts: list[dict] = []

    if failures:
        pts = min(40, len(failures) * 12)
        parts.append({
            "name": "Action Failures",
            "points": pts,
            "evidence": failures,
            "why": f"{len(failures)} action(s) failed or targeted non-interactive elements.",
        })

    if backtracks:
        pts = min(30, len(backtracks) * 10)
        parts.append({
            "name": "Navigation Backtracking",
            "points": pts,
            "evidence": backtracks,
            "why": f"Returned to previously visited pages {len(backtracks)} time(s), indicating disorientation.",
        })

    if friction_steps:
        pts = min(30, len(friction_steps) * 8)
        parts.append({
            "name": "Reported UX Friction",
            "points": pts,
            "evidence": friction_steps,
            "why": f"User flagged confusion, ambiguous CTAs, or interface friction at {len(friction_steps)} point(s).",
        })

    if excess_steps > 0:
        pts = min(25, excess_steps * 3)
        evidence = [s.n for s in steps[ideal_steps:ideal_steps + 6]]
        parts.append({
            "name": "Exploration Overhead",
            "points": pts,
            "evidence": evidence,
            "why": f"{excess_steps} extra exploratory step(s) taken beyond the estimated direct path.",
        })

    if not completed:
        pts = 35
        last_step = [steps[-1].n] if steps else []
        parts.append({
            "name": "Incomplete Objective",
            "points": pts,
            "evidence": last_step,
            "why": "The task was aborted or terminated before reaching completion.",
        })

    total = min(100, sum(p["points"] for p in parts))
    if total < 25:
        label = "Low"
    elif total < 50:
        label = "Moderate"
    elif total < 75:
        label = "High"
    else:
        label = "Severe"

    return {
        "total": total,
        "label": label,
        "parts": parts,
        "steps_taken": steps_taken,
        "ideal_steps": ideal_steps,
    }


def build_report(
    client: Groq,
    model: str,
    steps: list[Step],
    completed: bool,
    task: str,
    persona: str,
) -> dict:
    score = compute_friction(steps, completed)

    steps_log = "\n".join([
        f"Step {s.n}: Action={s.action}, Target/Label='{s.label}', URL='{s.url}', URL_After='{s.url_after}', OK={s.ok}"
        + (f", Friction={s.friction_type} ('{s.friction_note}')" if s.friction_type else "")
        + f"\n  Thought: {s.thought}"
        for s in steps
    ])

    prompt = f"""You are an expert UX auditor writing a Sabotage Report analyzing user testing session friction.

Task: {task}
Persona: {persona}
Completed: {completed}
Friction Score: {score['total']}/100 ({score['label']} friction)

Execution Steps:
{steps_log}

Score Breakdown:
{json.dumps(score['parts'], indent=2)}

Generate a detailed usability finding report.
Respond ONLY with a valid JSON object matching this schema:
{{
  "verdict": "2-3 concise sentences summarizing the primary friction points and overall outcome.",
  "findings": [
    {{
      "title": "Short descriptive title of the issue",
      "severity": "critical" | "high" | "medium",
      "evidence_steps": [1, 2],
      "what_happened": "Clear explanation of what the user encountered",
      "impact": "How this harmed task completion, confidence, or speed",
      "recommendation": "Specific actionable fix for designers and developers"
    }}
  ]
}}
IMPORTANT:
- Only reference valid step numbers (1 to {len(steps)}) in evidence_steps.
- Provide between 1 and 4 high-value findings based strictly on the steps log.
"""

    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        max_tokens=2000,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    narrative = json.loads(resp.choices[0].message.content)
    valid = {s.n for s in steps}
    for f in narrative.get("findings", []):
        f["evidence_steps"] = [n for n in f.get("evidence_steps", []) if isinstance(n, int) and n in valid]

    return {"score": score, **narrative}
