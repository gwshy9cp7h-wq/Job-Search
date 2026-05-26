"""
Job Board Agent — searches LinkedIn, Indeed, and Glassdoor using a saved
browser session (logged in = more results). Claude extracts all relevant
job listings and flags each one as Remote / Hybrid / Onsite.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import quote_plus

from playwright.async_api import async_playwright, BrowserContext, Page, Playwright

import llm as llm_module
from config import JOB_KEYWORDS, JOB_LOCATIONS, JOB_DAYS_BACK

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

SESSION_DIR = Path(".job_boards_session")

_LINKEDIN_TPR = {1: "r86400", 7: "r604800", 14: "r1209600", 30: "r2592000"}


# ---------------------------------------------------------------------------
# Session / login helpers
# ---------------------------------------------------------------------------

BOARD_LOGINS = {
    "LinkedIn":  {
        "check_url":  "https://www.linkedin.com/feed/",
        "login_url":  "https://www.linkedin.com/login",
        "logged_in":  lambda url: "feed" in url and "login" not in url,
        "ready_sel":  ".global-nav__primary-link, .feed-identity-module",
        "emoji":      "🔗",
    },
    "Glassdoor": {
        "check_url":  "https://www.glassdoor.com/member/home/index.htm",
        "login_url":  "https://www.glassdoor.com/profile/login_input.htm",
        "logged_in":  lambda url: "glassdoor.com" in url and "login" not in url,
        "ready_sel":  '[data-test="header-main-nav"], .DesktopNavBar',
        "emoji":      "🚪",
    },
    "Indeed":    {
        "check_url":  "https://www.indeed.com/",
        "login_url":  "https://secure.indeed.com/auth",
        "logged_in":  lambda url: "indeed.com" in url and "auth" not in url and "login" not in url,
        "ready_sel":  '#indeed-ia, [data-gnav-ph-id]',
        "emoji":      "🔍",
    },
}


async def _board_logged_in(context: BrowserContext, board: str) -> bool:
    cfg = BOARD_LOGINS[board]
    page = await context.new_page()
    try:
        await page.goto(cfg["check_url"], wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)
        return cfg["logged_in"](page.url)
    except Exception:
        return False
    finally:
        await page.close()


async def _interactive_login_board(p: Playwright, board: str, console=None) -> None:
    cfg = BOARD_LOGINS[board]
    SESSION_DIR.mkdir(exist_ok=True)
    if console:
        console.print(
            f"\n[bold yellow]{cfg['emoji']} {board} login required[/bold yellow]\n"
            f"[dim]A browser window will open. Log in to {board} "
            f"(you can use your Google account).\n"
            f"Once you're on the home page, wait — the script will continue.[/dim]\n"
        )
    browser = await p.chromium.launch_persistent_context(
        str(SESSION_DIR), headless=False, viewport={"width": 1280, "height": 800}
    )
    page = await browser.new_page()
    await page.goto(cfg["login_url"])
    try:
        await page.wait_for_selector(cfg["ready_sel"], timeout=180000)
        if console:
            console.print(f"[green]  ✓ {board} login detected — saving session.[/green]")
    except Exception:
        if console:
            console.print(f"[yellow]  Timed out waiting for {board} — saving session anyway.[/yellow]")
    await browser.close()


# ---------------------------------------------------------------------------
# Scrapers
# ---------------------------------------------------------------------------

async def _scrape_linkedin(page: Page, keywords: str, location: str, days: int) -> list[str]:
    tpr = _LINKEDIN_TPR.get(days, "r604800")
    url = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={quote_plus(keywords)}&location={quote_plus(location)}"
        f"&f_TPR={tpr}&position=1&pageNum=0"
    )
    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(2500)

    # Logged-in results use a different container than public
    cards = await page.query_selector_all(".job-card-container, .base-card")
    texts = [(await c.inner_text()).strip() for c in cards[:30] if await c.inner_text()]
    return texts


async def _scrape_indeed(page: Page, keywords: str, location: str, days: int) -> list[str]:
    url = (
        f"https://www.indeed.com/jobs"
        f"?q={quote_plus(keywords)}&l={quote_plus(location)}&fromage={days}&sort=date"
    )
    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(2500)

    cards = await page.query_selector_all("[data-jk]")
    if not cards:
        cards = await page.query_selector_all(".job_seen_beacon")
    texts = [(await c.inner_text()).strip() for c in cards[:30] if await c.inner_text()]
    return texts


async def _scrape_glassdoor(page: Page, keywords: str, location: str, days: int) -> list[str]:
    url = (
        f"https://www.glassdoor.com/Job/jobs.htm"
        f"?sc.keyword={quote_plus(keywords)}&locT=N&fromAge={days}"
        f"&locKeyword={quote_plus(location)}"
    )
    await page.goto(url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(3000)

    cards = await page.query_selector_all("[data-test='jobListing'], .react-job-listing")
    texts = [(await c.inner_text()).strip() for c in cards[:30] if await c.inner_text()]
    return texts


# ---------------------------------------------------------------------------
# Claude parsing
# ---------------------------------------------------------------------------

def _parse_with_claude(
    client,
    raw_cards: list[str],
    source: str,
    keywords: str,
    location: str,
) -> tuple[list[dict], dict]:
    """Returns (jobs, usage)."""
    empty_usage = {"input_tokens": 0, "output_tokens": 0, "api_calls": 0}
    if not raw_cards:
        return [], empty_usage

    numbered = "\n\n".join(f"[Card {i + 1}]\n{t}" for i, t in enumerate(raw_cards))

    prompt = f"""You are a job search assistant. Below is raw text scraped from {source} for:
