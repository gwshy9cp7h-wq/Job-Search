"""
Email agent debugger — shows every step so you can see exactly what
Playwright scraped and what Claude decided about each email.

Usage:
    ./.venv/bin/python3 debug_email.py              # show all scraped + classifications
    ./.venv/bin/python3 debug_email.py --raw        # only show raw scraped rows (no Claude)
    ./.venv/bin/python3 debug_email.py --search foo # filter raw rows containing "foo"
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
import anthropic

from config import ANTHROPIC_API_KEY, MODEL
from agents.email_agent import _scrape_emails, _classify_batch

console = Console()

args = sys.argv[1:]
raw_only  = "--raw"    in args
search_kw = ""
if "--search" in args:
    idx = args.index("--search")
    search_kw = args[idx + 1].lower() if idx + 1 < len(args) else ""


async def main():
    console.print(Panel("[bold cyan]Email Agent Debugger[/bold cyan]", expand=False))

    # ── Step 1: scrape ────────────────────────────────────────────────────
    console.print("\n[bold]Step 1 — Playwright scrape[/bold]")
    raw_emails = await _scrape_emails(console)

    if not raw_emails:
        console.print("[red]No emails scraped. Check the Playwright session.[/red]")
        return

    # Save all raw rows to a file for inspection
    raw_path = Path("debug_raw_emails.txt")
    with raw_path.open("w") as f:
        for i, e in enumerate(raw_emails, 1):
            f.write(f"=== Email {i} ===\n{e['raw']}\n\n")
    console.print(f"[green]✓ {len(raw_emails)} rows scraped.[/green] Full dump → [underline]{raw_path}[/underline]\n")

    # Print a preview table of all raw rows
    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold", title="All scraped email rows")
    t.add_column("#", width=4, justify="right")
    t.add_column("First line (subject/sender preview)", max_width=80)

    for i, e in enumerate(raw_emails, 1):
        first = e["raw"].split("\n")[0][:100]
        style = "bold yellow" if search_kw and search_kw in e["raw"].lower() else ""
        t.add_row(str(i), f"[{style}]{first}[/{style}]" if style else first)

    console.print(t)

    if search_kw:
        matches = [e for e in raw_emails if search_kw in e["raw"].lower()]
        console.print(f"\n[yellow]'{search_kw}' found in {len(matches)} raw row(s).[/yellow]")
        for m in matches:
            console.print(Panel(m["raw"][:600], title="Matching raw row", border_style="yellow"))

    if raw_only:
        return

    # ── Step 2: Claude classification (verbose) ───────────────────────────
    console.print("\n[bold]Step 2 — Claude classification (all emails, no filtering)[/bold]")
    console.print("[dim]Running with confidence threshold lowered to 0 — shows everything Claude sees.[/dim]\n")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    all_results = []

    for batch_start in range(0, len(raw_emails), 30):
        batch = raw_emails[batch_start:batch_start + 30]
        batch_num = batch_start // 30 + 1
        console.print(f"[dim]Batch {batch_num} ({len(batch)} emails)...[/dim]")

        # Call Claude with threshold=0 to see ALL decisions
        numbered = "\n\n".join(f"[Email {i+1}]\n{e['raw']}" for i, e in enumerate(batch))
        prompt = f"""You are a job search assistant. Analyse each email row below.

For EVERY email (including non-job ones) output a JSON object:
{{
  "email_number": <number>,
  "is_job_related": true or false,
  "confidence": 0-100,
  "category": "offer"|"recruiter"|"interview"|"application_update"|"rejection"|"other_job"|"not_job_related",
  "company": "name or null",
  "role": "title or null",
  "reason": "one sentence explaining your decision"
}}

Raw email rows:
---
{numbered}
---

Respond ONLY with a valid JSON array. No markdown."""

        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        try:
            start, end = text.index("["), text.rindex("]") + 1
            decisions = json.loads(text[start:end])
        except Exception as e:
            console.print(f"[red]Parse error in batch {batch_num}: {e}[/red]")
            decisions = []

        for d in decisions:
            idx = d.get("email_number", 1) - 1
            raw = batch[idx]["raw"] if 0 <= idx < len(batch) else ""
            d["first_line"] = raw.split("\n")[0][:90]
            d["batch"] = batch_num
        all_results.extend(decisions)

    # ── Step 3: Results table ─────────────────────────────────────────────
    console.print()
    t2 = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold",
               title="Claude's decision on every email")
    t2.add_column("#",          width=4, justify="right")
    t2.add_column("Job?",       width=5)
    t2.add_column("Conf",       width=5, justify="right")
    t2.add_column("Category",   width=20)
    t2.add_column("Subject preview", max_width=45)
    t2.add_column("Reason",     max_width=40)

    for d in all_results:
        is_job = d.get("is_job_related", False)
        conf   = d.get("confidence", 0)
        cat    = d.get("category", "")
        flagged = is_job and conf >= 60

        job_cell  = "[green]✓[/green]" if flagged else ("[yellow]~[/yellow]" if is_job else "[dim]✗[/dim]")
        conf_style = "bold green" if conf >= 80 else "yellow" if conf >= 60 else "dim"

        t2.add_row(
            str(d.get("email_number", "?")),
            job_cell,
            f"[{conf_style}]{conf}[/{conf_style}]",
            cat.replace("_", " ").title(),
            d.get("first_line", ""),
            d.get("reason", ""),
        )

    console.print(t2)

    flagged_count = sum(1 for d in all_results if d.get("is_job_related") and d.get("confidence", 0) >= 60)
    missed_count  = sum(1 for d in all_results if d.get("is_job_related") and d.get("confidence", 0) < 60)
    console.print(
        f"\n[green]✓ flagged (conf ≥ 60): {flagged_count}[/green]  "
        f"[yellow]~ job-related but below threshold (conf < 60): {missed_count}[/yellow]  "
        f"[dim]✗ not job-related: {len(all_results) - flagged_count - missed_count}[/dim]"
    )
    console.print(
        "\n[dim]Legend: ✓ = picked up by agent  ~ = job-related but filtered out  ✗ = not job-related[/dim]"
    )
    console.print(f"[dim]Full raw dump saved to: {raw_path}[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
