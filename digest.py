"""
Saves the job search digest as an HTML file you can open in any browser.
(SMTP is skipped — Microsoft blocks basic auth on Outlook.com accounts.)
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

CATEGORY_EMOJI = {
    "offer":              "💼",
    "recruiter":          "📩",
    "interview":          "🗓️",
    "application_update": "📋",
    "rejection":          "❌",
    "other_job":          "📌",
}


def _email_rows(emails: list[dict]) -> str:
    if not emails:
        return "<p><em>No job-related emails found.</em></p>"
    rows = ""
    for e in emails:
        icon = CATEGORY_EMOJI.get(e.get("category", ""), "📧")
        rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee">{icon} {e.get('category','').replace('_',' ').title()}</td>
          <td style="padding:8px;border-bottom:1px solid #eee"><b>{e.get('subject','')}</b><br><small>{e.get('from','')}</small></td>
          <td style="padding:8px;border-bottom:1px solid #eee">{e.get('company') or '—'}</td>
          <td style="padding:8px;border-bottom:1px solid #eee">{e.get('role') or '—'}</td>
          <td style="padding:8px;border-bottom:1px solid #eee">{e.get('action_needed') or '—'}</td>
        </tr>"""
    return f"""
    <table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:14px">
      <thead>
        <tr style="background:#f0f4ff">
          <th style="padding:8px;text-align:left">Type</th>
          <th style="padding:8px;text-align:left">Email</th>
          <th style="padding:8px;text-align:left">Company</th>
          <th style="padding:8px;text-align:left">Role</th>
          <th style="padding:8px;text-align:left">Action</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>"""


def _job_rows(jobs: list[dict]) -> str:
    if not jobs:
        return "<p><em>No relevant job postings found.</em></p>"
    rows = ""
    for j in jobs:
        score = j.get("relevance_score", 0)
        score_color = "#22c55e" if score >= 80 else "#f59e0b" if score >= 65 else "#94a3b8"
        wt = j.get("work_type", "Unknown")
        wt_color = {"Remote": "#22c55e", "Hybrid": "#f59e0b", "Onsite": "#3b82f6"}.get(wt, "#94a3b8")
        url = j.get("source_url")
        title_cell = f'<a href="{url}" target="_blank">{j.get("title","")}</a>' if url else j.get("title", "")
        rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee">{title_cell}</td>
          <td style="padding:8px;border-bottom:1px solid #eee">{j.get('company','—')}</td>
          <td style="padding:8px;border-bottom:1px solid #eee">{j.get('location','—')}</td>
          <td style="padding:8px;border-bottom:1px solid #eee">
            <span style="color:{wt_color};font-weight:bold">{wt}</span>
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee">{j.get('source','')}</td>
          <td style="padding:8px;border-bottom:1px solid #eee">
            <span style="color:{score_color};font-weight:bold">{score}</span>/100
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;color:#555;font-size:13px">{j.get('summary','')}</td>
        </tr>"""
    return f"""
    <table style="width:100%;border-collapse:collapse;font-family:sans-serif;font-size:14px">
      <thead>
        <tr style="background:#f5f0ff">
          <th style="padding:8px;text-align:left">Title</th>
          <th style="padding:8px;text-align:left">Company</th>
          <th style="padding:8px;text-align:left">Location</th>
          <th style="padding:8px;text-align:left">Work Type</th>
          <th style="padding:8px;text-align:left">Source</th>
          <th style="padding:8px;text-align:left">Score</th>
          <th style="padding:8px;text-align:left">Summary</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>"""


def _usage_row(usage: dict) -> str:
    if not usage or not usage.get("total_tokens"):
        return ""
    return f"""
  <div style="margin-top:32px;padding:12px 16px;background:#f8fafc;border-radius:8px;
              font-family:monospace;font-size:13px;color:#475569;border:1px solid #e2e8f0">
    🤖 <b>Claude API usage</b> &nbsp;|&nbsp;
    Input: <b>{usage.get('input_tokens', 0):,}</b> tokens &nbsp;|&nbsp;
    Output: <b>{usage.get('output_tokens', 0):,}</b> tokens &nbsp;|&nbsp;
    Total: <b>{usage.get('total_tokens', 0):,}</b> tokens &nbsp;|&nbsp;
    API calls: <b>{usage.get('api_calls', 0)}</b>
  </div>"""


def build_html(emails: list[dict], jobs: list[dict], usage: dict | None = None) -> str:
    date_str = datetime.now().strftime("%B %d, %Y – %H:%M")
    return f"""<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;max-width:960px;margin:auto;padding:24px;color:#1e293b">
  <h1 style="border-bottom:3px solid #6366f1;padding-bottom:8px">
    Job Search Digest — {date_str}
  </h1>
  <h2 style="color:#2563eb">📧 Job-Related Emails ({len(emails)})</h2>
  {_email_rows(emails)}
  <h2 style="color:#7c3aed;margin-top:32px">🔍 Job Board Postings ({len(jobs)})</h2>
  {_job_rows(jobs)}
  {_usage_row(usage or {})}
  <p style="margin-top:16px;font-size:12px;color:#94a3b8">
    Generated by Job Search Agents &bull; Claude-powered
  </p>
</body>
</html>"""


def save(emails: list[dict], jobs: list[dict], usage: dict | None = None) -> Path:
    """Save digest as an HTML file and return its path."""
    Path("digests").mkdir(exist_ok=True)
    filename = Path("digests") / f"digest_{datetime.now().strftime('%Y%m%d_%H%M')}.html"
    filename.write_text(build_html(emails, jobs, usage), encoding="utf-8")
    return filename
