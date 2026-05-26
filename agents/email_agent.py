"""
Email Agent — reads Outlook inbox via Playwright (Outlook web).

First run: opens a real browser window so you can log in manually.
The session is saved to .outlook_session/ and reused headlessly on future runs.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, BrowserContext, Playwright

import llm as llm_module
from config import MODEL

SESSION_DIR = Path(".outlook_session")
OUTLOOK_INBOX = "https://outlook.live.com/mail/0/"


# ---------------------------------------------------------------------------
# Login detection
# ---------------------------------------------------------------------------

async def _is_logged_in(context: BrowserContext, console=None) -> bool:
    """Returns True only if we can see Outlook inbox email items."""
    page = await context.new_page()
    try:
        await page.goto(OUTLOOK_INBOX, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        url = page.url
        if console:
            console.print(f"[dim]  → {url[:70]}[/dim]")

        # Must be on outlook.live.com to be logged in
        if "outlook.live.com" not in url:
            return False

        # Look for Outlook-specific email list elements
        inbox = (
            await page.query_selector('[aria-label="Message list"]') or
            await page.query_selector('[data-convid]') or
            await page.query_selector('[role="option"][data-is-focusable]')
        )
        return bool(inbox)
    except Exception as exc:
        if console:
            console.print(f"[dim]  Login check error: {exc}[/dim]")
        return False
    finally:
        await page.close()


# ---------------------------------------------------------------------------
# Interactive login (headed browser, user logs in manually)
# ---------------------------------------------------------------------------

async def _interactive_login(p: Playwright, console=None) -> None:
    SESSION_DIR.mkdir(exist_ok=True)
    if console:
        console.print(
            "\n[bold yellow]📧 Outlook login required[/bold yellow]\n"
            "[dim]A browser window will open. Log in to your Microsoft account.\n"
            "Once your inbox is visible, wait — the script will continue automatically.[/dim]\n"
        )

    browser = await p.chromium.launch_persistent_context(
        str(SESSION_DIR),
        headless=False,
        viewport={"width": 1280, "height": 800},
    )
    page = await browser.new_page()
    await page.goto(OUTLOOK_INBOX)

    if console:
        console.print("[dim]  Waiting for inbox (up to 3 minutes)...[/dim]")

    try:
        # Wait until we see email items — means login is complete
        await page.wait_for_selector(
            '[data-convid], [aria-label="Message list"]',
            timeout=180000,
        )
        if console:
            console.print("[green]  ✓ Login detected — saving session.[/green]")
    except Exception:
        if console:
            console.print("[yellow]  Timed out waiting for inbox — saving session anyway.[/yellow]")

    await browser.close()


# ---------------------------------------------------------------------------
# Email scraping
# ---------------------------------------------------------------------------

async def _scrape_emails(console=None) -> list[dict]:
    SESSION_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:

        # ── Step 1: try headless with any saved session ──────────────────
        if console:
            console.print("[dim]  Checking for saved Outlook session...[/dim]")

        context = await p.chromium.launch_persistent_context(
            str(SESSION_DIR), headless=True
        )
        logged_in = await _is_logged_in(context, console)
        await context.close()

        # ── Step 2: interactive login if needed ──────────────────────────
        if not logged_in:
            await _interactive_login(p, console)

            context = await p.chromium.launch_persistent_context(
                str(SESSION_DIR), headless=True
            )
            logged_in = await _is_logged_in(context, console)
            await context.close()

            if not logged_in:
                if console:
                    console.print("[red]  Could not verify inbox access after login.[/red]")
                return []

        # ── Step 3: scrape inbox ─────────────────────────────────────────
        if console:
            console.print("[dim]  Session OK — loading inbox...[/dim]")

        context = await p.chromium.launch_persistent_context(
            str(SESSION_DIR), headless=True
        )
        page = await context.new_page()
        await page.goto(OUTLOOK_INBOX, wait_until="domcontentloaded", timeout=30000)

        try:
            await page.wait_for_selector(
                '[data-convid], [aria-label="Message list"]',
                timeout=15000,
            )
        except Exception:
            pass

        await page.wait_for_timeout(2000)

        emails = []
        emails += await _collect_tab_emails(page, "Focused", console)
        emails += await _collect_tab_emails(page, "Other",   console)

        await context.close()
        return emails


async def _collect_tab_emails(page, tab_name: str, console=None) -> list[dict]:
    """Switch to a named Outlook tab (Focused / Other) and scrape all visible emails."""

    # Try to click the tab if it exists
    tab = await page.query_selector(f'[data-automation-id="Tab-{tab_name}"], button:has-text("{tab_name}")')
    if tab:
        await tab.click()
        await page.wait_for_timeout(1500)
    elif tab_name == "Other":
        # "Other" tab may not exist if Focused Inbox is off — that's fine
        return []

    collected: list[dict] = []
    seen_texts: set[str] = set()

    # Scroll the message list in steps to trigger lazy-loading
    for scroll_round in range(8):
        items = await page.query_selector_all("[data-convid]")

        if not items:
            container = await page.query_selector('[aria-label="Message list"]')
            if container:
                items = await container.query_selector_all('[role="option"]')

        for item in items:
            try:
                text = (await item.inner_text()).strip()
                if text and text not in seen_texts:
                    seen_texts.add(text)
                    collected.append({"raw": text, "tab": tab_name})
            except Exception:
                pass

        # Scroll the message list container to load more
        scrolled = await page.evaluate("""() => {
            const list = document.querySelector('[aria-label="Message list"]')
                       || document.querySelector('[role="list"]');
            if (list) { list.scrollBy(0, 800); return true; }
            return false;
        }""")
        if not scrolled:
            break
        await page.wait_for_timeout(600)

    if console:
        console.print(f"[dim]  [{tab_name}] {len(collected)} emails collected.[/dim]")

    return collected


# ---------------------------------------------------------------------------
# Claude classification
# ---------------------------------------------------------------------------

def _classify_batch(client, raw_items: list[dict]) -> tuple[list[dict], dict]:
    """Returns (results, usage) where usage = {input_tokens, output_tokens, api_calls}."""
    empty_usage = {"input_tokens": 0, "output_tokens": 0, "api_calls": 0}
    if not raw_items:
        return [], empty_usage

    numbered = "\n\n".join(
        f"[Email {i + 1}]\n{e['raw']}" for i, e in enumerate(raw_items)
    )

    prompt = f"""You are a job search assistant. Below is raw text scraped from an Outlook inbox
