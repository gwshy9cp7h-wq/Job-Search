"""
Job Search Agents — orchestrator
Runs both agents and prints results to the console, then sends an email digest.

Usage:
    python main.py               # run both agents
    python main.py --email-only  # only the email agent
    python main.py --jobs-only   # only the job board agent
"""
from __future__ import annotations

import subprocess
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

import config  # validates env vars on import
from agents import email_agent, job_board_agent
import digest

console = Console()

CATEGORY_STYLE = {
    "offer":              "bold green",
    "recruiter":          "cyan",
    "interview":          "bold yellow",
    "application_update": "blue",
    "rejection":          "red",
    "other_job":          "magenta",
}


def print_email_results(emails: list[dict]):
    console.print(Panel(f"[bold cyan]Job-Related Emails[/bold cyan] — {len(emails)} found", expand=False))

    if not emails:
        console.print("[dim]  No job-related emails found.[/dim]\n")
        return

    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    t.add_column("Category", style="bold", no_wrap=True)
    t.add_column("Subject", max_width=40)
    t.add_column("From", max_width=30)
    t.add_column("Company")
    t.add_column("Role")
    t.add_column("Action Needed", max_width=35)

    for e in emails:
        cat = e.get("category", "")
        style = CATEGORY_STYLE.get(cat, "white")
        t.add_row(
            f"[{style}]{cat.replace('_', ' ').title()}[/{style}]",
            e.get("subject", ""),
            e.get("from", ""),
            e.get("company") or "—",
            e.get("role") or "—",
            e.get("action_needed") or "—",
        )

    console.print(t)
    console.print()


def print_job_results(jobs: list[dict]):
    console.print(Panel(f"[bold magenta]Job Board Postings[/bold magenta] — {len(jobs)} found", expand=False))

    if not jobs:
        console.print("[dim]  No relevant job postings found.[/dim]\n")
        return

    WORK_TYPE_STYLE = {"Remote": "bold green", "Hybrid": "yellow", "Onsite": "cyan", "Unknown": "dim"}

    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
    t.add_column("Score", justify="right", no_wrap=True)
    t.add_column("Title", max_width=35)
    t.add_column("Company", max_width=25)
    t.add_column("Location", max_width=20)
    t.add_column("Work Type", no_wrap=True)
    t.add_column("Source", no_wrap=True)
    t.add_column("Summary", max_width=45)

    for j in jobs:
        score = j.get("relevance_score", 0)
        score_style = "bold green" if score >= 80 else "yellow" if score >= 65 else "dim"
        wt = j.get("work_type", "Unknown")
        wt_style = WORK_TYPE_STYLE.get(wt, "dim")
        t.add_row(
            f"[{score_style}]{score}[/{score_style}]",
            j.get("title", ""),
            j.get("company", "—"),
            j.get("location", "—"),
            f"[{wt_style}]{wt}[/{wt_style}]",
            j.get("source", ""),
            j.get("summary", ""),
        )

    console.print(t)
    console.print()


def main():
    args = sys.argv[1:]
    run_email = "--jobs-only" not in args
    run_jobs = "--email-only" not in args

    console.print(Panel(
        "[bold]Job Search Agents[/bold]\n"
        f"[dim]Keywords: {', '.join(config.JOB_KEYWORDS)}[/dim]\n"
        f"[dim]Locations: {', '.join(config.JOB_LOCATIONS)}[/dim]",
        style="bold blue",
        expand=False,
    ))
    console.print()

    emails: list[dict] = []
    jobs: list[dict] = []
    combined_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "api_calls": 0}

    if run_email:
        try:
            emails, email_usage = email_agent.run(console)
            for k in combined_usage:
                combined_usage[k] += email_usage.get(k, 0)
        except Exception as exc:
            console.print(f"[red]Email agent error:[/red] {exc}\n")

    if run_jobs:
        try:
            jobs, job_usage = job_board_agent.run(console)
            for k in combined_usage:
                combined_usage[k] += job_usage.get(k, 0)
        except Exception as exc:
            console.print(f"[red]Job board agent error:[/red] {exc}\n")

    print_email_results(emails)
    print_job_results(jobs)

    # Token usage summary
    console.print(
        f"[dim]Token usage — "
        f"input: {combined_usage['input_tokens']:,}  "
        f"output: {combined_usage['output_tokens']:,}  "
        f"total: {combined_usage['total_tokens']:,}  "
        f"API calls: {combined_usage['api_calls']}[/dim]\n"
    )

    try:
        path = digest.save(emails, jobs, combined_usage)
        console.print(f"[green]✓ Digest saved:[/green] [underline]{path}[/underline]")
        # Open in Chrome (fall back to default browser if Chrome not found)
        if sys.platform == "darwin":
            try:
                subprocess.run(["open", "-a", "Google Chrome", str(path)], check=True)
            except Exception:
                subprocess.run(["open", str(path)])
    except Exception as exc:
        console.print(f"[red]Digest save failed:[/red] {exc}")


if __name__ == "__main__":
    main()
