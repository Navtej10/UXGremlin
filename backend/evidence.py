import base64
import io
import json
import os
import re
from typing import Any
from PIL import Image, ImageDraw

_AXE_SCRIPT: str | None = None


def get_axe_script() -> str:
    """Loads axe.min.js from backend directory or returns empty string if unavailable."""
    global _AXE_SCRIPT
    if _AXE_SCRIPT is not None:
        return _AXE_SCRIPT

    local_path = os.path.join(os.path.dirname(__file__), "axe.min.js")
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                _AXE_SCRIPT = f.read()
                return _AXE_SCRIPT
        except Exception:
            pass
    return ""


async def inject_axe(page: Any) -> bool:
    """Injects axe-core into the active page if not already loaded."""
    try:
        has_axe = await page.evaluate("() => typeof window.axe !== 'undefined'")
        if has_axe:
            return True

        script = get_axe_script()
        if script:
            await page.evaluate(script)
            return True

        # Fallback to CDN script tag
        if hasattr(page, "add_script_tag"):
            await page.add_script_tag(url="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js")
            return True
    except Exception:
        pass
    return False


async def collect_axe_violations(page: Any) -> list[dict]:
    """Runs axe-core accessibility audit and extracts violation records with bounding boxes."""
    try:
        injected = await inject_axe(page)
        if not injected:
            return []

        axe_run_js = """
        async () => {
            if (!window.axe) return [];
            try {
                const results = await window.axe.run(document, {
                    runOnly: {
                        type: 'tag',
                        values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice']
                    }
                });
                const violations = [];
                for (const v of (results.violations || [])) {
                    for (const node of (v.nodes || [])) {
                        const sel = (node.target && node.target.length) ? node.target.join(' ') : '';
                        let bbox = null;
                        if (sel) {
                            try {
                                const el = document.querySelector(sel);
                                if (el) {
                                    const r = el.getBoundingClientRect();
                                    if (r.width > 0 && r.height > 0) {
                                        bbox = {
                                            x: Math.round(r.x),
                                            y: Math.round(r.y),
                                            width: Math.round(r.width),
                                            height: Math.round(r.height)
                                        };
                                    }
                                }
                            } catch (e) {}
                        }
                        violations.push({
                            id: v.id,
                            impact: v.impact || 'moderate',
                            selector: sel,
                            help: v.help || '',
                            bounding_box: bbox
                        });
                    }
                }
                return violations;
            } catch (e) {
                return [];
            }
        }
        """
        violations = await page.evaluate(axe_run_js)
        return violations if isinstance(violations, list) else []
    except Exception:
        return []


