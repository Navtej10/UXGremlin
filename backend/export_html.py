import html
from typing import Any
from report_translator import translate_full_report, get_user_display_name


def generate_printable_html(report: dict[str, Any]) -> str:
    """
    Generates a print-friendly, self-contained HTML report structured for
    non-technical stakeholders (founders, marketers, designers, judges).
    Top to bottom layout:
    1. Header & Verdict card (friction score + plain label + outcome sentence + penalty reasons)
    2. Baseline failure card (if goal was unreachable, with last screenshot and blocker)
    3. 'What went wrong' timeline (step-by-step user journey with screenshots & stuck marker)
    4. 'Top problems to fix first' cards (with plain language, cropped screenshots & collapsible technical block)
    5. 'More minor issues' collapsed section
    """
    # Ensure report findings and scores are translated into plain-language format
    report = translate_full_report(dict(report))

    session_id = html.escape(str(report.get("session_id", "N/A")))
    url = html.escape(str(report.get("url", "N/A")))
    task = html.escape(str(report.get("task", "N/A")))
    persona = html.escape(str(report.get("persona", "pro_tester")))
    outcome = html.escape(str(report.get("outcome", "completed")).upper())
    outcome_reason = html.escape(str(report.get("outcome_reason", "")))
    verdict = html.escape(str(report.get("verdict", "")))
    user_name = get_user_display_name(report.get("persona"))

    score_dict = report.get("score", {}) if isinstance(report.get("score"), dict) else {}
    score_total = score_dict.get("total", score_dict.get("score", report.get("score", 0)))
    score_label = html.escape(str(score_dict.get("label", "Friction Score")))
    plain_label = html.escape(str(score_dict.get("plain_label", f"{score_total}/100: Usability Friction")))
    steps_taken = score_dict.get("steps_taken", len(report.get("actions", [])))
    ideal_steps = score_dict.get("ideal_steps", 1)

    score_color = "#39FF14" if score_total <= 20 else "#FBBF24" if score_total <= 45 else "#F97316" if score_total <= 70 else "#EF4444"

    # 1. Plain-Language Outcome Sentence
    if outcome.lower() in ("abandoned", "gave_up"):
        outcome_sentence = f"{user_name} tried to complete the task \"{task}\" but gave up at step {steps_taken} due to friction."
    elif outcome.lower() in ("timeout", "system_error"):
        outcome_sentence = f"The test stopped early at step {steps_taken} due to a system timeout limit while trying to \"{task}\"."
    else:
        outcome_sentence = f"{user_name} successfully finished the goal \"{task}\" across {steps_taken} steps."

    # 2. Score breakdown rows ("Why the score is this high")
    parts_html = ""
    for p in score_dict.get("parts", []):
        p_name = html.escape(str(p.get("name", "")))
        p_points = p.get("points", 0)
        p_why = html.escape(str(p.get("why", "")))
        parts_html += f"""
        <div class="part-item">
            <div class="part-header">
                <span class="part-name">{p_name}</span>
                <span class="part-points">+{p_points} pts</span>
            </div>
            <p class="part-why">{p_why}</p>
        </div>
        """

    # 3. Baseline Failure Blocker Card
    baseline_html = ""
    if report.get("baseline_failed"):
        b_note = html.escape(str(report.get("baseline_note", "")))
        actions = report.get("actions", [])
        last_shot = ""
        for a in reversed(actions):
            if a.get("screenshot"):
                s = a["screenshot"]
                last_shot = f"data:image/jpeg;base64,{s}" if not s.startswith("data:") else s
                break

        last_img_tag = f"""<div class="baseline-screenshot"><img src="{last_shot}" alt="Stuck point screenshot" /></div>""" if last_shot else ""
        baseline_html = f"""
        <div class="card baseline-card">
            <div class="baseline-header">
                <span class="badge badge-critical">Goal Blocked</span>
                <span class="baseline-title">The test user could not complete the goal</span>
            </div>
            <p class="baseline-desc">Here is where they got stuck and what was in their way: <em>{b_note or 'The user encountered an impassable obstacle or unclear navigation path.'}</em></p>
            {last_img_tag}
        </div>
        """

    # 4. Helper to render a finding card
    def render_finding_card(f: dict[str, Any], idx: int) -> str:
        f_title = html.escape(str(f.get("title", "Finding")))
        f_sev = html.escape(str(f.get("severity", "Medium")))
        f_sev_label = html.escape(str(f.get("severity_label", "")))
        f_where = html.escape(str(f.get("where", "")))
        f_what = html.escape(str(f.get("what_happened", "")))
        f_why = html.escape(str(f.get("why_it_matters", f.get("impact", ""))))
        f_fix = html.escape(str(f.get("how_to_fix", f.get("recommendation", f.get("suggested_fix", "")))))
        f_count = html.escape(str(f.get("affected_count", "Appears on this page")))
        f_caption = html.escape(str(f.get("screenshot_caption", f"Step {f.get('step_number', 1)}: {f_where}")))

        f_shot = f.get("screenshot")
        shot_img_tag = ""
        if f_shot:
            src = f"data:image/jpeg;base64,{f_shot}" if not f_shot.startswith("data:") else f_shot
            shot_img_tag = f"""
            <div class="finding-screenshot">
                <img src="{src}" alt="{f_title} preview" />
                <div class="screenshot-caption">{f_caption}</div>
            </div>
            """

        # Technical details (developer view, hidden by default)
        tech = f.get("technical", {})
        rule_id = html.escape(str(tech.get("rule_id", "ux-heuristic")))
        selector = html.escape(str(tech.get("selector", "N/A")))
        wcag = html.escape(str(tech.get("wcag", "N/A")))
        code_fix = html.escape(str(tech.get("suggested_css_or_html", "")))

        code_block = f"""<pre class="tech-code"><code>{code_fix}</code></pre>""" if code_fix else ""

        tech_html = f"""
        <details class="tech-details">
            <summary class="tech-summary">Show technical details (for developers)</summary>
            <div class="tech-body">
                <div><strong>Automated Rule:</strong> <code>{rule_id}</code></div>
                <div><strong>Standard Reference:</strong> {wcag}</div>
                <div><strong>Technical Location:</strong> <code>{selector}</code></div>
                {code_block}
            </div>
        </details>
        """

        where_badge = f"""<span class="location-badge">{f_where}</span>""" if f_where else ""
        count_badge = f"""<span class="count-badge">{f_count}</span>""" if f_count else ""

        return f"""
        <div class="finding-card">
            <div class="finding-header">
                <div class="finding-header-left">
                    <span class="finding-num">#{idx}</span>
                    <span class="finding-title">{f_title}</span>
                </div>
                <div class="finding-badges">
                    <span class="badge badge-{f_sev.lower()}">{f_sev} · {f_sev_label}</span>
                </div>
            </div>
            <div class="finding-meta">
                {where_badge}
                {count_badge}
            </div>
            <div class="finding-body">
                <p><strong>What happened:</strong> {f_what}</p>
                <p><strong>Why it matters:</strong> {f_why}</p>
                <div class="how-to-fix-box">
                    <strong>How to fix:</strong> {f_fix}
                </div>
                {shot_img_tag}
                {tech_html}
            </div>
        </div>
        """

    # 5. Top Problems to Fix First
    top_findings = report.get("top_findings") or report.get("findings", [])[:6]
    minor_findings = report.get("minor_findings") or report.get("findings", [])[6:]

    top_findings_html = ""
    if top_findings:
        for idx, f in enumerate(top_findings, 1):
            top_findings_html += render_finding_card(f, idx)
    else:
        top_findings_html = "<p class='no-findings'>No critical friction or defects detected during this audit.</p>"

    # 6. More Minor Issues Collapsed List
    minor_issues_html = ""
    if minor_findings:
        minor_cards = ""
        for idx, f in enumerate(minor_findings, len(top_findings) + 1):
            minor_cards += render_finding_card(f, idx)

        minor_issues_html = f"""
        <section class="section">
            <details class="minor-section-details">
                <summary class="minor-section-summary">More minor issues ({len(minor_findings)} found)</summary>
                <div class="minor-cards-container">
                    {minor_cards}
                </div>
            </details>
        </section>
        """

    # 7. "What went wrong" Journey Timeline
    actions_html = ""
    actions = report.get("actions", [])
    for idx, a in enumerate(actions, 1):
        st_num = a.get("step_number", idx)
        st_act = html.escape(str(a.get("action", "")))
        st_tgt = html.escape(str(a.get("target", "")))
        st_tht = html.escape(str(a.get("thought", "")))
        st_shot = a.get("screenshot")
        is_stuck = (idx == len(actions)) and (outcome.lower() in ("abandoned", "gave_up", "timeout"))

        stuck_badge = """<span class="stuck-badge">STUCK HERE</span>""" if is_stuck else ""
        shot_tag = f"""<img class="timeline-thumb" src="data:image/jpeg;base64,{st_shot}" alt="Step {st_num}" />""" if st_shot else ""

        actions_html += f"""
        <div class="timeline-item {'timeline-item-stuck' if is_stuck else ''}">
            <div class="timeline-step">Step {st_num} {stuck_badge}</div>
            <div class="timeline-content">
                <div class="timeline-action"><strong>[{st_act.upper()}]</strong> {st_tgt}</div>
                <div class="timeline-thought">{st_tht}</div>
                {shot_tag}
            </div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UXGremlin Usability Report - {session_id}</title>
    <style>
        :root {{
            --bg-color: #0B0C10;
            --card-bg: #1F2833;
            --text-color: #C5C6C7;
            --heading-color: #FFFFFF;
            --purple: #9D00FF;
            --green: #39FF14;
            --border-color: #374151;
            --critical: #EF4444;
            --medium: #F59E0B;
            --low: #3B82F6;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 30px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 920px;
            margin: 0 auto;
        }}
        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 20px;
            border-bottom: 2px solid var(--purple);
            margin-bottom: 25px;
        }}
        .logo-title {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .logo-title h1 {{
            margin: 0;
            font-size: 24px;
            color: var(--heading-color);
            letter-spacing: 1px;
            text-transform: uppercase;
        }}
        .print-btn {{
            background: var(--purple);
            color: #FFFFFF;
            border: none;
            padding: 9px 16px;
            border-radius: 8px;
            font-weight: bold;
            font-size: 13px;
            cursor: pointer;
        }}
        .meta-strip {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            background: var(--card-bg);
            padding: 14px 18px;
            border-radius: 10px;
            margin-bottom: 20px;
            border: 1px solid var(--border-color);
            font-size: 13px;
        }}
        .meta-item label {{
            display: block;
            font-size: 11px;
            text-transform: uppercase;
            color: #9CA3AF;
            font-weight: bold;
            margin-bottom: 2px;
        }}
        .meta-item p {{
            margin: 0;
            color: #F3F4F6;
            word-break: break-all;
        }}
        .verdict-card {{
            background: #111827;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
        }}
        .verdict-header {{
            display: flex;
            align-items: center;
            gap: 20px;
            padding-bottom: 18px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 16px;
        }}
        .score-number {{
            font-size: 52px;
            font-weight: 900;
            font-family: monospace;
            line-height: 1;
            color: {score_color};
        }}
        .verdict-title {{
            font-size: 18px;
            font-weight: bold;
            color: #FFFFFF;
            margin: 0 0 4px 0;
        }}
        .verdict-outcome {{
            font-size: 14px;
            color: #9CA3AF;
            margin: 0;
        }}
        .verdict-summary {{
            font-size: 14px;
            line-height: 1.6;
            color: #E5E7EB;
            margin: 0 0 20px 0;
        }}
        .parts-title {{
            font-size: 12px;
            text-transform: uppercase;
            font-weight: bold;
            color: #9CA3AF;
            letter-spacing: 0.5px;
            margin-bottom: 12px;
        }}
        .parts-list {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 12px;
        }}
        .part-item {{
            background: #1F2833;
            border: 1px solid var(--border-color);
            padding: 12px 14px;
            border-radius: 8px;
        }}
        .part-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 13px;
            font-weight: bold;
            margin-bottom: 4px;
        }}
        .part-name {{ color: #F3F4F6; }}
        .part-points {{ color: var(--critical); font-family: monospace; }}
        .part-why {{
            font-size: 12px;
            color: #9CA3AF;
            margin: 0;
            line-height: 1.4;
        }}
        .baseline-card {{
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        .baseline-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 8px;
        }}
        .baseline-title {{
            font-size: 16px;
            font-weight: bold;
            color: #F87171;
        }}
        .baseline-desc {{
            font-size: 13px;
            color: #E5E7EB;
            margin: 0 0 12px 0;
        }}
        .baseline-screenshot img {{
            max-width: 100%;
            border-radius: 8px;
            border: 1px solid #4B5563;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .section h2 {{
            font-size: 18px;
            color: #FFFFFF;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
            margin-bottom: 18px;
        }}
        .finding-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 18px;
        }}
        .finding-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 8px;
        }}
        .finding-header-left {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .finding-num {{
            font-size: 12px;
            font-family: monospace;
            background: #111827;
            padding: 3px 8px;
            border-radius: 6px;
            color: #9CA3AF;
            font-weight: bold;
        }}
        .finding-title {{
            font-size: 16px;
            font-weight: bold;
            color: #FFFFFF;
        }}
        .finding-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 12px;
        }}
        .location-badge {{
            font-size: 11px;
            font-weight: 600;
            background: #111827;
            color: #60A5FA;
            padding: 3px 10px;
            border-radius: 6px;
            border: 1px solid #1E3A8A;
        }}
        .count-badge {{
            font-size: 11px;
            font-weight: 600;
            background: #111827;
            color: #FBBF24;
            padding: 3px 10px;
            border-radius: 6px;
            border: 1px solid #78350F;
        }}
        .finding-body p {{
            margin: 0 0 8px 0;
            font-size: 13px;
            color: #D1D5DB;
        }}
        .how-to-fix-box {{
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            border-radius: 8px;
            padding: 10px 14px;
            font-size: 13px;
            color: #6EE7B7;
            margin-top: 10px;
            margin-bottom: 14px;
        }}
        .finding-screenshot {{
            margin-top: 14px;
            margin-bottom: 14px;
            text-align: center;
            background: #111827;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }}
        .finding-screenshot img {{
            max-width: 100%;
            border-radius: 6px;
            display: block;
            margin: 0 auto;
        }}
        .screenshot-caption {{
            font-size: 12px;
            color: #9CA3AF;
            margin-top: 8px;
            font-weight: 500;
        }}
        .tech-details {{
            margin-top: 12px;
            border-top: 1px solid var(--border-color);
            padding-top: 10px;
            font-size: 12px;
        }}
        .tech-summary {{
            color: #9CA3AF;
            cursor: pointer;
            font-weight: 600;
            user-select: none;
        }}
        .tech-summary:hover {{ color: #F3F4F6; }}
        .tech-body {{
            background: #111827;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            margin-top: 8px;
            color: #9CA3AF;
            font-size: 12px;
            line-height: 1.6;
        }}
        .tech-body code {{
            color: #F43F5E;
            font-family: monospace;
        }}
        .tech-code {{
            background: #0B0C10;
            padding: 8px;
            border-radius: 6px;
            overflow-x: auto;
            color: #34D399;
            margin-top: 6px;
            font-size: 11px;
        }}
        .minor-section-summary {{
            font-size: 15px;
            font-weight: bold;
            color: #9CA3AF;
            cursor: pointer;
            padding: 12px;
            background: var(--card-bg);
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }}
        .minor-section-summary:hover {{ color: #FFFFFF; }}
        .minor-cards-container {{ margin-top: 14px; }}
        .timeline-item {{
            display: flex;
            gap: 14px;
            padding: 12px;
            background: #111827;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            margin-bottom: 10px;
            font-size: 13px;
        }}
        .timeline-item-stuck {{
            border-color: var(--critical);
            background: rgba(239, 68, 68, 0.08);
        }}
        .timeline-step {{
            font-weight: bold;
            color: #F3F4F6;
            min-width: 80px;
        }}
        .stuck-badge {{
            display: inline-block;
            background: var(--critical);
            color: #FFFFFF;
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 4px;
            font-weight: 800;
        }}
        .timeline-content {{ flex: 1; }}
        .timeline-action {{ color: #E5E7EB; margin-bottom: 2px; }}
        .timeline-thought {{ color: #9CA3AF; font-style: italic; font-size: 12px; }}
        .timeline-thumb {{
            max-height: 80px;
            margin-top: 6px;
            border-radius: 4px;
            border: 1px solid var(--border-color);
        }}
        .badge {{
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
            text-transform: uppercase;
        }}
        .badge-critical, .badge-high {{ background: rgba(239, 68, 68, 0.2); color: #F87171; border: 1px solid rgba(239, 68, 68, 0.4); }}
        .badge-medium {{ background: rgba(245, 158, 11, 0.2); color: #FBBF24; border: 1px solid rgba(245, 158, 11, 0.4); }}
        .badge-low {{ background: rgba(59, 130, 246, 0.2); color: #60A5FA; border: 1px solid rgba(59, 130, 246, 0.4); }}
        .badge-completed {{ background: rgba(16, 185, 129, 0.2); color: #34D399; }}
        .badge-abandoned, .badge-gave_up {{ background: rgba(239, 68, 68, 0.2); color: #F87171; }}
        @media print {{
            body {{ background: #FFFFFF; color: #111827; padding: 10px; }}
            .verdict-card, .finding-card, .meta-strip, .timeline-item {{ background: #FFFFFF; border-color: #E5E7EB; color: #111827; }}
            .verdict-title, .finding-title, .section h2, .logo-title h1 {{ color: #111827; }}
            .print-btn {{ display: none; }}
            .tech-details {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-title">
                <span style="font-size: 28px;">😈</span>
                <h1>UXGremlin Usability Audit</h1>
            </div>
            <button class="print-btn" onclick="window.print()">Print / Export PDF</button>
        </div>

        <div class="meta-strip">
            <div class="meta-item">
                <label>Website Tested</label>
                <p>{url}</p>
            </div>
            <div class="meta-item">
                <label>Goal / Objective</label>
                <p>"{task}"</p>
            </div>
            <div class="meta-item">
                <label>Tester Profile</label>
                <p>{persona} ({user_name})</p>
            </div>
            <div class="meta-item">
                <label>Audit Reference</label>
                <p style="font-family: monospace;">{session_id}</p>
            </div>
        </div>

        <!-- 1. Verdict Card -->
        <div class="verdict-card">
            <div class="verdict-header">
                <div>
                    <div class="score-number">{score_total}</div>
                </div>
                <div style="flex: 1;">
                    <div class="verdict-title">{plain_label}</div>
                    <p class="verdict-outcome">{outcome_sentence}</p>
                </div>
            </div>

            <p class="verdict-summary">{verdict}</p>

            <div class="parts-title">Why the score is this high</div>
            <div class="parts-list">
                {parts_html}
            </div>
        </div>

        <!-- 2. Baseline Failure Blocker Card (if applicable) -->
        {baseline_html}

        <!-- 3. Top Problems to Fix First -->
        <section class="section">
            <h2>Top problems to fix first ({len(top_findings)})</h2>
            {top_findings_html}
        </section>

        <!-- 4. More Minor Issues (Collapsed) -->
        {minor_issues_html}

        <!-- 5. What Went Wrong Timeline -->
        <section class="section">
            <h2>What went wrong — step-by-step journey ({len(actions)} Steps)</h2>
            <div style="max-height: 480px; overflow-y: auto; padding-right: 6px;">
                {actions_html}
            </div>
        </section>
    </div>
</body>
</html>
"""
