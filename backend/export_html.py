import html
from typing import Any


def generate_printable_html(report: dict[str, Any]) -> str:
    """
    Generates a print-friendly, self-contained HTML report with
    score, outcome, breakdown, and findings with screenshots.
    """
    session_id = html.escape(str(report.get("session_id", "N/A")))
    url = html.escape(str(report.get("url", "N/A")))
    task = html.escape(str(report.get("task", "N/A")))
    persona = html.escape(str(report.get("persona", "pro_tester")))
    outcome = html.escape(str(report.get("outcome", "completed")).upper())
    outcome_reason = html.escape(str(report.get("outcome_reason", "")))
    verdict = html.escape(str(report.get("verdict", "")))

    score_dict = report.get("score", {}) if isinstance(report.get("score"), dict) else {}
    score_total = score_dict.get("total", report.get("score", 0))
    score_label = html.escape(str(score_dict.get("label", "Friction Score")))
    steps_taken = score_dict.get("steps_taken", len(report.get("actions", [])))
    ideal_steps = score_dict.get("ideal_steps", 1)

    score_color = "#39FF14" if score_total <= 20 else "#FBBF24" if score_total <= 45 else "#F97316" if score_total <= 70 else "#EF4444"

    # Score parts HTML
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

    # Persona comparison HTML (if compare mode)
    comparison_html = ""
    comparison_summary = report.get("comparison_summary", [])
    if not comparison_summary and isinstance(report.get("comparison"), dict):
        comparison_summary = list(report["comparison"].values())

    if comparison_summary:
        comparison_rows = ""
        for item in comparison_summary:
            p_name = html.escape(str(item.get("persona_label") or item.get("persona", "")))
            p_score = item.get("score", 0)
            p_outcome = html.escape(str(item.get("outcome", "completed")).upper())
            p_steps = item.get("steps", 0)
            p_finding = html.escape(str(item.get("top_finding", "No major issues")))
            p_color = "#10B981" if p_score <= 20 else "#F59E0B" if p_score <= 45 else "#F97316" if p_score <= 70 else "#EF4444"

            comparison_rows += f"""
            <tr>
                <td><strong>{p_name}</strong></td>
                <td><span style="font-weight: bold; color: {p_color};">{p_score}</span> / 100</td>
                <td><span class="badge badge-{item.get('outcome', 'completed')}">{p_outcome}</span></td>
                <td>{p_steps}</td>
                <td>{p_finding}</td>
            </tr>
            """

        comparison_html = f"""
        <section class="section">
            <h2>Persona Usability Comparison</h2>
            <table class="table">
                <thead>
                    <tr>
                        <th>Persona Archetype</th>
                        <th>Score</th>
                        <th>Outcome</th>
                        <th>Steps</th>
                        <th>Top Finding</th>
                    </tr>
                </thead>
                <tbody>
                    {comparison_rows}
                </tbody>
            </table>
        </section>
        """

    # Findings HTML with screenshots
    findings_html = ""
    findings = report.get("findings", [])
    if findings:
        for idx, f in enumerate(findings, 1):
            f_title = html.escape(str(f.get("title", "Finding")))
            f_sev = html.escape(str(f.get("severity", "medium")).upper())
            f_what = html.escape(str(f.get("what_happened", "")))
            f_impact = html.escape(str(f.get("impact", "")))
            f_rec = html.escape(str(f.get("recommendation", f.get("suggested_fix", ""))))
            f_shot = f.get("screenshot")

            shot_img_tag = ""
            if f_shot:
                src = f"data:image/jpeg;base64,{f_shot}" if not f_shot.startswith("data:") else f_shot
                shot_img_tag = f"""
                <div class="finding-screenshot">
                    <img src="{src}" alt="{f_title} screenshot" />
                </div>
                """

            findings_html += f"""
            <div class="finding-card">
                <div class="finding-header">
                    <span class="finding-num">#{idx}</span>
                    <span class="finding-title">{f_title}</span>
                    <span class="badge badge-{f.get('severity', 'medium').lower()}">{f_sev}</span>
                </div>
                <div class="finding-body">
                    <p><strong>Observation:</strong> {f_what}</p>
                    <p><strong>Impact:</strong> {f_impact}</p>
                    <p><strong>Recommended Fix:</strong> <span class="fix-text">{f_rec}</span></p>
                    {shot_img_tag}
                </div>
            </div>
            """
    else:
        findings_html = "<p class='no-findings'>No critical friction or defects detected during this audit.</p>"

    # Steps transcript HTML
    actions_html = ""
    for a in report.get("actions", []):
        st_num = a.get("step_number", "")
        st_act = html.escape(str(a.get("action", "")))
        st_tgt = html.escape(str(a.get("target", "")))
        st_tht = html.escape(str(a.get("thought", "")))
        actions_html += f"""
        <div class="action-item">
            <span class="action-step">Step {st_num}</span>
            <span class="action-type">[{st_act}]</span>
            <span class="action-desc">{st_tgt} — {st_tht}</span>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UXGremlin Report - {session_id}</title>
    <style>
        :root {{
            --bg-color: #0B0C10;
            --card-bg: #1F2833;
            --text-color: #C5C6C7;
            --heading-color: #FFFFFF;
            --purple: #9D00FF;
            --green: #39FF14;
            --border-color: #374151;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 30px;
            line-height: 1.5;
        }}
        .container {{
            max-width: 900px;
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
            font-size: 26px;
            color: var(--heading-color);
            letter-spacing: 1px;
            text-transform: uppercase;
        }}
        .print-btn {{
            background: var(--purple);
            color: #FFFFFF;
            border: none;
            padding: 10px 18px;
            border-radius: 8px;
            font-weight: bold;
            font-size: 13px;
            cursor: pointer;
            box-shadow: 0 0 15px rgba(157, 0, 255, 0.4);
        }}
        .print-btn:hover {{
            background: #8000d6;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 25px;
        }}
        .meta-item label {{
            display: block;
            font-size: 11px;
            text-transform: uppercase;
            color: #9CA3AF;
            font-weight: bold;
            margin-bottom: 4px;
        }}
        .meta-item p {{
            margin: 0;
            color: #FFFFFF;
            font-size: 14px;
            word-break: break-all;
        }}
        .score-banner {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #000000;
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px 25px;
            margin-bottom: 25px;
        }}
        .score-number {{
            font-size: 56px;
            font-weight: 900;
            color: {score_color};
            line-height: 1;
        }}
        .score-info h3 {{
            margin: 0 0 5px 0;
            color: #FFFFFF;
            font-size: 18px;
        }}
        .score-info p {{
            margin: 0;
            font-size: 13px;
            color: #9CA3AF;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .section h2 {{
            color: #FFFFFF;
            font-size: 18px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
            margin-bottom: 15px;
        }}
        .part-item {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px 16px;
            margin-bottom: 10px;
        }}
        .part-header {{
            display: flex;
            justify-content: space-between;
            font-weight: bold;
            color: #FFFFFF;
            font-size: 13px;
        }}
        .part-why {{
            margin: 4px 0 0 0;
            font-size: 12px;
            color: #9CA3AF;
        }}
        .finding-card {{
            background: #14171E;
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 18px;
            margin-bottom: 20px;
            page-break-inside: avoid;
        }}
        .finding-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }}
        .finding-num {{
            font-family: monospace;
            color: var(--purple);
            font-weight: bold;
            font-size: 14px;
        }}
        .finding-title {{
            font-size: 15px;
            font-weight: bold;
            color: #FFFFFF;
            flex: 1;
        }}
        .finding-body p {{
            margin: 6px 0;
            font-size: 13px;
        }}
        .fix-text {{
            color: var(--green);
            font-weight: 500;
        }}
        .finding-screenshot {{
            margin-top: 12px;
            border: 1px solid #4B5563;
            border-radius: 8px;
            overflow: hidden;
            background: #000000;
        }}
        .finding-screenshot img {{
            width: 100%;
            height: auto;
            display: block;
        }}
        .table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            background: var(--card-bg);
            border-radius: 8px;
            overflow: hidden;
        }}
        .table th, .table td {{
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }}
        .table th {{
            background: #111827;
            color: #D1D5DB;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: bold;
            text-transform: uppercase;
            font-family: monospace;
        }}
        .badge-critical {{ background: #7F1D1D; color: #FCA5A5; }}
        .badge-high {{ background: #7C2D12; color: #FDBA74; }}
        .badge-medium {{ background: #78350F; color: #FDE68A; }}
        .badge-completed {{ background: #064E3B; color: #6EE7B7; }}
        .badge-abandoned {{ background: #78350F; color: #FDE68A; }}
        .badge-gave_up, .badge-error {{ background: #7F1D1D; color: #FCA5A5; }}

        .action-item {{
            font-family: monospace;
            font-size: 11px;
            padding: 6px 10px;
            border-bottom: 1px solid #1F2937;
            display: flex;
            gap: 8px;
        }}
        .action-step {{ color: var(--purple); font-weight: bold; }}
        .action-type {{ color: var(--green); }}

        /* Print Media Styles */
        @media print {{
            body {{
                background-color: #FFFFFF !important;
                color: #111827 !important;
                padding: 0 !important;
            }}
            .print-btn {{ display: none !important; }}
            .header {{ border-bottom: 2px solid #000000; }}
            .logo-title h1 {{ color: #000000 !important; }}
            .meta-grid, .score-banner, .part-item, .finding-card, .table {{
                background-color: #F9FAFB !important;
                border: 1px solid #E5E7EB !important;
                color: #111827 !important;
                box-shadow: none !important;
            }}
            .meta-item p, .score-info h3, .part-header, .finding-title {{
                color: #000000 !important;
            }}
            .score-number {{ color: #111827 !important; }}
            .fix-text {{ color: #059669 !important; }}
            .finding-card {{ page-break-inside: avoid; }}
            .finding-screenshot {{ border: 1px solid #D1D5DB !important; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <div class="logo-title">
                <h1>UXGremlin Sabotage Report</h1>
            </div>
            <button class="print-btn" onclick="window.print()">Print / Save as PDF</button>
        </header>

        <div class="meta-grid">
            <div class="meta-item">
                <label>Target URL</label>
                <p>{url}</p>
            </div>
            <div class="meta-item">
                <label>Target Task</label>
                <p>{task}</p>
            </div>
            <div class="meta-item">
                <label>Persona</label>
                <p>{persona}</p>
            </div>
            <div class="meta-item">
                <label>Task Outcome</label>
                <p><span class="badge badge-{report.get('outcome', 'completed')}">{outcome}</span></p>
            </div>
            <div class="meta-item">
                <label>Session ID</label>
                <p style="font-family: monospace;">{session_id}</p>
            </div>
        </div>

        <div class="score-banner">
            <div>
                <div class="score-number">{score_total}</div>
            </div>
            <div class="score-info" style="flex: 1; padding-left: 25px;">
                <h3>Friction Assessment: {score_label}</h3>
                <p>{steps_taken} steps taken (ideal: ~{ideal_steps}). {verdict}</p>
                {f"<p style='color: #FCA5A5; margin-top: 4px;'>{outcome_reason}</p>" if outcome_reason else ""}
            </div>
        </div>

        {comparison_html}

        <section class="section">
            <h2>Friction Score Breakdown</h2>
            <div class="parts-list">
                {parts_html}
            </div>
        </section>

        <section class="section">
            <h2>Detailed Usability Findings ({len(findings)})</h2>
            {findings_html}
        </section>

        <section class="section">
            <h2>Action Transcript ({len(report.get('actions', []))} Steps)</h2>
            <div style="background: #111827; border-radius: 8px; padding: 10px; max-height: 400px; overflow-y: auto;">
                {actions_html}
            </div>
        </section>
    </div>
</body>
</html>
"""