async def collect_dom_violations(page: Any) -> dict:
    """
    Evaluates visible interactive items for:
    1. Tap targets under 44x44px
    2. Low-contrast text (< 4.5:1, or < 3.0:1 for large text)
    3. Overlapping interactive elements
    """
    dom_check_js = """
    () => {
        const interactiveSelectors = 'button, a[href], input, select, textarea, [role="button"], [role="link"], [onclick], [tabindex]:not([tabindex="-1"])';
        const allEls = Array.from(document.querySelectorAll(interactiveSelectors));

        const visibleItems = [];
        for (const el of allEls) {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
            const rect = el.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) continue;
            visibleItems.push({ el, rect, style });
        }

        // 1. Tap targets under 44x44px
        const smallTapTargets = [];
        for (const item of visibleItems) {
            const w = Math.round(item.rect.width);
            const h = Math.round(item.rect.height);
            if (w < 44 || h < 44) {
                let sel = item.el.id ? `#${item.el.id}` : '';
                if (!sel && item.el.className && typeof item.el.className === 'string') {
                    const cls = item.el.className.trim().split(/\\s+/).filter(c => !c.startsWith('uxg-'))[0];
                    if (cls) sel = `${item.el.tagName.toLowerCase()}.${cls}`;
                }
                if (!sel) sel = item.el.tagName.toLowerCase();
                const text = (item.el.innerText || item.el.getAttribute('aria-label') || item.el.getAttribute('title') || item.el.value || '').trim().slice(0, 50);
                smallTapTargets.push({
                    selector: sel,
                    text: text,
                    width: w,
                    height: h,
                    bounding_box: { x: Math.round(item.rect.x), y: Math.round(item.rect.y), width: w, height: h },
                    help: `Tap target (${w}x${h}px) is under 44x44px recommended size`
                });
            }
        }

        // 2. Low-contrast text
        function parseRgb(colorStr) {
            if (!colorStr) return null;
            const match = colorStr.match(/rgba?\\s*\\(\\s*(\\d+)\\s*,\\s*(\\d+)\\s*,\\s*(\\d+)/i);
            if (!match) return null;
            return [parseInt(match[1]), parseInt(match[2]), parseInt(match[3])];
        }
        function luminance(r, g, b) {
            const a = [r, g, b].map(v => {
                v /= 255;
                return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
            });
            return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
        }
        function contrastRatio(rgb1, rgb2) {
            const lum1 = luminance(rgb1[0], rgb1[1], rgb1[2]);
            const lum2 = luminance(rgb2[0], rgb2[1], rgb2[2]);
            const brightest = Math.max(lum1, lum2);
            const darkest = Math.min(lum1, lum2);
            return (brightest + 0.05) / (darkest + 0.05);
        }
        function getEffectiveBg(el) {
            let cur = el;
            while (cur && cur !== document.documentElement) {
                const bg = window.getComputedStyle(cur).backgroundColor;
                if (bg && bg !== 'transparent' && !bg.includes('rgba(0, 0, 0, 0)')) {
                    const rgb = parseRgb(bg);
                    if (rgb) return rgb;
                }
                cur = cur.parentElement;
            }
            return [255, 255, 255];
        }

        const lowContrast = [];
        for (const item of visibleItems) {
            const text = (item.el.innerText || item.el.getAttribute('aria-label') || item.el.value || '').trim();
            if (!text) continue;
            const fgRgb = parseRgb(item.style.color);
            const bgRgb = getEffectiveBg(item.el);
            if (fgRgb && bgRgb) {
                const ratio = Math.round(contrastRatio(fgRgb, bgRgb) * 10) / 10;
                const fontSize = parseFloat(item.style.fontSize) || 16;
                const isBold = parseInt(item.style.fontWeight) >= 700 || item.style.fontWeight === 'bold';
                const minRatio = (fontSize >= 24 || (fontSize >= 18.5 && isBold)) ? 3.0 : 4.5;
                if (ratio < minRatio) {
                    let sel = item.el.id ? `#${item.el.id}` : item.el.tagName.toLowerCase();
                    lowContrast.push({
                        selector: sel,
                        text: text.slice(0, 50),
                        contrast_ratio: ratio,
                        min_ratio: minRatio,
                        fg_color: item.style.color,
                        bounding_box: {
                            x: Math.round(item.rect.x),
                            y: Math.round(item.rect.y),
                            width: Math.round(item.rect.width),
                            height: Math.round(item.rect.height)
                        },
                        help: `Low contrast ratio ${ratio}:1 below minimum ${minRatio}:1 threshold`
                    });
                }
            }
        }

        // 3. Overlapping interactive elements
        const overlaps = [];
        for (let i = 0; i < visibleItems.length; i++) {
            for (let j = i + 1; j < visibleItems.length; j++) {
                const itemA = visibleItems[i];
                const itemB = visibleItems[j];
                if (itemA.el.contains(itemB.el) || itemB.el.contains(itemA.el)) continue;

                const rA = itemA.rect;
                const rB = itemB.rect;
                const xOverlap = Math.max(0, Math.min(rA.right, rB.right) - Math.max(rA.left, rB.left));
                const yOverlap = Math.max(0, Math.min(rA.bottom, rB.bottom) - Math.max(rA.top, rB.top));
                const overlapArea = Math.round(xOverlap * yOverlap);

                if (overlapArea > 50) {
                    let selA = itemA.el.id ? `#${itemA.el.id}` : '';
                    if (!selA && itemA.el.className && typeof itemA.el.className === 'string') {
                        const cls = itemA.el.className.trim().split(/\\s+/).filter(c => !c.startsWith('uxg-'))[0];
                        if (cls) selA = `${itemA.el.tagName.toLowerCase()}.${cls}`;
                    }
                    if (!selA) selA = itemA.el.tagName.toLowerCase();

                    let selB = itemB.el.id ? `#${itemB.el.id}` : '';
                    if (!selB && itemB.el.className && typeof itemB.el.className === 'string') {
                        const cls = itemB.el.className.trim().split(/\\s+/).filter(c => !c.startsWith('uxg-'))[0];
                        if (cls) selB = `${itemB.el.tagName.toLowerCase()}.${cls}`;
                    }
                    if (!selB) selB = itemB.el.tagName.toLowerCase();

                    const textA = (itemA.el.innerText || itemA.el.getAttribute('aria-label') || '').trim().slice(0, 30);
                    const textB = (itemB.el.innerText || itemB.el.getAttribute('aria-label') || '').trim().slice(0, 30);
                    overlaps.push({
                        selector: selA,
                        overlaps_with: selB,
                        text: textA ? `${textA} / ${textB}` : `${selA} / ${selB}`,
                        overlap_area: overlapArea,
                        bounding_box: {
                            x: Math.round(Math.max(rA.left, rB.left)),
                            y: Math.round(Math.max(rA.top, rB.top)),
                            width: Math.round(xOverlap),
                            height: Math.round(yOverlap)
                        },
                        help: `Interactive element (${selA}) overlaps with (${selB}) by ${overlapArea}px²`
                    });
                }
            }
        }

        return {
            tap_targets: smallTapTargets.slice(0, 10),
            contrast_issues: lowContrast.slice(0, 10),
            overlapping_elements: overlaps.slice(0, 10)
        };
    }
    """
    try:
        res = await page.evaluate(dom_check_js)
        if isinstance(res, dict):
            return res
    except Exception:
        pass
    return {"tap_targets": [], "contrast_issues": [], "overlapping_elements": []}


