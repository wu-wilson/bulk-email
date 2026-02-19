## ⚡ Overview

Send personalized emails via Gmail using a CSV list and a text template.

## 🛠️ Local Setup

### Retrieve OAuth Credentials

1. Create a Google Cloud project
2. Enable **Gmail API**
3. Configure OAuth consent screen (External → add yourself as test user)
4. Create OAuth client ID (Desktop app)
5. Download JSON → rename to `credentials.json` → place in project root

### Install Dependencies

```bash
pip install -r requirements.txt
```

## 🚀 Example Usage

```bash
python send_emails.py --csv recipients.csv --template template.txt
python send_emails.py --csv recipients.csv --template template.txt --delay 1.5
```

On first run, a browser window will open to Google's login page. Sign in and grant the app permission to send email. A `token.json` is then saved in the project root — subsequent runs skip the browser and use the saved token.

| Flag         | Required | Description                                  |
| ------------ | -------- | -------------------------------------------- |
| `--csv`      | Yes      | Path to recipients CSV                       |
| `--template` | Yes      | Path to email template                       |
| `--delay`    | No       | Seconds to wait between sends (default: `0`) |

## 📂 Required Files

**`recipients.csv`** — requires an `email` column; all other columns are available as `$variable` placeholders in the template:

```
email,name,company
jane@example.com,Jane,Acme
john@example.com,John,Globex
```

**`template.txt`** — first line must be the subject; remaining lines are the body. Use `$column_name` for personalization:

```
Subject: Hi $name, quick question
Hi $name,

I wanted to reach out about $company...
```

## ✨ Output

After each run, two files are written:

- **`send_emails.log`** — timestamped log of every send attempt, including failures.
- **`sent.csv`** — record of every successfully delivered email.
