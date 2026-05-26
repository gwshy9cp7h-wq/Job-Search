"""
Shows the raw LLM response for the latest email log, before any JSON parsing.
Run: .venv/bin/python3 debug_llm.py
"""
from __future__ import annotations
from dotenv import load_dotenv
load_dotenv(override=True)

from pathlib import Path
import llm as llm_module
from config import MODEL, LLM_PROVIDER, LLM_BASE_URL

# Load the latest raw email log
logs = sorted(Path("logs").glob("raw_emails_*.txt"), reverse=True)
if not logs:
    print("No log files found. Run main.py --email-only first.")
    exit(1)

log_path = logs[0]
print(f"Using: {log_path}\n")
raw_text = log_path.read_text(encoding="utf-8")

# Parse individual emails from the log
emails = []
blocks = raw_text.split("--- Email ")
for block in blocks[1:]:
    lines = block.strip().split("\n", 1)
    content = lines[1].strip() if len(lines) > 1 else ""
    if content:
        emails.append({"raw": content})

print(f"Provider : {LLM_PROVIDER}")
print(f"Model    : {MODEL}")
print(f"Base URL : {LLM_BASE_URL}")
print(f"Emails   : {len(emails)}")
print("-" * 60)

numbered = "\n\n".join(f"[Email {i+1}]\n{e['raw']}" for i, e in enumerate(emails))

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

print("Sending to LLM...\n")
client = llm_module.get_client()
text, usage = llm_module.complete(client, prompt, max_tokens=3000)

print("=== RAW LLM RESPONSE ===")
print(text)
print("========================")
print(f"\nTokens — input: {usage['input_tokens']}  output: {usage['output_tokens']}")