async def collect_step_evidence(page: Any) -> dict:
    """Orchestrates axe-core injection and DOM checks for the current stabilized step."""
    axe_violations = await collect_axe_violations(page)
    dom_res = await collect_dom_violations(page)
    return {
        "axe_violations": axe_violations,
        "tap_targets": dom_res.get("tap_targets", []),
        "contrast_issues": dom_res.get("contrast_issues", []),
        "overlapping_elements": dom_res.get("overlapping_elements", []),
    }


def draw_red_bounding_box(base64_image: str | None, bbox: dict | None) -> str | None:
    """Draws a 4px red bounding box (#ef4444) on the base64 screenshot."""
    if not base64_image or not bbox:
        return base64_image
    try:
        raw_b64 = base64_image
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(raw_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img)

        x = max(0, int(bbox.get("x", 0)))
        y = max(0, int(bbox.get("y", 0)))
        w = max(10, int(bbox.get("width", 20)))
        h = max(10, int(bbox.get("height", 20)))

        draw.rectangle([x, y, x + w, y + h], outline="#ef4444", width=4)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return base64_image


def _default_fix_from_evidence(finding: dict) -> str:
    """Generates a high-quality deterministic CSS or copy fix suggestion from raw evidence."""
    raw = finding.get("raw_evidence", {})
    ev_type = raw.get("type", "")
    sel = finding.get("selector") or raw.get("selector") or ".interactive-target"

    if ev_type == "tap_target":
        return f"CSS: {sel} {{\n  min-width: 44px;\n  min-height: 44px;\n  padding: 10px 14px;\n  display: inline-flex;\n  align-items: center;\n  justify-content: center;\n}}"
    elif ev_type == "contrast":
        return f"CSS: {sel} {{\n  color: #0f172a;\n  /* Upgrades contrast to > 7:1 against background for WCAG AA compliance */\n}}"
    elif ev_type == "overlap":
        with_sel = raw.get("overlaps_with", "neighbor")
        return f"CSS: {sel} {{\n  margin-right: 12px;\n  position: relative;\n  z-index: 10;\n}}\n{with_sel} {{\n  margin-left: 12px;\n}}"
    elif ev_type == "axe":
        axe_id = raw.get("id", "")
        if "contrast" in axe_id:
            return f"CSS: {sel} {{\n  color: #111827;\n}}"
        elif "button" in axe_id or "name" in axe_id or "label" in axe_id:
            return f"HTML: <button aria-label=\"Descriptive Action Label\"> or add inner text to {sel}."
        elif "image" in axe_id or "alt" in axe_id:
            return f"HTML: <img alt=\"Meaningful context description\" /> for {sel}."
        return f"CSS/HTML: Update {sel} to include valid accessible attributes and WCAG compliant attributes."
    elif ev_type == "dead_click":
        return f"JS: Ensure {sel} event listener is attached and renders immediate visual feedback or loading state on click."
    elif ev_type == "error":
        return f"JS: Add defensive null checks or verify backend endpoint response status handling."
    elif ev_type == "trust_signals":
        return f"Copy: Add explicit Privacy Policy link, customer review ratings, and clear pricing visibility before checkout."
    return f"CSS: {sel} {{\n  outline-offset: 2px;\n  transition: all 0.2s ease;\n}}"