(each block is one email row as it appears in the message list).

IMPORTANT: The candidate is based in Portugal. Emails may be written in Portuguese, English,
or other languages. Treat Portuguese words like "oportunidades" (opportunities), "emprego" (job),
"vaga" (vacancy), "candidatura" (application), "entrevista" (interview), "recrutamento" (recruiting)
as strong job-related signals — classify them the same way you would their English equivalents.

Identify which emails relate to employment opportunities:
job offers, recruiter outreach, interview invitations, application updates, rejections,
or any career opportunity — in ANY language.

For each job-related email (confidence >= 45) output a JSON object:
{{
  "email_number": <number from the block header>,
  "category": "offer" | "recruiter" | "interview" | "application_update" | "rejection" | "other_job",
  "company": "company name or null",
  "role": "job title or null",
  "summary": "1-2 sentence summary in English",
  "action_needed": "what to do next or null",
  "confidence": 0-100
}}

Raw email rows:
---
{numbered}
---

Respond ONLY with a valid JSON array of job-related emails. If none found, return [].
No markdown, no explanation."""

    text, usage = llm_module.complete(client, prompt, max_tokens=3000)
    text = text.strip()
    try:
        start = text.index("[")
        end = text.rindex("]") + 1
        hits = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return [], usage

    results = []
    for hit in hits:
        if hit.get("confidence", 0) < 45:
            continue
        idx = hit.get("email_number", 1) - 1
        raw = raw_items[idx]["raw"] if 0 <= idx < len(raw_items) else ""
        first_line = raw.split("\n")[0][:120] if raw else ""
        results.append({
            "subject":       first_line,
            "from":          "",
            "category":      hit.get("category"),
            "company":       hit.get("company"),
            "role":          hit.get("role"),
            "summary":       hit.get("summary"),
            "action_needed": hit.get("action_needed"),
            "confidence":    hit.get("confidence"),
        })
    return results, usage


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _save_raw_log(raw_emails: list[dict]) -> Path:
    """Dump every scraped email row to a timestamped log file before LLM processing."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"raw_emails_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    with log_path.open("w", encoding="utf-8") as f:
        f.write(f"Raw email scrape — {datetime.now().isoformat()}\n")
        f.write(f"Total rows: {len(raw_emails)}\n")
        f.write("=" * 60 + "\n\n")
        for i, e in enumerate(raw_emails, 1):
            tab = e.get("tab", "?")
            f.write(f"--- Email {i} [{tab}] ---\n")
            f.write(e["raw"])
            f.write("\n\n")

    return log_path


def run(console=None) -> list[dict]:
    if console:
        console.print("[bold cyan]Email Agent[/bold cyan] — opening Outlook web...")

    raw_emails = asyncio.run(_scrape_emails(console))

    # Always log raw scrape results before LLM — useful for debugging
    if raw_emails:
        log_path = _save_raw_log(raw_emails)
        if console:
            console.print(f"[dim]  Raw scrape logged → {log_path}[/dim]")

    if not raw_emails:
        if console:
            console.print("[yellow]  No emails retrieved. Check logs/ for details.[/yellow]\n")
        # Still write an empty log so we know the agent ran
        log_path = _save_raw_log([])
        if console:
            console.print(f"[dim]  Empty scrape logged → {log_path}[/dim]")
        return [], {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "api_calls": 0}

    if console:
        console.print(f"[cyan]  {len(raw_emails)} emails found. Classifying with LLM...[/cyan]")

    client = llm_module.get_client()
    results = []
    total_usage = {"input_tokens": 0, "output_tokens": 0, "api_calls": 0}

    for i in range(0, len(raw_emails), 30):
        batch_results, batch_usage = _classify_batch(client, raw_emails[i:i + 30])
        results.extend(batch_results)
        for k in total_usage:
            total_usage[k] += batch_usage[k]

    total_usage["total_tokens"] = total_usage["input_tokens"] + total_usage["output_tokens"]

    if console:
        console.print(f"[cyan]  Done — {len(results)} job-related emails found.[/cyan]\n")

    return results, total_usage
