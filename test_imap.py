"""Quick IMAP connection test — tries multiple servers to find what works."""
import imaplib
from dotenv import load_dotenv
import os

load_dotenv()

EMAIL    = os.getenv("EMAIL_ADDRESS", "")
PASSWORD = os.getenv("EMAIL_PASSWORD", "")
PORT     = 993

SERVERS = [
    "imap-mail.outlook.com",       # personal Outlook.com / Hotmail
    "outlook.office365.com",       # Microsoft 365 / work accounts
]

print(f"Testing IMAP for: {EMAIL}\n")

success = False
for server in SERVERS:
    print(f"Trying {server}:{PORT} ...", end=" ")
    try:
        mail = imaplib.IMAP4_SSL(server, PORT)
    except Exception as e:
        print(f"✗ Could not connect: {e}")
        continue

    try:
        mail.login(EMAIL, PASSWORD)
        mail.select("INBOX")
        _, data = mail.search(None, "ALL")
        count = len(data[0].split()) if data[0] else 0
        print(f"✓ Login OK — {count} messages in inbox")
        mail.logout()
        print(f"\n✅ Working server: {server}")
        print(f"   Update IMAP_SERVER in config.py to: \"{server}\"")
        success = True
        break
    except imaplib.IMAP4.error as e:
        print(f"✗ Login failed: {e}")

if not success:
    print("\n❌ Login failed on all servers.")
    print("Most likely cause: Basic Auth is blocked by Microsoft.")
    print("Next step: switch to OAuth2 (no Azure registration needed).")
    print("Run: .venv/bin/python3 test_oauth.py   ← we'll create this next")