def detect_findings_from_evidence(session: dict | Any) -> list[dict]:
    """
    Automated finding detection from collected step evidence.
    The LLM is strictly excluded from detection; all findings are derived from real evidence.
    """
    if isinstance(session, dict):
        steps = session.get("steps", [])
        baseline_failed = session.get("baseline_failed", False)
        baseline_note = session.get("baseline_note", "")
    else:
        steps = getattr(session, "steps", [])
        baseline_failed = getattr(session, "baseline_failed", False)
        baseline_note = getattr(session, "baseline_note", "")

    findings: list[dict] = []
    seen_keys: set[str] = set()

    if baseline_failed:
        findings.append({
            "title": "Baseline Failure: Objective May Be Unreachable",
            "severity": "critical",
            "step_number": 1,
            "evidence_steps": [1],
            "what_happened": f"The efficient baseline tester was unable to complete the task ({baseline_note or 'task may be unreachable or unclear'}).",
            "impact": "Indicates that the task instructions, starting page, or user flow may be broken or impossible to fulfill.",
            "recommendation": "Review the task description and target URL to ensure the objective can be completed directly.",
            "suggested_fix": "Copy: Clarify entry page links or navigation hierarchy so new users can directly reach the goal.",
            "selector": "body",
            "bounding_box": None,
            "raw_evidence": {"type": "baseline_failed", "note": baseline_note},
        })

    for s in steps:
        step_n = getattr(s, "n", 1) if not isinstance(s, dict) else s.get("n", 1)
        axes = (getattr(s, "axe_violations", []) if not isinstance(s, dict) else s.get("axe_violations", [])) or []
        taps = (getattr(s, "tap_targets", []) if not isinstance(s, dict) else s.get("tap_targets", [])) or []
        contrasts = (getattr(s, "contrast_issues", []) if not isinstance(s, dict) else s.get("contrast_issues", [])) or []
        overlaps = (getattr(s, "overlapping_elements", []) if not isinstance(s, dict) else s.get("overlapping_elements", [])) or []
        c_errs = (getattr(s, "console_errors", []) if not isinstance(s, dict) else s.get("console_errors", [])) or []
        n_errs = (getattr(s, "failed_requests", []) if not isinstance(s, dict) else s.get("failed_requests", [])) or []
        dead_click = getattr(s, "dead_click", False) if not isinstance(s, dict) else s.get("dead_click", False)
        target = getattr(s, "target", "") if not isinstance(s, dict) else s.get("target", "")
        label = getattr(s, "label", "") if not isinstance(s, dict) else s.get("label", "")

        # 1. Overlapping interactive elements (critical)
        for o in overlaps:
            key = f"overlap:{o.get('selector')}:{o.get('overlaps_with')}"
            if key not in seen_keys:
                seen_keys.add(key)
                findings.append({
                    "title": f"Overlapping Elements: {o.get('selector')} & {o.get('overlaps_with')}",
                    "severity": "critical",
                    "step_number": step_n,
                    "evidence_steps": [step_n],
                    "what_happened": f"Interactive element '{o.get('selector')}' overlaps with '{o.get('overlaps_with')}' by {o.get('overlap_area', 0)}px².",
                    "impact": "Users attempting to click or tap one control may inadvertently activate the other or encounter dead clicks.",
                    "recommendation": "",
                    "suggested_fix": "",
                    "selector": o.get("selector"),
                    "bounding_box": o.get("bounding_box"),
                    "raw_evidence": {"type": "overlap", "selector": o.get("selector"), "overlaps_with": o.get("overlaps_with"), "area": o.get("overlap_area")},
                })

        # 2. Axe accessibility violations
        for a in axes:
            key = f"axe:{a.get('id')}:{a.get('selector')}"
            if key not in seen_keys:
                seen_keys.add(key)
                impact = a.get("impact", "moderate")
                sev = "critical" if impact in ("critical", "serious") else "high" if impact == "moderate" else "medium"
                findings.append({
                    "title": f"Accessibility: {a.get('id')} ({a.get('selector')})",
                    "severity": sev,
                    "step_number": step_n,
                    "evidence_steps": [step_n],
                    "what_happened": f"Axe automated audit flagged '{a.get('id')}': {a.get('help', '')} on '{a.get('selector', '')}'.",
                    "impact": f"Fails WCAG guidelines with {impact} severity, impeding accessibility for users.",
                    "recommendation": "",
                    "suggested_fix": "",
                    "selector": a.get("selector"),
                    "bounding_box": a.get("bounding_box"),
                    "raw_evidence": {"type": "axe", "id": a.get("id"), "selector": a.get("selector"), "help": a.get("help"), "impact": impact},
                })

        # 3. Tap targets under 44x44px
        for t in taps:
            key = f"tap:{t.get('selector')}"
            if key not in seen_keys:
                seen_keys.add(key)
                w, h = t.get("width", 0), t.get("height", 0)
                sev = "high" if (w < 32 or h < 32) else "medium"
                findings.append({
                    "title": f"Undersized Touch Target: '{t.get('text') or t.get('selector')}' ({w}x{h}px)",
                    "severity": sev,
                    "step_number": step_n,
                    "evidence_steps": [step_n],
                    "what_happened": f"Interactive control '{t.get('text') or t.get('selector')}' is {w}x{h}px, below the recommended 44x44px target size.",
                    "impact": "Increases mis-taps, interaction friction, and rage clicks on mobile and touch devices.",
                    "recommendation": "",
                    "suggested_fix": "",
                    "selector": t.get("selector"),
                    "bounding_box": t.get("bounding_box"),
                    "raw_evidence": {"type": "tap_target", "selector": t.get("selector"), "width": w, "height": h, "text": t.get("text")},
                })

        # 4. Low-contrast text
        for c in contrasts:
            key = f"contrast:{c.get('selector')}"
            if key not in seen_keys:
                seen_keys.add(key)
                ratio = c.get("contrast_ratio", 0)
                sev = "high" if ratio < 3.0 else "medium"
                findings.append({
                    "title": f"Low Contrast Text: {ratio}:1 on '{c.get('text')}'",
                    "severity": sev,
                    "step_number": step_n,
                    "evidence_steps": [step_n],
                    "what_happened": f"Text '{c.get('text')}' has a contrast ratio of {ratio}:1 against background (minimum required is {c.get('min_ratio', 4.5)}:1).",
                    "impact": "Fails accessibility contrast thresholds, making copy illegible in bright environments or for impaired vision.",
                    "recommendation": "",
                    "suggested_fix": "",
                    "selector": c.get("selector"),
                    "bounding_box": c.get("bounding_box"),
                    "raw_evidence": {"type": "contrast", "selector": c.get("selector"), "contrast_ratio": ratio, "fg": c.get("fg_color")},
                })

        # 5. Dead clicks
        if dead_click:
            key = f"dead_click:{target or label}"
            if key not in seen_keys:
                seen_keys.add(key)
                findings.append({
                    "title": f"Unresponsive Target: Dead Click on '{label or target}'",
                    "severity": "high",
                    "step_number": step_n,
                    "evidence_steps": [step_n],
                    "what_happened": f"Clicking '{label or target}' yielded no DOM mutation, navigation, or visual state update.",
                    "impact": "Leaves users confused about whether their input was registered, provoking rage clicking.",
                    "recommendation": "",
                    "suggested_fix": "",
                    "selector": target,
                    "bounding_box": None,
                    "raw_evidence": {"type": "dead_click", "label": label, "target": target},
                })

        # 6. Technical errors
        if c_errs or n_errs:
            key = f"tech_error:{step_n}"
            if key not in seen_keys:
                seen_keys.add(key)
                err_sample = (c_errs + n_errs)[0][:100]
                findings.append({
                    "title": f"Technical Runtime Failure at Step {step_n}",
                    "severity": "high",
                    "step_number": step_n,
                    "evidence_steps": [step_n],
                    "what_happened": f"Encountered technical failures: {err_sample}.",
                    "impact": "Breaks scripts, styles, or API data fetching required to fulfill user tasks.",
                    "recommendation": "",
                    "suggested_fix": "",
                    "selector": "script",
                    "bounding_box": None,
                    "raw_evidence": {"type": "error", "console": c_errs[:2], "network": n_errs[:2]},
                })

    # Sort by severity: critical -> high -> medium
    sev_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}
    findings.sort(key=lambda f: sev_rank.get(f.get("severity", ""), 0), reverse=True)

    # Attach deterministic default fix initially
    for f in findings:
        f["suggested_fix"] = _default_fix_from_evidence(f)
        f["recommendation"] = f["suggested_fix"]

    # Limit to top 5 most actionable findings
    return findings[:5]


