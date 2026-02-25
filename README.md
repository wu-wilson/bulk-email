## ⚡ Overview

Send personalized emails via Gmail using a CSV list and a markdown template.

## 🛠️ Local Setup

#### 1. Prerequisites

- Python 3.14+
- [Pipenv](https://pipenv.pypa.io) — manages dependencies and virtualenv

```bash
brew install pipenv
```

#### 2. Retrieve OAuth Credentials

1. Create a [Google Cloud](https://console.cloud.google.com) project
2. Enable Gmail API
3. Configure OAuth consent screen (External → add yourself as test user)
4. Create OAuth client ID (Desktop app)
5. Download JSON → rename to `credentials.json` → place in project root

#### 3. Install Dependencies

```bash
pipenv install
```

#### 4. Start a Shell Session

```bash
pipenv shell
```

## 🚀 Usage

```bash
python3 script.py --csv recipients.csv --template template.md
```

On the first run, a browser window will open to Google's login page. Sign in and grant the app permission to send emails.

A `token.json` is then saved in the project root. Subsequent runs will use the saved token.

| Flag         | Required | Description                                         |
| ------------ | -------- | --------------------------------------------------- |
| `--csv`      | Yes      | Path to recipients CSV                              |
| `--template` | Yes      | Path to email template                              |
| `--delay`    | No       | Seconds to wait between sends (default: `0`)        |
| `--cc`       | No       | 1+ addresses to CC on every email (space-separated) |

## 🗂️ Required Files

The `examples/` folder contains working versions of both files you can use as a reference.

1. **`recipients.csv`** — requires an `email` column; all other columns are available as `$variable` placeholders in the template.

2. **`template.md`** — first line must be the subject; remaining lines are the body. Use `$column_name` for personalization.

## ✨ Output

After each run, two files are written:

- **`script.log`** — timestamped log of every send attempt, including failures.
- **`sent.csv`** — record of every successfully delivered email.
