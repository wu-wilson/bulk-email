import argparse
import base64
import csv
import logging
import sys
import time
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
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
LOG_FILE = "script.log"

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
    """Parsed email template with separate subject and body Template objects."""
    subject: Template
    body: Template

@dataclass
class SendResult:
    """Outcome of a single send attempt."""
    email: str
    sent_at: str
    success: bool
    error: str = ""

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_gmail_service():
    """Authenticate via OAuth2 and return an authorized Gmail API service.

    On first run, opens a browser window to complete the OAuth2 flow and
    writes the resulting token to TOKEN_FILE. 
    
    On subsequent runs, the cached token is loaded and refreshed 
    automatically if expired.

    Returns:
        A Gmail API service object ready to make authorized requests.
    """
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
    """Parse an email template file into subject and body Templates.

    The first line must begin with 'Subject:'. Everything after the colon is
    treated as the subject. All remaining lines form the body. 
    
    Both support Python's string.Template substitution syntax ($variable 
    or ${variable}).

    Args:
        path: Path to the template file.

    Returns:
        An EmailTemplate with separate subject and body Template objects.

    Exits:
        If the file does not begin with 'Subject:'.
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
    """Load the list of recipients from a CSV file.

    Each row is returned as a dict keyed by column name. The 'email' column
    is required.
    
    Any additional columns are passed through and can be referenced as 
    template variables.

    Args:
        path: Path to the CSV file.

    Returns:
        A list of dicts, one per recipient row.

    Exits:
        If the file is empty or missing an 'email' column.
    """
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
    """Convert plain text to a minimal HTML representation.

    Escapes special HTML characters, converts newlines to <br> tags, and
    wraps any URLs in <a> tags so they are clickable in HTML-capable
    email clients.

    Args:
        text: Plain text string to convert.

    Returns:
        An HTML string suitable for use as the HTML part of a MIME email.
    """
    escaped = html.escape(text)
    linked = re.sub(
        r"(https?://[^\s]+)",
        r'<a href="\1">\1</a>',
        escaped,
    )
    return "<br>\n".join(linked.splitlines())


def build_mime_message(to: str, subject: str, body: str, cc: list[str] | None = None) -> dict:
    """Construct a multipart MIME email and encode it for the Gmail API.

    Sends both a plain-text part and an HTML part. Mail clients that support
    HTML will render the HTML version; others fall back to plain text.

    Args:
        to:      Recipient email address.
        subject: Email subject line.
        body:    Plain-text email body.
        cc:      Optional list of addresses to CC.

    Returns:
        A dict with a 'raw' key containing the base64url-encoded message,
        ready to pass directly to the Gmail API.
    """
    msg = MIMEMultipart("alternative")
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(plain_to_html(body), "html", "utf-8"))
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


def send_email(service, recipient: dict, template: EmailTemplate, cc: list[str] | None = None) -> SendResult:
    """Send a single personalized email to one recipient.

    Substitutes the recipient's CSV fields into the template subject and body,
    builds the MIME message, and delivers it via the Gmail API.

    Args:
        service:   Authorized Gmail API service object.
        recipient: Dict of CSV fields for this recipient (must include 'email').
        template:  Parsed email template with subject and body.
        cc:        Optional list of addresses to CC on the message.

    Returns:
        A SendResult indicating whether the send succeeded or failed.
    """
    to = recipient["email"].strip()
    sent_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        message = build_mime_message(
            to=to,
            subject=template.subject.safe_substitute(recipient),
            body=template.body.safe_substitute(recipient),
            cc=cc,
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
    """Append successfully sent emails to the sent log CSV.

    Creates the file with a header row if it does not yet exist, then appends
    one row per successful send.

    Args:
        results: List of SendResult objects from the current run.
    """
    sent = [r for r in results if r.success]
    if not sent:
        return

    with open(SENT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "sent_at"])
        if f.tell() == 0:
            writer.writeheader()
        writer.writerows({"email": r.email, "sent_at": r.sent_at} for r in sent)

    log.info(f"Sent log written to '{SENT_CSV}'.")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Define and parse command-line arguments.

    Returns:
        A Namespace object with attributes: csv, template, delay, cc.
    """
    parser = argparse.ArgumentParser(description="Send cold emails via Gmail.")
    parser.add_argument("--csv", required=True, help="Path to recipients CSV.")
    parser.add_argument("--template", required=True, help="Path to email template.")
    parser.add_argument("--delay", type=float, default=0.0, help="Seconds to wait between sends.")
    parser.add_argument("--cc", nargs="*", default=[], metavar="ADDRESS", help="One or more addresses to CC on every email.")
    return parser.parse_args()


def main() -> None:
    """Entry point — orchestrates loading, sending, and logging."""
    args = parse_args()

    template = load_template(args.template)
    recipients = load_recipients(args.csv)
    service = get_gmail_service()

    results: list[SendResult] = []
    for i, recipient in enumerate(recipients):
        results.append(send_email(service, recipient, template, cc=args.cc or None))
        if args.delay and i < len(recipients) - 1:
            time.sleep(args.delay)

    write_sent_csv(results)

    success = sum(r.success for r in results)
    failure = len(results) - success
    log.info(f"Done — {success} sent, {failure} failed.")


if __name__ == "__main__":
    main()