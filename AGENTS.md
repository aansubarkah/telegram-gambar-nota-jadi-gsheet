# AGENTS.md

Guidance for AI coding agents working on this repository.

## Quick Start

**Production script running on VPS:**
```bash
python app_with_database.py
```

## What This Project Does

Telegram bot → receives image/PDF/text of invoices → extracts structured data via Vision AI (NanoGPT API) → saves to Google Sheets + logs to SQLite for quota tracking.

## Key Files

| File | Purpose |
|---|---|
| `app_with_database.py` | **Production bot** — VPS entrypoint |
| `config.py` | All config (AI model, tiers, timeouts, admin IDs) |
| `credentials.py` | Secrets (gitignored) — `NANOGPT_API_KEY`, `TELEGRAM_BOT_TOKEN`, etc. |
| `prompts.py` | AI prompts for image and text extraction |
| `init_database.py` | Creates SQLite tables |
| `data.db` | SQLite database (gitignored) |
| `app_multi_users_qwen.py` | Legacy bot (backup, uses Chutes API) |

## Tech Stack

- **Runtime**: Python 3, `python-telegram-bot` library
- **AI**: NanoGPT API (`nano-gpt.com/api/v1/chat/completions`), primary model `moonshotai/kimi-k2.6`
- **Sheets**: `gspread` + Google service account
- **Database**: SQLite via SQLAlchemy

## Rules

1. Never commit `credentials.py`, `credentials.json`, `credentials_vps.json`, or `data.db`
2. AI model and fallbacks are configured in `config.py` only
3. Tier limits and admin IDs are in `config.py`
4. All timestamps use Asia/Jakarta (WIB) timezone
5. The bot must auto-register new users on first interaction
6. Keep `app_multi_users_qwen.py` as backup — don't delete it

## Architecture (app_with_database.py)

Single-file monolith with inline:
- Command handlers (`/start`, `/usage`, `/settier`, `/help`, etc.)
- Media handler (photo, PDF, text)
- AI processor (NanoGPT API call with retry + fallback chain)
- Google Sheets writer
- SQLite database operations (user management, activity logging, quota enforcement)
- Tier-based access control

## Common Tasks

- **Change AI model**: Edit `config.py` → `AI_MODEL` and `AI_MODEL_FALLBACKS`
- **Add admin**: Edit `config.py` → `ADMIN_USER_IDS`
- **Change tier limits**: Edit `config.py` → `TIER_LIMITS`
- **Reset database**: Delete `data.db`, run `python init_database.py`
- **Add new bot command**: Add handler in `app_with_database.py`, register in `Application` builder

## API Providers

- **Current**: NanoGPT (`nano-gpt.com`)
- **Legacy**: Chutes (`llm.chutes.ai`) — kept in config for reference only
