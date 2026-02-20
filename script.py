"""
send_emails.py — Send personalized cold emails via Gmail.

Usage:
    python send_emails.py --csv recipients.csv --template template.txt [--delay 1.5]

Setup:
    See README.md for Gmail OAuth2 credentials setup instructions.
"""

import argparse
import base64
import csv
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
import html
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from string import Template

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
SENT_CSV = "sent.csv"
LOG_FILE = "send_emails.log"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class EmailTemplate:
    subject: Template
    body: Template


@dataclass
class SendResult:
    email: str
    sent_at: str
    success: bool
    error: str = ""

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_gmail_service():
    """Authenticate via OAuth2 and return a Gmail API service."""
    creds = None

    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(TOKEN_FILE).write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)

# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

def load_template(path: str) -> EmailTemplate:
    """
    Parse an email template file.

    Expected format:
        Subject: Your subject with $variables
        Body line one...
        Body line two...
    """
    lines = Path(path).read_text(encoding="utf-8").splitlines()

    if not lines or not lines[0].lower().startswith("subject:"):
        sys.exit("Error: Template must begin with 'Subject: ...'")

    subject = Template(lines[0].split(":", 1)[1].strip())
    body = Template("\n".join(lines[1:]).strip())

    return EmailTemplate(subject=subject, body=body)

# ---------------------------------------------------------------------------
# Recipients
# ---------------------------------------------------------------------------

def load_recipients(path: str) -> list[dict]:
    """Load recipients from a CSV file. Requires an 'email' column."""
    with open(path, newline="", encoding="utf-8") as f:
        recipients = list(csv.DictReader(f))

    if not recipients:
        sys.exit(f"Error: '{path}' is empty.")

    if "email" not in recipients[0]:
        sys.exit("Error: CSV must contain an 'email' column.")

    return recipients

# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

def plain_to_html(text: str) -> str:
    """Convert plain text to HTML, auto-linking URLs and preserving line breaks."""
    escaped = html.escape(text)
    linked = re.sub(
        r"(https?://[^\s]+)",
        r'<a href="\1">\1</a>',
        escaped,
    )
    return "<br>\n".join(linked.splitlines())


def build_mime_message(to: str, subject: str, body: str) -> dict:
    """Build a multipart plain+HTML email and encode it for the Gmail API."""
    msg = MIMEMultipart("alternative")
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(plain_to_html(body), "html", "utf-8"))
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


def send_email(service, recipient: dict, template: EmailTemplate) -> SendResult:
    """Send a single email and return the result."""
    to = recipient["email"].strip()
    sent_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        message = build_mime_message(
            to=to,
            subject=template.subject.safe_substitute(recipient),
            body=template.body.safe_substitute(recipient),
        )
        service.users().messages().send(userId="me", body=message).execute()
        log.info(f"SENT     {to}")
        return SendResult(email=to, sent_at=sent_at, success=True)
    except HttpError as e:
        log.error(f"FAILED   {to} — {e}")
        return SendResult(email=to, sent_at=sent_at, success=False, error=str(e))

# ---------------------------------------------------------------------------
# Sent log
# ---------------------------------------------------------------------------

def write_sent_csv(results: list[SendResult]) -> None:
    """Write successfully sent emails to a CSV log."""
    sent = [r for r in results if r.success]
    if not sent:
        return

    with open(SENT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "sent_at"])
        writer.writeheader()
        writer.writerows({"email": r.email, "sent_at": r.sent_at} for r in sent)

    log.info(f"Sent log written to '{SENT_CSV}'.")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send cold emails via Gmail.")
    parser.add_argument("--csv", required=True, help="Path to recipients CSV.")
    parser.add_argument("--template", required=True, help="Path to email template.")
    parser.add_argument("--delay", type=float, default=0.0, help="Seconds to wait between sends.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    template = load_template(args.template)
    recipients = load_recipients(args.csv)
    service = get_gmail_service()

    results: list[SendResult] = []
    for i, recipient in enumerate(recipients):
        results.append(send_email(service, recipient, template))
        if args.delay and i < len(recipients) - 1:
            time.sleep(args.delay)

    write_sent_csv(results)

    success = sum(r.success for r in results)
    failure = len(results) - success
    log.info(f"Done — {success} sent, {failure} failed.")


if __name__ == "__main__":
    main()