def attach_screenshots_with_bounding_boxes(findings: list[dict], steps: list[Any]) -> None:
    """Attaches step screenshot with a red bounding box (#ef4444) drawn on the offending element."""
    step_shots: dict[int, str] = {}
    for i, s in enumerate(steps):
        n = getattr(s, "n", i + 1) if not isinstance(s, dict) else s.get("n", i + 1)
        shot = getattr(s, "screenshot", None) if not isinstance(s, dict) else s.get("screenshot")
        if shot:
            step_shots[n] = shot

    for f in findings:
        step_n = f.get("step_number")
        if not step_n and f.get("evidence_steps"):
            step_n = f["evidence_steps"][0]
            f["step_number"] = step_n
        if not step_n and step_shots:
            step_n = list(step_shots.keys())[0]
            f["step_number"] = step_n

        raw_shot = step_shots.get(step_n) if step_n else None
        bbox = f.get("bounding_box")
        if raw_shot and bbox:
            f["screenshot"] = draw_red_bounding_box(raw_shot, bbox)
        elif raw_shot:
            f["screenshot"] = raw_shot
        else:
            f["screenshot"] = None


def generate_suggested_fixes(findings: list[dict], client: Any = None, model: str | None = None) -> None:
    """
    Invokes the LLM solely to generate concrete CSS or copy fix suggestions from the evidence.
    The LLM does NOT detect issues; it only writes the fix suggestions.
    """
    if not findings or client is None:
        return

    items_to_fix = [
        {
            "index": i,
            "title": f["title"],
            "selector": f.get("selector"),
            "what_happened": f["what_happened"],
            "raw_evidence": f.get("raw_evidence", {}),
        }
        for i, f in enumerate(findings)
    ]

    prompt = f"""You are a principal frontend engineer.
For each detected usability/accessibility issue below, provide a concrete, production-ready suggested fix (CSS code or copy text).
CRITICAL: Do NOT detect or invent any new issues. Only provide a specific fix suggestion for each issue below.

Issues:
{json.dumps(items_to_fix, indent=2)}

Respond ONLY with a valid JSON object matching this schema:
{{
  "fixes": [
    {{
      "index": 0,
      "suggested_fix": "CSS: .target {{ min-height: 44px; min-width: 44px; }}"
    }}
  ]
}}
"""
    try:
        if hasattr(client, "sync_chat_completion"):
            resp = client.sync_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model_type="text",
                temperature=0.2,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
        elif hasattr(client, "chat") and hasattr(client.chat, "completions"):
            resp = client.chat.completions.create(
                model=model or "openai/gpt-oss-120b",
                temperature=0.2,
                max_tokens=1500,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            data = json.loads(resp.choices[0].message.content)
        else:
            data = {}

        fixes = data.get("fixes", [])
        for item in fixes:
            idx = item.get("index")
            fix_text = item.get("suggested_fix")
            if idx is not None and 0 <= idx < len(findings) and fix_text:
                findings[idx]["suggested_fix"] = fix_text
                findings[idx]["recommendation"] = fix_text
    except Exception as e:
        print(f"LLM suggested fix generation exception: {e}")
