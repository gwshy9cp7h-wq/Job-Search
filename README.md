# Job Search Agents

Two Claude-powered agents that help you track job opportunities:

1. **Email Agent** — scans your Outlook inbox and flags job-related emails (offers, recruiter outreach, interviews, application updates)
2. **Job Board Agent** — searches LinkedIn, Indeed, and Glassdoor for relevant postings and scores their relevance

Results are printed to your terminal and optionally sent as an HTML email digest.

---

## Setup

### 1. Install dependencies

```bash
cd job-search-agents
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values (see below for each credential).

### 3. Anthropic API key

Get your key from [console.anthropic.com](https://console.anthropic.com) and set `ANTHROPIC_API_KEY`.

### 4. Azure App Registration (for Outlook)

You need to create a free Azure app to read your emails. It takes ~5 minutes:

1. Go to [portal.azure.com](https://portal.azure.com) (sign in with the same Microsoft account as your email)
2. Search for **"App registrations"** → **New registration**
3. Name it anything (e.g. `job-search-agent`)
4. Under **Supported account types**, select:
   - `Accounts in any organizational directory and personal Microsoft accounts` (if using Outlook.com/Hotmail)
   - Or `Accounts in this organizational directory only` (if using a work/school account)
5. Click **Register**
6. Copy the **Application (client) ID** → set as `AZURE_CLIENT_ID`
7. Copy the **Directory (tenant) ID** → set as `AZURE_TENANT_ID`
   - If using a personal account (Outlook.com/Hotmail), set `AZURE_TENANT_ID=consumers`
8. In the left sidebar: **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions**
9. Add: `Mail.Read` and `Mail.Send`
10. Click **Grant admin consent** (if available; for personal accounts it's granted automatically on first login)
11. In the left sidebar: **Authentication** → **Add a platform** → **Mobile and desktop applications**
12. Check `https://login.microsoftonline.com/common/oauth2/nativeclient`
13. Enable **Allow public client flows** → Save

The first time you run the agents, a device code login link will be printed in the terminal. Open it in your browser and sign in — the token is then cached for future runs.

### 5. Configure your preferences

In `.env`:

```env
JOB_KEYWORDS=software engineer,python developer,backend engineer
JOB_LOCATION=Remote         # or "London, UK", "New York, NY", etc.
JOB_DAYS_BACK=7             # look back N days on job boards
EMAIL_DAYS_BACK=3           # scan N days of emails
DIGEST_TO_EMAIL=your@email.com   # leave blank to skip digest
```

---

## Usage

```bash
# Run both agents
python main.py

# Email agent only
python main.py --email-only

# Job boards only
python main.py --jobs-only
```

### Scheduling (optional)

Run daily with cron (macOS/Linux):

```bash
crontab -e
# Add this line to run every morning at 8am:
0 8 * * * cd /path/to/job-search-agents && python main.py >> logs/daily.log 2>&1
```

---

## How it works

```
main.py
├── agents/email_agent.py
│   ├── Authenticate with Microsoft Graph (MSAL device code, cached)
│   ├── Fetch emails from last N days
│   └── Claude classifies each email → extracts company, role, action needed
│
├── agents/job_board_agent.py
│   ├── Playwright launches headless Chromium
│   ├── Searches LinkedIn, Indeed, Glassdoor for each keyword
│   └── Claude extracts and scores job listings from raw page text
│
└── digest.py
    └── Sends HTML email via Microsoft Graph API
```

---

## Notes

- Job board scraping is for **personal use only**. LinkedIn, Indeed, and Glassdoor prohibit automated scraping in their ToS — use responsibly.
- The MSAL token cache is stored in `.msal_token_cache.json` — keep it out of version control (it's gitignored).
- Claude model used: `claude-opus-4-7` — change `MODEL` in `config.py` if you want a cheaper/faster option (`claude-sonnet-4-6`).
