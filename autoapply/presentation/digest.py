"""HTML Copilot Action Dashboard and Markdown Daily Digest rendering."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


def render_copilot_html(items: list[dict], candidate_name: str, output_path: Path) -> None:
    """Render an interactive HTML action dashboard for Smart Copilot."""
    cards_html = []
    for it in items:
        score = it.get("score", 0)
        badge_class = "badge-high" if score >= 80 else ("badge-med" if score >= 65 else "badge-low")
        pdf_button = (
            f'<a href="generated_resumes/{it["pdf_name"]}" target="_blank" class="btn btn-pdf">📄 Open Tailored PDF</a>'
            if it.get("pdf_path")
            else '<span class="skipped-label">Below Threshold</span>'
        )

        comp_clean = it.get("company", "Company").replace(" ", "_").replace("'", "")

        cover_note = it.get("cover_note", "")
        note_section = (
            f'<div class="note-box">'
            f'<strong>📨 Recruiter Outreach Note:</strong>'
            f'<p class="note-text" id="note-{comp_clean}">{cover_note}</p>'
            f'<button onclick="navigator.clipboard.writeText(document.getElementById(\'note-{comp_clean}\').innerText); alert(\'Copied outreach note!\');" class="btn btn-copy">📋 Copy Outreach Note</button>'
            f'</div>'
            if cover_note
            else ""
        )

        referral_note = it.get("referral_note", "")
        referral_section = (
            f'<div class="note-box ref-box">'
            f'<strong>🤝 Employee Referral Pitch:</strong>'
            f'<p class="note-text" id="ref-{comp_clean}">{referral_note}</p>'
            f'<button onclick="navigator.clipboard.writeText(document.getElementById(\'ref-{comp_clean}\').innerText); alert(\'Copied referral pitch!\');" class="btn btn-copy btn-ref">📋 Copy Referral Pitch</button>'
            f'</div>'
            if referral_note
            else ""
        )

        platform_str = it.get("platform", "web").upper()

        cards_html.append(f"""
        <div class="job-card" data-comp="{comp_clean}">
            <div class="card-header">
                <div>
                    <h3>{it.get('role', 'Software Engineer')}</h3>
                    <div class="company-sub">{it.get('company', 'Company')} • <span class="loc">{it.get('location', 'India')}</span> • <span class="plat">{platform_str}</span></div>
                </div>
                <div class="score-badge {badge_class}">{score}% ATS</div>
            </div>
            <div class="card-actions">
                {pdf_button}
                <a href="{it.get('url', '#')}" target="_blank" class="btn btn-apply">🚀 Apply on {it.get('platform', 'Web').title()}</a>
                <button onclick="markApplied('{comp_clean}')" class="btn btn-mark">Mark as Applied</button>
            </div>
            {note_section}
            {referral_section}
        </div>
        """)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart Copilot — Daily Action Digest</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }}
        .container {{ max-width: 960px; margin: 0 auto; }}
        header {{ text-align: center; margin-bottom: 2rem; border-bottom: 1px solid #334155; padding-bottom: 1.5rem; }}
        h1 {{ font-size: 1.8rem; margin: 0 0 0.5rem 0; color: #38bdf8; }}
        p.subtitle {{ color: #94a3b8; margin: 0; }}
        .job-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.25rem; transition: all 0.2s; }}
        .job-card.applied {{ border-color: #22c55e; background: #0f291e; opacity: 0.85; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem; }}
        h3 {{ margin: 0 0 0.25rem 0; font-size: 1.25rem; color: #f1f5f9; }}
        .company-sub {{ font-size: 0.9rem; color: #94a3b8; }}
        .plat {{ background: #475569; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; color: #fff; font-weight: 600; }}
        .score-badge {{ font-weight: bold; padding: 6px 12px; border-radius: 8px; font-size: 0.95rem; }}
        .badge-high {{ background: #166534; color: #86efac; border: 1px solid #22c55e; }}
        .badge-med {{ background: #854d0e; color: #fef08a; border: 1px solid #eab308; }}
        .badge-low {{ background: #7f1d1d; color: #fca5a5; }}
        .card-actions {{ display: flex; gap: 0.75rem; align-items: center; margin-top: 1rem; flex-wrap: wrap; }}
        .btn {{ display: inline-block; padding: 8px 16px; border-radius: 6px; font-size: 0.9rem; text-decoration: none; font-weight: 500; cursor: pointer; border: none; }}
        .btn-apply {{ background: #2563eb; color: #fff; }}
        .btn-apply:hover {{ background: #1d4ed8; }}
        .btn-pdf {{ background: #059669; color: #fff; }}
        .btn-pdf:hover {{ background: #047857; }}
        .btn-copy {{ background: #334155; color: #f8fafc; font-size: 0.8rem; margin-top: 0.5rem; }}
        .btn-copy:hover {{ background: #475569; }}
        .btn-ref {{ background: #1e3a8a; }}
        .btn-ref:hover {{ background: #2563eb; }}
        .btn-mark {{ background: #1e293b; color: #94a3b8; border: 1px solid #475569; }}
        .btn-mark:hover {{ background: #334155; color: #fff; }}
        .note-box {{ background: #0f172a; border: 1px dashed #475569; border-radius: 8px; padding: 0.75rem 1rem; margin-top: 1rem; }}
        .ref-box {{ border-color: #3b82f6; }}
        .note-text {{ margin: 0.35rem 0 0.5rem 0; font-size: 0.88rem; color: #cbd5e1; font-style: italic; line-height: 1.4; }}
        .skipped-label {{ color: #94a3b8; font-size: 0.85rem; font-style: italic; }}
    </style>
    <script>
        function markApplied(compClean) {{
            const card = document.querySelector(`[data-comp="${{compClean}}"]`);
            if (card) {{
                card.classList.toggle('applied');
                const isApp = card.classList.contains('applied');
                localStorage.setItem('applied_' + compClean, isApp ? '1' : '0');
                const btn = card.querySelector('.btn-mark');
                if (btn) btn.innerText = isApp ? '✓ Applied' : 'Mark as Applied';
            }}
        }}
        window.addEventListener('DOMContentLoaded', () => {{
            document.querySelectorAll('.job-card').forEach(card => {{
                const comp = card.getAttribute('data-comp');
                if (comp && localStorage.getItem('applied_' + comp) === '1') {{
                    card.classList.add('applied');
                    const btn = card.querySelector('.btn-mark');
                    if (btn) btn.innerText = '✓ Applied';
                }}
            }});
        }});
    </script>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎯 Smart Copilot Action Digest</h1>
            <p class="subtitle">Candidate: <strong>{candidate_name}</strong> • High-Impact Target Roles</p>
        </header>
        {"".join(cards_html) if cards_html else '<p style="text-align:center; color:#94a3b8;">🎉 All caught up! No active jobs in queue.</p>'}
    </div>
</body>
</html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def render_daily_digest_markdown(
    items: list[dict],
    candidate_name: str,
    output_path: Path,
    applied_items: list[dict] | None = None,
) -> None:
    """Render a clean Markdown summary for GitHub viewing."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# 🌅 Daily Job & Resume Action Digest — {now_str[:10]}",
        "",
        f"**Candidate:** {candidate_name} | **Target Profile:** Assistant Manager / Java Backend (Spring Boot, Kafka, Microservices)",
        f"**Last Sync:** `{now_str}`",
        "",
        "## 🎯 Action Queue (Ready to Apply)",
        "",
    ]

    if items:
        lines.extend([
            "| Company | Role | Location | ATS Match | Apply Link | Tailored Resume | Recruiter Note | Referral Pitch |",
            "|:---|:---|:---|:---:|:---:|:---:|:---|:---|",
        ])
        for it in items:
            company = it.get("company", "Company")
            role = it.get("role", "Software Engineer")
            loc = it.get("location") or "Bengaluru / Gurgaon"
            score = it.get("score", 0)
            url = it.get("url", "#")
            pdf_name = it.get("pdf_name")
            pdf_link = f"[📄 Download PDF](data/generated_resumes/{pdf_name})" if pdf_name else "N/A"
            note = it.get("cover_note", "").replace("\n", " ").strip()
            note_short = f"<details><summary>Outreach</summary>{note}</details>" if note else "-"

            ref_note = it.get("referral_note", "").replace("\n", " ").strip()
            ref_short = f"<details><summary>Pitch</summary>{ref_note}</details>" if ref_note else "-"

            apply_btn = f"[🚀 Apply Now]({url})" if url != "#" else "Direct Search"
            lines.append(
                f"| **{company}** | {role} | {loc} | **{score}%** | {apply_btn} | {pdf_link} | {note_short} | {ref_short} |"
            )
    else:
        lines.append("> 🎉 **All caught up!** You have applied to all recommended roles in the queue. The next automated morning run will discover and tailor fresh roles.")

    if applied_items:
        lines.extend([
            "",
            f"## ✅ Submitted Applications History ({len(applied_items)} Total)",
            "",
            "| Company | Role | Platform | ATS Match | Applied Date | Tailored Resume |",
            "|:---|:---|:---:|:---:|:---|:---:|",
        ])
        for it in applied_items:
            comp = it.get("company", "Company")
            role = it.get("role", "Software Engineer")
            plat = it.get("platform", "web").upper()
            score = it.get("score", 0)
            applied_at = it.get("applied_at", "-")
            pdf_name = it.get("pdf_name")
            pdf_link = f"[📄 PDF](data/generated_resumes/{pdf_name})" if pdf_name else "-"
            lines.append(
                f"| **{comp}** | {role} | {plat} | **{score}%** | `{applied_at}` | {pdf_link} |"
            )

    lines.append("")
    lines.append("---")
    lines.append("*Generated by AutoApply Smart Copilot. Resumes are 100% truthful without fabricated credentials or certifications.*")
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