Role: "{keywords}" | Location searched: "{location}"

The candidate is based in Lisbon, Portugal and open to:
- Fully remote (anywhere in the world)
- On-site or hybrid in Lisbon / Portugal
- Relocation within Europe, Africa, or the Middle East for the project duration

Extract EVERY job listing visible. For each one provide:
- title: job title
- company: company name
- location: location as shown in the listing
- work_type: "Remote" | "Hybrid" | "Onsite" | "Unknown"
- relevance_score: 0-100 (how well the role matches "{keywords}")
- summary: 1-2 sentence description
- source_url: URL if visible in the text, else null

Include all jobs with relevance_score >= 50. Do NOT filter by work_type — include all.

Raw cards:
---
{numbered}
---

Respond ONLY with a valid JSON array (no markdown):
[{{"title":...,"company":...,"location":...,"work_type":...,"relevance_score":...,"summary":...,"source_url":...}}]

If no jobs found, return: []"""

    text, usage = llm_module.complete(client, prompt, max_tokens=3000)
    text = text.strip()
    try:
        start = text.index("[")
        end = text.rindex("]") + 1
        return json.loads(text[start:end]), usage
    except (ValueError, json.JSONDecodeError):
        return [], usage


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def _run_async(console=None) -> tuple[list[dict], dict]:
    client = llm_module.get_client()
    all_jobs: list[dict] = []
    total_usage = {"input_tokens": 0, "output_tokens": 0, "api_calls": 0}
    SESSION_DIR.mkdir(exist_ok=True)

    async with async_playwright() as p:

        # ── Check / establish login for each board ───────────────────────
        for board in list(BOARD_LOGINS.keys()):
            context = await p.chromium.launch_persistent_context(
                str(SESSION_DIR), headless=True, user_agent=USER_AGENT
            )
            logged_in = await _board_logged_in(context, board)
            await context.close()

            if not logged_in:
                await _interactive_login_board(p, board, console)
                context = await p.chromium.launch_persistent_context(
                    str(SESSION_DIR), headless=True, user_agent=USER_AGENT
                )
                logged_in = await _board_logged_in(context, board)
                await context.close()

            status = "✓ logged in" if logged_in else "not logged in — results may be limited"
            style  = "dim" if logged_in else "yellow"
            if console:
                console.print(f"[{style}]  {board}: {status}[/{style}]")

        # ── Scrape ───────────────────────────────────────────────────────
        scrapers = {
            "LinkedIn":  _scrape_linkedin,
            "Indeed":    _scrape_indeed,
            "Glassdoor": _scrape_glassdoor,
        }

        context = await p.chromium.launch_persistent_context(
            str(SESSION_DIR), headless=True, user_agent=USER_AGENT
        )
        page = await context.new_page()

        for keywords in JOB_KEYWORDS:
            for location in JOB_LOCATIONS:
                for source_name, scraper_fn in scrapers.items():
                    if console:
                        console.print(
                            f"[cyan]  {source_name}: \"{keywords}\" in {location}...[/cyan]"
                        )
                    try:
                        raw = await scraper_fn(page, keywords, location, JOB_DAYS_BACK)
                        jobs, usage = _parse_with_claude(client, raw, source_name, keywords, location)
                        for job in jobs:
                            job["source"] = source_name
                        all_jobs.extend(jobs)
                        for k in total_usage:
                            total_usage[k] += usage[k]
                    except Exception as exc:
                        if console:
                            console.print(f"[yellow]  ⚠ {source_name} / {keywords} / {location}: {exc}[/yellow]")

        await context.close()

    # Deduplicate by (title, company)
    seen: set[tuple] = set()
    unique: list[dict] = []
    for job in all_jobs:
        key = (job.get("title", "").lower().strip(), job.get("company", "").lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(job)

    total_usage["total_tokens"] = total_usage["input_tokens"] + total_usage["output_tokens"]
    return sorted(unique, key=lambda j: j.get("relevance_score", 0), reverse=True), total_usage


def run(console=None) -> tuple[list[dict], dict]:
    if console:
        console.print("[bold magenta]Job Board Agent[/bold magenta] — LinkedIn, Indeed, Glassdoor...")

    results, usage = asyncio.run(_run_async(console))

    if console:
        console.print(f"[magenta]  Done — {len(results)} unique postings found.[/magenta]\n")

    return results, usage
