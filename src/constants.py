# OAuth2 scope — grants send-only access to the Gmail account.
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# OAuth2 client secrets downloaded from the Google Cloud Console.
CREDENTIALS_FILE = "credentials.json"

# Cached OAuth2 token written after the first successful authorization.
TOKEN_FILE = "token.json"

# CSV log of successfully sent emails.
SENT_CSV = "sent.csv"

# Log file for all send attempts (successes and failures).
LOG_FILE = "script.log"