# Step to add your own GSheets

1. Copy GSheets URL
2. Share GSheets as Editor to below users:
   - basangdata@gmail.com
   - telegram-bot-vps@gen-lang-client-0172843846.iam.gserviceaccount.com
   - telegram-gsheets-gemini@gen-lang-client-0172843846.iam.gserviceaccount.com
3. Check your Telegram user ID using `/checkid` in the bot

## Running the Bot

```bash
python app_with_database.py
```

## Tech Stack

- **AI**: NanoGPT API (`moonshotai/kimi-k2.6` with fallback models)
- **Sheets**: gspread + Google service account
- **Database**: SQLite (SQLAlchemy) for tier-based quota tracking
- **Telegram**: python-telegram-bot

## Key Files

- `app_with_database.py` — Production bot (VPS entrypoint)
- `config.py` — AI model, tier limits, admin IDs, timeouts
- `credentials.py` — API keys and tokens (gitignored)
- `prompts.py` — AI extraction prompts
- `init_database.py` — SQLite table creation

## Adding Google Sheets Access

The bot uses a Google service account to write to spreadsheets. The service account email must be granted **Editor** access to any target spreadsheet. Users on Free tier share a default sheet; Silver+ tiers get a personal sheet linked to their account.
