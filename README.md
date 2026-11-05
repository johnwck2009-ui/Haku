# White Deer (白鹿店铺)

White Deer is a Telegram personal organizer for daily tasks, reminders, notes, and habit tracking.

## MVP features

- Daily overview of open tasks and reminders
- Personal task list with completion
- One-time reminders with persistent SQLite storage
- Quick notes
- Habit list and daily check-ins
- Per-user timezone settings
- Telegram reply-keyboard navigation

## Requirements

- Python 3.10+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

## Run locally

1. Clone the repository.
2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

   On Windows, activate with `.venv\\Scripts\\activate`.

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and add your bot token.

5. Load environment variables and start the bot:

   ```bash
   # macOS / Linux
   set -a && source .env && set +a
   python bot.py
   ```

   On Windows PowerShell:

   ```powershell
   Get-Content .env | ForEach-Object {
     if ($_ -match '^([^#][^=]+)=(.*)$') {
       [Environment]::SetEnvironmentVariable($matches[1], $matches[2])
     }
   }
   python bot.py
   ```

## Commands

| Command | Description |
| --- | --- |
| `/start` | Open White Deer |
| `/help` | Show help |
| `/today` | View today's tasks and reminders |
| `/tasks` | List open tasks |
| `/addtask <title>` | Add a task |
| `/done <id>` | Complete a task |
| `/remind YYYY-MM-DD HH:MM <text>` | Schedule a reminder in your timezone |
| `/reminders` | List upcoming reminders |
| `/note <text>` | Save a note |
| `/notes` | View recent notes |
| `/addhabit <name>` | Create a habit |
| `/habits` | View habits and today's status |
| `/checkhabit <id>` | Mark a habit complete today |
| `/timezone <Area/City>` | Set your timezone, e.g. `Africa/Lagos` |

## Data and privacy

- User data is separated by Telegram user ID.
- Tasks, reminders, notes, habits, and timezone preferences are stored in a local SQLite database.
- The database file and environment secrets are excluded from Git.
- The bot does not ask for passwords, OTPs, or other account credentials.
- Before a public launch, publish a privacy policy and add in-bot data export and deletion controls.

## Deployment notes

Run one bot process against a persistent disk so scheduled reminders continue to be checked and the SQLite database survives restarts. Do not commit `.env` or expose the bot token in logs, source code, screenshots, or issue reports.

This is an initial MVP. Before production launch, add automated tests, a user data export/deletion command, rate limiting, database backups, and monitoring.
